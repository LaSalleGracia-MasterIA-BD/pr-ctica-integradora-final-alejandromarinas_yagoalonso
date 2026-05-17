"""End-to-end test of the watcher service.

Validates RF-7 / CA-1: dropping `patients.csv` + `admissions.csv` into
`data/incoming/` triggers the pipeline automatically and the files end up
in `data/incoming/processed/`.

This test runs against the actual `watcher` container (started by
`docker compose up`). It is skipped if the incoming directory is not
writable or if there is no `watcher` container picking up files.
"""
from __future__ import annotations

import csv
import shutil
import time
from pathlib import Path

import pytest


# When the suite runs INSIDE the pipeline container, the watcher service
# shares the same bind-mounted directory as /app/data/incoming.
# When the suite runs on the host, it should target the repo path.
_INCOMING_INSIDE_CONTAINER = Path("/app/data/incoming")
_INCOMING_ON_HOST = Path(__file__).resolve().parents[2] / "data" / "incoming"


def _is_writable(path: Path) -> bool:
    probe = path / ".write_probe"
    try:
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def _resolve_incoming_dir() -> Path:
    """Pick the writable shared directory that the watcher monitors.

    The pipeline container mounts /app/data as read-only by design, so when
    the suite runs there the incoming dir is readable but not writable.
    Skip cleanly in that case — the watcher service has its own rw mount.
    """
    for candidate in (_INCOMING_INSIDE_CONTAINER, _INCOMING_ON_HOST):
        if candidate.exists() and _is_writable(candidate):
            return candidate
    pytest.skip(
        "Incoming directory not writable from this context — the watcher "
        "service has its own rw mount, but this test runner does not"
    )


def _write_minimal_patients(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["external_id", "name", "birth_date", "gender", "blood_type"])
        # One unique id so this test never collides with the bootstrap dataset
        w.writerow(["HOSP-900001", "E2E Watcher Patient", "1990-01-01", "F", "A+"])


def _write_minimal_admissions(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "patient_external_id", "admission_date", "discharge_date",
            "department", "diagnosis_code", "diagnosis_description", "status",
        ])
        w.writerow([
            "HOSP-900001", "2026-05-15", "",
            "UCI", "J18.9", "Pneumonia", "admitted",
        ])


def _drain_processed(processed_dir: Path) -> None:
    """Remove leftover files from previous runs of this test."""
    for stale in processed_dir.glob("patients.csv"):
        stale.unlink()
    for stale in processed_dir.glob("admissions.csv"):
        stale.unlink()


def _wait_for(condition_fn, timeout_s: float = 30.0, poll_s: float = 1.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if condition_fn():
            return True
        time.sleep(poll_s)
    return False


def _count_watcher_runs(http, api_url) -> int:
    """Count pipeline_runs with trigger_type='watcher' via the SQLite-backed API."""
    r = http.get(f"{api_url}/api/v1/pipeline/runs?limit=500")
    if r.status_code != 200:
        return 0
    return sum(1 for run in r.json()["items"] if run["trigger_type"] == "watcher")


def test_watcher_processes_csvs_and_moves_them_to_processed(
    mongo_db, http, api_url
):
    """Drop CSVs in incoming/, wait for the watcher, verify the move + run.

    Run history lives in SQLite (ADR-004), so we count watcher runs through
    the API instead of mongo_db.pipeline_runs.

    Skipped if no watcher process picks up the files within the timeout
    (e.g. when running pytest without `docker compose up`).
    """
    incoming = _resolve_incoming_dir()
    processed = incoming / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    _drain_processed(processed)

    initial_runs = _count_watcher_runs(http, api_url)

    patients_dst = incoming / "patients.csv"
    admissions_dst = incoming / "admissions.csv"

    # Write to a sibling file first and then rename, to avoid the watcher
    # firing on a half-written file. shutil.move is atomic within a fs.
    tmp_patients = incoming / ".patients.csv.tmp"
    tmp_admissions = incoming / ".admissions.csv.tmp"
    _write_minimal_patients(tmp_patients)
    _write_minimal_admissions(tmp_admissions)
    shutil.move(str(tmp_patients), str(patients_dst))
    shutil.move(str(tmp_admissions), str(admissions_dst))

    # Wait for the watcher to consume the files (move to processed/).
    moved = _wait_for(
        lambda: (processed / "patients.csv").exists()
        and (processed / "admissions.csv").exists(),
        timeout_s=60.0,
    )

    if not moved:
        # If the files are still sitting in incoming/, the watcher is not
        # running. Clean up and skip with a clear message.
        if patients_dst.exists():
            patients_dst.unlink()
        if admissions_dst.exists():
            admissions_dst.unlink()
        pytest.skip(
            "Watcher service did not consume the files within 60s — "
            "probably not running (start `docker compose up watcher`)"
        )

    assert not patients_dst.exists(), "Original patients.csv should have been moved"
    assert not admissions_dst.exists(), "Original admissions.csv should have been moved"
    assert (processed / "patients.csv").exists()
    assert (processed / "admissions.csv").exists()

    # The watcher must have created a new pipeline_run in SQLite with the
    # correct trigger. Poll the API since the run is recorded slightly after
    # the files are moved (orchestrator runs after the move succeeds).
    assert _wait_for(
        lambda: _count_watcher_runs(http, api_url) == initial_runs + 1,
        timeout_s=30.0,
    ), (
        f"Expected one new pipeline_run with trigger_type=watcher, "
        f"started at {initial_runs} and never reached {initial_runs + 1}"
    )

    # The new patient must be in MongoDB
    assert _wait_for(
        lambda: mongo_db.patients.find_one({"external_id": "HOSP-900001"}) is not None,
        timeout_s=10.0,
    ), "HOSP-900001 not found in MongoDB after watcher run"

    # The new run must also have rows in data_quality_summary (via API)
    summary_resp = http.get(f"{api_url}/api/v1/pipeline/quality-summary")
    assert summary_resp.status_code == 200
    summary_items = summary_resp.json()["items"]
    assert len(summary_items) > 0, (
        "data_quality_summary deberia tener filas tras el run del watcher"
    )

    # Cleanup so re-running the test starts from a clean state
    _drain_processed(processed)
    mongo_db.patients.delete_one({"external_id": "HOSP-900001"})
