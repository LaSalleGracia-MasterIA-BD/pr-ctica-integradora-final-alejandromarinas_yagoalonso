"""Glue between the FastAPI router and the actual ETL orchestrator.

The HTTP handler `POST /api/v1/pipeline/trigger` should respond fast (with
the new run id) but the heavy PySpark work has to happen somewhere. This
launcher splits that into two parts:

  * `start_run(trigger_type)` — synchronous: creates the `pipeline_runs`
    row in SQLite so the API can return the run id (UUID string)
    immediately
  * `execute(run_id, patients_csv, admissions_csv)` — long-running: runs
    the orchestrator under a fresh SparkSession + writers, reusing the
    run id so the run history is consistent

Polyglot persistence (ADR-004): the run lifecycle (start/finish + quality
summary) lives in SQLite, while rejected records and patient/admissions
documents live in MongoDB. The launcher creates both writers per call.

`execute` is intended to be scheduled with FastAPI's `BackgroundTasks`. It
catches exceptions and only logs — the orchestrator has already marked
the run as failed in SQLite, so re-raising would just generate noise in
uvicorn without changing state.
"""
from __future__ import annotations

from pathlib import Path

from src.pipeline.logging_config import get_logger
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.spark_session import get_spark_session
from src.pipeline.storage.mongo_writer import get_mongo_writer_from_env
from src.pipeline.storage.sql_writer import get_sql_writer_from_env

logger = get_logger(__name__)


class PipelineLauncher:
    def start_run(self, trigger_type: str = "manual") -> str:
        sql_writer = get_sql_writer_from_env()
        try:
            return sql_writer.start_pipeline_run(trigger_type=trigger_type)
        finally:
            sql_writer.close()

    def execute(
        self,
        run_id: str,
        patients_csv: Path,
        admissions_csv: Path,
    ) -> None:
        spark = get_spark_session(
            app_name="hospital-api-trigger", master="local[*]"
        )
        mongo_writer = get_mongo_writer_from_env()
        sql_writer = get_sql_writer_from_env()
        try:
            orchestrator = PipelineOrchestrator(
                spark=spark,
                mongo_writer=mongo_writer,
                sql_writer=sql_writer,
            )
            orchestrator.run_from_files(
                patients_csv=patients_csv,
                admissions_csv=admissions_csv,
                run_id=run_id,
            )
        except Exception:
            logger.exception("Background pipeline run %s failed", run_id)
            # No re-raising: the run is already marked as failed in SQLite
            # by the orchestrator. Re-raising in a BackgroundTask would only
            # generate a noisy traceback in uvicorn without changing state.
        finally:
            mongo_writer.close()
            sql_writer.close()
            # We intentionally don't stop Spark — getOrCreate reuses the
            # session for subsequent triggers within the same API process.
