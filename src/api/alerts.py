"""Reglas de alertas operativas (Feature 15, ADR-009).

Funcion pura `evaluate(state) -> list[Alert]`: convierte lecturas crudas
(ya filtradas por el caller a la ventana temporal pertinente) en alertas.

NO abre conexiones, NO conoce el reloj, NO filtra por ventana — eso es
responsabilidad del router/script que llama. De esa forma:

  * El endpoint `/alerts` usa ventana `[since, now]`.
  * El endpoint `/reports/daily` y el script `daily_report.py` usan
    ventana estricta del dia `[00:00, 23:59:59.999]` UTC.
  * Ambos invocan la MISMA `evaluate` pasando listas distintas.

Patron equivalente al sistema de reglas del triaje (ADR-008) y a la
Sesion 07 de Yuri (sistemas basados en reglas, `ruleBasedSystem/`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Severity = Literal["critical", "high", "medium", "low"]
AlertType = Literal["pipeline_failed", "data_quality_low", "triage_severe"]

# Orden de severity para ordenacion DESC (menor numero = mas critico).
_SEVERITY_ORDER: dict[Severity, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


@dataclass(frozen=True)
class Alert:
    """Alerta operativa calculada al vuelo. Inmutable (frozen=True).

    `source_id` es opcional para alertas que no tienen una entidad concreta
    detras (raro en este sistema, pero el contrato lo permite).
    """
    type: AlertType
    severity: Severity
    title: str
    detail: str
    source: str
    source_id: str | None
    created_at: datetime


def evaluate(
    failed_runs: list[dict],
    quality_snapshots: list[dict],
    severe_triage_patients: list[dict],
    threshold: float = 0.10,
) -> list[Alert]:
    """Aplica las 3 reglas RF-2 y devuelve la lista ordenada (RF-8).

    Reglas (todas dependen del caller para haber filtrado por ventana):

    * Por cada run en `failed_runs` -> alerta `pipeline_failed`/`high`.
    * Por cada snapshot en `quality_snapshots` con
      `rejection_rate > threshold` (estricto) -> `data_quality_low`/`medium`.
    * Por cada paciente en `severe_triage_patients` -> `triage_severe`/`critical`.

    Orden de salida: severity DESC (critical primero), luego created_at DESC.
    """
    alerts: list[Alert] = []

    for run in failed_runs:
        trigger = run.get("trigger_type", "?")
        error = run.get("error_message") or "Sin mensaje de error"
        alerts.append(Alert(
            type="pipeline_failed",
            severity="high",
            title=f"Run del pipeline fallido ({trigger})",
            detail=error,
            source="pipeline_runs",
            source_id=run["id"],
            created_at=run["started_at"],
        ))

    for snap in quality_snapshots:
        if snap["rejection_rate"] > threshold:
            alerts.append(Alert(
                type="data_quality_low",
                severity="medium",
                title=f"Calidad de datos baja en {snap['dimension']}",
                detail=(
                    f"rejection_rate={snap['rejection_rate']:.4f} > "
                    f"umbral={threshold:.2f}; rechazados {snap['rejected']} "
                    f"de {snap['total']}"
                ),
                source="data_quality_summary",
                source_id=f"{snap['pipeline_run_id']}:{snap['dimension']}",
                created_at=snap["recorded_at"],
            ))

    for patient in severe_triage_patients:
        triage = patient.get("triage", {})
        reasons = triage.get("reasons", [])
        name = patient.get("name", "?")
        alerts.append(Alert(
            type="triage_severe",
            severity="critical",
            title="Paciente triajeado como GRAVE",
            detail=f"reasons={reasons}; name={name}",
            source="patients.triage",
            source_id=patient["external_id"],
            created_at=triage["triaged_at"],
        ))

    alerts.sort(
        key=lambda a: (_SEVERITY_ORDER[a.severity], -a.created_at.timestamp())
    )
    return alerts
