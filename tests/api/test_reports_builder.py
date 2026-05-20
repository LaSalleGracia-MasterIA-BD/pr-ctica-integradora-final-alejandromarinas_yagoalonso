"""Tests del builder + render del informe diario (Feature 15, T7).

Cubre:
  * RF-4: estructura del JSON (date, pipeline, quality, counts, triage, alerts).
  * RNF-6 + CA-11: `render_markdown` byte-a-byte estable, sin `generated_at`,
    sin sets sin orden, sin `datetime.now()`.

Todo PURO: sin Mongo, sin SQLite, sin red.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

from src.api.reports import build_daily_report, render_markdown


UTC = timezone.utc


def _state_for_day_with_some_activity() -> dict:
    """Estado representativo: 2 runs (1 failed), 2 snapshots, 3 triajes
    (1 grave, 1 medio, 1 leve)."""
    run_ok = {
        "id": "run-ok", "trigger_type": "watcher", "status": "success",
        "started_at": datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 5, 20, 8, 5, tzinfo=UTC),
        "records_processed": 100, "records_rejected": 5,
        "images_processed": 0, "error_message": None,
    }
    run_fail = {
        "id": "run-fail", "trigger_type": "manual", "status": "failed",
        "started_at": datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 5, 20, 12, 1, tzinfo=UTC),
        "records_processed": 0, "records_rejected": 0,
        "images_processed": 0, "error_message": "boom",
    }
    snap_patients = {
        "pipeline_run_id": "run-ok", "dimension": "patients",
        "total": 100, "valid": 95, "rejected": 5, "rejection_rate": 0.05,
        "recorded_at": datetime(2026, 5, 20, 8, 5, tzinfo=UTC),
    }
    snap_admissions = {
        "pipeline_run_id": "run-ok", "dimension": "admissions",
        "total": 50, "valid": 40, "rejected": 10, "rejection_rate": 0.20,
        "recorded_at": datetime(2026, 5, 20, 8, 5, tzinfo=UTC),
    }
    p_grave = {
        "external_id": "P-1", "name": "Grave",
        "triage": {
            "level": "grave", "reasons": ["SpO2<90"],
            "triaged_at": datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
        },
    }
    p_medio = {
        "external_id": "P-2", "name": "Medio",
        "triage": {
            "level": "medio", "reasons": [],
            "triaged_at": datetime(2026, 5, 20, 9, 30, tzinfo=UTC),
        },
    }
    p_leve = {
        "external_id": "P-3", "name": "Leve",
        "triage": {
            "level": "leve", "reasons": [],
            "triaged_at": datetime(2026, 5, 20, 10, 0, tzinfo=UTC),
        },
    }
    return {
        "failed_runs_in_day": [run_fail],
        "runs_in_day": [run_ok, run_fail],
        "quality_snapshots_in_day": [snap_patients, snap_admissions],
        "triage_patients_in_day": [p_grave, p_medio, p_leve],
        "severe_triage_patients_in_day": [p_grave],
        "counts_snapshot": {
            "patients_total": 4745,
            "admissions_total": 5200,
            "radiographies_total": 3000,
        },
    }


# -- RF-4: estructura ----------------------------------------------------

def test_build_daily_report_has_all_sections():
    state = _state_for_day_with_some_activity()
    report = build_daily_report(date(2026, 5, 20), threshold=0.10, **state)

    assert report["date"] == "2026-05-20"
    assert "generated_at" in report
    assert set(report.keys()) >= {
        "date", "generated_at", "pipeline", "quality",
        "counts", "triage", "alerts",
    }


def test_build_daily_report_pipeline_counts_correctly():
    state = _state_for_day_with_some_activity()
    report = build_daily_report(date(2026, 5, 20), threshold=0.10, **state)
    assert report["pipeline"]["runs_in_day"] == 2
    assert report["pipeline"]["failed_in_day"] == 1
    assert report["pipeline"]["last_run_of_day"] is not None


def test_build_daily_report_triage_breakdown():
    state = _state_for_day_with_some_activity()
    report = build_daily_report(date(2026, 5, 20), threshold=0.10, **state)
    triage = report["triage"]
    assert triage["grave"] == 1
    assert triage["medio"] == 1
    assert triage["leve"] == 1
    assert triage["in_day_total"] == 3


def test_build_daily_report_counts_passes_through_snapshot():
    state = _state_for_day_with_some_activity()
    report = build_daily_report(date(2026, 5, 20), threshold=0.10, **state)
    assert report["counts"] == state["counts_snapshot"]


def test_build_daily_report_alerts_include_data_quality_above_threshold():
    state = _state_for_day_with_some_activity()
    report = build_daily_report(date(2026, 5, 20), threshold=0.10, **state)
    alert_types = {a["type"] for a in report["alerts"]}
    # patients tiene 0.05 (no alerta), admissions tiene 0.20 (alerta).
    # Failed run y triage_severe tambien alertan.
    assert "data_quality_low" in alert_types
    assert "pipeline_failed" in alert_types
    assert "triage_severe" in alert_types


def test_build_daily_report_empty_state_does_not_crash():
    report = build_daily_report(
        date(2026, 5, 20),
        threshold=0.10,
        failed_runs_in_day=[],
        runs_in_day=[],
        quality_snapshots_in_day=[],
        triage_patients_in_day=[],
        severe_triage_patients_in_day=[],
        counts_snapshot={
            "patients_total": 0, "admissions_total": 0, "radiographies_total": 0,
        },
    )
    assert report["pipeline"]["runs_in_day"] == 0
    assert report["pipeline"]["failed_in_day"] == 0
    assert report["alerts"] == []
    assert report["triage"]["in_day_total"] == 0


# -- RNF-6 + CA-11: idempotencia del Markdown ----------------------------

def test_render_markdown_does_not_include_generated_at():
    state = _state_for_day_with_some_activity()
    report = build_daily_report(date(2026, 5, 20), threshold=0.10, **state)
    md = render_markdown(report)
    assert "generated_at" not in md
    assert report["generated_at"] not in md


def test_render_markdown_is_deterministic():
    """Mismo report dict -> mismo Markdown byte-a-byte (hash igual)."""
    state = _state_for_day_with_some_activity()
    report1 = build_daily_report(
        date(2026, 5, 20), threshold=0.10,
        generated_at=datetime(2026, 5, 20, 14, 0, tzinfo=UTC),
        **state,
    )
    report2 = build_daily_report(
        date(2026, 5, 20), threshold=0.10,
        generated_at=datetime(2026, 5, 20, 23, 59, tzinfo=UTC),
        **state,
    )
    # Aunque `generated_at` difiere, el Markdown debe ser identico.
    md1 = render_markdown(report1)
    md2 = render_markdown(report2)
    assert md1 == md2
    assert hashlib.sha256(md1.encode()).hexdigest() == \
        hashlib.sha256(md2.encode()).hexdigest()


def test_render_markdown_includes_all_sections():
    state = _state_for_day_with_some_activity()
    report = build_daily_report(date(2026, 5, 20), threshold=0.10, **state)
    md = render_markdown(report)
    assert "# Informe diario" in md
    assert "## Pipeline" in md
    assert "## Calidad de datos" in md
    assert "## Conteos" in md
    assert "## Triaje" in md
    assert "## Alertas" in md


def test_render_markdown_for_empty_day_still_has_sections():
    report = build_daily_report(
        date(2026, 5, 20), threshold=0.10,
        failed_runs_in_day=[], runs_in_day=[],
        quality_snapshots_in_day=[], triage_patients_in_day=[],
        severe_triage_patients_in_day=[],
        counts_snapshot={
            "patients_total": 0, "admissions_total": 0, "radiographies_total": 0,
        },
    )
    md = render_markdown(report)
    assert "## Pipeline" in md
    assert "## Alertas" in md


def test_render_markdown_lists_are_stable_across_input_reorder():
    """Si reordeno listas de entrada, el render debe ser identico
    (porque dentro del render se ordena por claves estables)."""
    state = _state_for_day_with_some_activity()
    # Reordenar listas
    state_reversed = {
        **state,
        "quality_snapshots_in_day": list(reversed(
            state["quality_snapshots_in_day"]
        )),
        "triage_patients_in_day": list(reversed(
            state["triage_patients_in_day"]
        )),
    }
    md1 = render_markdown(
        build_daily_report(date(2026, 5, 20), threshold=0.10, **state)
    )
    md2 = render_markdown(
        build_daily_report(date(2026, 5, 20), threshold=0.10, **state_reversed)
    )
    assert md1 == md2
