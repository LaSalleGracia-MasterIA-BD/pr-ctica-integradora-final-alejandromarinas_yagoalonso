"""Daemon watcher long-running que dispara el ETL al llegar CSVs.

Esta es la version productizada de `IncomingFilesWatcher` (T9). Conecta el
watcher a un `PipelineOrchestrator` real y mantiene el proceso vivo para que
el contenedor pueda quedarse esperando archivos. Se usa como entrypoint del
servicio `watcher` en docker-compose.

Comportamiento:
  * Al arrancar, crea Spark + Mongo + orchestrator + watcher una sola vez.
  * Vigila `data/incoming/` esperando `patients.csv` + `admissions.csv`.
  * Cuando llegan ambos, ejecuta el ETL completo (`trigger_type=watcher`) y mueve
    los archivos a `data/incoming/processed/` para evitar re-procesamiento.
  * Gestiona SIGINT/SIGTERM limpiamente para que `docker compose down` sea graceful.

Esta es la segunda mitad de RF-7 (ingesta automatica). La primera mitad es el
endpoint manual `POST /api/v1/pipeline/trigger` expuesto por la API.
"""
from __future__ import annotations

import os
import signal
import threading
from pathlib import Path

from src.pipeline.logging_config import get_logger
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.spark_session import get_spark_session
from src.pipeline.storage.mongo_writer import get_mongo_writer_from_env
from src.pipeline.storage.sql_writer import get_sql_writer_from_env
from src.pipeline.watcher import IncomingFilesWatcher

logger = get_logger(__name__)

INCOMING_DIR = Path(os.environ.get("INCOMING_DIR", "/app/data/incoming"))


def main() -> None:
    logger.info("=== Hospital watcher daemon starting ===")
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)

    spark = get_spark_session(app_name="hospital-watcher", master="local[*]")
    mongo_writer = get_mongo_writer_from_env()
    sql_writer = get_sql_writer_from_env()
    orchestrator = PipelineOrchestrator(
        spark=spark,
        mongo_writer=mongo_writer,
        sql_writer=sql_writer,
    )

    def on_ready(patients_csv: Path, admissions_csv: Path) -> None:
        logger.info(
            "Watcher detected new batch: %s + %s",
            patients_csv.name,
            admissions_csv.name,
        )
        try:
            orchestrator.run_from_files(
                patients_csv=patients_csv,
                admissions_csv=admissions_csv,
                trigger_type="watcher",
            )
        except Exception:
            # El orquestador ya logea y marca como failed. Tragar aqui para
            # que el watcher siga corriendo para futuros batches.
            logger.exception("Pipeline run triggered by watcher failed")

    watcher = IncomingFilesWatcher(incoming_dir=INCOMING_DIR, on_ready=on_ready)
    watcher.start()

    stop_event = threading.Event()

    def _shutdown(_signum, _frame) -> None:
        logger.info("Shutdown signal received, stopping watcher...")
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Watcher daemon ready, watching %s", INCOMING_DIR)
    try:
        stop_event.wait()
    finally:
        watcher.stop()
        mongo_writer.close()
        sql_writer.close()
        spark.stop()
        logger.info("=== Hospital watcher daemon stopped ===")


if __name__ == "__main__":
    main()
