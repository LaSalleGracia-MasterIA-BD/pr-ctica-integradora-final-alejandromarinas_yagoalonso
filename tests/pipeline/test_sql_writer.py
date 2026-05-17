"""Tests for SqlWriter."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed")

from sqlalchemy import text

from src.pipeline.storage.sql_engine import create_all_tables, get_sql_engine_from_env
from src.pipeline.storage.sql_writer import SqlWriter, get_sql_writer_from_env


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@pytest.fixture
def sqlite_path(tmp_path: Path, monkeypatch) -> Path:
    db_path = tmp_path / "test_writer.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    engine = get_sql_engine_from_env()
    create_all_tables(engine)
    engine.dispose()
    return db_path


@pytest.fixture
def writer(sqlite_path: Path):
    w = get_sql_writer_from_env()
    yield w
    w.close()


def test_start_pipeline_run_returns_uuid_string(writer: SqlWriter):
    run_id = writer.start_pipeline_run(trigger_type="manual")
    assert isinstance(run_id, str)
    assert UUID_PATTERN.match(run_id)


def test_start_pipeline_run_persists_row(writer: SqlWriter):
    run_id = writer.start_pipeline_run(trigger_type="bootstrap")
    with writer._engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, trigger_type, status FROM pipeline_runs WHERE id=:id"),
            {"id": run_id},
        ).first()
    assert row is not None
    assert row.id == run_id
    assert row.trigger_type == "bootstrap"
    assert row.status == "running"


def test_finish_pipeline_run_updates_status_and_stats(writer: SqlWriter):
    run_id = writer.start_pipeline_run(trigger_type="manual")
    writer.finish_pipeline_run(
        run_id,
        status="success",
        stats={"records_processed": 100, "records_rejected": 5, "images_processed": 0},
    )
    with writer._engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT status, records_processed, records_rejected, finished_at "
                "FROM pipeline_runs WHERE id=:id"
            ),
            {"id": run_id},
        ).first()
    assert row.status == "success"
    assert row.records_processed == 100
    assert row.records_rejected == 5
    assert row.finished_at is not None


def test_finish_pipeline_run_stores_error_message_on_failure(writer: SqlWriter):
    run_id = writer.start_pipeline_run(trigger_type="manual")
    writer.finish_pipeline_run(
        run_id, status="failed", error_message="ValueError: bad input"
    )
    with writer._engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, error_message FROM pipeline_runs WHERE id=:id"),
            {"id": run_id},
        ).first()
    assert row.status == "failed"
    assert "bad input" in row.error_message


def test_finish_pipeline_run_with_unknown_id_does_not_crash(writer: SqlWriter):
    # Should log a warning and not raise
    writer.finish_pipeline_run("nonexistent-uuid", status="success")


def test_write_quality_summary_persists_all_dimensions(writer: SqlWriter):
    run_id = writer.start_pipeline_run(trigger_type="manual")
    summaries = [
        {"dimension": "patients", "total": 100, "valid": 95, "rejected": 5,
         "rejection_rate": 0.05},
        {"dimension": "admissions", "total": 200, "valid": 180, "rejected": 20,
         "rejection_rate": 0.10},
    ]
    writer.write_quality_summary(run_id, summaries)
    with writer._engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT dimension, total, valid, rejected, rejection_rate "
                "FROM data_quality_summary WHERE pipeline_run_id=:rid "
                "ORDER BY dimension"
            ),
            {"rid": run_id},
        ).all()
    assert len(rows) == 2
    by_dim = {r.dimension: r for r in rows}
    assert by_dim["patients"].total == 100
    assert by_dim["admissions"].rejected == 20


def test_write_quality_summary_handles_empty_list(writer: SqlWriter):
    run_id = writer.start_pipeline_run(trigger_type="manual")
    writer.write_quality_summary(run_id, [])
    with writer._engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM data_quality_summary WHERE pipeline_run_id=:rid"),
            {"rid": run_id},
        ).all()
    assert rows == []


def test_write_quality_summary_records_timestamp(writer: SqlWriter):
    run_id = writer.start_pipeline_run(trigger_type="manual")
    writer.write_quality_summary(
        run_id,
        [{"dimension": "patients", "total": 1, "valid": 1, "rejected": 0, "rejection_rate": 0.0}],
    )
    with writer._engine.connect() as conn:
        row = conn.execute(
            text("SELECT recorded_at FROM data_quality_summary WHERE pipeline_run_id=:rid"),
            {"rid": run_id},
        ).first()
    assert row.recorded_at is not None


def test_ping_returns_true(writer: SqlWriter):
    assert writer.ping() is True
