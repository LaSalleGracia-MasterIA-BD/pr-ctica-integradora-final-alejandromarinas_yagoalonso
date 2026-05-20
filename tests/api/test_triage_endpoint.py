"""Integration tests of the triage endpoint (POST /api/v1/triage/patients).

Covers spec criterios CA-1..CA-10 except CA-6 (que vive en
test_triage_rules.py) y CA-7/CA-8/CA-9 (validados en otro punto).

Reproduce el indice unico `external_id` que en produccion crea el
script `docker/mongo-init/init-db.js`; sin el indice, los tests de
retry no podrian reproducir el contrato de RF-7.
"""
from __future__ import annotations

import os
import re
from datetime import date

import pytest

pymongo = pytest.importorskip("pymongo")
fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from src.api.main import build_app
from src.pipeline.storage.mongo_writer import MongoWriter


TEST_DB_NAME = "hospital_test_triage"


@pytest.fixture
def mongo_writer():
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
    w.db.patients.create_index("external_id", unique=True)


@pytest.fixture
def client(mongo_writer: MongoWriter) -> TestClient:
    app = build_app(mongo_db_name=TEST_DB_NAME)
    return TestClient(app)


# -- payload helper ---------------------------------------------------------


def _payload(**overrides):
    base = {
        "name": "Paciente Test",
        "gender": "M",
        "age": 40,
        "vital_signs": {
            "temperature_celsius": 36.8,
            "oxygen_saturation": 98,
            "heart_rate": 75,
            "respiratory_rate": 16,
            "systolic_bp": 120,
        },
        "symptoms": [],
        "risk_factors": [],
    }
    if "vital_signs" in overrides:
        base["vital_signs"] = {**base["vital_signs"], **overrides.pop("vital_signs")}
    base.update(overrides)
    return base


# -- US-1: paciente grave (CA-1) -------------------------------------------


def test_post_grave_returns_201_with_triage(client: TestClient):
    """SpO2 = 88 dispara `spo2_lt_92` -> level=grave."""
    body = _payload(vital_signs={"oxygen_saturation": 88})

    r = client.post("/api/v1/triage/patients", json=body)

    assert r.status_code == 201, r.text
    data = r.json()
    assert data["triage"]["level"] == "grave"
    assert "spo2_lt_92" in data["triage"]["reasons"]
    assert data["triage"]["source"] == "manual_triage"
    assert data["triage"]["rules_version"] == "1.0"


def test_post_grave_with_critical_symptom(client: TestClient):
    """`alteracion_conciencia` dispara grave aunque los signos vitales sean normales."""
    body = _payload(symptoms=["alteracion_conciencia"])

    r = client.post("/api/v1/triage/patients", json=body)

    assert r.status_code == 201, r.text
    assert r.json()["triage"]["level"] == "grave"


# -- US-2: paciente medio (CA-2) -------------------------------------------


def test_post_medio_returns_201_with_triage(client: TestClient):
    """SpO2 = 93 cae en `spo2_92_94` -> level=medio."""
    body = _payload(vital_signs={"oxygen_saturation": 93})

    r = client.post("/api/v1/triage/patients", json=body)

    assert r.status_code == 201, r.text
    data = r.json()
    assert data["triage"]["level"] == "medio"
    assert "spo2_92_94" in data["triage"]["reasons"]


def test_post_anciano_con_fiebre_is_medio(client: TestClient):
    """edad>=70 + fiebre dispara `anciano_riesgo_respiratorio` -> medio."""
    body = _payload(age=75, vital_signs={"temperature_celsius": 38.5})

    r = client.post("/api/v1/triage/patients", json=body)

    assert r.status_code == 201, r.text
    data = r.json()
    assert data["triage"]["level"] == "medio"
    assert "anciano_riesgo_respiratorio" in data["triage"]["reasons"]


# -- US-3: paciente leve (CA-3) --------------------------------------------


def test_post_leve_returns_201_with_triage(client: TestClient):
    """Todos los signos normales, sin sintomas criticos -> leve."""
    body = _payload()

    r = client.post("/api/v1/triage/patients", json=body)

    assert r.status_code == 201, r.text
    data = r.json()
    assert data["triage"]["level"] == "leve"
    assert data["triage"]["reasons"] == []
    assert data["triage"]["score"] == 0


# -- CA-4: payloads invalidos -> 422 ---------------------------------------


def test_post_without_vital_signs_returns_422(client: TestClient):
    body = _payload()
    del body["vital_signs"]
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 422


def test_post_with_spo2_out_of_range_returns_422(client: TestClient):
    body = _payload(vital_signs={"oxygen_saturation": 150})
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 422


def test_post_without_birth_date_nor_age_returns_422(client: TestClient):
    body = _payload()
    body["age"] = None
    body["birth_date"] = None
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 422


