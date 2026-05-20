"""Endpoint GET /api/v1/reports/daily (Feature 15).

Devuelve el informe del dia consultado en formato JSON, calculado SOBRE
LA VENTANA DEL DIA `[00:00, 23:59:59.999]` UTC. NO reutiliza la ventana
de `/alerts` (ultimas N horas desde ahora) — son ventanas diferentes:

  * `/alerts`: estado actual del sistema -> ultimas 24h.
  * `/reports/daily`: cierre del dia pedido -> dia natural UTC.

Llama internamente al mismo `build_daily_report(...)` que usa el script
`src/automation/daily_report.py` (DRY). La diferencia: el endpoint
incluye `generated_at` dinamico en el JSON; el script no lo incluye en
el Markdown (idempotencia byte-a-byte, RNF-6).

Ver spec RF-4, design seccion `src/api/routers/reports.py`.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.models import DailyReportResponse
from src.api.reports import build_daily_report
from src.api.time_window import day_window_utc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _default_threshold() -> float:
    return float(os.environ.get("ALERT_REJECTION_RATE_THRESHOLD", "0.10"))


def _parse_date_or_today(raw: str | None) -> date:
    """Si `raw` viene -> ISO YYYY-MM-DD obligatorio; si no -> hoy UTC."""
    if raw is None:
        return datetime.now(timezone.utc).date()
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"date debe ser ISO YYYY-MM-DD valida, recibido: {raw!r}",
        ) from exc


@router.get(
    "/daily",
    response_model=DailyReportResponse,
    summary="Informe diario del dia consultado (RF-4)",
    responses={
        200: {"description": "Informe del dia"},
        422: {"description": "Parametro `date` con formato invalido"},
        503: {"description": "MongoDB o SQLite no disponibles"},
    },
)
def get_daily_report(
    request: Request,
    date: str | None = Query(
        None,
        description=(
            "Fecha ISO YYYY-MM-DD del informe. Si se omite, hoy UTC."
        ),
    ),
) -> dict:
    target_date = _parse_date_or_today(date)
    start, end = day_window_utc(target_date)
    threshold = _default_threshold()

    sql_reader = request.app.state.sql_reader
    mongo_reader = request.app.state.mongo_reader

    try:
        runs_in_day = sql_reader.list_runs_between(start, end)
        failed_runs_in_day = sql_reader.list_failed_runs_between(start, end)
        quality_snapshots_in_day = sql_reader.list_quality_snapshots_between(
            start, end,
        )
        triage_in_day = mongo_reader.list_triage_patients_between(start, end)
        severe_in_day = mongo_reader.list_severe_triage_patients_between(
            start, end,
        )
        counts_snapshot = mongo_reader.get_total_counts()
    except Exception as exc:  # pragma: no cover  defensive
        logger.exception("Error reading daily report sources")
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return build_daily_report(
        target_date,
        failed_runs_in_day=failed_runs_in_day,
        runs_in_day=runs_in_day,
        quality_snapshots_in_day=quality_snapshots_in_day,
        triage_patients_in_day=triage_in_day,
        severe_triage_patients_in_day=severe_in_day,
        counts_snapshot=counts_snapshot,
        threshold=threshold,
        # generated_at: builder usa now() si es None — JSON dinamico OK.
    )
