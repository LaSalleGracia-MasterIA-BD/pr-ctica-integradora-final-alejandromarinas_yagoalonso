"""Integration tests for MongoWriter against the running MongoDB service."""
from __future__ import annotations

import os

import pytest

from src.pipeline.storage.mongo_writer import MongoWriter, get_mongo_writer_from_env


TEST_DB_NAME = "hospital_test_t4"


@pytest.fixture
def writer():
    w = MongoWriter(
        host=os.environ["MONGO_HOST"],
        port=int(os.environ.get("MONGO_PORT", "27017")),
        db_name=TEST_DB_NAME,
    )
    _reset_db(w)
    yield w
    _reset_db(w)
    w.close()


def _reset_db(w: MongoWriter) -> None:
    w.db.patients.drop()
    w.db.rejected_records.drop()
    # Recrear el indice unico de `external_id` (en produccion lo crea
    # `docker/mongo-init/init-db.js` para la BD `hospital`; las BDs de
    # tests no pasan por ese script, asi que lo creamos aqui para
    # reproducir la condicion de produccion — necesario para que
    # `insert_patient` lance DuplicateKeyError ante colisiones).
    w.db.patients.create_index("external_id", unique=True)


def test_bulk_upsert_patients_inserts_new_documents(writer: MongoWriter):
    records = [
        {"external_id": "HOSP-000001", "name": "Ana", "age": 40},
        {"external_id": "HOSP-000002", "name": "Bob", "age": 55},
    ]
    stats = writer.bulk_upsert_patients(records)

    assert stats["upserted"] == 2
    assert writer.db.patients.count_documents({}) == 2


def test_bulk_upsert_patients_is_idempotent(writer: MongoWriter):
    records = [
        {"external_id": "HOSP-000001", "name": "Ana", "age": 40},
        {"external_id": "HOSP-000002", "name": "Bob", "age": 55},
    ]
    writer.bulk_upsert_patients(records)
    writer.bulk_upsert_patients(records)
    writer.bulk_upsert_patients(records)

    assert writer.db.patients.count_documents({}) == 2


def test_bulk_upsert_patients_updates_existing_fields(writer: MongoWriter):
    writer.bulk_upsert_patients([{"external_id": "HOSP-000001", "name": "Ana", "age": 40}])
    writer.bulk_upsert_patients([{"external_id": "HOSP-000001", "name": "Ana", "age": 41}])

    doc = writer.db.patients.find_one({"external_id": "HOSP-000001"})
    assert doc["age"] == 41


def test_add_radiography_to_patient_appends_to_array(writer: MongoWriter):
    writer.bulk_upsert_patients([{"external_id": "HOSP-000001", "name": "Ana"}])
    radiography = {"minio_object_key": "radios/HOSP-000001_1.png", "ingested_at": "2026-04-20"}

    added = writer.add_radiography_to_patient("HOSP-000001", radiography)
    assert added is True

    doc = writer.db.patients.find_one({"external_id": "HOSP-000001"})
    assert len(doc["radiographies"]) == 1
    assert doc["radiographies"][0]["minio_object_key"] == "radios/HOSP-000001_1.png"


def test_add_radiography_is_idempotent_on_repeated_calls(writer: MongoWriter):
    """CB-4: re-ingesting the same radiography must not create duplicates."""
    writer.bulk_upsert_patients([{"external_id": "HOSP-000001", "name": "Ana"}])
    radiography = {"minio_object_key": "radios/HOSP-000001_1.png", "ingested_at": "2026-04-20"}

    writer.add_radiography_to_patient("HOSP-000001", radiography)
    writer.add_radiography_to_patient("HOSP-000001", radiography)
    writer.add_radiography_to_patient("HOSP-000001", radiography)

    doc = writer.db.patients.find_one({"external_id": "HOSP-000001"})
    assert len(doc["radiographies"]) == 1


def test_add_radiography_returns_false_for_missing_patient(writer: MongoWriter):
    added = writer.add_radiography_to_patient(
        "HOSP-UNKNOWN",
        {"minio_object_key": "x", "ingested_at": "2026-04-20"},
    )
    assert added is False


def test_ping_returns_true_when_mongodb_is_reachable(writer: MongoWriter):
    assert writer.ping() is True


