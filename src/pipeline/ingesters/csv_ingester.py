"""Lee archivos CSV hospitalarios a DataFrames de PySpark.

Esta capa solo gestiona la ingesta (lectura + validacion de schema). NO
filtra ni rechaza filas — eso corresponde a la etapa de validacion (T7).
Las filas con casos borde (nulls, valores malformados) se preservan literales
para que los validators downstream puedan generar motivos de rechazo utiles.
"""
from __future__ import annotations

from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)

PATIENT_SCHEMA_COLUMNS: tuple[str, ...] = (
    "external_id",
    "name",
    "birth_date",
    "gender",
    "blood_type",
)

ADMISSION_SCHEMA_COLUMNS: tuple[str, ...] = (
    "patient_external_id",
    "admission_date",
    "discharge_date",
    "department",
    "diagnosis_code",
    "diagnosis_description",
    "status",
)

SOURCE_FILE_COLUMN = "_source_file"


class MissingColumnsError(ValueError):
    """Se lanza cuando a un CSV le faltan una o mas columnas obligatorias."""


class CSVIngester:
    def __init__(self, spark: SparkSession) -> None:
        self._spark = spark

    def read_patients(self, csv_path: Path) -> DataFrame:
        return self._read(csv_path, PATIENT_SCHEMA_COLUMNS, entity="patients")

    def read_admissions(self, csv_path: Path) -> DataFrame:
        return self._read(csv_path, ADMISSION_SCHEMA_COLUMNS, entity="admissions")

    def _read(
        self,
        csv_path: Path,
        required_columns: tuple[str, ...],
        entity: str,
    ) -> DataFrame:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file does not exist: {path}")

        # Leer todo como string. El casting de tipos y la validacion se hacen despues.
        schema = StructType(
            [StructField(col, StringType(), nullable=True) for col in required_columns]
        )

        # Usar la cabecera para auto-detectar el orden de columnas; las faltantes saldran abajo.
        df = (
            self._spark.read
            .option("header", "true")
            .option("mode", "PERMISSIVE")
            .csv(str(path))
        )

        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            raise MissingColumnsError(
                f"CSV {path.name} is missing required columns: {missing}"
            )

        df = df.select(*required_columns)

        # Forzar el schema nominal para que el codigo downstream vea tipos consistentes.
        for field in schema.fields:
            df = df.withColumn(field.name, F.col(field.name).cast(field.dataType))

        df = df.withColumn(SOURCE_FILE_COLUMN, F.lit(path.name))

        # Los conteos de filas los logean las etapas downstream (validator, cleaner)
        # para evitar disparar una accion extra sobre el DataFrame aqui.
        logger.info("Ingested %s from %s", entity, path.name)
        return df
