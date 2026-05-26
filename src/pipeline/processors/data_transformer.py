"""Enriquece registros hospitalarios y calcula metricas agregadas.

El transformer opera sobre filas que ya pasaron validacion y limpieza
(T7). El enriquecimiento anade campos derivados; las agregaciones producen
DataFrames de resumen pensados para la capa API/dashboard.

Notas de diseno:
  - `age` es un snapshot en el momento del procesado. El `birth_date` raw
    se conserva para que los consumidores downstream puedan recalcular si lo necesitan.
  - `diagnosis_category` mapea codigos ICD-10 a las tres categorias clinicas
    alineadas con el objetivo de clasificacion del proyecto: COVID-19, Pneumonia,
    Other (cualquier otro). Los codigos nulos pasan a "Unknown" para que los
    conteos sigan siendo utiles incluso antes de que la validacion upstream los capture.
"""
from __future__ import annotations

from datetime import date

from pyspark.sql import DataFrame, functions as F

from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)

# Prefijos ICD-10 agrupados por la categoria clinica que nos interesa.
COVID_ICD10_PREFIXES = ("U07",)
# J12-J18 cubren neumonias virales y bacterianas (no especificada, lobar, bronco,
# viral, bacteriana, por aspiracion y neumonia no especificada).
PNEUMONIA_ICD10_PREFIXES = ("J12", "J13", "J14", "J15", "J16", "J17", "J18")


class DataTransformer:
    def enrich_patients(
        self, df: DataFrame, reference_date: date | None = None
    ) -> DataFrame:
        """Anade una columna `age` calculada desde `birth_date`.

        Pasar `reference_date` mantiene los tests deterministas. Los callers
        de produccion normalmente lo omiten para usar `current_date()`.
        """
        if reference_date is None:
            ref = F.current_date()
        else:
            ref = F.to_date(F.lit(reference_date.isoformat()))

        birth = F.to_date(F.col("birth_date"))
        age = F.when(
            birth.isNull(), F.lit(None)
        ).otherwise(
            F.floor(F.months_between(ref, birth) / F.lit(12)).cast("integer")
        )
        enriched = df.withColumn("age", age)
        logger.info("Enriched %d patients with age", enriched.count())
        return enriched

    def enrich_admissions(self, df: DataFrame) -> DataFrame:
        """Anade una columna `diagnosis_category` derivada de `diagnosis_code`."""
        code = F.col("diagnosis_code")
        covid_pred = self._prefix_match(code, COVID_ICD10_PREFIXES)
        pneumonia_pred = self._prefix_match(code, PNEUMONIA_ICD10_PREFIXES)

        category = (
            F.when(code.isNull(), F.lit("Unknown"))
            .when(covid_pred, F.lit("COVID-19"))
            .when(pneumonia_pred, F.lit("Pneumonia"))
            .otherwise(F.lit("Other"))
        )
        enriched = df.withColumn("diagnosis_category", category)
        logger.info("Enriched %d admissions with diagnosis_category", enriched.count())
        return enriched

    def admissions_by_department(self, df: DataFrame) -> DataFrame:
        return df.groupBy("department").count().orderBy(F.desc("count"))

    def admissions_by_month(self, df: DataFrame) -> DataFrame:
        return (
            df.withColumn(
                "month", F.date_format(F.to_date(F.col("admission_date")), "yyyy-MM")
            )
            .groupBy("month")
            .count()
            .orderBy("month")
        )

    def admissions_by_diagnosis_category(self, df: DataFrame) -> DataFrame:
        enriched = (
            df if "diagnosis_category" in df.columns else self.enrich_admissions(df)
        )
        return enriched.groupBy("diagnosis_category").count().orderBy(F.desc("count"))

    @staticmethod
    def _prefix_match(column, prefixes: tuple[str, ...]):
        """Construye una expresion booleana: `column` empieza con alguno de los prefijos."""
        expr = F.lit(False)
        for prefix in prefixes:
            expr = expr | column.startswith(prefix)
        return expr
