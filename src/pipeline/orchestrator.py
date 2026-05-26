"""Coordina el run ETL end-to-end sobre un par de CSVs de entrada.

El orquestador conecta los ingesters, processors y la capa de storage en
un unico run de pipeline atomico. Cada llamada:

  1. Abre una fila `pipeline_run` en SQLite (status=running) via `SqlWriter`
  2. Ingesta los CSVs de pacientes e ingresos en DataFrames de PySpark
  3. Valida las filas, separando validas de rechazadas
  4. Limpia y transforma las filas validas (age, diagnosis_category)
  5. Validacion cross-entity: los ingresos cuyo paciente no existe en
     este batch van a rechazados con motivo `orphan patient_external_id`
  6. Escribe los pacientes enriquecidos con sus ingresos embebidos a MongoDB
  7. Persiste las filas rechazadas en MongoDB con su motivo (referencia
     blanda cross-DB: `pipeline_run_id` es el UUID de SQLite como string)
  8. Construye una fila `data_quality_summary` por dimension y la persiste
     en SQLite via `SqlWriter`
  9. Cierra el run con status=success/failed y stats agregadas en SQLite

Persistencia poliglota (ADR-004):
  - SQLite: pipeline_runs + data_quality_summary
  - MongoDB: patients/admissions/radiographies/rejected_records
  - MinIO: binarios PNG (los gestiona el bootstrap/watcher, no aqui)

Los fallos en cualquier etapa marcan el run como failed (CB-5) antes de
relanzar, asi que el historial siempre refleja lo que ocurrio.
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
    run_id: str  # string UUID de SQLite
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
        """Ejecuta el ETL completo sobre los CSVs dados.

        Si se proporciona `run_id`, se reutiliza (lo usa el launcher de la API
        que arranca el run sincronicamente para devolver su id, y luego
        programa la ejecucion como BackgroundTask). Si no, se arranca un run nuevo.

        Los errores en CUALQUIER etapa — incluyendo la llamada inicial
        `start_pipeline_run` — se logean y, cuando es posible, se registran
        como run `failed` antes de relanzar. Nunca se silencian excepciones (CB-5).
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

            # Validacion cross-entity: descartar ingresos cuyo paciente no
            # existe en este batch. El validador por fila no puede hacerlo
            # porque carece de acceso al dataframe de pacientes.
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
            # Referencia blanda cross-DB: pipeline_run_id es el UUID de SQLite
            # almacenado en MongoDB como string. Ver ADR-004.
            self._mongo.write_rejected(rejected, run_id)

            # Persistir el quality summary agregado en SQLite (para el dashboard)
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
                # Best-effort: intentar marcar el run como failed en SQLite.
                # Si SQLite es la causa del fallo, logear y dejar que la
                # excepcion original se propague.
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
        """Divide los ingresos en (validos, huerfanos) segun si su
        `patient_external_id` existe en el batch de pacientes.

        Los huerfanos son ingresos que pasan el validador por fila pero
        referencian a un paciente que no existe en el dataset de pacientes
        de este run. Sin este chequeo desaparecerian silenciosamente en
        el paso de embedding.
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