def test_bulk_upsert_patients_with_admissions_embeds_subdocs(writer: MongoWriter):
    patients = [
        {"external_id": "HOSP-000001", "name": "Ana", "age": 45},
        {"external_id": "HOSP-000002", "name": "Luis", "age": 50},
    ]
    admissions = [
        {"patient_external_id": "HOSP-000001", "admission_date": "2025-03-10",
         "department": "UCI", "status": "admitted"},
        {"patient_external_id": "HOSP-000001", "admission_date": "2025-06-01",
         "department": "Urgencias", "status": "discharged"},
        {"patient_external_id": "HOSP-000002", "admission_date": "2025-04-05",
         "department": "Cardiologia", "status": "admitted"},
    ]

    writer.bulk_upsert_patients_with_admissions(patients, admissions)

    ana = writer.db.patients.find_one({"external_id": "HOSP-000001"})
    assert len(ana["admissions"]) == 2
    luis = writer.db.patients.find_one({"external_id": "HOSP-000002"})
    assert len(luis["admissions"]) == 1


def test_bulk_upsert_patients_with_admissions_is_idempotent(writer: MongoWriter):
    patients = [{"external_id": "HOSP-000001", "name": "Ana"}]
    admissions = [
        {"patient_external_id": "HOSP-000001", "admission_date": "2025-03-10",
         "department": "UCI", "status": "admitted"},
    ]

    writer.bulk_upsert_patients_with_admissions(patients, admissions)
    writer.bulk_upsert_patients_with_admissions(patients, admissions)
    writer.bulk_upsert_patients_with_admissions(patients, admissions)

    assert writer.db.patients.count_documents({}) == 1
    ana = writer.db.patients.find_one({"external_id": "HOSP-000001"})
    assert len(ana["admissions"]) == 1


def test_write_rejected_accepts_string_run_id(writer: MongoWriter):
    """pipeline_run_id is a soft cross-DB reference to SQLite (string UUID).

    The Mongo collection stores it as-is; no FK enforcement. See ADR-004.
    """
    run_id = "550e8400-e29b-41d4-a716-446655440000"  # uuid v4 string
    rejected = [
        {"source_file": "patients.csv", "rejection_reason": "missing name", "raw_data": {"name": ""}},
        {"source_file": "patients.csv", "rejection_reason": "invalid birth_date", "raw_data": {"birth_date": "31/02/2020"}},
    ]
    inserted = writer.write_rejected(rejected, run_id)
    assert inserted == 2

    docs = list(writer.db.rejected_records.find({"pipeline_run_id": run_id}))
    assert len(docs) == 2
    assert all(isinstance(d["pipeline_run_id"], str) for d in docs)
    assert all(d["pipeline_run_id"] == run_id for d in docs)


def test_bulk_upsert_patients_handles_empty_list(writer: MongoWriter):
    stats = writer.bulk_upsert_patients([])
    assert stats["upserted"] == 0
    assert stats["modified"] == 0


def test_get_mongo_writer_from_env_uses_env_vars():
    assert os.environ["MONGO_HOST"]
    w = get_mongo_writer_from_env(db_name=TEST_DB_NAME)
    assert w is not None
    w.close()


# -----------------------------------------------------------------
# Radiography classification (Feature 2: clasificacion-radiografias)
# -----------------------------------------------------------------

def _classification_payload(predicted_class: str = "Normal") -> dict:
    from datetime import datetime, timezone
    return {
        "predicted_class": predicted_class,
        "probabilities": {"Normal": 0.7, "Pneumonia": 0.2, "COVID-19": 0.1},
        "predicted_at": datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc),
        "model_version": "test-v1.0",
    }


