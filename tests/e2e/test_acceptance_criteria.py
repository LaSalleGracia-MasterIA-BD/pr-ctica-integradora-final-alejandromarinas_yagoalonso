"""End-to-end acceptance tests against the running stack.

Each test maps 1:1 to a criterio de aceptacion (CA-1..CA-8) defined in
`specs/pipeline-datos.md`. Together they verify that the implemented system
fulfils the spec.

These tests assume the full stack is up (`docker compose up`). They are
self-skipping when a backend service is unreachable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# CA-1 (RF-1): "Al colocar un CSV en el directorio de entrada, el pipeline
#              lo procesa y los datos aparecen en MongoDB"
# ---------------------------------------------------------------------------

def test_ca1_pipeline_processed_csvs_into_mongodb(mongo_db):
    """Tras `docker compose up`, los CSVs de fixtures deben estar en MongoDB."""
    n_patients = mongo_db.patients.count_documents({})
    assert n_patients > 0, "El pipeline deberia haber procesado patients.csv"
    assert n_patients > 4000, f"Se esperaban ~4.745 patients, hay {n_patients}"

    sample = mongo_db.patients.find_one({"external_id": "HOSP-000000"})
    assert sample is not None, "El paciente HOSP-000000 deberia existir"
    assert sample.get("name"), "El paciente deberia tener nombre"


# ---------------------------------------------------------------------------
# CA-2 (RF-2): "Al colocar imagenes PNG en el directorio de entrada, se
#              almacenan en MinIO con sus metadatos"
# ---------------------------------------------------------------------------

def test_ca2_radiographies_uploaded_to_minio_with_correct_keys(minio_client):
    keys = [obj.object_name for obj in minio_client.list_objects("radiographies", recursive=True)]
    assert len(keys) >= 17, f"Esperaba >=17 radiografias, hay {len(keys)}"

    for key in keys:
        assert "/" in key, f"Object key debe ser {{patient_id}}/{{filename}}, es: {key}"
        patient_part, filename = key.rsplit("/", 1)
        assert patient_part.startswith("HOSP-"), f"Prefix invalido: {patient_part}"
        assert filename.endswith(".png"), f"Filename no es PNG: {filename}"


# ---------------------------------------------------------------------------
# CA-3 (RF-3, CB-1, CB-3): "Registros con valores nulos en campos
#                           obligatorios se marcan como rechazados con
#                           motivo, no rompen el pipeline"
# ---------------------------------------------------------------------------

def test_ca3_invalid_records_in_rejected_collection_with_reason(mongo_db):
    n_rejected = mongo_db.rejected_records.count_documents({})
    assert n_rejected > 0, "Los datos sinteticos deberian generar rechazos"

    sample = mongo_db.rejected_records.find_one({})
    assert sample is not None
    assert sample.get("rejection_reason"), "rejection_reason ausente o vacio"
    assert sample.get("pipeline_run_id"), "Falta el pipeline_run_id (auditoria)"

    reasons = {
        d["rejection_reason"]
        for d in mongo_db.rejected_records.find({}, {"rejection_reason": 1})
    }
    assert len(reasons) >= 2, f"Esperaba multiples motivos de rechazo, encontrados: {reasons}"


def test_ca3_orphan_admissions_persisted_as_rejected(mongo_db):
    """T3 inyecta ~5% de admissions con patient_external_id huerfano.
    Esos NO deben evaporarse: deben quedar en rejected_records con motivo claro."""
    orphans = list(mongo_db.rejected_records.find(
        {"rejection_reason": "orphan patient_external_id"}
    ).limit(5))
    assert len(orphans) > 0, (
        "Los admissions huerfanos del dataset sintetico deberian aparecer "
        "en rejected_records con motivo 'orphan patient_external_id'"
    )
    sample = orphans[0]
    assert sample["source_file"] == "admissions.csv"
    assert sample["raw_data"]["patient_external_id"], "Falta el patient_external_id en raw_data"


# ---------------------------------------------------------------------------
# CA-4 (RF-4): "Los datos en MongoDB estan normalizados y enriquecidos
#              (ej: edad calculada, categorias estandarizadas)"
# ---------------------------------------------------------------------------

def test_ca4_patients_are_enriched_with_age(mongo_db):
    p = mongo_db.patients.find_one({"age": {"$exists": True, "$ne": None}})
    assert p is not None, "Algun paciente deberia tener `age` calculada"
    assert isinstance(p["age"], int) and 0 < p["age"] < 130, f"Edad fuera de rango: {p['age']}"


def test_ca4_admissions_are_enriched_with_diagnosis_category(mongo_db):
    p = mongo_db.patients.find_one({"admissions.diagnosis_category": {"$exists": True}})
    assert p is not None, "Algun paciente deberia tener admissions con categoria"
    valid = {"COVID-19", "Pneumonia", "Other", "Unknown"}
    for adm in p["admissions"]:
        if "diagnosis_category" in adm:
            assert adm["diagnosis_category"] in valid, f"Categoria invalida: {adm['diagnosis_category']}"


# ---------------------------------------------------------------------------
# CA-5 (RF-5, RF-6): "Los datos procesados son consultables via endpoint
#                    GET de la API"
# ---------------------------------------------------------------------------

def test_ca5_api_serves_patients(http, api_url):
    r = http.get(f"{api_url}/api/v1/patients?limit=3")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] > 0
    assert len(data["items"]) > 0


def test_ca5_api_serves_admissions(http, api_url):
    r = http.get(f"{api_url}/api/v1/admissions?limit=3")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] > 0


def test_ca5_api_serves_pipeline_status(http, api_url):
    r = http.get(f"{api_url}/api/v1/pipeline/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in {"running", "success", "failed"}


def test_ca5_api_health_endpoint(http, api_url):
    r = http.get(f"{api_url}/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# CA-6 (RF-7, CB-4): "Ejecutar el pipeline dos veces con los mismos datos
#                    no genera duplicados"
# ---------------------------------------------------------------------------

def test_ca6_no_duplicate_patients_by_external_id(mongo_db):
    """Invariante: cada external_id aparece en MongoDB exactamente una vez."""
    duplicates = list(mongo_db.patients.aggregate([
        {"$group": {"_id": "$external_id", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
    ]))
    assert duplicates == [], f"Hay external_ids duplicados: {duplicates}"


def test_ca6_orchestrator_run_twice_keeps_counts_stable(spark_session, mongo_db):
    """Ejecutar el orchestrator dos veces con los mismos CSVs no aumenta los conteos."""
    from src.pipeline.orchestrator import PipelineOrchestrator
    from src.pipeline.storage.mongo_writer import get_mongo_writer_from_env

    fixtures_dir = Path("/app/data/raw")
    if not fixtures_dir.exists():
        fixtures_dir = Path(__file__).resolve().parents[2] / "data" / "raw"
    patients_csv = fixtures_dir / "patients.csv"
    admissions_csv = fixtures_dir / "admissions.csv"
    if not patients_csv.exists():
        pytest.skip("Fixtures no disponibles en este entorno")

    writer = get_mongo_writer_from_env()
    initial_patients = mongo_db.patients.count_documents({})

    orchestrator = PipelineOrchestrator(spark=spark_session, mongo_writer=writer)
    orchestrator.run_from_files(
        patients_csv=patients_csv,
        admissions_csv=admissions_csv,
        trigger_type="e2e-test",
    )

    final_patients = mongo_db.patients.count_documents({})
    writer.close()

    assert final_patients == initial_patients, (
        f"Pipeline no idempotente: paso de {initial_patients} a {final_patients} patients"
    )


# ---------------------------------------------------------------------------
# CA-7 (RNF-1): "Todo el pipeline arranca con `docker-compose up`"
# ---------------------------------------------------------------------------

def test_ca7_system_is_up_and_serving(http, api_url, mongo_db, minio_client):
    """Verifica los 3 servicios criticos del sistema en una sola pasada."""
    r = http.get(f"{api_url}/api/v1/health")
    assert r.status_code == 200, "API no responde a /health"

    assert mongo_db.patients.count_documents({}) > 0, "MongoDB sin datos tras docker compose up"

    assert minio_client.bucket_exists("radiographies"), "Bucket radiographies no existe"

    runs_count = mongo_db.pipeline_runs.count_documents({})
    assert runs_count > 0, "Esperaba al menos un pipeline_run registrado tras el bootstrap"


# ---------------------------------------------------------------------------
# CA-8 (RNF-4, CB-5): "Si MinIO o MongoDB no estan disponibles, el pipeline
#                     loguea el error y no crashea silenciosamente"
# ---------------------------------------------------------------------------

def test_ca8_orchestrator_raises_explicit_error_on_unreachable_mongo(
    spark_session, tmp_path
):
    """El orchestrator debe levantar un error explicito (no fallar en silencio)
    cuando MongoDB no esta disponible al iniciar el run."""
    from pymongo import MongoClient
    from src.pipeline.storage.mongo_writer import MongoWriter
    from src.pipeline.orchestrator import PipelineOrchestrator

    # Build a writer pointing at an unreachable host with a SHORT timeout
    # so the test does not hang for 30s waiting for a connection.
    bad_writer = MongoWriter.__new__(MongoWriter)
    bad_writer._client = MongoClient(
        host="nonexistent.invalid",
        port=27017,
        serverSelectionTimeoutMS=1000,
        connectTimeoutMS=1000,
    )
    bad_writer.db = bad_writer._client["ignored"]

    fake_csv = tmp_path / "patients.csv"
    fake_csv.write_text("external_id,name,birth_date,gender,blood_type\n")
    fake_admissions = tmp_path / "admissions.csv"
    fake_admissions.write_text(
        "patient_external_id,admission_date,discharge_date,department,"
        "diagnosis_code,diagnosis_description,status\n"
    )

    orchestrator = PipelineOrchestrator(spark=spark_session, mongo_writer=bad_writer)

    # El run debe levantar una excepcion explicita; lo importante es que NO
    # devuelva success silenciosamente cuando MongoDB no esta disponible.
    with pytest.raises(Exception):
        orchestrator.run_from_files(
            patients_csv=fake_csv,
            admissions_csv=fake_admissions,
        )
    bad_writer.close()


def test_ca8_failed_runs_are_recorded_with_error_message(mongo_db):
    """Si hay runs registrados con status='failed', deben llevar error_message."""
    failed = list(mongo_db.pipeline_runs.find({"status": "failed"}))
    # No hay garantia de que haya runs fallidos en un sistema sano, pero si los
    # hay, deben estar bien formados (auditoria visible).
    for run in failed:
        assert run.get("error_message"), (
            f"Run fallido sin error_message: {run['_id']}"
        )
