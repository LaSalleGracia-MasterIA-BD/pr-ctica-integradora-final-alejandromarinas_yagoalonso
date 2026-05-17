"""Tests for SQL engine factory and schema creation."""
from __future__ import annotations

from pathlib import Path

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed")

from sqlalchemy import inspect, text

from src.pipeline.storage.sql_engine import (
    create_all_tables,
    get_sql_engine_from_env,
    get_sql_session_factory,
)
from src.pipeline.storage.sql_models import Base


@pytest.fixture
def sqlite_path(tmp_path: Path, monkeypatch) -> Path:
    db_path = tmp_path / "test_hospital.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    return db_path


def test_get_sql_engine_creates_sqlite_engine(sqlite_path: Path):
    engine = get_sql_engine_from_env()
    assert engine.url.drivername.startswith("sqlite")
    engine.dispose()


def test_wal_mode_is_active(sqlite_path: Path):
    """PRAGMA journal_mode=WAL must be set on every new connection."""
    engine = get_sql_engine_from_env()
    create_all_tables(engine)
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert mode.lower() == "wal"
    engine.dispose()


def test_create_all_tables_creates_expected_tables(sqlite_path: Path):
    engine = get_sql_engine_from_env()
    create_all_tables(engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "pipeline_runs" in tables
    assert "data_quality_summary" in tables
    engine.dispose()


def test_create_all_tables_is_idempotent(sqlite_path: Path):
    """Calling create_all_tables multiple times must not raise nor duplicate."""
    engine = get_sql_engine_from_env()
    create_all_tables(engine)
    create_all_tables(engine)
    create_all_tables(engine)
    inspector = inspect(engine)
    assert "pipeline_runs" in inspector.get_table_names()
    engine.dispose()


def test_pipeline_runs_has_expected_columns(sqlite_path: Path):
    engine = get_sql_engine_from_env()
    create_all_tables(engine)
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("pipeline_runs")}
    expected = {
        "id", "trigger_type", "started_at", "finished_at", "status",
        "records_processed", "records_rejected", "images_processed",
        "error_message",
    }
    assert expected.issubset(cols)
    engine.dispose()


def test_data_quality_summary_has_expected_columns(sqlite_path: Path):
    engine = get_sql_engine_from_env()
    create_all_tables(engine)
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("data_quality_summary")}
    expected = {
        "id", "pipeline_run_id", "dimension", "total", "valid",
        "rejected", "rejection_rate", "recorded_at",
    }
    assert expected.issubset(cols)
    engine.dispose()


def test_session_factory_yields_usable_session(sqlite_path: Path):
    engine = get_sql_engine_from_env()
    create_all_tables(engine)
    SessionFactory = get_sql_session_factory(engine)
    with SessionFactory() as session:
        result = session.execute(text("SELECT 1")).scalar()
    assert result == 1
    engine.dispose()
