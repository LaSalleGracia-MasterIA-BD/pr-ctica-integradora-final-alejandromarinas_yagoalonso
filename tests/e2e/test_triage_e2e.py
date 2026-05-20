"""E2E tests of triage-pacientes against the live stack.

Requires `docker compose up` running. If the API is not reachable from
where the tests run, all tests in this module are skipped.

Cover CA-1, CA-2, CA-3, CA-4, CA-5 end-to-end.
"""
from __future__ import annotations

import re

import pytest


_TRIAGE_ID_RE = re.compile(r"^TRIAGE-\d{8}-\d{4}$")


def _payload(**overrides):
    base = {
        "name": "Paciente E2E",
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


def test_e2e_create_grave_then_get_patient(api_url, http):
    """CA-1 + CA-5: crear paciente grave -> GET /patients/{id} con `triage` poblado."""
    body = _payload(vital_signs={"oxygen_saturation": 88})

    r = http.post(f"{api_url}/api/v1/triage/patients", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    external_id = data["external_id"]
    assert _TRIAGE_ID_RE.match(external_id)
    assert data["triage"]["level"] == "grave"

    # Roundtrip: el paciente queda consultable en /patients/{id}
    r2 = http.get(f"{api_url}/api/v1/patients/{external_id}")
    assert r2.status_code == 200, r2.text
    persisted = r2.json()
    assert persisted["external_id"] == external_id
    assert persisted["triage"]["level"] == "grave"
    assert "spo2_lt_92" in persisted["triage"]["reasons"]


def test_e2e_create_medio(api_url, http):
    """CA-2: paciente medio."""
    body = _payload(vital_signs={"oxygen_saturation": 93})
    r = http.post(f"{api_url}/api/v1/triage/patients", json=body)
    assert r.status_code == 201
    assert r.json()["triage"]["level"] == "medio"


def test_e2e_create_leve(api_url, http):
    """CA-3: paciente leve (todos los signos normales)."""
    body = _payload()
    r = http.post(f"{api_url}/api/v1/triage/patients", json=body)
    assert r.status_code == 201
    assert r.json()["triage"]["level"] == "leve"


def test_e2e_post_invalid_returns_422(api_url, http):
    """CA-4: payload invalido (sin vital_signs)."""
    body = _payload()
    del body["vital_signs"]
    r = http.post(f"{api_url}/api/v1/triage/patients", json=body)
    assert r.status_code == 422


def test_e2e_get_rules_returns_definition(api_url, http):
    """CA-10: GET /triage/rules devuelve la definicion vigente."""
    r = http.get(f"{api_url}/api/v1/triage/rules")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == "1.0"
    assert "grave" in data["levels"]


def test_e2e_created_patient_appears_in_list_patients(api_url, http):
    """Crea un paciente y comprueba que SI aparece en `GET /patients`
    paginando hasta el final usando `total`.

    El orden por external_id alfabetico ascendente coloca los TRIAGE-*
    despues de los HOSP-NNNNNN, asi que el nuevo paciente cae cerca del
    final. Calculamos el offset de la ultima pagina con `total` y
    verificamos que aparece.
    """
    body = _payload()
    r = http.post(f"{api_url}/api/v1/triage/patients", json=body)
    assert r.status_code == 201
    new_id = r.json()["external_id"]

    # 1) Total actual de pacientes (para calcular el offset de la ultima pagina)
    r_count = http.get(f"{api_url}/api/v1/patients?limit=1&offset=0")
    assert r_count.status_code == 200
    total = r_count.json()["total"]
    assert total >= 1

    # 2) Leer la ultima pagina alineada al `limit`
    limit = 200
    last_page_offset = ((total - 1) // limit) * limit
    r_last = http.get(
        f"{api_url}/api/v1/patients?limit={limit}&offset={last_page_offset}"
    )
    assert r_last.status_code == 200
    ids_last = [p["external_id"] for p in r_last.json()["items"]]

    # 3) Buscar el nuevo paciente en la ultima pagina; si por timing cae
    # justo en el limite, ampliar a la penultima.
    if new_id not in ids_last and last_page_offset >= limit:
        r_prev = http.get(
            f"{api_url}/api/v1/patients?limit={limit}&offset={last_page_offset - limit}"
        )
        assert r_prev.status_code == 200
        ids_last.extend(p["external_id"] for p in r_prev.json()["items"])

    assert new_id in ids_last, (
        f"new_id {new_id} no aparece en las ultimas paginas. total={total}, "
        f"limit={limit}, offset={last_page_offset}"
    )
