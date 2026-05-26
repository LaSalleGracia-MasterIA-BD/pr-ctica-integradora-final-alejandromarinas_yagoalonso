"""Factory de SparkSession para el pipeline de datos del hospital."""
from __future__ import annotations

import os

from pyspark.sql import SparkSession

from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_APP_NAME = "hospital-pipeline"
DEFAULT_MASTER = "local[*]"
DEFAULT_DRIVER_MEMORY = "2g"
DEFAULT_SHUFFLE_PARTITIONS = "4"


def get_spark_session(
    app_name: str | None = None,
    master: str | None = None,
) -> SparkSession:
    """Crea u obtiene una SparkSession configurada para el pipeline del hospital.

    Reutiliza cualquier SparkSession activa via getOrCreate para evitar drivers duplicados.
    """
    name = app_name or os.environ.get("SPARK_APP_NAME", DEFAULT_APP_NAME)
    master_url = master or os.environ.get("SPARK_MASTER", DEFAULT_MASTER)
    driver_memory = os.environ.get("SPARK_DRIVER_MEMORY", DEFAULT_DRIVER_MEMORY)
    shuffle_partitions = os.environ.get(
        "SPARK_SHUFFLE_PARTITIONS", DEFAULT_SHUFFLE_PARTITIONS
    )

    logger.info("Creating SparkSession app=%s master=%s", name, master_url)

    spark = (
        SparkSession.builder.appName(name)
        .master(master_url)
        .config("spark.driver.memory", driver_memory)
        .config("spark.sql.shuffle.partitions", shuffle_partitions)
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")
    return spark
