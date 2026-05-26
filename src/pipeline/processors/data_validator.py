"""Valida registros hospitalarios y separa filas validas de rechazadas.

El validator aplica reglas de negocio en orden determinista. La primera regla
que una fila falla determina su `rejection_reason`. Las filas validas mantienen
su schema original; las rechazadas reciben una columna `rejection_reason` anadida.
"""
from __future__ import annotations

from dataclasses import dataclass

from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import StringType

from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)

PATIENT_ID_PATTERN = r"^HOSP-\d{6}$"
ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
VALID_GENDERS = ["M", "F", "Other"]
VALID_BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
VALID_STATUSES = ["admitted", "discharged", "transferred"]

REASON_COLUMN = "rejection_reason"
_REASON_TMP = "_reason"


@dataclass(frozen=True)
class ValidationResult:
    """Dos DataFrames: `valid` con el schema original, `rejected` con motivo."""

    valid: DataFrame
    rejected: DataFrame


class DataValidator:
    def validate_patients(self, df: DataFrame) -> ValidationResult:
        original_columns = df.columns
        df = df.withColumn(_REASON_TMP, F.lit(None).cast(StringType()))

        df = _apply_rule(
            df,
            F.col("external_id").isNull() | ~F.col("external_id").rlike(PATIENT_ID_PATTERN),
            "invalid external_id",
        )
        df = _apply_rule(
            df,
            F.col("name").isNull() | (F.trim(F.col("name")) == ""),
            "missing name",
        )
        df = _apply_rule(
            df,
            F.col("birth_date").isNull() | ~F.col("birth_date").rlike(ISO_DATE_PATTERN),
            "invalid birth_date",
        )
        df = _apply_rule(
            df,
            F.col("gender").isNull() | ~F.col("gender").isin(VALID_GENDERS),
            "invalid gender",
        )
        df = _apply_rule(
            df,
            F.col("blood_type").isNull() | ~F.col("blood_type").isin(VALID_BLOOD_TYPES),
            "invalid blood_type",
        )

        return _split(df, original_columns)

    def validate_admissions(self, df: DataFrame) -> ValidationResult:
        original_columns = df.columns
        df = df.withColumn(_REASON_TMP, F.lit(None).cast(StringType()))

        df = _apply_rule(
            df,
            F.col("patient_external_id").isNull()
            | ~F.col("patient_external_id").rlike(PATIENT_ID_PATTERN),
            "invalid patient_external_id",
        )
        df = _apply_rule(
            df,
            F.col("admission_date").isNull()
            | ~F.col("admission_date").rlike(ISO_DATE_PATTERN),
            "invalid admission_date",
        )
        df = _apply_rule(
            df,
            F.col("department").isNull() | (F.trim(F.col("department")) == ""),
            "missing department",
        )
        df = _apply_rule(
            df,
            F.col("status").isNull() | ~F.col("status").isin(VALID_STATUSES),
            "invalid status",
        )

        return _split(df, original_columns)


def _apply_rule(df: DataFrame, failing_condition, reason: str) -> DataFrame:
    """Etiqueta con `reason` las filas que fallan `failing_condition`, pero solo
    si no llevan ya un motivo de rechazo previo (first-failure-wins)."""
    return df.withColumn(
        _REASON_TMP,
        F.when(
            F.col(_REASON_TMP).isNull() & failing_condition,
            F.lit(reason),
        ).otherwise(F.col(_REASON_TMP)),
    )


def _split(df: DataFrame, original_columns: list[str]) -> ValidationResult:
    valid = df.filter(F.col(_REASON_TMP).isNull()).select(*original_columns)
    rejected = df.filter(F.col(_REASON_TMP).isNotNull()).withColumnRenamed(
        _REASON_TMP, REASON_COLUMN
    )
    valid_count = valid.count()
    rejected_count = rejected.count()
    logger.info(
        "Validation done: %d valid rows, %d rejected rows",
        valid_count,
        rejected_count,
    )
    return ValidationResult(valid=valid, rejected=rejected)
