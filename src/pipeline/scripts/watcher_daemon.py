"""Long-running watcher daemon that triggers the ETL on incoming CSVs.

This is the productized side of `IncomingFilesWatcher` (T9). It wires the
watcher to a real `PipelineOrchestrator` and keeps the process alive so the
container can sit there waiting for files. Used as the entrypoint of the
`watcher` service in docker-compose.

Behaviour:
  * On startup, creates Spark + Mongo + orchestrator + watcher once.
  * Watches `data/incoming/` for `patients.csv` + `admissions.csv`.
  * When both arrive, runs the full ETL (`trigger_type=watcher`) and moves
    the files into `data/incoming/processed/` to avoid reprocessing.
  * Handles SIGINT/SIGTERM cleanly so `docker compose down` is graceful.

This is the second half of RF-7 (automated ingestion). The first half is
the manual `POST /api/v1/pipeline/trigger` endpoint exposed by the API.
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
            # Already logged + marked as failed by the orchestrator. Swallow
            # here so the watcher keeps running for future batches.
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
