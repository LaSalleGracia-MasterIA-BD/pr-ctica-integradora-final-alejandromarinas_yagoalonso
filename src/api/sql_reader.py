"""Acceso de lectura al store de metadatos SQLite (pipeline_runs + summary).

Espejo de `MongoReader` para el lado SQL del modelo de persistencia poliglota
(ver ADR-004). Se mantiene separado de `SqlWriter` para que las superficies
de lectura y escritura puedan evolucionar de forma independiente.

Todas las filas devueltas son dicts planos (sin objetos del ORM de SQLAlchemy
filtrandose hacia la capa API): el router solo aplica validacion Pydantic encima.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc, func, select
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
    """Consultas de solo lectura contra el store de metadatos SQLite."""

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
        """Devuelve todas las filas del summary mas recientemente registrado.

        El "mas reciente" se decide por el `recorded_at` de las propias filas,
        no por el `started_at` del run — esto mantiene el "ultimo snapshot
        de calidad" del dashboard alineado con la escritura SQL real.
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
        """Total de filas en `data_quality_summary` para una dimension dada.

        Usado por la API para exponer un `total` fiel en respuestas de
        historial paginadas — `len(items)` solo describiria la pagina actual.
        """
        with self._SessionFactory() as session:
            stmt = select(func.count()).select_from(DataQualitySummaryRow).where(
                DataQualitySummaryRow.dimension == dimension
            )
            return session.execute(stmt).scalar_one()

    # -- Alertas: ventana abierta desde `since` hasta ahora -----------------
    # Usado por GET /api/v1/alerts (Feature 15, ADR-009).

    def list_failed_runs_since(self, since: datetime) -> list[dict]:
        """Runs con status='failed' y started_at >= since, mas nuevos primero."""
        with self._SessionFactory() as session:
            stmt = (
                select(PipelineRunRow)
                .where(and_(
                    PipelineRunRow.status == "failed",
                    PipelineRunRow.started_at >= since,
                ))
                .order_by(desc(PipelineRunRow.started_at))
            )
            return [_pipeline_run_to_dict(r) for r in session.scalars(stmt).all()]

    def list_quality_snapshots_since(self, since: datetime) -> list[dict]:
        """Snapshots con recorded_at >= since, mas nuevos primero."""
        with self._SessionFactory() as session:
            stmt = (
                select(DataQualitySummaryRow)
                .where(DataQualitySummaryRow.recorded_at >= since)
                .order_by(desc(DataQualitySummaryRow.recorded_at))
            )
            return [_quality_summary_to_dict(r) for r in session.scalars(stmt).all()]

    # -- Informe diario: ventana cerrada [start, end] -----------------------
    # Usado por GET /api/v1/reports/daily y src/automation/daily_report.py.
    # NO reutiliza la ventana de /alerts: el informe es del dia pedido,
    # no de "ultimas 24h desde ahora" (ver spec RF-4 + CB-7b).

    def list_failed_runs_between(
        self, start: datetime, end: datetime,
    ) -> list[dict]:
        """Runs failed con started_at en [start, end] (ambos inclusivos)."""
        with self._SessionFactory() as session:
            stmt = (
                select(PipelineRunRow)
                .where(and_(
                    PipelineRunRow.status == "failed",
                    PipelineRunRow.started_at >= start,
                    PipelineRunRow.started_at <= end,
                ))
                .order_by(PipelineRunRow.started_at)
            )
            return [_pipeline_run_to_dict(r) for r in session.scalars(stmt).all()]

    def list_runs_between(
        self, start: datetime, end: datetime,
    ) -> list[dict]:
        """Todos los runs (cualquier status) con started_at en [start, end]."""
        with self._SessionFactory() as session:
            stmt = (
                select(PipelineRunRow)
                .where(and_(
                    PipelineRunRow.started_at >= start,
                    PipelineRunRow.started_at <= end,
                ))
                .order_by(PipelineRunRow.started_at)
            )
            return [_pipeline_run_to_dict(r) for r in session.scalars(stmt).all()]

    def list_quality_snapshots_between(
        self, start: datetime, end: datetime,
    ) -> list[dict]:
        """Snapshots con recorded_at en [start, end]."""
        with self._SessionFactory() as session:
            stmt = (
                select(DataQualitySummaryRow)
                .where(and_(
                    DataQualitySummaryRow.recorded_at >= start,
                    DataQualitySummaryRow.recorded_at <= end,
                ))
                .order_by(DataQualitySummaryRow.recorded_at)
            )
            return [_quality_summary_to_dict(r) for r in session.scalars(stmt).all()]


def get_sql_reader_from_env() -> SqlReader:
    engine = get_sql_engine_from_env()
    return SqlReader(engine)
