"""Pegamento entre el router de FastAPI y el orquestador ETL real.

El handler HTTP `POST /api/v1/pipeline/trigger` debe responder rapido (con
el id del nuevo run) pero el trabajo pesado de PySpark debe ocurrir en
algun sitio. Este launcher lo divide en dos partes:

  * `start_run(trigger_type)` — sincrono: crea la fila en `pipeline_runs`
    en SQLite para que la API pueda devolver el id del run (string UUID)
    inmediatamente
  * `execute(run_id, patients_csv, admissions_csv)` — long-running: ejecuta
    el orquestador con una SparkSession + writers nuevos, reutilizando el
    id del run para que el historial sea consistente

Persistencia poliglota (ADR-004): el ciclo de vida del run (start/finish +
quality summary) vive en SQLite, mientras que los registros rechazados y
los documentos de pacientes/ingresos viven en MongoDB. El launcher crea
ambos writers en cada llamada.

`execute` esta pensado para programarse con `BackgroundTasks` de FastAPI.
Captura excepciones y solo logea — el orquestador ya ha marcado el run
como fallido en SQLite, asi que relanzar solo generaria ruido en uvicorn
sin cambiar el estado.
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
            # Sin re-raise: el run ya queda marcado como fallido en SQLite
            # por el orquestador. Relanzar en un BackgroundTask solo
            # generaria un traceback ruidoso en uvicorn sin cambiar el estado.
        finally:
            mongo_writer.close()
            sql_writer.close()
            # No paramos Spark a proposito — getOrCreate reutiliza la
            # sesion para triggers posteriores dentro del mismo proceso de API.
