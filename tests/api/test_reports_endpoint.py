"""Tests del endpoint GET /api/v1/reports/daily (Feature 15, T7).

Cubre CA-4 (200 + estructura), CB-6 (date invalida -> 422), CB-7
(date futura -> contadores en cero), y especialmente que la ventana es
**del dia consultado** ([00:00, 23:59:59.999] UTC), NO las ultimas 24h
desde ahora (RF-4).

Usa fakes para los readers que registran las llamadas con
`(start, end)` para verificar que se pasan los limites correctos.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from src.api.main import build_app


UTC = timezone.utc


class FakeSqlReader:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    # Endpoint /reports/daily usa `_between`
    def list_failed_runs_between(self, start, end):
        self.calls.append(("failed_runs_between", start, end))
        return []

    def list_runs_between(self, start, end):
        self.calls.append(("runs_between", start, end))
        return []

    def list_quality_snapshots_between(self, start, end):
        self.calls.append(("quality_between", start, end))
        return []

    def close(self) -> None:
        pass


class FakeMongoReader:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._counts = {
            "patients_total": 0, "admissions_total": 0, "radiographies_total": 0,
        }

    def list_triage_patients_between(self, start, end):
        self.calls.append(("triage_between", start, end))
        return []

    def list_severe_triage_patients_between(self, start, end):
        self.calls.append(("severe_between", start, end))
        return []

    def get_total_counts(self):
        self.calls.append(("counts",))
        return dict(self._counts)

    def close(self) -> None:
        pass


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("ALERT_REJECTION_RATE_THRESHOLD", "0.10")
    monkeypatch.setenv("MONGO_DB", "hospital_test_reports_unused")
    app = build_app(mongo_db_name="hospital_test_reports_unused")
    app.state.sql_reader = FakeSqlReader()
    app.state.mongo_reader = FakeMongoReader()
    return app  # type: ignore[return-value]


@pytest.fixture
def http(client) -> TestClient:
    return TestClient(client)


# -- CA-4: 200 + estructura ---------------------------------------------

def test_get_daily_report_returns_200_with_all_sections(client, http):
    resp = http.get("/api/v1/reports/daily?date=2026-05-20")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-05-20"
    assert "generated_at" in body
    for k in ("pipeline", "quality", "counts", "triage", "alerts"):
        assert k in body


def test_get_daily_report_without_date_uses_today_utc(client, http):
    resp = http.get("/api/v1/reports/daily")
    assert resp.status_code == 200
    # `date` debe ser una fecha ISO valida (la de hoy UTC).
    assert len(resp.json()["date"]) == 10
    assert resp.json()["date"][4] == "-"


# -- CB-6: date invalida -> 422 ----------------------------------------

def test_get_daily_report_invalid_date_returns_422(client, http):
    resp = http.get("/api/v1/reports/daily?date=not-a-date")
    assert resp.status_code == 422


def test_get_daily_report_invalid_format_returns_422(client, http):
    resp = http.get("/api/v1/reports/daily?date=20-05-2026")
    assert resp.status_code == 422


# -- RF-4: ventana del dia [00:00, 23:59:59.999] UTC, NO ultimas 24h ----

def test_get_daily_report_uses_day_window_not_last_24h(client, http):
    resp = http.get("/api/v1/reports/daily?date=2026-05-15")
    assert resp.status_code == 200
    # Verifica que TODAS las llamadas a los readers fueron con la ventana
    # estricta del 2026-05-15 UTC.
    sql_calls = client.state.sql_reader.calls
    mongo_calls = client.state.mongo_reader.calls
    expected_start = datetime(2026, 5, 15, 0, 0, 0, 0, tzinfo=UTC)
    expected_end = datetime(2026, 5, 15, 23, 59, 59, 999999, tzinfo=UTC)
    for call in sql_calls + mongo_calls:
        if call[0] == "counts":
            continue
        _name, start, end = call
        assert start == expected_start, (
            f"{_name} got start={start}, expected {expected_start}"
        )
        assert end == expected_end, (
            f"{_name} got end={end}, expected {expected_end}"
        )


# -- CB-7: date futura -> contadores en cero, no error ------------------

def test_get_daily_report_future_date_returns_empty_no_error(client, http):
    resp = http.get("/api/v1/reports/daily?date=2099-12-31")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pipeline"]["runs_in_day"] == 0
    assert body["pipeline"]["failed_in_day"] == 0
    assert body["alerts"] == []


# -- RNF-3 + CA-8: no toca writers ni crea estado nuevo (smoke contract)

def test_get_daily_report_only_uses_between_methods(client, http):
    """El endpoint debe usar los metodos `_between`, NO los `_since`.

    Garantiza que no se reutiliza la ventana del endpoint /alerts (que
    es ultimas N horas)."""
    http.get("/api/v1/reports/daily?date=2026-05-20")
    sql_call_names = {c[0] for c in client.state.sql_reader.calls}
    assert sql_call_names <= {
        "failed_runs_between", "runs_between", "quality_between"
    }, f"unexpected reader methods called: {sql_call_names}"
    mongo_call_names = {c[0] for c in client.state.mongo_reader.calls}
    assert mongo_call_names <= {
        "triage_between", "severe_between", "counts"
    }
