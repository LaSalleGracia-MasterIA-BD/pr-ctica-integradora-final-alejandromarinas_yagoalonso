"""Sistema basado en reglas para asignar prioridad de triaje a un paciente.

Punto unico de la logica de triaje. La funcion `evaluate` es **pura**:
recibe un dict con signos vitales + sintomas + edad y devuelve un
`TriageResult` (level + score + reasons). NO toca Mongo, NO toca
FastAPI. Esto la hace trivial de testear (ver tests/api/test_triage_rules.py).

Ver:
  * specs/triage-pacientes.md RF-5 para las reglas y RF-6 para el
    formato del external_id.
  * decisions/ADR-008-triaje-basado-en-reglas.md para la justificacion
    de "reglas vs ML" (conexion con la teoria del Master).

Disclaimer: los umbrales son academicos simplificados. NO es un
sistema clinico validado. El producto se entrega como asistencia al
triaje, no como diagnostico ni decision medica vinculante.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


RULES_VERSION = "1.0"


# Sintomas que activan reglas. Cualquier otro string en `symptoms` se
# persiste en el paciente como metadato pero NO dispara reglas (CB-4).
_SYMPTOM_GRAVE = {"alteracion_conciencia", "dolor_toracico_fuerte"}
_SYMPTOM_RESPIRATORIO = {"tos", "disnea", "fiebre"}


@dataclass(frozen=True)
class TriageResult:
    """Salida de `evaluate`. Pura, serializable y testeable."""
    level: str  # "grave" | "medio" | "leve"
    score: int
    reasons: list[str]


def _vital(payload: dict[str, Any], key: str) -> float:
    """Lectura defensiva de un signo vital del payload validado."""
    vs = payload.get("vital_signs", {})
    return vs[key]


def _patient_age(payload: dict[str, Any]) -> int | None:
    """Edad efectiva: si viene `age`, se usa tal cual. Si no, se deriva
    de `birth_date` redondeando a anos enteros. Si tampoco hay
    birth_date (no deberia, Pydantic lo bloquea), devuelve None."""
    age = payload.get("age")
    if age is not None:
        return int(age)
    bd = payload.get("birth_date")
    if not bd:
        return None
    try:
        birth = date.fromisoformat(bd)
    except ValueError:
        return None
    today = date.today()
    years = today.year - birth.year - (
        (today.month, today.day) < (birth.month, birth.day)
    )
    return years


def _eval_grave(payload: dict[str, Any]) -> list[str]:
    """Devuelve los IDs de reglas de grave que disparan. Vacio si ninguna."""
    reasons: list[str] = []
    spo2 = _vital(payload, "oxygen_saturation")
    sbp = _vital(payload, "systolic_bp")
    fr = _vital(payload, "respiratory_rate")
    fc = _vital(payload, "heart_rate")
    symptoms = set(payload.get("symptoms") or [])

    if spo2 < 92:
        reasons.append("spo2_lt_92")
    if sbp < 90:
        reasons.append("sbp_lt_90")
    if fr > 30:
        reasons.append("fr_gt_30")
    if fc > 130:
        reasons.append("fc_gt_130")
    for sym in _SYMPTOM_GRAVE:
        if sym in symptoms:
            reasons.append(sym)
    return reasons


def _eval_medio(payload: dict[str, Any]) -> list[str]:
    """IDs de reglas de medio que disparan (asume NO grave). Vacio si ninguna."""
    reasons: list[str] = []
    spo2 = _vital(payload, "oxygen_saturation")
    temp = _vital(payload, "temperature_celsius")
    fr = _vital(payload, "respiratory_rate")
    fc = _vital(payload, "heart_rate")
    symptoms = set(payload.get("symptoms") or [])
    age = _patient_age(payload)

    if 92 <= spo2 <= 94:
        reasons.append("spo2_92_94")
    if temp >= 39:
        reasons.append("temp_ge_39")
    if 22 <= fr <= 30:
        reasons.append("fr_22_30")
    if 110 <= fc <= 130:
        reasons.append("fc_110_130")
    if age is not None and age >= 70:
        has_resp = bool(symptoms & _SYMPTOM_RESPIRATORIO)
        if temp >= 38 or has_resp:
            reasons.append("anciano_riesgo_respiratorio")
    return reasons


def evaluate(payload: dict[str, Any]) -> TriageResult:
    """Evalua las reglas y devuelve `TriageResult`.

    El orden es:
      1. Comprobar reglas de grave. Si alguna dispara -> level=grave.
      2. Si no, comprobar reglas de medio. Si alguna dispara -> level=medio.
      3. Si no, level=leve, reasons=[].

    Reglas detalladas en design/triage-pacientes.md.
    """
    grave_reasons = _eval_grave(payload)
    if grave_reasons:
        return TriageResult(
            level="grave",
            score=len(grave_reasons),
            reasons=grave_reasons,
        )

    medio_reasons = _eval_medio(payload)
    if medio_reasons:
        return TriageResult(
            level="medio",
            score=len(medio_reasons),
            reasons=medio_reasons,
        )

    return TriageResult(level="leve", score=0, reasons=[])


def get_rules_definition() -> dict[str, Any]:
    """Devuelve la definicion de las reglas vigentes (RF-8).

    Usado por GET /api/v1/triage/rules para auto-documentar la version
    actual del sistema basado en reglas (ver ADR-008).
    """
    return {
        "version": RULES_VERSION,
        "levels": {
            "grave": [
                {"id": "spo2_lt_92",
                 "description": "saturacion de oxigeno menor que 92"},
                {"id": "sbp_lt_90",
                 "description": "tension sistolica menor que 90"},
                {"id": "fr_gt_30",
                 "description": "frecuencia respiratoria mayor que 30"},
                {"id": "fc_gt_130",
                 "description": "frecuencia cardiaca mayor que 130"},
                {"id": "alteracion_conciencia",
                 "description": "sintoma de alteracion de la conciencia"},
                {"id": "dolor_toracico_fuerte",
                 "description": "sintoma de dolor toracico fuerte"},
            ],
            "medio": [
                {"id": "spo2_92_94",
                 "description": "saturacion de oxigeno entre 92 y 94"},
                {"id": "temp_ge_39",
                 "description": "temperatura mayor o igual a 39"},
                {"id": "fr_22_30",
                 "description": "frecuencia respiratoria entre 22 y 30"},
                {"id": "fc_110_130",
                 "description": "frecuencia cardiaca entre 110 y 130"},
                {"id": "anciano_riesgo_respiratorio",
                 "description": (
                     "edad mayor o igual a 70 con temperatura >= 38 "
                     "o sintoma respiratorio (tos, disnea, fiebre)"
                 )},
            ],
        },
        "notes": (
            "Reglas academicas simplificadas, alineadas con la teoria de "
            "Modelos de IA del Master (sistemas basados en reglas como "
            "alternativa a los modelos aprendidos cuando no hay dataset "
            "etiquetado). NO es un sistema clinico validado. Asistencia al "
            "triaje, no diagnostico ni decision medica vinculante."
        ),
    }


# -- Helper para el router: generacion del external_id ---------------------


def build_triage_external_id(today: date, counter: int) -> str:
    """Devuelve `TRIAGE-YYYYMMDD-NNNN` con `NNNN` en 4 digitos zero-padded."""
    return f"TRIAGE-{today.strftime('%Y%m%d')}-{counter:04d}"
