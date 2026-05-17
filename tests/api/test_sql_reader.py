"""Unit tests for SqlReader: read-only access to SQLite pipeline metadata.

Polyglot persistence (ADR-004): pipeline_runs + data_quality_summary live
in SQLite. The API reads from this layer through SqlReader.
"""
from __future__ import annotations

from pathlib import Path

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed")

from src.api.sql_reader import SqlReader
from src.pipeline.storage.sql_engine import create_all_tables, get_sql_engine_from_env
from src.pipeline.storage.sql_writer import SqlWriter


@pytest.fixture
def engine(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "reader.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    eng = get_sql_engine_from_env()
    create_all_tables(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def writer(engine):
    w = SqlWriter(engine)
    yield w
    w.close()


@pytest.fixture
def reader(engine):
    r = SqlReader(engine)
    yield r
    r.close()


def _finish(writer: SqlWriter, run_id: str, *, status: str = "success",
            processed: int = 0, rejected: int = 0, images: int = 0) -> None:
    writer.finish_pipeline_run(
        run_id,
        status=status,
        stats={
            "records_processed": processed,
            "records_rejected": rejected,
            "images_processed": images,
        },
    )


def test_count_pipeline_runs_returns_zero_on_empty_db(reader: SqlReader):
    assert reader.count_pipeline_runs() == 0


def test_count_pipeline_runs_counts_all_rows(writer: SqlWriter, reader: SqlReader):
    writer.start_pipeline_run(trigger_type="manual")
    writer.start_pipeline_run(trigger_type="bootstrap")
    writer.start_pipeline_run(trigger_type="watcher")

    assert reader.count_pipeline_runs() == 3


def test_list_pipeline_runs_returns_newest_first(writer: SqlWriter, reader: SqlReader):
    older = writer.start_pipeline_run(trigger_type="manual")
    _finish(writer, older, status="success", processed=10)
    newer = writer.start_pipeline_run(trigger_type="watcher")
    _finish(writer, newer, status="failed")

    runs = reader.list_pipeline_runs(limit=10, offset=0)

    assert len(runs) == 2
    assert runs[0]["id"] == newer
    assert runs[1]["id"] == older
    assert runs[0]["status"] == "failed"
    assert runs[1]["status"] == "success"


def test_list_pipeline_runs_respects_limit_and_offset(writer: SqlWriter, reader: SqlReader):
    ids = []
    for _ in range(5):
        ids.append(writer.start_pipeline_run(trigger_type="manual"))

    page1 = reader.list_pipeline_runs(limit=2, offset=0)
    page2 = reader.list_pipeline_runs(limit=2, offset=2)

    assert len(page1) == 2
    assert len(page2) == 2
    # No overlap
    assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})


def test_latest_pipeline_run_returns_none_on_empty_db(reader: SqlReader):
    assert reader.latest_pipeline_run() is None


def test_latest_pipeline_run_returns_most_recent(writer: SqlWriter, reader: SqlReader):
    writer.start_pipeline_run(trigger_type="manual")
    newest = writer.start_pipeline_run(trigger_type="watcher")
    _finish(writer, newest, status="success", processed=42)

    latest = reader.latest_pipeline_run()

    assert latest is not None
    assert latest["id"] == newest
    assert latest["records_processed"] == 42


def test_latest_quality_summary_returns_empty_when_no_summary(
    writer: SqlWriter, reader: SqlReader
):
    """If there is no summary yet, return an empty list, not a crash."""
    assert reader.latest_quality_summary() == []


