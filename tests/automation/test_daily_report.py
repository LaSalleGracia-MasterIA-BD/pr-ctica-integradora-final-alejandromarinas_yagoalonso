"""Tests del script CLI src/automation/daily_report.py (Feature 15, T10).

Cubre CA-5 (creacion del fichero), CA-11 + RNF-6 (idempotencia byte-a-byte
del Markdown a igualdad de estado), CB-10 (crea docs/reports/ si falta).

Para evitar abrir Mongo/SQLite en los tests, parchea las factorias
`get_sql_reader_from_env` y `get_mongo_reader_from_env` con readers
fake que devuelven listas deterministas.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest


UTC = timezone.utc


class _FakeSqlReader:
    def list_failed_runs_between(self, start, end):
        return [{
            "id": "run-fail", "trigger_type": "manual", "status": "failed",
            "started_at": datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            "finished_at": datetime(2026, 5, 20, 12, 1, tzinfo=UTC),
            "records_processed": 0, "records_rejected": 0,
            "images_processed": 0, "error_message": "boom",
        }]

    def list_runs_between(self, start, end):
        return [
            {
                "id": "run-ok", "trigger_type": "watcher", "status": "success",
                "started_at": datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
                "finished_at": datetime(2026, 5, 20, 8, 5, tzinfo=UTC),
                "records_processed": 100, "records_rejected": 5,
                "images_processed": 0, "error_message": None,
            },
            {
                "id": "run-fail", "trigger_type": "manual", "status": "failed",
                "started_at": datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
                "finished_at": datetime(2026, 5, 20, 12, 1, tzinfo=UTC),
                "records_processed": 0, "records_rejected": 0,
                "images_processed": 0, "error_message": "boom",
            },
        ]

    def list_quality_snapshots_between(self, start, end):
        return [{
            "pipeline_run_id": "run-ok", "dimension": "patients",
            "total": 100, "valid": 95, "rejected": 5, "rejection_rate": 0.05,
            "recorded_at": datetime(2026, 5, 20, 8, 5, tzinfo=UTC),
        }]

    def close(self) -> None:
        pass


class _FakeMongoReader:
    def list_triage_patients_between(self, start, end):
        return [{
            "external_id": "P-1", "name": "Grave",
            "triage": {
                "level": "grave", "reasons": ["SpO2<90"],
                "triaged_at": datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
            },
        }]

    def list_severe_triage_patients_between(self, start, end):
        return [{
            "external_id": "P-1", "name": "Grave",
            "triage": {
                "level": "grave", "reasons": ["SpO2<90"],
                "triaged_at": datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
            },
        }]

    def get_total_counts(self):
        return {
            "patients_total": 100, "admissions_total": 50,
            "radiographies_total": 10,
        }

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _patch_factories(monkeypatch):
    """Reemplaza las factorias del modulo daily_report por fakes."""
    from src.automation import daily_report as mod
    monkeypatch.setattr(mod, "get_sql_reader_from_env", lambda: _FakeSqlReader())
    monkeypatch.setattr(
        mod, "get_mongo_reader_from_env", lambda: _FakeMongoReader()
    )


# -- CA-5: el script crea el fichero ----------------------------------

def test_script_creates_markdown_file(tmp_path: Path):
    from src.automation.daily_report import main
    output = tmp_path / "2026-05-20.md"
    rc = main(["--date", "2026-05-20", "--output", str(output)])
    assert rc == 0
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "# Informe diario - 2026-05-20" in content


# -- CA-11 + RNF-6: idempotencia byte-a-byte --------------------------

def test_script_idempotent_same_day_same_state(tmp_path: Path):
    """Dos ejecuciones consecutivas con la misma fecha + mismo estado
    producen exactamente el mismo Markdown (sha256 igual)."""
    from src.automation.daily_report import main
    out1 = tmp_path / "first" / "2026-05-20.md"
    out2 = tmp_path / "second" / "2026-05-20.md"
    main(["--date", "2026-05-20", "--output", str(out1)])
    main(["--date", "2026-05-20", "--output", str(out2)])

    hash1 = hashlib.sha256(out1.read_bytes()).hexdigest()
    hash2 = hashlib.sha256(out2.read_bytes()).hexdigest()
    assert hash1 == hash2


def test_script_does_not_include_dynamic_generated_at(tmp_path: Path):
    """El Markdown NO debe contener `generated_at` ni timestamp ISO de
    'ahora' (RNF-6)."""
    from src.automation.daily_report import main
    output = tmp_path / "x.md"
    main(["--date", "2026-05-20", "--output", str(output)])
    content = output.read_text(encoding="utf-8")
    assert "generated_at" not in content


# -- CB-10: crea la carpeta si falta ----------------------------------

def test_script_creates_reports_dir_if_missing(tmp_path: Path):
    from src.automation.daily_report import main
    nested = tmp_path / "deep" / "nested" / "dir" / "out.md"
    assert not nested.parent.exists()
    rc = main(["--date", "2026-05-20", "--output", str(nested)])
    assert rc == 0
    assert nested.exists()


# -- Default output: docs/reports/YYYY-MM-DD.md -----------------------

def test_script_default_output_is_in_docs_reports(tmp_path: Path, monkeypatch):
    """Sin --output, escribe en docs/reports/YYYY-MM-DD.md."""
    monkeypatch.chdir(tmp_path)
    from src.automation.daily_report import main
    rc = main(["--date", "2026-05-20"])
    assert rc == 0
    expected = tmp_path / "docs" / "reports" / "2026-05-20.md"
    assert expected.exists()


def test_script_invalid_date_returns_nonzero(tmp_path: Path):
    from src.automation.daily_report import main
    rc = main(["--date", "not-a-date", "--output", str(tmp_path / "x.md")])
    assert rc != 0
