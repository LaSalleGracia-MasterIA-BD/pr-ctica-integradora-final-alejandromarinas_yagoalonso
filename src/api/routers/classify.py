"""Endpoints para clasificacion de radiografias (Feature 2) + proxy de imagenes (Feature 4).

POST /api/v1/radiographies/classify        — inferir + persistir
GET  /api/v1/radiographies/classification   — leer resultado persistido
GET  /api/v1/radiographies/image            — proxy de los bytes PNG desde MinIO

La key de MinIO llega en el body (POST) o como query param (GET) en
lugar de como parametro de path porque contiene `/` (ej. `HOSP-000001/xray1.png`)
y `{key:path}` complica a clientes y herramientas.
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
    summary="Clasifica una radiografia almacenada en MinIO y persiste el resultado",
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
        # La radiografia no esta registrada en ningun documento de paciente.
        # Podriamos servir la prediccion igualmente, pero la spec dice que
        # el endpoint DEBE persistir; sin un paciente padre, el resultado
        # se perderia. 404 hace ese contrato explicito.
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
    summary="Lee la clasificacion persistida de una radiografia",
)
def get_classification(
    request: Request,
    key: str = Query(..., min_length=1, description="Clave del objeto MinIO"),
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
        # Backfill para clasificaciones persistidas antes de introducir la
        # regla del umbral (Feature 16). Esas filas usaban argmax puro.
        decision_rule=doc.get("decision_rule", "legacy_argmax"),
    )


@router.get(
    "/image",
    summary="Proxy de los bytes PNG de una radiografia desde MinIO",
    responses={
        200: {"content": {"image/png": {}}},
        404: {"description": "Objeto no encontrado en MinIO"},
        422: {"description": "key ausente o vacia"},
        502: {"description": "Error en el almacenamiento de objetos upstream"},
    },
)
def get_radiography_image(
    request: Request,
    key: str = Query(..., min_length=1, description="Clave del objeto MinIO"),
) -> Response:
    """Proxy de solo lectura de los bytes del objeto MinIO para el dashboard.

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
