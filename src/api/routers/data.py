"""Endpoints GET para consumir datos hospitalarios desde MongoDB."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.models import (
    Admission,
    AdmissionsPage,
    Patient,
    PatientsPage,
    Radiography,
    RadiographiesPage,
)

router = APIRouter(prefix="/api/v1", tags=["data"])


def _reader(request: Request):
    return request.app.state.mongo_reader


@router.get("/patients", response_model=PatientsPage)
def list_patients(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> PatientsPage:
    reader = _reader(request)
    items = reader.list_patients(limit=limit, offset=offset)
    total = reader.count_patients()
    return PatientsPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[Patient.model_validate(doc) for doc in items],
    )


@router.get("/patients/{external_id}", response_model=Patient)
def get_patient(request: Request, external_id: str) -> Patient:
    reader = _reader(request)
    doc = reader.find_patient(external_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Patient {external_id} not found")
    return Patient.model_validate(doc)


@router.get("/admissions", response_model=AdmissionsPage)
def list_admissions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AdmissionsPage:
    reader = _reader(request)
    items = reader.list_admissions(limit=limit, offset=offset)
    total = reader.count_admissions()
    return AdmissionsPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[Admission.model_validate(doc) for doc in items],
    )


@router.get("/radiographies", response_model=RadiographiesPage)
def list_radiographies(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> RadiographiesPage:
    reader = _reader(request)
    items = reader.list_radiographies(limit=limit, offset=offset)
    total = reader.count_radiographies()
    return RadiographiesPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[Radiography.model_validate(doc) for doc in items],
    )
