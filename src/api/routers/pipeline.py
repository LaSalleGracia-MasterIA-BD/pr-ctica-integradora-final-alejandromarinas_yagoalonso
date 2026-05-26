"""Endpoints para consultar y disparar el pipeline ETL.

Las lecturas sobre `pipeline_runs` y `data_quality_summary` pasan por el
`SqlReader` respaldado por SQLite (ver ADR-004). El launcher no cambia a
nivel de HTTP: los clientes siguen haciendo POST a /trigger y reciben un run_id.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from src.api.models import (
    PipelineRun,
    PipelineRunsPage,
    PipelineTriggerResponse,
    QualitySummaryHistoryPage,
    QualitySummaryItem,
    QualitySummaryResponse,
)
from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


def _sql_reader(request: Request):
    return request.app.state.sql_reader


@router.get("/runs", response_model=PipelineRunsPage)
def list_runs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> PipelineRunsPage:
    reader = _sql_reader(request)
    items = reader.list_pipeline_runs(limit=limit, offset=offset)
    total = reader.count_pipeline_runs()
    return PipelineRunsPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[PipelineRun.model_validate(doc) for doc in items],
    )


@router.get("/status", response_model=PipelineRun)
def pipeline_status(request: Request) -> PipelineRun:
    reader = _sql_reader(request)
    doc = reader.latest_pipeline_run()
    if doc is None:
        raise HTTPException(status_code=404, detail="No pipeline runs recorded yet")
    return PipelineRun.model_validate(doc)


@router.get("/quality-summary", response_model=QualitySummaryResponse)
def latest_quality_summary(request: Request) -> QualitySummaryResponse:
    """Ultimo snapshot de calidad de datos: una fila por dimension."""
    reader = _sql_reader(request)
    rows = reader.latest_quality_summary()
    return QualitySummaryResponse(
        items=[QualitySummaryItem.model_validate(r) for r in rows],
    )


@router.get(
    "/quality-summary/history",
    response_model=QualitySummaryHistoryPage,
)
def quality_summary_history(
    request: Request,
    dimension: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> QualitySummaryHistoryPage:
    """Historial de snapshots de calidad para una dimension dada.

    `total` es el numero real de filas en `data_quality_summary` para la
    dimension solicitada, no el tamano de la pagina actual — los clientes
    lo necesitan para gestionar la paginacion correctamente.
    """
    reader = _sql_reader(request)
    rows = reader.quality_summary_history(
        dimension=dimension, limit=limit, offset=offset
    )
    total = reader.count_quality_summary_by_dimension(dimension=dimension)
    return QualitySummaryHistoryPage(
        total=total,
        limit=limit,
        offset=offset,
        dimension=dimension,
        items=[QualitySummaryItem.model_validate(r) for r in rows],
    )


@router.post("/trigger", response_model=PipelineTriggerResponse, status_code=202)
def trigger_pipeline(
    request: Request,
    background: BackgroundTasks,
) -> PipelineTriggerResponse:
    """Arranca el ETL en segundo plano y devuelve el id del nuevo run.

    El pipeline tarda segundos en el dataset de demo; devolver 202 Accepted
    y ejecutar en una background task mantiene la peticion HTTP rapida y
    permite a los clientes hacer polling de `/pipeline/status` o
    `/pipeline/runs` para ver el progreso.
    """
    launcher = getattr(request.app.state, "pipeline_launcher", None)
    if launcher is None:
        raise HTTPException(
            status_code=503,
            detail="Pipeline launcher is not configured in this deployment",
        )

    patients_csv = Path(request.app.state.patients_csv_path)
    admissions_csv = Path(request.app.state.admissions_csv_path)

    # Arrancamos el run sincronamente para poder devolver un run_id real
    # (string UUID desde SQLite) y ejecutamos el procesamiento pesado en background.
    run_id = launcher.start_run(trigger_type="manual")
    background.add_task(
        launcher.execute, run_id=run_id,
        patients_csv=patients_csv, admissions_csv=admissions_csv,
    )
    logger.info("Triggered pipeline run %s via API", run_id)
    return PipelineTriggerResponse(
        run_id=str(run_id),
        status="accepted",
        message="Pipeline run started in the background",
    )
