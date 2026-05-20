"""Pydantic response schemas for the API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class VitalSigns(BaseModel):
    """Signos vitales basicos usados por el sistema de triaje.

    Rangos plausibles (no umbrales validados medicamente; cubren
    errores de tecleo, no juicio clinico). Ver specs/triage-pacientes.md
    RF-1 + design seccion "Datos de entrada".
    """
    model_config = ConfigDict(extra="ignore")

    temperature_celsius: float = Field(ge=30, le=45)
    oxygen_saturation: int = Field(ge=0, le=100)
    heart_rate: int = Field(ge=0, le=300)
    respiratory_rate: int = Field(ge=0, le=100)
    systolic_bp: int = Field(ge=0, le=300)


class TriageInfo(BaseModel):
    """Resultado de triaje embebido en un paciente dado de alta manualmente.

    Lo emite `src/api/triage.py::evaluate` y lo persiste el endpoint
    POST /api/v1/triage/patients. Ver ADR-008 (reglas vs ML).
    """
    model_config = ConfigDict(extra="ignore")

    level: Literal["grave", "medio", "leve"]
    score: int
    reasons: list[str]
    vital_signs: VitalSigns
    symptoms: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    triaged_at: datetime
    source: str = "manual_triage"
    rules_version: str


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
    # RNF-6: declarado explicitamente para que Pydantic no lo descarte
    # (model_config=extra="ignore"). Solo presente en pacientes creados
    # via POST /api/v1/triage/patients.
    triage: TriageInfo | None = None


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


# -- Triaje de pacientes en alta manual (Feature 14) --

class TriagePatientRequest(BaseModel):
    """Body of POST /api/v1/triage/patients.

    Requiere `name` no vacio, `gender`, signos vitales y uno de los dos:
    `birth_date` (ISO YYYY-MM-DD pasada/actual) o `age`. El servidor
    genera el `external_id`. Las validaciones estrictas viven en
    `field_validator`s para devolver 422 con mensaje concreto.
    """
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    gender: Literal["M", "F", "Other"]
    birth_date: str | None = None  # ISO YYYY-MM-DD
    age: int | None = Field(default=None, ge=0, le=130)
    blood_type: str | None = None
    vital_signs: VitalSigns
    symptoms: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, v: str) -> str:
        """name=' ' pasaria `min_length=1`. Forzamos contenido real."""
        if not v.strip():
            raise ValueError("name no puede estar vacio ni ser solo espacios")
        return v

    @field_validator("birth_date")
    @classmethod
    def _birth_date_must_be_iso_and_not_future(cls, v: str | None) -> str | None:
        """Si viene, debe ser ISO YYYY-MM-DD parseable y no futura.

        Devolver None si el campo no se envia. Si llega informado pero
        es invalido o futuro, Pydantic devuelve 422 con el mensaje.
        """
        if v is None:
            return v
        try:
            parsed = date.fromisoformat(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"birth_date debe ser ISO YYYY-MM-DD valido, recibido: {v!r}"
            ) from exc
        if parsed > date.today():
            raise ValueError(
                f"birth_date no puede ser futura, recibido: {v}"
            )
        return v

    @model_validator(mode="after")
    def _require_birth_date_or_age(self) -> "TriagePatientRequest":
        if self.birth_date is None and self.age is None:
            raise ValueError("birth_date o age es obligatorio")
        return self


class TriagePatientResponse(Patient):
    """Respuesta del endpoint POST /api/v1/triage/patients.

    Hereda explicitamente de Patient (mejor OpenAPI que un alias y
    permite anadir campos especificos en el futuro sin tocar Patient).
    Garantiza que `triage` queda poblado en la respuesta.
    """
    triage: TriageInfo


# -- Alertas + informes operativos (Feature 15) --

class AlertResponse(BaseModel):
    """Una alerta calculada al vuelo desde las fuentes existentes.

    Ver `src/api/alerts.py::evaluate` para las reglas y
    `decisions/ADR-009-alertas-como-vista-derivada.md` para la decision
    de no persistirlas como entidades.
    """
    model_config = ConfigDict(extra="ignore")

    type: Literal["pipeline_failed", "data_quality_low", "triage_severe"]
    severity: Literal["critical", "high", "medium", "low"]
    title: str
    detail: str
    source: str
    source_id: str | None = None
    created_at: datetime


class AlertsResponse(BaseModel):
    """Respuesta de GET /api/v1/alerts."""
    items: list[AlertResponse]
    total: int
    generated_at: datetime
    threshold: float
    window_start: datetime


class DailyReportResponse(BaseModel):
    """Respuesta de GET /api/v1/reports/daily.

    Estructura segun spec automatizacion-alertas RF-4. El `generated_at`
    es dinamico (cuando se calculo el informe), por eso el endpoint no
    es idempotente — la idempotencia byte-a-byte aplica solo al
    Markdown del script `daily_report.py` (que NO incluye este campo).
    """
    date: str
    generated_at: datetime
    pipeline: dict
    quality: dict
    counts: dict
    triage: dict
    alerts: list[AlertResponse]
    threshold: float
