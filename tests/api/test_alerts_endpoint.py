"""Tests del endpoint GET /api/v1/alerts (Feature 15, T5).

Cubre CA-1 (200 + estructura), CA-2 (cada tipo de alerta), CA-3 (filtro
por severity + 422 en valor invalido), CB-1 (sin datos -> items=[]).

El router se prueba con **fakes** para los readers (sql_reader,
mongo_reader). Los readers tienen sus propios tests en
test_sql_reader.py y los nuevos metodos `_since` se ejercitan ademas
en el smoke real (T16). Aqui verificamos el contrato del router:

  * Llama a los metodos `_since` con `since` correcto.
  * Pasa el `threshold` correcto a `evaluate`.
  * Devuelve {items, total, generated_at, threshold, window_start}.
  * Filtra por `severity` cuando se pasa el query param.
  * Devuelve 422 con valores invalidos.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from src.api.main import build_app


UTC = timezone.utc


class FakeSqlReader:
    """Fake del SqlReader. Solo implementa los metodos que /alerts usa."""

    def __init__(
        self,
        failed_runs: list[dict] | None = None,
        quality_snapshots: list[dict] | None = None,
    ) -> None:
        self._failed_runs = failed_runs or []
        self._quality_snapshots = quality_snapshots or []
        self.calls: list[tuple] = []

    def list_failed_runs_since(self, since: datetime) -> list[dict]:
        self.calls.append(("failed_runs_since", since))
        return list(self._failed_runs)

    def list_quality_snapshots_since(self, since: datetime) -> list[dict]:
        self.calls.append(("quality_snapshots_since", since))
        return list(self._quality_snapshots)

    def close(self) -> None:
        pass


class FakeMongoReader:
    def __init__(self, severe_patients: list[dict] | None = None) -> None:
        self._severe_patients = severe_patients or []
        self.calls: list[tuple] = []

    def list_severe_triage_patients_since(self, since: datetime) -> list[dict]:
        self.calls.append(("severe_since", since))
        return list(self._severe_patients)

    def close(self) -> None:
        pass


@pytest.fixture
def client_factory(monkeypatch):
    """Factory que monta TestClient con readers fakeados."""

    def _factory(
        failed_runs: list[dict] | None = None,
        quality_snapshots: list[dict] | None = None,
        severe_patients: list[dict] | None = None,
        threshold: str = "0.10",
        window_hours: str = "24",
    ) -> TestClient:
        monkeypatch.setenv("ALERT_REJECTION_RATE_THRESHOLD", threshold)
        monkeypatch.setenv("ALERT_WINDOW_HOURS", window_hours)
        # build_app intenta abrir Mongo/SQLite reales; swallow errors via
        # override directo de app.state tras construir.
        # Para evitar IO al SQLite real, sustituimos antes via env var:
        monkeypatch.setenv("MONGO_DB", "hospital_test_alerts_unused")
        app = build_app(mongo_db_name="hospital_test_alerts_unused")
        app.state.sql_reader = FakeSqlReader(failed_runs, quality_snapshots)
        app.state.mongo_reader = FakeMongoReader(severe_patients)
        return TestClient(app)

    return _factory


# -- CA-1 + CB-1: 200 + estructura, sin datos ----------------------------

def test_get_alerts_empty_returns_200_with_zero(client_factory):
    client = client_factory()
    resp = client.get("/api/v1/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert "generated_at" in body
    assert "threshold" in body
    assert "window_start" in body


# -- CA-2 (a): pipeline_failed ------------------------------------------

def test_get_alerts_with_failed_run(client_factory):
    run = {
        "id": "run-abc",
        "trigger_type": "watcher",
        "started_at": datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        "status": "failed",
        "error_message": "ETL crashed",
    }
    client = client_factory(failed_runs=[run])
    resp = client.get("/api/v1/alerts")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "pipeline_failed"
    assert items[0]["severity"] == "high"
    assert items[0]["source_id"] == "run-abc"


# -- CA-2 (b): data_quality_low -----------------------------------------

def test_get_alerts_with_low_quality(client_factory):
    snap = {
        "pipeline_run_id": "run-q",
        "dimension": "patients",
        "total": 100,
        "valid": 80,
        "rejected": 20,
        "rejection_rate": 0.20,
        "recorded_at": datetime(2026, 5, 20, 11, 0, tzinfo=UTC),
    }
    client = client_factory(quality_snapshots=[snap])
    resp = client.get("/api/v1/alerts")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "data_quality_low"
    assert items[0]["severity"] == "medium"


# -- CA-2 (c): triage_severe --------------------------------------------

def test_get_alerts_with_severe_triage_patient(client_factory):
    patient = {
        "external_id": "P-999",
        "name": "Test",
        "triage": {
            "level": "grave",
            "reasons": ["SpO2<90"],
            "triaged_at": datetime(2026, 5, 20, 13, 0, tzinfo=UTC),
        },
    }
    client = client_factory(severe_patients=[patient])
    resp = client.get("/api/v1/alerts")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "triage_severe"
    assert items[0]["severity"] == "critical"
    assert items[0]["source_id"] == "P-999"


# -- CA-3: filtro por severity + 422 ------------------------------------

def test_get_alerts_filter_by_severity(client_factory):
    run = {
        "id": "run-1", "trigger_type": "w",
        "started_at": datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        "status": "failed", "error_message": "x",
    }
    patient = {
        "external_id": "P-1", "name": "Test",
        "triage": {
            "level": "grave", "reasons": [],
            "triaged_at": datetime(2026, 5, 20, 13, 0, tzinfo=UTC),
        },
    }
    client = client_factory(failed_runs=[run], severe_patients=[patient])

    resp = client.get("/api/v1/alerts?severity=critical")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["severity"] == "critical"

    resp = client.get("/api/v1/alerts?severity=high")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["severity"] == "high"


def test_get_alerts_invalid_severity_returns_422(client_factory):
    client = client_factory()
    resp = client.get("/api/v1/alerts?severity=banana")
    assert resp.status_code == 422


# -- RF-3: query param `since` sobreescribe la ventana ------------------

def test_get_alerts_since_overrides_default_window(client_factory):
    client = client_factory()
    custom_since = "2026-01-01T00:00:00Z"
    resp = client.get(f"/api/v1/alerts?since={custom_since}")
    assert resp.status_code == 200
    body = resp.json()
    # window_start del response debe coincidir con `since`
    assert body["window_start"].startswith("2026-01-01")

    # Verificamos que los readers recibieron ese `since`
    sql_calls = client.app.state.sql_reader.calls
    assert any(c[0] == "failed_runs_since" for c in sql_calls)
    failed_call = next(c for c in sql_calls if c[0] == "failed_runs_since")
    assert failed_call[1].year == 2026
    assert failed_call[1].month == 1


def test_get_alerts_invalid_since_returns_422(client_factory):
    client = client_factory()
    resp = client.get("/api/v1/alerts?since=not-a-date")
    assert resp.status_code == 422


# -- RNF-7: threshold se lee de env var ---------------------------------

def test_threshold_comes_from_env_var(client_factory):
    """Con threshold=0.50 (env), un snapshot a 0.20 NO debe alertar."""
    snap = {
        "pipeline_run_id": "run-q", "dimension": "patients",
        "total": 100, "valid": 80, "rejected": 20,
        "rejection_rate": 0.20,
        "recorded_at": datetime(2026, 5, 20, 11, 0, tzinfo=UTC),
    }
    client = client_factory(quality_snapshots=[snap], threshold="0.50")
    resp = client.get("/api/v1/alerts")
    body = resp.json()
    assert body["items"] == []
    assert body["threshold"] == 0.50


# -- RF-8: orden severity DESC, created_at DESC -------------------------

def test_alerts_returned_sorted_critical_first(client_factory):
    run = {
        "id": "r", "trigger_type": "w",
        "started_at": datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
        "status": "failed", "error_message": "x",
    }
    snap = {
        "pipeline_run_id": "rq", "dimension": "patients",
        "total": 100, "valid": 70, "rejected": 30, "rejection_rate": 0.30,
        "recorded_at": datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
    }
    patient = {
        "external_id": "P", "name": "Test",
        "triage": {
            "level": "grave", "reasons": [],
            "triaged_at": datetime(2026, 5, 20, 7, 0, tzinfo=UTC),
        },
    }
    client = client_factory(
        failed_runs=[run],
        quality_snapshots=[snap],
        severe_patients=[patient],
    )
    items = client.get("/api/v1/alerts").json()["items"]
    severities = [a["severity"] for a in items]
    assert severities == ["critical", "high", "medium"]
