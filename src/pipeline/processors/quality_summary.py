"""Agrega conteos por dimension para el data_quality_summary del dashboard.

Funcion pura sin I/O — facil de testear, facil de componer. Vive en
`processors/` porque transforma datos, como el validator y el cleaner,
aunque no toca PySpark.

Los ingresos huerfanos detectados por validacion cross-entity (ingresos cuyo
`patient_external_id` no existe en el batch) cuentan dentro del total de
`admissions.rejected`. NO son una dimension separada: el dashboard razona
en terminos de "que fraccion de ingresos fue rechazada, por cualquier motivo".
"""
from __future__ import annotations


def build(
    *,
    patients_total: int,
    patients_valid: int,
    patients_rejected: int,
    admissions_total: int,
    admissions_valid: int,
    admissions_rejected: int,
    admissions_orphans: int,
) -> list[dict]:
    """Construye las filas de summary listas para alimentar `SqlWriter.write_quality_summary`."""
    patients = _row(
        dimension="patients",
        total=patients_total,
        valid=patients_valid,
        rejected=patients_rejected,
    )
    # Los huerfanos se contabilizan junto a los rechazos por regla en admissions.
    admissions = _row(
        dimension="admissions",
        total=admissions_total,
        valid=admissions_valid,
        rejected=admissions_rejected + admissions_orphans,
    )
    return [patients, admissions]


def _row(*, dimension: str, total: int, valid: int, rejected: int) -> dict:
    rate = (rejected / total) if total > 0 else 0.0
    return {
        "dimension": dimension,
        "total": total,
        "valid": valid,
        "rejected": rejected,
        "rejection_rate": rate,
    }