def test_set_classification_updates_specific_radiography(writer: MongoWriter):
    writer.bulk_upsert_patients([{"external_id": "HOSP-CLS-1", "name": "Ana"}])
    writer.add_radiography_to_patient("HOSP-CLS-1", {
        "minio_object_key": "HOSP-CLS-1/xray1.png",
        "original_filename": "xray1.png",
    })
    writer.add_radiography_to_patient("HOSP-CLS-1", {
        "minio_object_key": "HOSP-CLS-1/xray2.png",
        "original_filename": "xray2.png",
    })

    ok = writer.set_radiography_classification(
        "HOSP-CLS-1/xray1.png", _classification_payload("COVID-19"),
    )

    assert ok is True
    doc = writer.db.patients.find_one({"external_id": "HOSP-CLS-1"})
    radios = {r["minio_object_key"]: r for r in doc["radiographies"]}
    assert radios["HOSP-CLS-1/xray1.png"]["classification"]["predicted_class"] == "COVID-19"
    # The other radiography is untouched
    assert "classification" not in radios["HOSP-CLS-1/xray2.png"] or \
           radios["HOSP-CLS-1/xray2.png"].get("classification") is None


def test_set_classification_returns_false_for_unknown_key(writer: MongoWriter):
    writer.bulk_upsert_patients([{"external_id": "HOSP-CLS-2", "name": "Bob"}])

    ok = writer.set_radiography_classification(
        "no/such/key.png", _classification_payload(),
    )

    assert ok is False


def test_set_classification_is_idempotent_returns_true_on_identical_payload(
    writer: MongoWriter,
):
    """matched_count > 0, not modified_count: identical re-runs must succeed."""
    writer.bulk_upsert_patients([{"external_id": "HOSP-CLS-3", "name": "Eve"}])
    writer.add_radiography_to_patient("HOSP-CLS-3", {
        "minio_object_key": "HOSP-CLS-3/xray.png",
    })
    payload = _classification_payload("Pneumonia")
    writer.set_radiography_classification("HOSP-CLS-3/xray.png", payload)

    ok = writer.set_radiography_classification("HOSP-CLS-3/xray.png", payload)

    assert ok is True  # would be False if we used modified_count


def test_set_classification_overwrites_previous(writer: MongoWriter):
    writer.bulk_upsert_patients([{"external_id": "HOSP-CLS-4", "name": "X"}])
    writer.add_radiography_to_patient("HOSP-CLS-4", {
        "minio_object_key": "HOSP-CLS-4/xray.png",
    })

    writer.set_radiography_classification(
        "HOSP-CLS-4/xray.png", _classification_payload("Normal"),
    )
    writer.set_radiography_classification(
        "HOSP-CLS-4/xray.png", _classification_payload("COVID-19"),
    )

    doc = writer.db.patients.find_one({"external_id": "HOSP-CLS-4"})
    radio = doc["radiographies"][0]
    assert radio["classification"]["predicted_class"] == "COVID-19"



# -- Triaje (T4b): insert_patient con insert_one, no upsert ----------------


def test_insert_patient_creates_new_document(writer: MongoWriter):
    doc = {
        "external_id": "TRIAGE-20260519-0001",
        "name": "Paciente Triaje",
        "age": 40,
        "gender": "M",
        "triage": {"level": "leve", "score": 0, "reasons": []},
    }

    returned_id = writer.insert_patient(doc)

    assert returned_id == "TRIAGE-20260519-0001"
    persisted = writer.db.patients.find_one(
        {"external_id": "TRIAGE-20260519-0001"}
    )
    assert persisted is not None
    assert persisted["name"] == "Paciente Triaje"
    assert persisted["triage"]["level"] == "leve"
    # created_at + updated_at are stamped by the writer
    assert "created_at" in persisted
    assert "updated_at" in persisted


def test_insert_patient_does_not_upsert_existing(writer: MongoWriter):
    """Garantia dura: si el external_id ya existe, insert_patient NO
    sobrescribe. Lanza pymongo.errors.DuplicateKeyError (propagado),
    para que el router decida si reintentar o devolver 409 (RF-7)."""
    from pymongo.errors import DuplicateKeyError

    original = {
        "external_id": "TRIAGE-20260519-0042",
        "name": "Original",
        "age": 30,
    }
    writer.insert_patient(original)

    duplicate = {
        "external_id": "TRIAGE-20260519-0042",
        "name": "Should NOT overwrite",
        "age": 99,
    }
    with pytest.raises(DuplicateKeyError):
        writer.insert_patient(duplicate)

    # El paciente original NO ha sido alterado:
    persisted = writer.db.patients.find_one(
        {"external_id": "TRIAGE-20260519-0042"}
    )
    assert persisted["name"] == "Original"
    assert persisted["age"] == 30
