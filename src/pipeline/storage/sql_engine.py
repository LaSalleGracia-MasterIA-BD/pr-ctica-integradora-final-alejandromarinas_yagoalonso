"""SQLAlchemy engine factory tuned for our SQLite + multi-thread use case.

Three concerns are addressed here:

  1. **Multi-thread access**: the watcher daemon's observer runs file-system
     events in a separate thread from the orchestrator's executor. SQLite
     would refuse to share connections across threads by default; we relax
     that with `check_same_thread=False`.

  2. **Concurrent reads + one writer**: with `PRAGMA journal_mode=WAL` the
     API can read pipeline_runs while the watcher is writing a new run.
     Default mode (DELETE) would block readers during writes.

  3. **Schema bootstrap**: `create_all_tables(engine)` is idempotent
     (`CREATE TABLE IF NOT EXISTS`) and is the only entry point for schema
     creation in the codebase. Called once from `bootstrap.py`.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker

from src.pipeline.logging_config import get_logger
from src.pipeline.storage.sql_models import Base

logger = get_logger(__name__)

DEFAULT_SQLITE_PATH = "/app/data/db/hospital.db"


def get_sql_engine_from_env() -> Engine:
    """Build the shared SQLite engine for this process.

    The file is created on first connection if its parent directory exists.
    Callers (bootstrap) are responsible for ensuring the directory exists.
    """
    sqlite_path = os.environ.get("SQLITE_PATH", DEFAULT_SQLITE_PATH)
    db_dir = Path(sqlite_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{sqlite_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_wal(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    logger.info("SQLite engine ready at %s (WAL mode)", sqlite_path)
    return engine


def get_sql_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_all_tables(engine: Engine) -> None:
    """Create every declared table if missing. Idempotent."""
    Base.metadata.create_all(engine)
    logger.info("SQL schema ready (pipeline_runs, data_quality_summary)")
