"""Coordinate the end-to-end ETL run over a pair of input CSVs.

The orchestrator wires the ingesters, processors and storage layer into a
single atomic pipeline run. Each call:

  1. Opens a `pipeline_run` document in MongoDB (status=running)
  2. Ingests patients and admissions CSVs into PySpark DataFrames
  3. Validates rows, splitting valid from rejected
  4. Cleans and transforms the valid rows (age, diagnosis_category)
  5. Writes enriched patients with embedded admissions to MongoDB
  6. Persists rejected rows with their reason for auditability
  7. Closes the run with status=success/failed and aggregated stats

Failures at any stage mark the run as failed (CB-5) before re-raising, so
the run history always reflects what happened.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bson import ObjectId
from pyspark.sql import DataFrame, SparkSession

from src.pipeline.ingesters.csv_ingester import CSVIngester
from src.pipeline.logging_config import get_logger
from src.pipeline.processors.data_cleaner import DataCleaner
from src.pipeline.processors.data_transformer import DataTransformer
from src.pipeline.processors.data_validator import DataValidator
from src.pipeline.storage.mongo_writer import MongoWriter

logger = get_logger(__name__)


@dataclass(frozen=True)
class PipelineRunResult:
    run_id: ObjectId
    status: str
    records_processed: int
    records_rejected: int


class PipelineOrchestrator:
    def __init__(
        self,
        spark: SparkSession,
        mongo_writer: MongoWriter,
        ingester: CSVIngester | None = None,
        validator: DataValidator | None = None,
        cleaner: DataCleaner | None = None,
        transformer: DataTransformer | None = None,
    ) -> None:
        self._spark = spark
        self._writer = mongo_writer
        self._ingester = ingester or CSVIngester(spark)
        self._validator = validator or DataValidator()
        self._cleaner = cleaner or DataCleaner()
        self._transformer = transformer or DataTransformer()

    def run_from_files(
        self,
        patients_csv: Path,
        admissions_csv: Path,
        trigger_type: str = "manual",
        run_id: ObjectId | None = None,
    ) -> PipelineRunResult:
        """Run the full ETL on the given CSVs.

        If `run_id` is provided, the orchestrator reuses it (used by the API
        launcher, which creates the run synchronously to return its id to the
        client and then schedules the heavy work as a background task).
        Otherwise a new run is created.

        Errors at ANY stage — including the initial `start_pipeline_run` call
        — are logged and, when possible, recorded as a `failed` run before
        re-raising. We never swallow exceptions silently (CB-5).
        """
        try:
            if run_id is None:
                run_id = self._writer.start_pipeline_run(trigger_type=trigger_type)

            patients_clean, patients_rejected = self._process_patients(patients_csv)
            admissions_clean, admissions_rejected = self._process_admissions(
                admissions_csv
            )

            patients_records = [row.asDict() for row in patients_clean.collect()]
            admissions_records = [row.asDict() for row in admissions_clean.collect()]

            # Cross-entity validation: drop admissions whose patient does not
            # exist in this batch. The single-row validator cannot do this
            # because it would need access to the full patients dataframe.
            # The data contract (design/pipeline-datos.md) requires
            # "patient debe existir" for admissions.
            admissions_records, orphan_admissions = self._split_orphan_admissions(
                admissions_records, patients_records
            )

            self._writer.bulk_upsert_patients_with_admissions(
                patients=patients_records,
                admissions=admissions_records,
            )

            rejected = (
                self._collect_rejected(patients_rejected, source="patients.csv")
                + self._collect_rejected(admissions_rejected, source="admissions.csv")
                + self._build_orphan_rejections(orphan_admissions)
            )
            self._writer.write_rejected(rejected, run_id)

            stats = {
                "records_processed": len(patients_records) + len(admissions_records),
                "records_rejected": len(rejected),
                "images_processed": 0,  # imagenes las maneja el bootstrap
            }
            self._writer.finish_pipeline_run(run_id, status="success", stats=stats)

            logger.info(
                "Pipeline run %s finished: %d processed, %d rejected (incl. %d orphan admissions)",
                run_id,
                stats["records_processed"],
                stats["records_rejected"],
                len(orphan_admissions),
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
                # Best-effort: try to mark the run as failed. If MongoDB itself
                # is the cause of the failure, this will also raise, which we
                # log but swallow so the original exception propagates.
                try:
                    self._writer.finish_pipeline_run(
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
