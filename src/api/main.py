"""Aplicacion FastAPI para el sistema hospitalario.

`build_app` es la factory testeable: acepta el nombre de MongoDB a usar y
opcionalmente un pipeline launcher. El `app` a nivel de modulo es el que
uvicorn importa en produccion (lee la configuracion de variables de entorno).
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from src.api.models import HealthResponse
from src.api.mongo_reader import MongoReader
from src.api.pipeline_launcher import PipelineLauncher
from src.api.routers import alerts as alerts_router
from src.api.routers import classify as classify_router
from src.api.routers import data as data_router
from src.api.routers import model as model_router
from src.api.routers import pipeline as pipeline_router
from src.api.routers import reports as reports_router
from src.api.routers import triage as triage_router
from src.api.sql_reader import get_sql_reader_from_env
from src.pipeline.storage.minio_client import get_minio_client_from_env
from src.pipeline.storage.mongo_writer import get_mongo_writer_from_env

logger = logging.getLogger(__name__)

API_VERSION = "0.1.0"

# Sentinela que distingue "usar el launcher por defecto de produccion" de
# "deshabilitar explicitamente el launcher" (usado por tests que no quieren
# levantar Spark en BackgroundTasks).
_USE_DEFAULT_LAUNCHER = object()


def _try_load_predictor():
    """Best-effort: devuelve un Predictor o None si falta el artefacto.

    Importa Predictor de forma lazy para que la API se importe correctamente
    incluso si tensorflow no esta disponible en el entorno actual (por ejemplo,
    ejecuciones ligeras de tests que no necesitan el modelo).
    """
    try:
        from src.ml.predictor import ModelNotAvailableError, Predictor
    except Exception as exc:  # pragma: no cover
        logger.warning("Cannot import Predictor (TF not installed?): %s", exc)
        return None

    try:
        predictor = Predictor.from_env()
        logger.info("Predictor loaded: %s", predictor.model_version)
        return predictor
    except ModelNotAvailableError as exc:
        logger.warning("Predictor not available: %s", exc)
        return None
    except Exception as exc:  # pragma: no cover  defensive
        logger.exception("Unexpected error loading predictor: %s", exc)
        return None


def build_app(
    mongo_db_name: str | None = None,
    pipeline_launcher=_USE_DEFAULT_LAUNCHER,
    patients_csv_path: Path | None = None,
    admissions_csv_path: Path | None = None,
) -> FastAPI:
    if pipeline_launcher is _USE_DEFAULT_LAUNCHER:
        pipeline_launcher = PipelineLauncher()

    db_name = mongo_db_name or os.environ.get("MONGO_DB", "hospital")
    reader = MongoReader(
        host=os.environ.get("MONGO_HOST", "localhost"),
        port=int(os.environ.get("MONGO_PORT", "27017")),
        db_name=db_name,
    )
    # SQLite es duenia de pipeline_runs + data_quality_summary (ADR-004). El
    # reader se construye de forma lazy para que los tests puedan sobreescribirlo
    # via app.state.
    sql_reader = get_sql_reader_from_env()

    # El writer + cliente MinIO son necesarios para el endpoint classify, que
    # tanto persiste en Mongo como descarga bytes de MinIO. Son best-effort:
    # si el despliegue carece de esas variables de entorno la app aun arranca
    # y los endpoints afectados fallan con un error claro.
    try:
        mongo_writer = get_mongo_writer_from_env(db_name=db_name)
    except Exception as exc:  # pragma: no cover
        logger.warning("Cannot build mongo_writer: %s", exc)
        mongo_writer = None
    try:
        minio_client = get_minio_client_from_env()
    except Exception as exc:  # pragma: no cover
        logger.warning("Cannot build minio_client: %s", exc)
        minio_client = None

    predictor = _try_load_predictor()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            reader.close()
            sql_reader.close()
            if mongo_writer is not None:
                try:
                    mongo_writer.close()
                except Exception:
                    pass
            # El cliente MinIO y el Predictor no tienen close explicito.

    app = FastAPI(
        title="laSalle Hospital API",
        version=API_VERSION,
        description="API REST para consultar datos hospitalarios y disparar el pipeline ETL.",
        lifespan=lifespan,
    )

    app.state.mongo_reader = reader
    app.state.sql_reader = sql_reader
    app.state.mongo_writer = mongo_writer
    app.state.minio_client = minio_client
    app.state.predictor = predictor
    app.state.pipeline_launcher = pipeline_launcher
    app.state.patients_csv_path = patients_csv_path or Path("/app/data/raw/patients.csv")
    app.state.admissions_csv_path = admissions_csv_path or Path("/app/data/raw/admissions.csv")
    app.state.radiographies_bucket = os.environ.get(
        "MINIO_BUCKET_RADIOGRAPHIES", "radiographies",
    )

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
    def health(request: Request) -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=API_VERSION,
            predictor_loaded=request.app.state.predictor is not None,
        )

    app.include_router(data_router.router)
    app.include_router(pipeline_router.router)
    app.include_router(classify_router.router)
    app.include_router(model_router.router)
    app.include_router(triage_router.router)
    app.include_router(alerts_router.router)
    app.include_router(reports_router.router)

    return app


# Entrypoint ASGI para uvicorn: `uvicorn src.api.main:app`
app = build_app()
