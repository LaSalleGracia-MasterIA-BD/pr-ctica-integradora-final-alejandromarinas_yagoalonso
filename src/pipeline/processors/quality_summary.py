"""Aggregate counts per dimension for the dashboard's data_quality_summary.

Pure function with no I/O — easy to test, easy to compose. Lives in
`processors/` because it transforms data, like the validator and the
cleaner, even though it does not touch PySpark.

Orphan admissions detected by cross-entity validation (admissions whose
`patient_external_id` does not exist in the batch) count towards the
`admissions.rejected` total. They are NOT a separate dimension: the
dashboard reasons in terms of "what fraction of admissions were rejected,
for any reason".
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
    """Build summary rows ready to feed `SqlWriter.write_quality_summary`."""
    patients = _row(
        dimension="patients",
        total=patients_total,
        valid=patients_valid,
        rejected=patients_rejected,
    )
    # Orphans are counted alongside rule-based rejections in admissions.
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
