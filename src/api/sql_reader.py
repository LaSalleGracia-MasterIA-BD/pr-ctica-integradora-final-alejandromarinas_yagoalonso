"""Read-side access to the SQLite metadata store (pipeline_runs + summary).

Mirror of `MongoReader` for the SQL side of the polyglot persistence model
(see ADR-004). Kept separate from `SqlWriter` so read and write surfaces
can evolve independently.

All returned rows are plain dicts (no SQLAlchemy ORM objects leaking up to
the API layer): the router only does Pydantic validation on top.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.engine import Engine
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


def _pipeline_run_to_dict(row: PipelineRunRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "trigger_type": row.trigger_type,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "status": row.status,
        "records_processed": row.records_processed,
        "records_rejected": row.records_rejected,
        "images_processed": row.images_processed,
        "error_message": row.error_message,
    }


def _quality_summary_to_dict(row: DataQualitySummaryRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "pipeline_run_id": row.pipeline_run_id,
        "dimension": row.dimension,
        "total": row.total,
        "valid": row.valid,
        "rejected": row.rejected,
        "rejection_rate": row.rejection_rate,
        "recorded_at": row.recorded_at,
    }


class SqlReader:
    """Read-only queries against the SQLite metadata store."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._SessionFactory: sessionmaker = get_sql_session_factory(engine)

    def close(self) -> None:
        self._engine.dispose()

    # -- pipeline_runs ------------------------------------------------------

    def count_pipeline_runs(self) -> int:
        with self._SessionFactory() as session:
            return session.query(PipelineRunRow).count()

    def list_pipeline_runs(self, limit: int, offset: int) -> list[dict]:
        with self._SessionFactory() as session:
            stmt = (
                select(PipelineRunRow)
                .order_by(desc(PipelineRunRow.started_at))
                .limit(limit)
                .offset(offset)
            )
            rows = session.scalars(stmt).all()
            return [_pipeline_run_to_dict(r) for r in rows]

    def latest_pipeline_run(self) -> dict | None:
        with self._SessionFactory() as session:
            stmt = (
                select(PipelineRunRow)
                .order_by(desc(PipelineRunRow.started_at))
                .limit(1)
            )
            row = session.scalars(stmt).first()
            return _pipeline_run_to_dict(row) if row else None

    # -- data_quality_summary ----------------------------------------------

    def latest_quality_summary(self) -> list[dict]:
        """Return all rows from the most recently recorded summary.

        Latest is decided by `recorded_at` of the rows themselves, not by
        the run's `started_at` — this keeps the dashboard's "last quality
        snapshot" aligned with the actual SQL write.
        """
        with self._SessionFactory() as session:
            latest_run = session.scalars(
                select(DataQualitySummaryRow.pipeline_run_id)
                .order_by(desc(DataQualitySummaryRow.recorded_at))
                .limit(1)
            ).first()
            if latest_run is None:
                return []
            stmt = (
                select(DataQualitySummaryRow)
                .where(DataQualitySummaryRow.pipeline_run_id == latest_run)
                .order_by(DataQualitySummaryRow.dimension)
            )
            rows = session.scalars(stmt).all()
            return [_quality_summary_to_dict(r) for r in rows]

    def quality_summary_history(
        self, dimension: str, limit: int, offset: int
    ) -> list[dict]:
        with self._SessionFactory() as session:
            stmt = (
                select(DataQualitySummaryRow)
                .where(DataQualitySummaryRow.dimension == dimension)
                .order_by(desc(DataQualitySummaryRow.recorded_at))
                .limit(limit)
                .offset(offset)
            )
            rows = session.scalars(stmt).all()
            return [_quality_summary_to_dict(r) for r in rows]

    def count_quality_summary_by_dimension(self, dimension: str) -> int:
        """Total rows in `data_quality_summary` for a given dimension.

        Used by the API to expose a faithful `total` in paginated history
        responses — `len(items)` would only describe the current page.
        """
        with self._SessionFactory() as session:
            stmt = select(func.count()).select_from(DataQualitySummaryRow).where(
                DataQualitySummaryRow.dimension == dimension
            )
            return session.execute(stmt).scalar_one()


def get_sql_reader_from_env() -> SqlReader:
    engine = get_sql_engine_from_env()
    return SqlReader(engine)
