"""Bring the hospital stack to a ready-to-use state.

Runs automatically at `docker compose up` via the pipeline service. It does
the work needed to turn a fresh set of containers into a demo-ready system:

  1. Verify that synthetic fixtures are present on disk (committed to the repo)
  2. Sync local radiographies into the MinIO `radiographies` bucket
  3. Run the full ETL pipeline (PySpark) if MongoDB has no patients yet,
     so the API has data to serve right away
  4. Persist radiography metadata in MongoDB (embedded in patients) so
     `GET /api/v1/radiographies` returns real data, not just bytes in MinIO
  5. Smoke-check connectivity with MongoDB

All steps are idempotent: re-running the stack only does work that is
actually needed, so warm restarts are fast.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.ingesters.image_ingester import (
    ImageIngester,
    IngestedImage,
)
from src.pipeline.logging_config import get_logger
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.spark_session import get_spark_session
from src.pipeline.storage.minio_client import get_minio_client_from_env
from src.pipeline.storage.mongo_writer import get_mongo_writer_from_env
from src.pipeline.storage.sql_engine import (
    create_all_tables,
    get_sql_engine_from_env,
)
from src.pipeline.storage.sql_writer import SqlWriter

logger = get_logger(__name__)

DATA_DIR = Path("/app/data/raw")
IMAGES_BUCKET = "radiographies"


def main() -> None:
    logger.info("=== Hospital pipeline bootstrap ===")

    patients_csv = DATA_DIR / "patients.csv"
    admissions_csv = DATA_DIR / "admissions.csv"
    images_dir = DATA_DIR / "images"

    for required in (patients_csv, admissions_csv, images_dir):
        if not required.exists():
            raise SystemExit(
                f"Missing fixture: {required}. The repository must ship "
                f"data/raw/ with the synthetic dataset."
            )

    logger.info(
        "Fixtures detected: %s (%d bytes), %s (%d bytes), %s (%d images)",
        patients_csv.name,
        patients_csv.stat().st_size,
        admissions_csv.name,
        admissions_csv.stat().st_size,
        images_dir,
        sum(1 for _ in images_dir.iterdir()),
    )

    # Polyglot persistence (ADR-004): SQLite owns pipeline_runs +
    # data_quality_summary. Bootstrap is the single owner of the DDL —
    # everything downstream assumes the schema already exists.
    _init_sql_schema()

    images_metadata = _sync_radiographies(images_dir)
    _run_etl_if_empty(patients_csv, admissions_csv)
    _persist_radiography_metadata(images_metadata)
    # Feature 4 (dashboard) T17: pre-cargar 1 radiografia de demo
    # `HOSP-DEMO-001` para que la vista Clasificador del dashboard tenga
    # al menos una imagen >= 32 px clasificable out-of-the-box (las 17
    # dummy del bootstrap son 1x1 y la API las rechaza con 422).
    # Origen/licencia: imagen sintetica generada con numpy. Ver
    # data/raw/images-demo/README.md
    _seed_demo_radiograph()
    # Si el dataset real del COVID-19 Radiography Database esta descargado
    # localmente, registrar 6 imagenes reales (2 por clase) como
    # HOSP-PRES-001..006 para que la demo del Clasificador tenga
    # radiografias reales clasificables. Si NO esta descargado: skip
    # silencioso. Las imagenes NO se commitean — solo se copian en
    # runtime si el dataset existe en el host. Ver
    # docs/runbooks/use-real-radiograph-for-demo.md
    _seed_presentation_radiographs()

    mongo = get_mongo_writer_from_env()
    try:
        mongo.ping()
        logger.info("MongoDB connection OK (db=%s)", mongo.db.name)
    finally:
        mongo.close()

    logger.info("=== Bootstrap complete. System is ready. ===")


def _init_sql_schema() -> None:
    """Create SQLite tables if they do not exist. Idempotent."""
    engine = get_sql_engine_from_env()
    try:
        create_all_tables(engine)
        logger.info("SQLite schema ready (pipeline_runs, data_quality_summary)")
    finally:
        engine.dispose()


def _sync_radiographies(images_dir: Path) -> list[IngestedImage]:
    """Sync local PNGs to MinIO and return metadata for ALL local images.

    Object keys are deterministic (`{patient_id}/{filename}`) so re-uploading
    the same file is a no-op in terms of MinIO state. We skip the upload when
    the key is already present, but still build the metadata record so the
    caller can persist it in MongoDB if needed.
    """
    minio = get_minio_client_from_env()
    minio.ensure_bucket(IMAGES_BUCKET)

    local_pngs = sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".png"
    )
    already_synced = {
        key.rsplit("/", 1)[-1]
        for key in minio.list_objects(IMAGES_BUCKET)
    }

    ingester = ImageIngester(minio_client=minio, bucket=IMAGES_BUCKET)
    all_metadata: list[IngestedImage] = []
    uploaded = 0
    skipped = 0
    for image_path in local_pngs:
        # ingest_file always re-validates and produces metadata; if the key
        # is already in MinIO we can technically skip the network upload, but
        # since `ingest_file` is idempotent (overwrite-on-same-key) and the
        # dataset is small, calling it unconditionally is the simpler invariant.
        meta = ingester.ingest_file(image_path)
        if meta is None:
            continue
        all_metadata.append(meta)
        if image_path.name in already_synced:
            skipped += 1
        else:
            uploaded += 1

    logger.info(
        "Radiographies in MinIO bucket '%s': %d total (%d uploaded now, %d already there)",
        IMAGES_BUCKET,
        len(all_metadata),
        uploaded,
        skipped,
    )
    return all_metadata


def _run_etl_if_empty(patients_csv: Path, admissions_csv: Path) -> None:
    """Populate MongoDB by running the full ETL on the bundled CSVs.

    Skipped when MongoDB already has patients — keeps warm restarts fast and
    respects the idempotency contract of the rest of the pipeline.
    """
    writer = get_mongo_writer_from_env()
    try:
        existing = writer.db.patients.count_documents({}, limit=1)
        if existing > 0:
            logger.info("MongoDB already has patients — skipping ETL run")
            return
    finally:
        writer.close()

    logger.info("MongoDB is empty, running full ETL on bundled fixtures...")
    spark = get_spark_session(app_name="hospital-bootstrap-etl", master="local[*]")
    mongo_writer = get_mongo_writer_from_env()
    sql_engine = get_sql_engine_from_env()
    sql_writer = SqlWriter(sql_engine)
    try:
        orchestrator = PipelineOrchestrator(
            spark=spark,
            mongo_writer=mongo_writer,
            sql_writer=sql_writer,
        )
        result = orchestrator.run_from_files(
            patients_csv=patients_csv,
            admissions_csv=admissions_csv,
            trigger_type="bootstrap",
        )
        logger.info(
            "ETL bootstrap complete: %d processed, %d rejected (run %s)",
            result.records_processed,
            result.records_rejected,
            result.run_id,
        )
    finally:
        mongo_writer.close()
        sql_writer.close()
        spark.stop()


def _persist_radiography_metadata(images: list[IngestedImage]) -> None:
    """Embed each radiography metadata into its patient's document.

    `add_radiography_to_patient` is idempotent (uses $ne on minio_object_key),
    so running this twice does NOT create duplicates — fulfils CB-4/CA-6 for
    the radiography branch of the pipeline.
    """
    if not images:
        return

    writer = get_mongo_writer_from_env()
    try:
        attached = 0
        orphans = 0
        for img in images:
            metadata = {
                "minio_object_key": img.minio_object_key,
                "original_filename": img.original_filename,
                "file_size_bytes": img.file_size_bytes,
                "ingested_at": img.ingested_at,
                "classification": None,  # populated when the ML model runs
            }
            if writer.add_radiography_to_patient(img.patient_external_id, metadata):
                attached += 1
            else:
                orphans += 1
                logger.warning(
                    "Patient %s not found, radiography %s not persisted in MongoDB",
                    img.patient_external_id,
                    img.original_filename,
                )
        logger.info(
            "Radiography metadata in MongoDB: %d attached to patients, %d orphans",
            attached,
            orphans,
        )
    finally:
        writer.close()


DEMO_PATIENT_ID = "HOSP-DEMO-001"
DEMO_RADIOGRAPHY_KEY = "HOSP-DEMO-001/HOSP-DEMO-001_xray1.png"


def _generate_demo_radiograph_bytes(seed: int = 42) -> bytes:
    """Generate a synthetic 256x256 grayscale PNG.

    Soft vertical gradient + gaussian noise + two darker ellipses that
    vaguely suggest lungs. NOT a real radiograph — purely there so the
    Classifier view of the dashboard has at least one image of >=32 px
    available out-of-the-box. See `data/raw/images-demo/README.md`.
    """
    import io

    import numpy as np
    from PIL import Image, ImageDraw

    rng = np.random.default_rng(seed)
    size = 256
    # Vertical gradient (darker top, lighter bottom): mimics typical X-ray exposure
    gradient = np.tile(np.linspace(60, 200, size, dtype=np.float32), (size, 1)).T
    # Gaussian noise to look "filmic" rather than flat
    noise = rng.normal(0.0, 12.0, size=(size, size)).astype(np.float32)
    arr = np.clip(gradient + noise, 0, 255).astype(np.uint8)

    img = Image.fromarray(arr, mode="L")
    # Two darker ellipses that suggest lungs (decorative, no clinical value)
    draw = ImageDraw.Draw(img)
    draw.ellipse((40, 70, 110, 200), fill=80)
    draw.ellipse((146, 70, 216, 200), fill=80)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _seed_demo_radiograph() -> None:
    """Upload the demo PNG to MinIO + register the demo patient in MongoDB.

    Idempotent: re-runs upload (MinIO overwrites by key) and use
    `add_radiography_to_patient` which is also idempotent on
    `minio_object_key`.
    """
    minio = get_minio_client_from_env()
    minio.ensure_bucket(IMAGES_BUCKET)
    png_bytes = _generate_demo_radiograph_bytes(seed=42)
    minio.upload_bytes(
        IMAGES_BUCKET, DEMO_RADIOGRAPHY_KEY, png_bytes, content_type="image/png",
    )
    logger.info(
        "Demo radiograph synthesised + uploaded to %s/%s (%d bytes)",
        IMAGES_BUCKET, DEMO_RADIOGRAPHY_KEY, len(png_bytes),
    )

    writer = get_mongo_writer_from_env()
    try:
        # Ensure the demo patient exists
        writer.bulk_upsert_patients([
            {
                "external_id": DEMO_PATIENT_ID,
                "name": "Demo Dashboard",
                "birth_date": "1980-01-01",
                "age": 45,
                "gender": "F",
                "blood_type": "A+",
            }
        ])
        # Attach the radiograph (idempotent)
        writer.add_radiography_to_patient(
            DEMO_PATIENT_ID,
            {
                "minio_object_key": DEMO_RADIOGRAPHY_KEY,
                "original_filename": "HOSP-DEMO-001_xray1.png",
                "file_size_bytes": len(png_bytes),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "classification": None,
            },
        )
        logger.info(
            "Demo patient %s registered with radiography %s",
            DEMO_PATIENT_ID, DEMO_RADIOGRAPHY_KEY,
        )
    finally:
        writer.close()


# ----------------------------------------------------------------------
# Feature 4 — radiografias reales de demo (HOSP-PRES-*)
# ----------------------------------------------------------------------

KAGGLE_DATASET_ROOT = Path(
    "/app/data/raw/covid_radiography/COVID-19_Radiography_Dataset"
)

# 6 imagenes, 2 por clase. La key codifica el paciente; la "true class"
# vive en el comentario y en el nombre del fichero. NO usamos
# HOSP-DEMO-* (reservado para sinteticas).
PRESENTATION_IMAGES: list[tuple[str, str, str]] = [
    # (patient_external_id, raw_filename, true_class — solo informativo)
    ("HOSP-PRES-001", "COVID/images/COVID-1.png",            "COVID-19"),
    ("HOSP-PRES-002", "COVID/images/COVID-2.png",            "COVID-19"),
    ("HOSP-PRES-003", "Normal/images/Normal-1.png",          "Normal"),
    ("HOSP-PRES-004", "Normal/images/Normal-2.png",          "Normal"),
    ("HOSP-PRES-005", "Viral Pneumonia/images/Viral Pneumonia-1.png", "Pneumonia"),
    ("HOSP-PRES-006", "Viral Pneumonia/images/Viral Pneumonia-2.png", "Pneumonia"),
]


def _seed_presentation_radiographs() -> None:
    """Idempotent: solo se ejecuta si el dataset esta descargado."""
    if not KAGGLE_DATASET_ROOT.exists():
        logger.info(
            "Presentation radiographs: dataset NO descargado en %s. "
            "Skip. Para demo con imagenes reales, ver "
            "docs/runbooks/use-real-radiograph-for-demo.md",
            KAGGLE_DATASET_ROOT,
        )
        return

    minio = get_minio_client_from_env()
    minio.ensure_bucket(IMAGES_BUCKET)
    writer = get_mongo_writer_from_env()
    try:
        uploaded = 0
        skipped = 0
        for patient_id, raw_path, true_class in PRESENTATION_IMAGES:
            src = KAGGLE_DATASET_ROOT / raw_path
            if not src.exists():
                logger.warning(
                    "Presentation image missing on disk: %s. Skip", src,
                )
                skipped += 1
                continue
            object_key = f"{patient_id}/{src.name}"
            minio.upload_file(IMAGES_BUCKET, object_key, src)
            writer.bulk_upsert_patients([{
                "external_id": patient_id,
                "name": f"Demo Presentacion ({true_class})",
                "birth_date": "1980-01-01",
                "age": 45,
                "gender": "M",
                "blood_type": "A+",
            }])
            writer.add_radiography_to_patient(patient_id, {
                "minio_object_key": object_key,
                "original_filename": src.name,
                "file_size_bytes": src.stat().st_size,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "classification": None,
            })
            uploaded += 1
        logger.info(
            "Presentation radiographs: %d registradas (HOSP-PRES-*), %d skipped",
            uploaded, skipped,
        )
    finally:
        writer.close()


if __name__ == "__main__":
    main()
