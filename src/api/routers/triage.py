"""Endpoints de triaje de pacientes en alta manual (feature triage-pacientes).

POST /api/v1/triage/patients   — crea un paciente nuevo y le asigna nivel
                                 de triaje aplicando las reglas RF-5.
GET  /api/v1/triage/rules      — documenta las reglas vigentes (RF-8).

Ver:
  * specs/triage-pacientes.md
  * design/triage-pacientes.md
  * decisions/ADR-008-triaje-basado-en-reglas.md

Disclaimer: asistencia al triaje, no diagnostico ni decision medica
vinculante. Los umbrales son academicos simplificados (ver ADR-008).
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pymongo.errors import DuplicateKeyError, PyMongoError

from src.api.models import (
    TriageInfo,
    TriagePatientRequest,
    TriagePatientResponse,
    VitalSigns,
)
from src.api.triage import (
    RULES_VERSION,
    build_triage_external_id,
    evaluate,
    get_rules_definition,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/triage", tags=["triage"])


# Numero maximo de reintentos al insertar con `NNNN`+1 si choca con un
# external_id ya existente (race condition concurrente o cupo diario
# agotado). Configurable via env var para tests. Ver RF-7.
TRIAGE_MAX_RETRIES = int(os.environ.get("TRIAGE_MAX_RETRIES", "5"))


def _derive_age(age: int | None, birth_date: str | None) -> int | None:
    """Edad efectiva. Si `age` viene en el payload se respeta. Si solo
    viene `birth_date`, se calcula con la fecha de hoy."""
    if age is not None:
        return age
    if not birth_date:
        return None
    try:
        b = date.fromisoformat(birth_date)
    except ValueError:
        return None
    today = date.today()
    return today.year - b.year - (
        (today.month, today.day) < (b.month, b.day)
    )


DAILY_TRIAGE_LIMIT = 9999  # spec RF-6: NNNN tiene 4 digitos


def _next_counter_for_today(mongo_reader, today: date) -> int:
    """Devuelve el siguiente NNNN como `max(NNNN existente) + 1`.

    Usar `max + 1` (en vez de `count + 1`) hace el helper robusto frente
    a borrados manuales en la coleccion y es ademas reproducible en
    tests sin tener que insertar 9999 pacientes (basta seedear el
    documento con `NNNN=9999`).
    """
    prefix = f"TRIAGE-{today.strftime('%Y%m%d')}-"
    cursor = (
        mongo_reader.db.patients.find(
            {"external_id": {"$regex": f"^{prefix}\\d{{4}}$"}},
            {"external_id": 1, "_id": 0},
        )
        .sort("external_id", -1)
        .limit(1)
    )
    docs = list(cursor)
    if not docs:
        return 1
    last_id = docs[0]["external_id"]
    try:
        last_n = int(last_id.rsplit("-", 1)[1])
    except (ValueError, IndexError):
        return 1
    return last_n + 1


def _build_patient_doc(
    body: TriagePatientRequest,
    external_id: str,
    triage_result,
    age_effective: int | None,
    now: datetime,
) -> dict:
    """Construye el documento que se persiste en MongoDB.

    Sigue la estructura definida en spec RF-3 + design.
    """
    vs = body.vital_signs.model_dump()
    triage_doc = {
        "level": triage_result.level,
        "score": triage_result.score,
        "reasons": triage_result.reasons,
        "vital_signs": vs,
        "symptoms": list(body.symptoms),
        "risk_factors": list(body.risk_factors),
        "triaged_at": now,
        "source": "manual_triage",
        "rules_version": RULES_VERSION,
    }
    return {
        "external_id": external_id,
        "name": body.name,
        "birth_date": body.birth_date,
        "age": age_effective,
        "gender": body.gender,
        "blood_type": body.blood_type,
        "admissions": [],
        "radiographies": [],
        "triage": triage_doc,
    }


@router.post(
    "/patients",
    response_model=TriagePatientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crea un paciente nuevo y le asigna nivel de triaje (RF-1)",
    responses={
        201: {"description": "Paciente creado con su triaje aplicado"},
        409: {"description": "Colision tras varios reintentos (cupo diario agotado o concurrencia)"},
        422: {"description": "Payload invalido"},
        503: {"description": "MongoDB no disponible"},
    },
)
def create_triage_patient(
    body: TriagePatientRequest,
    request: Request,
) -> TriagePatientResponse:
    mongo_writer = request.app.state.mongo_writer
    mongo_reader = request.app.state.mongo_reader

    if mongo_writer is None or mongo_reader is None:
        # CB-6 / RNF-X: el deployment no tiene Mongo cableado.
        raise HTTPException(
            status_code=503,
            detail="MongoDB writer not available in this deployment",
        )

    triage_result = evaluate(body.model_dump())
    age_effective = _derive_age(body.age, body.birth_date)
    today = date.today()
    now = datetime.now(timezone.utc)

    # Generar external_id candidato + retry con `NNNN+1` ante colision.
    try:
        counter = _next_counter_for_today(mongo_reader, today)
    except PyMongoError as exc:
        logger.exception("Mongo error counting TRIAGE patients")
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    last_error: Exception | None = None
    for attempt in range(TRIAGE_MAX_RETRIES):
        candidate_counter = counter + attempt
        if candidate_counter > DAILY_TRIAGE_LIMIT:
            # RF-6: 4 digitos -> maximo 9999 triajes por dia.
            logger.warning(
                "Daily triage limit reached (NNNN=%d > %d) for date %s",
                candidate_counter, DAILY_TRIAGE_LIMIT, today,
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cupo diario de triaje agotado: ya se han creado "
                    f"{DAILY_TRIAGE_LIMIT} pacientes con prefijo "
                    f"TRIAGE-{today.strftime('%Y%m%d')}-. "
                    f"Maximo permitido por dia: {DAILY_TRIAGE_LIMIT}."
                ),
            )
        external_id = build_triage_external_id(today, candidate_counter)
        doc = _build_patient_doc(
            body, external_id, triage_result, age_effective, now,
        )
        try:
            mongo_writer.insert_patient(doc)
            logger.info(
                "Created triage patient %s level=%s reasons=%s",
                external_id,
                triage_result.level,
                triage_result.reasons,
            )
            return TriagePatientResponse(
                external_id=external_id,
                name=body.name,
                birth_date=body.birth_date,
                age=age_effective,
                gender=body.gender,
                blood_type=body.blood_type,
                admissions=[],
                radiographies=[],
                triage=TriageInfo(
                    level=triage_result.level,
                    score=triage_result.score,
                    reasons=triage_result.reasons,
                    vital_signs=VitalSigns(**body.vital_signs.model_dump()),
                    symptoms=list(body.symptoms),
                    risk_factors=list(body.risk_factors),
                    triaged_at=now,
                    source="manual_triage",
                    rules_version=RULES_VERSION,
                ),
            )
        except DuplicateKeyError as exc:
            last_error = exc
            logger.warning(
                "DuplicateKeyError on insert_patient (attempt %d/%d, id=%s); "
                "retrying with next NNNN",
                attempt + 1,
                TRIAGE_MAX_RETRIES,
                external_id,
            )
            continue
        except PyMongoError as exc:
            logger.exception("Mongo error inserting triage patient")
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Agotados los reintentos: 409 explicito (RF-7).
    logger.error(
        "Triage insertion exhausted %d retries for date %s",
        TRIAGE_MAX_RETRIES, today,
    )
    raise HTTPException(
        status_code=409,
        detail=(
            f"No se pudo crear el paciente de triaje tras {TRIAGE_MAX_RETRIES} "
            f"reintentos. Posible cupo diario agotado o colisiones concurrentes."
        ),
    ) from last_error


@router.get(
    "/rules",
    summary="Devuelve la definicion de las reglas de triaje vigentes (RF-8)",
)
def get_rules(_: Request) -> dict:
    return get_rules_definition()