def test_latest_quality_summary_returns_rows_from_most_recent_run(
    writer: SqlWriter, reader: SqlReader
):
    older = writer.start_pipeline_run(trigger_type="manual")
    writer.write_quality_summary(older, [
        {"dimension": "patients", "total": 100, "valid": 90, "rejected": 10, "rejection_rate": 0.1},
    ])
    newer = writer.start_pipeline_run(trigger_type="watcher")
    writer.write_quality_summary(newer, [
        {"dimension": "patients", "total": 200, "valid": 180, "rejected": 20, "rejection_rate": 0.1},
        {"dimension": "admissions", "total": 150, "valid": 140, "rejected": 10, "rejection_rate": 0.0667},
    ])

    summary = reader.latest_quality_summary()

    assert len(summary) == 2
    assert {row["dimension"] for row in summary} == {"patients", "admissions"}
    patients = next(r for r in summary if r["dimension"] == "patients")
    assert patients["total"] == 200
    assert patients["pipeline_run_id"] == newer


def test_quality_summary_history_filters_by_dimension(
    writer: SqlWriter, reader: SqlReader
):
    run1 = writer.start_pipeline_run(trigger_type="manual")
    writer.write_quality_summary(run1, [
        {"dimension": "patients", "total": 100, "valid": 95, "rejected": 5, "rejection_rate": 0.05},
        {"dimension": "admissions", "total": 80, "valid": 78, "rejected": 2, "rejection_rate": 0.025},
    ])
    run2 = writer.start_pipeline_run(trigger_type="watcher")
    writer.write_quality_summary(run2, [
        {"dimension": "patients", "total": 110, "valid": 100, "rejected": 10, "rejection_rate": 0.0909},
        {"dimension": "admissions", "total": 90, "valid": 88, "rejected": 2, "rejection_rate": 0.0222},
    ])

    patients_history = reader.quality_summary_history(
        dimension="patients", limit=10, offset=0
    )

    assert len(patients_history) == 2
    assert all(row["dimension"] == "patients" for row in patients_history)


def test_quality_summary_history_orders_by_recorded_at_desc(
    writer: SqlWriter, reader: SqlReader
):
    run1 = writer.start_pipeline_run(trigger_type="manual")
    writer.write_quality_summary(run1, [
        {"dimension": "patients", "total": 100, "valid": 95, "rejected": 5, "rejection_rate": 0.05},
    ])
    run2 = writer.start_pipeline_run(trigger_type="watcher")
    writer.write_quality_summary(run2, [
        {"dimension": "patients", "total": 200, "valid": 180, "rejected": 20, "rejection_rate": 0.1},
    ])

    history = reader.quality_summary_history(
        dimension="patients", limit=10, offset=0
    )

    assert history[0]["pipeline_run_id"] == run2
    assert history[1]["pipeline_run_id"] == run1


def test_quality_summary_history_respects_limit(
    writer: SqlWriter, reader: SqlReader
):
    for _ in range(5):
        rid = writer.start_pipeline_run(trigger_type="manual")
        writer.write_quality_summary(rid, [
            {"dimension": "patients", "total": 1, "valid": 1, "rejected": 0, "rejection_rate": 0.0},
        ])

    page = reader.quality_summary_history(dimension="patients", limit=2, offset=0)
    assert len(page) == 2


def test_count_quality_summary_returns_zero_when_no_rows(reader: SqlReader):
    assert reader.count_quality_summary_by_dimension(dimension="patients") == 0


def test_count_quality_summary_counts_all_rows_for_dimension(
    writer: SqlWriter, reader: SqlReader
):
    """Count is independent of any limit/offset used elsewhere."""
    for _ in range(5):
        rid = writer.start_pipeline_run(trigger_type="manual")
        writer.write_quality_summary(rid, [
            {"dimension": "patients", "total": 1, "valid": 1, "rejected": 0, "rejection_rate": 0.0},
            {"dimension": "admissions", "total": 2, "valid": 2, "rejected": 0, "rejection_rate": 0.0},
        ])

    assert reader.count_quality_summary_by_dimension(dimension="patients") == 5
    assert reader.count_quality_summary_by_dimension(dimension="admissions") == 5
    assert reader.count_quality_summary_by_dimension(dimension="other") == 0

    # Sanity: paginar con limit=1 NO debe alterar el count
    page = reader.quality_summary_history(dimension="patients", limit=1, offset=0)
    assert len(page) == 1
    assert reader.count_quality_summary_by_dimension(dimension="patients") == 5
