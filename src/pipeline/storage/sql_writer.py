"""Write operations against the SQLite metadata store.

Replaces the `start_pipeline_run`, `finish_pipeline_run` methods that used to
live in `MongoWriter`, and adds `write_quality_summary` for the new
`data_quality_summary` table.

Identifiers are plain `uuid.uuid4()` strings — see ADR-004 for why we do NOT
reuse `bson.ObjectId` here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from src.pipeline.logging_config import get_logger
from src.pipeline.storage.sql_engine import (
    get_sql_engine_from_env,
    get_sql_session_factory,
)
from src.pipeline.storage.sql_models import (
    DataQualitySummaryRow,
    PipelineRunRow,
)

logger = get_logger(__name__)


class SqlWriter:
    """Thin wrapper around a SQLAlchemy session for write operations."""

    def __init__(self, engine) -> None:
        self._engine = engine
        self._SessionFactory: sessionmaker = get_sql_session_factory(engine)

    def close(self) -> None:
        self._engine.dispose()

    def ping(self) -> bool:
        """Return True if the engine can execute a trivial query."""
        with self._engine.connect() as conn:
            return conn.execute(text("SELECT 1")).scalar() == 1

    def start_pipeline_run(self, trigger_type: str = "manual") -> str:
        """Insert a new run with `status=running` and return its UUID."""
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        row = PipelineRunRow(
            id=run_id,
            trigger_type=trigger_type,
            started_at=now,
            status="running",
            records_processed=0,
            records_rejected=0,
            images_processed=0,
        )
        with self._SessionFactory() as session:
            session.add(row)
            session.commit()
        logger.info("SQL pipeline_run started: %s (trigger=%s)", run_id, trigger_type)
        return run_id

    def finish_pipeline_run(
        self,
        run_id: str,
        status: str,
        stats: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update a run with final status, stats and timestamp.

        If `run_id` does not exist, the call is a no-op with a warning log;
        we do NOT raise because losing the audit trail of a finished run is
        worse than letting the caller continue.
        """
        with self._SessionFactory() as session:
            row = session.get(PipelineRunRow, run_id)
            if row is None:
                logger.warning(
                    "Tried to finish pipeline_run %s but it does not exist", run_id
                )
                return
            row.status = status
            row.finished_at = datetime.now(timezone.utc)
            if stats:
                row.records_processed = stats.get(
                    "records_processed", row.records_processed
                )
                row.records_rejected = stats.get(
                    "records_rejected", row.records_rejected
                )
                row.images_processed = stats.get(
                    "images_processed", row.images_processed
                )
            if error_message is not None:
                row.error_message = error_message
            session.commit()
        logger.info("SQL pipeline_run finished: %s status=%s", run_id, status)

    def write_quality_summary(
        self, run_id: str, summaries: list[dict]
    ) -> int:
        """Persist one row per dimension for a given run."""
        if not summaries:
            return 0
        now = datetime.now(timezone.utc)
        rows = [
            DataQualitySummaryRow(
                pipeline_run_id=run_id,
                dimension=s["dimension"],
                total=s["total"],
                valid=s["valid"],
                rejected=s["rejected"],
                rejection_rate=s["rejection_rate"],
                recorded_at=now,
            )
            for s in summaries
        ]
        with self._SessionFactory() as session:
            session.add_all(rows)
            session.commit()
        logger.info(
            "SQL data_quality_summary: %d rows persisted for run %s",
            len(rows),
            run_id,
        )
        return len(rows)


def get_sql_writer_from_env() -> SqlWriter:
    """Build a SqlWriter using the env-configured engine.

    Schema creation is NOT done here on purpose: it is the responsibility of
    `bootstrap.py` so we have a single place that owns DDL.
    """
    engine = get_sql_engine_from_env()
    return SqlWriter(engine)
