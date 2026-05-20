"""Endpoints for radiography classification (Feature 2) + image proxy (Feature 4).

POST /api/v1/radiographies/classify        — infer + persist
GET  /api/v1/radiographies/classification   — read persisted result
GET  /api/v1/radiographies/image            — proxy of PNG bytes from MinIO

The MinIO key comes in the body (POST) or as a query param (GET) instead
of a path param because it contains `/` (e.g. `HOSP-000001/xray1.png`)
and `{key:path}` complicates clients and tooling.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, Response
from minio.error import S3Error

from src.api.models import (
    ClassificationResponse,
    ClassifyRequest,
)
from src.ml.preprocessing import InvalidImageError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/radiographies", tags=["radiographies"])


def _predictor(request: Request):
    predictor = getattr(request.app.state, "predictor", None)
    if predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Classification model is not loaded in this deployment",
        )
    return predictor


def _bucket(request: Request) -> str:
    return getattr(request.app.state, "radiographies_bucket", "radiographies")


@router.post(
    "/classify",
    response_model=ClassificationResponse,
    summary="Classify a radiography stored in MinIO and persist the result",
)
def classify_radiography(
    payload: ClassifyRequest,
    request: Request,
) -> ClassificationResponse:
    predictor = _predictor(request)
    minio_client = request.app.state.minio_client
    mongo_writer = request.app.state.mongo_writer
    bucket = _bucket(request)
    key = payload.minio_object_key

    try:
        image_bytes = minio_client.download_bytes(bucket, key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject"}:
            raise HTTPException(
                status_code=404,
                detail=f"Radiography not found in MinIO: {key}",
            ) from exc
        logger.exception("Unexpected S3 error fetching %s/%s", bucket, key)
        raise HTTPException(
            status_code=502,
            detail="Upstream object storage error",
        ) from exc

    try:
        prediction = predictor.predict(image_bytes)
    except InvalidImageError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Image cannot be processed: {exc}",
        ) from exc

    classification = {
        "predicted_class": prediction.predicted_class,
        "probabilities": prediction.probabilities,
        "predicted_at": datetime.now(timezone.utc),
        "model_version": prediction.model_version,
        "decision_rule": prediction.decision_rule,
    }

    matched = mongo_writer.set_radiography_classification(key, classification)
    if not matched:
        # The radiography is not registered in any patient document. We
        # could still serve the prediction, but the spec says the
        # endpoint MUST persist; without a parent patient, the result
        # would be lost. 404 makes that contract explicit.
        raise HTTPException(
            status_code=404,
            detail=f"No patient owns radiography {key}",
        )

    logger.info(
        "Classified %s as %s (model_version=%s, decision_rule=%s)",
        key, prediction.predicted_class, prediction.model_version,
        prediction.decision_rule,
    )
    return ClassificationResponse(
        minio_object_key=key,
        predicted_class=prediction.predicted_class,
        probabilities=prediction.probabilities,
        predicted_at=classification["predicted_at"],
        model_version=prediction.model_version,
        decision_rule=prediction.decision_rule,
    )


@router.get(
    "/classification",
    response_model=ClassificationResponse,
    summary="Read the persisted classification for a radiography",
)
def get_classification(
    request: Request,
    key: str = Query(..., min_length=1, description="MinIO object key"),
) -> ClassificationResponse:
    mongo_reader = request.app.state.mongo_reader
    doc = mongo_reader.get_radiography_classification(key)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"No classification persisted for {key}",
        )
    return ClassificationResponse(
        minio_object_key=key,
        predicted_class=doc["predicted_class"],
        probabilities=doc["probabilities"],
        predicted_at=doc["predicted_at"],
        model_version=doc["model_version"],
        # Backfill for classifications persisted before the threshold rule
        # was introduced (Feature 16). Those rows used pure argmax.
        decision_rule=doc.get("decision_rule", "legacy_argmax"),
    )


@router.get(
    "/image",
    summary="Proxy PNG bytes of a radiography from MinIO",
    responses={
        200: {"content": {"image/png": {}}},
        404: {"description": "Object not found in MinIO"},
        422: {"description": "key missing or empty"},
        502: {"description": "Upstream object storage error"},
    },
)
def get_radiography_image(
    request: Request,
    key: str = Query(..., min_length=1, description="MinIO object key"),
) -> Response:
    """Read-only proxy of MinIO object bytes for the dashboard.

    NO toca MongoDB, NO clasifica. Existe para que el dashboard
    (servicio aparte sin acceso directo a MinIO) pueda renderizar
    la imagen seleccionada en la vista Clasificador.
    """
    minio_client = request.app.state.minio_client
    bucket = _bucket(request)
    try:
        data = minio_client.download_bytes(bucket, key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject"}:
            raise HTTPException(
                status_code=404,
                detail=f"Radiography not found in MinIO: {key}",
            ) from exc
        logger.exception("Unexpected S3 error fetching %s/%s", bucket, key)
        raise HTTPException(
            status_code=502,
            detail="Upstream object storage error",
        ) from exc
    return Response(content=data, media_type="image/png")
