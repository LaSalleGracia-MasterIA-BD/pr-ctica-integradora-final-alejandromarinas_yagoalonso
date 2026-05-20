"""Endpoint GET /api/v1/alerts (Feature 15, ADR-009).

Calcula alertas operativas en tiempo real combinando:
  * `pipeline_runs` (SQLite, status='failed') via SqlReader.
  * `data_quality_summary` (SQLite, rejection_rate > umbral) via SqlReader.
  * `patients.triage` (MongoDB, level='grave') via MongoReader.

Las reglas son la funcion pura `evaluate()` en `src/api/alerts.py`. El
router solo orquesta lecturas + filtro de severidad + serializacion JSON.

Ver:
  * specs/automatizacion-alertas.md (RF-1, RF-2, RF-3, RF-8)
  * design/automatizacion-alertas.md
  * decisions/ADR-009-alertas-como-vista-derivada.md
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.alerts import Severity, evaluate
from src.api.models import AlertResponse, AlertsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["alerts"])


def _default_threshold() -> float:
    return float(os.environ.get("ALERT_REJECTION_RATE_THRESHOLD", "0.10"))


def _default_window_hours() -> int:
    return int(os.environ.get("ALERT_WINDOW_HOURS", "24"))


@router.get(
    "/alerts",
    response_model=AlertsResponse,
    summary="Devuelve las alertas activas calculadas en tiempo real (RF-1)",
    responses={
        200: {"description": "Lista de alertas (puede ser vacia)"},
        422: {"description": "since/severity con formato invalido"},
        503: {"description": "MongoDB o SQLite no disponibles"},
    },
)
def get_alerts(
    request: Request,
    since: datetime | None = Query(
        None,
        description=(
            "ISO datetime UTC; si se omite se usa "
            "now() - ALERT_WINDOW_HOURS (default 24h)."
        ),
    ),
    severity: Severity | None = Query(
        None,
        description="Filtra resultados por severidad (critical|high|medium|low).",
    ),
) -> AlertsResponse:
    threshold = _default_threshold()
    window_hours = _default_window_hours()
    now = datetime.now(timezone.utc)
    window_start = since or (now - timedelta(hours=window_hours))

    sql_reader = request.app.state.sql_reader
    mongo_reader = request.app.state.mongo_reader

    try:
        failed_runs = sql_reader.list_failed_runs_since(window_start)
        quality_snapshots = sql_reader.list_quality_snapshots_since(window_start)
        severe_patients = mongo_reader.list_severe_triage_patients_since(
            window_start
        )
    except Exception as exc:  # pragma: no cover  defensive
        logger.exception("Error reading alert sources")
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    alerts = evaluate(
        failed_runs, quality_snapshots, severe_patients, threshold=threshold,
    )

    if severity is not None:
        alerts = [a for a in alerts if a.severity == severity]

    items = [AlertResponse(**asdict(a)) for a in alerts]
    return AlertsResponse(
        items=items,
        total=len(items),
        generated_at=now,
        threshold=threshold,
        window_start=window_start,
    )
