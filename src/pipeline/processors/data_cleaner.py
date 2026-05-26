"""Limpia registros hospitalarios: recorta whitespace, elimina duplicados.

El cleaner opera sobre filas que ya pasaron validacion (T7). Es deliberadamente
conservador: nunca modifica campos de negocio, solo normaliza artefactos
obvios (whitespace al final) y colapsa duplicados por clave de negocio.

Nota sobre dedup: cuando varias filas comparten la misma tupla de clave,
cual sobrevive no esta garantizado. La garantia es la unicidad de la clave,
no la preservacion del orden de insercion.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, functions as F

from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)


class DataCleaner:
    def clean_patients(self, df: DataFrame) -> DataFrame:
        cleaned = (
            df.withColumn("name", F.trim(F.col("name")))
              .dropDuplicates(subset=["external_id"])
        )
        logger.info("Cleaned patients: %d rows after dedup", cleaned.count())
        return cleaned

    def clean_admissions(self, df: DataFrame) -> DataFrame:
        # Un paciente puede tener multiples ingresos; deduplicar solo cuando el
        # mismo paciente tenga la misma fecha y departamento — casi seguro son
        # duplicados, no dos ingresos distintos.
        cleaned = (
            df.withColumn("department", F.trim(F.col("department")))
              .dropDuplicates(
                  subset=["patient_external_id", "admission_date", "department"]
              )
        )
        logger.info("Cleaned admissions: %d rows after dedup", cleaned.count())
        return cleaned
