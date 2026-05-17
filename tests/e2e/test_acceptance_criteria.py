"""End-to-end acceptance tests against the running stack.

Each test maps 1:1 to a criterio de aceptacion (CA-1..CA-8) defined in
`specs/pipeline-datos.md`. Together they verify that the implemented system
fulfils the spec.

These tests assume the full stack is up (`docker compose up`). They are
self-skipping when a backend service is unreachable.

Polyglot persistence (ADR-004): pipeline_runs + data_quality_summary live
in SQLite and are consulted via the API. MongoDB owns patients, admissions
embedded and rejected_records. MinIO owns the radiography binaries.
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
    # pipeline_run_id is a soft cross-DB reference to SQLite (string UUID)
    pipeline_run_id = sample.get("pipeline_run_id")
    assert pipeline_run_id, "Falta el pipeline_run_id (auditoria)"
    assert isinstance(pipeline_run_id, str), (
        f"pipeline_run_id debe ser string UUID, es {type(pipeline_run_id).__name__}"
    )

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


def test_orphans_appear_in_both_rejected_and_quality_summary(
    mongo_db, http, api_url
):
    """Cobertura cruzada del bug fix de admissions huerfanos:
       - rejected_records (Mongo) tiene >0 filas con motivo orphan
       - data_quality_summary (SQL, via API) cuenta rejected >= n_orphans
         en la dimension admissions, restringido al MISMO run_id
       - coherencia: huerfanos del run <= rejected en admissions del summary
         de ese mismo run.

    No usamos `latest_quality_summary` porque puede apuntar a runs
    posteriores al bootstrap (los tests de CA-6 reejecutan el orchestrator
    sobre los mismos CSV → re-runs sin huerfanos nuevos). En su lugar
    buscamos por history cualquier run cuyo summary admissions tenga
    rejected > 0, y cruzamos contra rejected_records por su pipeline_run_id.
    """
    history_resp = http.get(
        f"{api_url}/api/v1/pipeline/quality-summary/history",
        params={"dimension": "admissions", "limit": 100},
    )
    assert history_resp.status_code == 200
    runs_with_rejected = [
        row for row in history_resp.json()["items"]
        if row["rejected"] > 0
    ]
    assert runs_with_rejected, (
        "Esperaba al menos un run con rejected>0 en admissions en el "
        "history (el bootstrap deberia haber generado uno)"
    )

    # Tomamos cualquiera de esos runs; el de bootstrap garantiza huerfanos
    target = runs_with_rejected[0]
    run_id = target["pipeline_run_id"]

    n_orphans = mongo_db.rejected_records.count_documents({
        "rejection_reason": "orphan patient_external_id",
        "pipeline_run_id": run_id,
    })
    assert n_orphans > 0, (
        f"Esperaba huerfanos en rejected_records para run {run_id}"
    )

    assert target["rejected"] >= n_orphans, (
        f"data_quality_summary.admissions.rejected ({target['rejected']}) "
        f"deberia incluir los {n_orphans} huerfanos de rejected_records "
        f"para el mismo run {run_id}"
    )


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


def test_ca5_api_serves_quality_summary(http, api_url):
    """SQLite-backed dashboard endpoint (ADR-004)."""
    r = http.get(f"{api_url}/api/v1/pipeline/quality-summary")
    assert r.status_code == 200
    data = r.json()
    items = data["items"]
    # After bootstrap there must be at least one snapshot
    assert len(items) > 0, "Esperaba al menos una entrada en quality-summary"
    dimensions = {row["dimension"] for row in items}
    assert "patients" in dimensions
    assert "admissions" in dimensions


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
    from src.pipeline.storage.sql_writer import get_sql_writer_from_env

    fixtures_dir = Path("/app/data/raw")
    if not fixtures_dir.exists():
        fixtures_dir = Path(__file__).resolve().parents[2] / "data" / "raw"
    patients_csv = fixtures_dir / "patients.csv"
    admissions_csv = fixtures_dir / "admissions.csv"
    if not patients_csv.exists():
        pytest.skip("Fixtures no disponibles en este entorno")

    mongo_writer = get_mongo_writer_from_env()
    sql_writer = get_sql_writer_from_env()
    initial_patients = mongo_db.patients.count_documents({})

    orchestrator = PipelineOrchestrator(
        spark=spark_session,
        mongo_writer=mongo_writer,
        sql_writer=sql_writer,
    )
    orchestrator.run_from_files(
        patients_csv=patients_csv,
        admissions_csv=admissions_csv,
        trigger_type="e2e-test",
    )

    final_patients = mongo_db.patients.count_documents({})
    mongo_writer.close()
    sql_writer.close()

    assert final_patients == initial_patients, (
        f"Pipeline no idempotente: paso de {initial_patients} a {final_patients} patients"
    )


# ---------------------------------------------------------------------------
# CA-7 (RNF-1): "Todo el pipeline arranca con `docker-compose up`"
# ---------------------------------------------------------------------------

def test_ca7_system_is_up_and_serving(http, api_url, mongo_db, minio_client):
    """Verifica los 4 servicios criticos del sistema en una sola pasada."""
    r = http.get(f"{api_url}/api/v1/health")
    assert r.status_code == 200, "API no responde a /health"

    assert mongo_db.patients.count_documents({}) > 0, "MongoDB sin datos tras docker compose up"

    assert minio_client.bucket_exists("radiographies"), "Bucket radiographies no existe"

    # pipeline_runs ahora viven en SQLite, accesibles via la API
    runs_response = http.get(f"{api_url}/api/v1/pipeline/runs?limit=1")
    assert runs_response.status_code == 200
    assert runs_response.json()["total"] > 0, (
        "Esperaba al menos un pipeline_run registrado en SQLite tras el bootstrap"
    )


# ---------------------------------------------------------------------------
# CA-8 (RNF-4, CB-5): "Si MinIO o MongoDB no estan disponibles, el pipeline
#                     loguea el error y no crashea silenciosamente"
# ---------------------------------------------------------------------------

def test_ca8_orchestrator_raises_explicit_error_on_unreachable_mongo(
    spark_session, tmp_path, monkeypatch
):
    """El orchestrator debe levantar un error explicito (no fallar en silencio)
    cuando MongoDB no esta disponible al iniciar el run.

    Verifica ademas que el run queda registrado en SQLite como `failed` con
    error_message — la auditoria del pipeline NUNCA debe perderse, ni cuando
    Mongo cae.
    """
    from pymongo.errors import ConnectionFailure
    from sqlalchemy import text

    from src.pipeline.storage.mongo_writer import get_mongo_writer_from_env
    from src.pipeline.storage.sql_engine import (
        create_all_tables,
        get_sql_engine_from_env,
    )
    from src.pipeline.storage.sql_writer import SqlWriter
    from src.pipeline.orchestrator import PipelineOrchestrator

    # Use an isolated SQLite file so the bad mongo doesn't pollute prod state
    sqlite_path = tmp_path / "isolated.db"
    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    engine = get_sql_engine_from_env()
    create_all_tables(engine)
    sql_writer = SqlWriter(engine)

    # Real writer pointing at the real Mongo, but with bulk_upsert patched to
    # simulate a connection failure mid-run. This is deterministic and faster
    # than relying on DNS/TCP timeouts of a fake host.
    mongo_writer = get_mongo_writer_from_env()

    def _boom(*_args, **_kwargs):
        raise ConnectionFailure("simulated: MongoDB unreachable")

    monkeypatch.setattr(
        mongo_writer, "bulk_upsert_patients_with_admissions", _boom
    )

    fake_csv = tmp_path / "patients.csv"
    fake_csv.write_text(
        "external_id,name,birth_date,gender,blood_type\n"
        "HOSP-000001,Ana,1990-01-01,F,A+\n"
    )
    fake_admissions = tmp_path / "admissions.csv"
    fake_admissions.write_text(
        "patient_external_id,admission_date,discharge_date,department,"
        "diagnosis_code,diagnosis_description,status\n"
        "HOSP-000001,2025-03-10,,UCI,J18.9,Pneumonia,admitted\n"
    )

    orchestrator = PipelineOrchestrator(
        spark=spark_session,
        mongo_writer=mongo_writer,
        sql_writer=sql_writer,
    )

    # El run debe levantar una excepcion explicita; lo importante es que NO
    # devuelva success silenciosamente cuando MongoDB no esta disponible.
    with pytest.raises(ConnectionFailure):
        orchestrator.run_from_files(
            patients_csv=fake_csv,
            admissions_csv=fake_admissions,
        )

    # Y el run queda registrado como failed con error_message
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT status, error_message FROM pipeline_runs WHERE status='failed'"
        )).all()
    assert len(rows) >= 1
    assert rows[-1].error_message and "MongoDB unreachable" in rows[-1].error_message

    mongo_writer.close()
    sql_writer.close()


def test_ca8_failed_runs_are_recorded_with_error_message(http, api_url):
    """Si hay runs registrados con status='failed', deben llevar error_message.

    Run history vive en SQLite (ADR-004), consultado via la API.
    """
    r = http.get(f"{api_url}/api/v1/pipeline/runs?limit=500")
    assert r.status_code == 200
    runs = r.json()["items"]
    failed = [run for run in runs if run["status"] == "failed"]
    # No hay garantia de que haya runs fallidos en un sistema sano, pero si los
    # hay, deben estar bien formados (auditoria visible).
    for run in failed:
        assert run.get("error_message"), (
            f"Run fallido sin error_message: {run['id']}"
        )
