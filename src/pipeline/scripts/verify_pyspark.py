"""Smoke test que verifica la configuracion de PySpark + logging dentro del contenedor."""
from __future__ import annotations

from src.pipeline.logging_config import get_logger
from src.pipeline.spark_session import get_spark_session


def main() -> None:
    logger = get_logger(__name__)
    logger.info("Starting PySpark setup verification")

    spark = get_spark_session(app_name="verify-pyspark")
    logger.info("SparkSession version: %s", spark.version)

    df = spark.createDataFrame([(1, "sana"), (2, "neumonia"), (3, "covid")], ["id", "label"])
    row_count = df.count()
    logger.info("Sample DataFrame created with %d rows", row_count)

    spark.stop()
    logger.info("PySpark setup verification completed successfully")


if __name__ == "__main__":
    main()
