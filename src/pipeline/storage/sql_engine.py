"""Factoria del engine de SQLAlchemy ajustada para SQLite + multi-thread.

Aqui se resuelven tres temas:

  1. **Acceso multi-thread**: el observer del daemon watcher procesa los
     eventos del file-system en un thread distinto al executor del
     orchestrator. Por defecto SQLite no permite compartir conexiones
     entre threads; lo relajamos con `check_same_thread=False`.

  2. **Lecturas concurrentes + un solo writer**: con `PRAGMA
     journal_mode=WAL` la API puede leer pipeline_runs mientras el
     watcher esta escribiendo un run nuevo. El modo por defecto (DELETE)
     bloquearia a los lectores durante las escrituras.

  3. **Bootstrap del schema**: `create_all_tables(engine)` es idempotente
     (`CREATE TABLE IF NOT EXISTS`) y es el unico punto de entrada para
     crear schema en el codigo. Se llama una vez desde `bootstrap.py`.
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
    """Construye el engine compartido de SQLite para este proceso.

    El fichero se crea en la primera conexion si el directorio padre ya
    existe. Los callers (bootstrap) son responsables de asegurarse de
    que el directorio existe.
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
    """Crea todas las tablas declaradas si faltan. Idempotente."""
    Base.metadata.create_all(engine)
    logger.info("SQL schema ready (pipeline_runs, data_quality_summary)")
