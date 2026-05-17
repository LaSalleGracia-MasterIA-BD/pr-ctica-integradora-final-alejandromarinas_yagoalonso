"""Endpoint to serve the offline model evaluation report (Feature 4).

GET /api/v1/model/evaluation → contents of `docs/model-evaluation/metrics.json`

The dashboard's "Evaluacion del modelo" sub-section (RF-7) consumes this
endpoint. The API reads the file directly via a `:ro` mount of the
evaluation directory.

Important: a 503 here does NOT mean `predictor_loaded=false` — they are
two independent signals (see ADR-007 + spec dashboard, CB-4):
  * `predictor_loaded=false` (from /health) → API cannot run inference.
  * `/model/evaluation` 503 → there is no evaluation report to display
    (`metrics.json` is missing). The model could still be loaded.
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
    summary="Read the offline evaluation report of the radiography classifier",
    responses={
        200: {"description": "metrics.json contents"},
        503: {"description": "metrics.json missing (model never trained)"},
        500: {"description": "metrics.json is present but corrupt"},
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
