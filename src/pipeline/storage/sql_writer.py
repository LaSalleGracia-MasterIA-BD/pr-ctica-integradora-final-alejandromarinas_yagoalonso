"""Operaciones de escritura contra el store de metadatos en SQLite.

Reemplaza los metodos `start_pipeline_run` y `finish_pipeline_run` que
antes vivian en `MongoWriter`, y anade `write_quality_summary` para la
nueva tabla `data_quality_summary`.

Los identificadores son strings de `uuid.uuid4()` — ver ADR-004 sobre
por que NO reutilizamos `bson.ObjectId` aqui.
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
    """Wrapper ligero sobre una sesion de SQLAlchemy para escrituras."""

    def __init__(self, engine) -> None:
        self._engine = engine
        self._SessionFactory: sessionmaker = get_sql_session_factory(engine)

    def close(self) -> None:
        self._engine.dispose()

    def ping(self) -> bool:
        """Devuelve True si el engine puede ejecutar una query trivial."""
        with self._engine.connect() as conn:
            return conn.execute(text("SELECT 1")).scalar() == 1

    def start_pipeline_run(self, trigger_type: str = "manual") -> str:
        """Inserta un run nuevo con `status=running` y devuelve su UUID."""
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
        """Actualiza un run con el status final, stats y timestamp.

        Si `run_id` no existe, la llamada es no-op con un warning en el
        log; NO lanzamos excepcion porque perder el audit trail de un
        run terminado es peor que dejar al caller seguir adelante.
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
        """Persiste una fila por dimension para un run dado."""
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
    """Construye un SqlWriter usando el engine configurado por env.

    La creacion del schema NO se hace aqui a proposito: es responsabilidad
    de `bootstrap.py` para tener un unico sitio que posea el DDL.
    """
    engine = get_sql_engine_from_env()
    return SqlWriter(engine)