def test_post_with_invalid_gender_returns_422(client: TestClient):
    body = _payload(gender="X")
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 422


def test_post_with_empty_name_returns_422(client: TestClient):
    body = _payload(name="")
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 422


def test_post_with_blank_name_returns_422(client: TestClient):
    """`name` = '   ' supera `min_length=1` pero el field_validator lo rechaza."""
    body = _payload(name="   ")
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 422


def test_post_with_invalid_birth_date_returns_422(client: TestClient):
    """`birth_date` no parseable como ISO YYYY-MM-DD -> 422."""
    body = _payload()
    body["age"] = None
    body["birth_date"] = "no-es-fecha"
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 422


def test_post_with_invalid_birth_date_month_returns_422(client: TestClient):
    """Mes/dia fuera de rango -> 422 (ISO estricto)."""
    body = _payload()
    body["age"] = None
    body["birth_date"] = "1990-13-40"
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 422


def test_post_with_future_birth_date_returns_422(client: TestClient):
    """`birth_date` futura -> 422 (no se aceptan pacientes nacidos en el futuro)."""
    from datetime import date, timedelta
    future = (date.today() + timedelta(days=365)).isoformat()
    body = _payload()
    body["age"] = None
    body["birth_date"] = future
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 422


# -- CA-5: paciente creado consultable via GET /patients/{id} --------------


def test_created_triage_patient_is_visible_via_get_patient(client: TestClient):
    body = _payload(vital_signs={"oxygen_saturation": 88})
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 201

    external_id = r.json()["external_id"]
    r2 = client.get(f"/api/v1/patients/{external_id}")

    assert r2.status_code == 200, r2.text
    persisted = r2.json()
    assert persisted["external_id"] == external_id
    assert persisted["triage"]["level"] == "grave"


def test_created_triage_patient_appears_in_list_patients(client: TestClient):
    body = _payload()
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 201
    new_id = r.json()["external_id"]

    r2 = client.get("/api/v1/patients?limit=50&offset=0")
    assert r2.status_code == 200
    body = r2.json()
    ids = [p["external_id"] for p in body["items"]]
    assert new_id in ids


# -- RF-6: formato del external_id -----------------------------------------


_TRIAGE_ID_RE = re.compile(r"^TRIAGE-\d{8}-\d{4}$")


def test_external_id_format(client: TestClient):
    body = _payload()
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 201

    external_id = r.json()["external_id"]
    assert _TRIAGE_ID_RE.match(external_id), external_id

    # El YYYYMMDD coincide con hoy
    today = date.today().strftime("%Y%m%d")
    assert today in external_id


def test_external_id_counter_increments(client: TestClient):
    body = _payload()
    r1 = client.post("/api/v1/triage/patients", json=body)
    r2 = client.post("/api/v1/triage/patients", json=body)
    assert r1.status_code == 201 and r2.status_code == 201

    id1 = r1.json()["external_id"]
    id2 = r2.json()["external_id"]
    n1 = int(id1.rsplit("-", 1)[1])
    n2 = int(id2.rsplit("-", 1)[1])
    assert n2 == n1 + 1


# -- RF-8: GET /api/v1/triage/rules (CA-10) --------------------------------


def test_get_triage_rules_returns_definition(client: TestClient):
    r = client.get("/api/v1/triage/rules")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["version"] == "1.0"
    assert "grave" in data["levels"]
    assert "medio" in data["levels"]
    # Cada regla tiene id + description
    for rule in data["levels"]["grave"]:
        assert "id" in rule and "description" in rule


# -- birth_date como alternativa a age -------------------------------------


def test_post_with_birth_date_instead_of_age(client: TestClient):
    body = _payload()
    body["age"] = None
    body["birth_date"] = "1985-06-15"
    r = client.post("/api/v1/triage/patients", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["birth_date"] == "1985-06-15"


def test_post_daily_limit_9999_returns_409(
    client: TestClient, mongo_writer: MongoWriter
):
    """RF-6: el contador NNNN tiene 4 digitos. Si el ultimo paciente del
    dia tiene NNNN=9999, intentar crear uno mas devuelve 409 (cupo diario
    agotado), no `NNNN=10000`."""
    from datetime import date

    # Seedeamos un paciente con NNNN = 9999 para hoy, para que
    # `_next_counter_for_today` calcule 10000.
    today_str = date.today().strftime("%Y%m%d")
    seeded_id = f"TRIAGE-{today_str}-9999"
    mongo_writer.db.patients.insert_one({
        "external_id": seeded_id,
        "name": "Seeded para test de limite",
        "gender": "M",
        "age": 50,
    })

    body = _payload()
    r = client.post("/api/v1/triage/patients", json=body)

    assert r.status_code == 409, r.text
    body = r.json()
    assert "9999" in body["detail"] or "agotado" in body["detail"].lower()
