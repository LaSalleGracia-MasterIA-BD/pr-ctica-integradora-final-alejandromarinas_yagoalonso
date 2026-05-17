"""Pydantic response schemas for the API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Admission(BaseModel):
    model_config = ConfigDict(extra="ignore")

    patient_external_id: str | None = None
    admission_date: str | None = None
    discharge_date: str | None = None
    department: str | None = None
    diagnosis_code: str | None = None
    diagnosis_description: str | None = None
    diagnosis_category: str | None = None
    status: str | None = None


class RadiographyClassification(BaseModel):
    """Persisted classification for a radiography.

    Lives in `patients.radiographies[].classification`. Used both as the
    nested sub-document of `Radiography` and as the body of the
    `GET /api/v1/radiographies/classification` and
    `POST /api/v1/radiographies/classify` responses.
    """
    model_config = ConfigDict(extra="ignore")

    predicted_class: str
    probabilities: dict[str, float]
    predicted_at: datetime
    model_version: str


class Radiography(BaseModel):
    model_config = ConfigDict(extra="ignore")

    patient_external_id: str | None = None
    minio_object_key: str
    original_filename: str | None = None
    file_size_bytes: int | None = None
    ingested_at: str | None = None
    # Previously `str | None`; now a structured object (Feature 2).
    classification: RadiographyClassification | None = None


class Patient(BaseModel):
    model_config = ConfigDict(extra="ignore")

    external_id: str
    name: str | None = None
    birth_date: str | None = None
    age: int | None = None
    gender: str | None = None
    blood_type: str | None = None
    admissions: list[Admission] = Field(default_factory=list)
    radiographies: list[Radiography] = Field(default_factory=list)


class Page(BaseModel):
    total: int
    limit: int
    offset: int


class PatientsPage(Page):
    items: list[Patient]


class AdmissionsPage(Page):
    items: list[Admission]


class RadiographiesPage(Page):
    items: list[Radiography]


class PipelineRun(BaseModel):
    """Audit row from the SQLite `pipeline_runs` table.

    `id` is a UUID v4 string (see ADR-004: SQLite owns this primary key,
    no bson.ObjectId is involved).
    """
    model_config = ConfigDict(extra="ignore")

    id: str
    trigger_type: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    records_processed: int = 0
    records_rejected: int = 0
    images_processed: int = 0
    error_message: str | None = None


class PipelineRunsPage(Page):
    items: list[PipelineRun]


class PipelineTriggerResponse(BaseModel):
    run_id: str
    status: str
    message: str


class QualitySummaryItem(BaseModel):
    """One row of the `data_quality_summary` SQL table."""
    model_config = ConfigDict(extra="ignore")

    pipeline_run_id: str
    dimension: str
    total: int
    valid: int
    rejected: int
    rejection_rate: float
    recorded_at: datetime | None = None


class QualitySummaryResponse(BaseModel):
    """Latest snapshot: one item per dimension for the most recent run."""
    items: list[QualitySummaryItem]


class QualitySummaryHistoryPage(Page):
    dimension: str
    items: list[QualitySummaryItem]


class HealthResponse(BaseModel):
    status: str
    version: str
    predictor_loaded: bool


# -- Classification (Feature 2: clasificacion-radiografias) --

class ClassifyRequest(BaseModel):
    """Body of POST /api/v1/radiographies/classify."""
    minio_object_key: str = Field(min_length=1)


class ClassificationResponse(RadiographyClassification):
    """Body of POST /classify and GET /classification responses.

    Includes the minio_object_key so callers can confirm which radiography
    the classification belongs to without round-tripping through the query.
    """
    minio_object_key: str
