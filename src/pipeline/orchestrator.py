"""Coordinate the end-to-end ETL run over a pair of input CSVs.

The orchestrator wires the ingesters, processors and storage layer into a
single atomic pipeline run. Each call:

  1. Opens a `pipeline_run` row in SQLite (status=running) via `SqlWriter`
  2. Ingests patients and admissions CSVs into PySpark DataFrames
  3. Validates rows, splitting valid from rejected
  4. Cleans and transforms the valid rows (age, diagnosis_category)
  5. Cross-entity validation: admissions whose patient does not exist in
     this batch go to rejected with reason `orphan patient_external_id`
  6. Writes enriched patients with embedded admissions to MongoDB
  7. Persists rejected rows in MongoDB with their reason (soft cross-DB
     reference: `pipeline_run_id` is the SQLite UUID as string)
  8. Builds a `data_quality_summary` row per dimension and persists it
     in SQLite via `SqlWriter`
  9. Closes the run with status=success/failed and aggregated stats in
     SQLite

Polyglot persistence (ADR-004):
  - SQLite: pipeline_runs + data_quality_summary
  - MongoDB: patients/admissions/radiographies/rejected_records
  - MinIO: PNG binaries (handled by the bootstrap/watcher, not here)

Failures at any stage mark the run as failed (CB-5) before re-raising,
so the run history always reflects what happened.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession

from src.pipeline.ingesters.csv_ingester import CSVIngester
from src.pipeline.logging_config import get_logger
from src.pipeline.processors.data_cleaner import DataCleaner
from src.pipeline.processors.data_transformer import DataTransformer
from src.pipeline.processors.data_validator import DataValidator
from src.pipeline.processors.quality_summary import build as build_quality_summary
from src.pipeline.storage.mongo_writer import MongoWriter
from src.pipeline.storage.sql_writer import SqlWriter

logger = get_logger(__name__)


@dataclass(frozen=True)
class PipelineRunResult:
    run_id: str  # SQLite UUID string
    status: str
    records_processed: int
    records_rejected: int


class PipelineOrchestrator:
    def __init__(
        self,
        spark: SparkSession,
        mongo_writer: MongoWriter,
        sql_writer: SqlWriter,
        ingester: CSVIngester | None = None,
        validator: DataValidator | None = None,
        cleaner: DataCleaner | None = None,
        transformer: DataTransformer | None = None,
    ) -> None:
        self._spark = spark
        self._mongo = mongo_writer
        self._sql = sql_writer
        self._ingester = ingester or CSVIngester(spark)
        self._validator = validator or DataValidator()
        self._cleaner = cleaner or DataCleaner()
        self._transformer = transformer or DataTransformer()

    def run_from_files(
        self,
        patients_csv: Path,
        admissions_csv: Path,
        trigger_type: str = "manual",
        run_id: str | None = None,
    ) -> PipelineRunResult:
        """Run the full ETL on the given CSVs.

        If `run_id` is provided, reuse it (used by the API launcher which
        starts the run synchronously to return its id, then schedules
        execution as a BackgroundTask). Otherwise a new run is started.

        Errors at ANY stage — including the initial `start_pipeline_run`
        call — are logged and, when possible, recorded as a `failed` run
        before re-raising. We never swallow exceptions silently (CB-5).
        """
        try:
            if run_id is None:
                run_id = self._sql.start_pipeline_run(trigger_type=trigger_type)

            patients_clean, patients_rejected = self._process_patients(patients_csv)
            admissions_clean, admissions_rejected = self._process_admissions(
                admissions_csv
            )

            patients_records = [row.asDict() for row in patients_clean.collect()]
            admissions_records = [row.asDict() for row in admissions_clean.collect()]

            # Cross-entity validation: drop admissions whose patient does not
            # exist in this batch. Single-row validator cannot do this since
            # it lacks access to the patients dataframe.
            admissions_records, orphan_admissions = self._split_orphan_admissions(
                admissions_records, patients_records
            )

            self._mongo.bulk_upsert_patients_with_admissions(
                patients=patients_records,
                admissions=admissions_records,
            )

            patients_rejected_count = patients_rejected.count()
            admissions_rejected_count = admissions_rejected.count()
            orphan_count = len(orphan_admissions)

            rejected = (
                self._collect_rejected(patients_rejected, source="patients.csv")
                + self._collect_rejected(admissions_rejected, source="admissions.csv")
                + self._build_orphan_rejections(orphan_admissions)
            )
            # Soft cross-DB reference: pipeline_run_id is the SQLite UUID
            # stored in MongoDB as a string. See ADR-004.
            self._mongo.write_rejected(rejected, run_id)

            # Persist aggregated quality summary in SQLite (for the dashboard)
            patients_total = len(patients_records) + patients_rejected_count
            admissions_total = (
                len(admissions_records) + admissions_rejected_count + orphan_count
            )
            summary = build_quality_summary(
                patients_total=patients_total,
                patients_valid=len(patients_records),
                patients_rejected=patients_rejected_count,
                admissions_total=admissions_total,
                admissions_valid=len(admissions_records),
                admissions_rejected=admissions_rejected_count,
                admissions_orphans=orphan_count,
            )
            self._sql.write_quality_summary(run_id, summary)

            stats = {
                "records_processed": len(patients_records) + len(admissions_records),
                "records_rejected": len(rejected),
                "images_processed": 0,  # imagenes las maneja el bootstrap
            }
            self._sql.finish_pipeline_run(run_id, status="success", stats=stats)

            logger.info(
                "Pipeline run %s finished: %d processed, %d rejected (incl. %d orphan admissions)",
                run_id,
                stats["records_processed"],
                stats["records_rejected"],
                orphan_count,
            )
            return PipelineRunResult(
                run_id=run_id,
                status="success",
                records_processed=stats["records_processed"],
                records_rejected=stats["records_rejected"],
            )

        except Exception as exc:
            logger.exception("Pipeline run failed (run_id=%s)", run_id)
            if run_id is not None:
                # Best-effort: try to mark the run as failed in SQLite.
                # If SQLite itself is the cause of the failure, log and let
                # the original exception propagate.
                try:
                    self._sql.finish_pipeline_run(
                        run_id,
                        status="failed",
                        error_message=f"{type(exc).__name__}: {exc}",
                    )
                except Exception:
                    logger.exception(
                        "Could not mark run %s as failed (storage unavailable?)",
                        run_id,
                    )
            raise

    def _process_patients(
        self, csv_path: Path
    ) -> tuple[DataFrame, DataFrame]:
        raw = self._ingester.read_patients(csv_path)
        validation = self._validator.validate_patients(raw)
        cleaned = self._cleaner.clean_patients(validation.valid)
        enriched = self._transformer.enrich_patients(cleaned)
        return enriched, validation.rejected

    def _process_admissions(
        self, csv_path: Path
    ) -> tuple[DataFrame, DataFrame]:
        raw = self._ingester.read_admissions(csv_path)
        validation = self._validator.validate_admissions(raw)
        cleaned = self._cleaner.clean_admissions(validation.valid)
        enriched = self._transformer.enrich_admissions(cleaned)
        return enriched, validation.rejected

    @staticmethod
    def _collect_rejected(rejected_df: DataFrame, source: str) -> list[dict]:
        out: list[dict] = []
        for row in rejected_df.collect():
            raw_data = {k: v for k, v in row.asDict().items() if k != "rejection_reason"}
            out.append(
                {
                    "source_file": source,
                    "rejection_reason": row["rejection_reason"],
                    "raw_data": raw_data,
                }
            )
        return out

    @staticmethod
    def _split_orphan_admissions(
        admissions: list[dict], patients: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Split admissions into (valid, orphans) based on whether their
        `patient_external_id` exists in the patients batch.

        Orphans are admissions that pass the per-row validator but reference
        a patient that does not exist in this run's patients dataset. Without
        this check they would silently disappear at the embedding step.
        """
        known_ids = {p["external_id"] for p in patients}
        valid: list[dict] = []
        orphans: list[dict] = []
        for adm in admissions:
            if adm.get("patient_external_id") in known_ids:
                valid.append(adm)
            else:
                orphans.append(adm)
        return valid, orphans

    @staticmethod
    def _build_orphan_rejections(orphan_admissions: list[dict]) -> list[dict]:
        return [
            {
                "source_file": "admissions.csv",
                "rejection_reason": "orphan patient_external_id",
                "raw_data": adm,
            }
            for adm in orphan_admissions
        ]
