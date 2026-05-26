"""Endpoint para servir el informe de evaluacion offline del modelo (Feature 4).

GET /api/v1/model/evaluation → contenido de `docs/model-evaluation/metrics.json`

La sub-seccion "Evaluacion del modelo" del dashboard (RF-7) consume este
endpoint. La API lee el archivo directamente via un montaje `:ro` del
directorio de evaluacion.

Importante: un 503 aqui NO significa `predictor_loaded=false` — son dos
senales independientes (ver ADR-007 + spec dashboard, CB-4):
  * `predictor_loaded=false` (desde /health) → la API no puede inferir.
  * `/model/evaluation` 503 → no hay informe de evaluacion que mostrar
    (`metrics.json` no existe). El modelo aun podria estar cargado.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/model", tags=["model"])


DEFAULT_EVAL_PATH = Path("/app/docs/model-evaluation/metrics.json")


@router.get(
    "/evaluation",
    summary="Lee el informe de evaluacion offline del clasificador de radiografias",
    responses={
        200: {"description": "Contenido de metrics.json"},
        503: {"description": "metrics.json no existe (modelo nunca entrenado)"},
        500: {"description": "metrics.json esta presente pero corrupto"},
    },
)
def get_model_evaluation() -> dict:
    path = Path(os.environ.get("MODEL_EVALUATION_PATH", str(DEFAULT_EVAL_PATH)))
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "Model evaluation report not available "
                "(metrics.json missing; train the model with "
                "`docker compose run --rm pipeline python -m src.ml.train`)"
            ),
        )
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        logger.exception("Corrupt metrics.json at %s", path)
        raise HTTPException(
            status_code=500,
            detail=f"Corrupt evaluation file: {exc}",
        ) from exc
