"""Unit tests for src.dashboard.api_client.

Use httpx.MockTransport so we never touch the network. The goal is to
verify:
  * each method maps 2xx → (data, None)
  * each documented HTTP status maps to the right ApiError.kind
  * network errors (connection refused / timeout) → ApiError(kind="network")
  * image_bytes returns raw bytes, not JSON
"""
from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest

from src.dashboard.api_client import ApiClient, ApiError


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> ApiClient:
    """Build an ApiClient backed by a MockTransport (no real network)."""
    transport = httpx.MockTransport(handler)
    client = ApiClient(base_url="http://api:8000", timeout=5.0)
    # Replace the underlying httpx.Client with one wired to the mock
    client._client = httpx.Client(base_url="http://api:8000", transport=transport)
    return client


def _json_handler(routes: dict[str, tuple[int, dict]]) -> Callable:
    """Build a handler that returns canned responses by URL path."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path not in routes:
            return httpx.Response(404, json={"detail": "test route missing"})
        status, body = routes[path]
        return httpx.Response(status, json=body)
    return handler


# ---------------------------------------------------------------------------
# happy paths
# ---------------------------------------------------------------------------

def test_health_returns_data_and_no_error():
    api = _make_client(_json_handler({
        "/api/v1/health": (200, {"status": "ok", "version": "0.1.0", "predictor_loaded": True}),
    }))
    data, err = api.health()
    assert err is None
    assert data["status"] == "ok"
    assert data["predictor_loaded"] is True


def test_count_patients_returns_total():
    api = _make_client(_json_handler({
        "/api/v1/patients": (200, {"total": 4745, "limit": 1, "offset": 0, "items": []}),
    }))
    data, err = api.count_patients()
    assert err is None
    assert data == 4745


def test_count_admissions_returns_total():
    api = _make_client(_json_handler({
        "/api/v1/admissions": (200, {"total": 8569, "limit": 1, "offset": 0, "items": []}),
    }))
    data, err = api.count_admissions()
    assert err is None
    assert data == 8569


def test_count_radiographies_returns_total():
    api = _make_client(_json_handler({
        "/api/v1/radiographies": (200, {"total": 18, "limit": 1, "offset": 0, "items": []}),
    }))
    data, err = api.count_radiographies()
    assert err is None
    assert data == 18


def test_list_patients_passes_limit_offset():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 0, "limit": 20, "offset": 40, "items": []})

    api = _make_client(handler)
    data, err = api.list_patients(limit=20, offset=40)
    assert err is None
    assert captured["params"] == {"limit": "20", "offset": "40"}


def test_classify_posts_body_and_returns_prediction():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "minio_object_key": "HOSP-1/x.png",
            "predicted_class": "COVID-19",
            "probabilities": {"Normal": 0.05, "Pneumonia": 0.10, "COVID-19": 0.85},
            "predicted_at": "2026-05-17T10:00:00Z",
            "model_version": "v1.0",
        })

    api = _make_client(handler)
    data, err = api.classify("HOSP-1/x.png")
    assert err is None
    assert captured["method"] == "POST"
    assert captured["body"] == {"minio_object_key": "HOSP-1/x.png"}
    assert data["predicted_class"] == "COVID-19"


def test_image_bytes_returns_raw_bytes_not_dict():
    png_bytes = b"\x89PNG\r\n\x1a\nFAKE"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=png_bytes, headers={"Content-Type": "image/png"})

    api = _make_client(handler)
    data, err = api.image_bytes("HOSP-1/x.png")
    assert err is None
    assert isinstance(data, bytes)
    assert data == png_bytes


def test_model_evaluation_returns_metrics():
    api = _make_client(_json_handler({
        "/api/v1/model/evaluation": (200, {
            "accuracy": 0.87,
            "macro_f1": 0.85,
            "per_class": {"Normal": {"recall": 0.93}, "Pneumonia": {"recall": 0.93}, "COVID-19": {"recall": 0.70}},
            "confusion_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "model_version": "v1.0",
        }),
    }))
    data, err = api.model_evaluation()
    assert err is None
    assert data["accuracy"] == 0.87


# ---------------------------------------------------------------------------
# error mapping
# ---------------------------------------------------------------------------

def test_404_maps_to_not_found():
    api = _make_client(_json_handler({
        "/api/v1/radiographies/classification": (
            404, {"detail": "No classification persisted for x/y.png"},
        ),
    }))
    data, err = api.get_classification("x/y.png")
    assert data is None
    assert err is not None
    assert err.kind == "not_found"
    assert err.status == 404


def test_422_maps_to_validation():
    """The classifier should expose `validation` to the dashboard so it can show
    the CB-7 message about dummy 1x1 images."""
    api = _make_client(_json_handler({
        "/api/v1/radiographies/classify": (
            422,
            {"detail": "Image cannot be processed: Image too small (1x1)"},
        ),
    }))
    data, err = api.classify("dummy/1x1.png")
    assert err is not None
    assert err.kind == "validation"
    assert err.status == 422
    assert "small" in err.detail.lower()


def test_503_on_classify_maps_to_unavailable():
    api = _make_client(_json_handler({
        "/api/v1/radiographies/classify": (
            503, {"detail": "Classification model is not loaded in this deployment"},
        ),
    }))
    data, err = api.classify("HOSP-1/x.png")
    assert err is not None
    assert err.kind == "unavailable"


def test_503_on_model_evaluation_maps_to_unavailable():
    api = _make_client(_json_handler({
        "/api/v1/model/evaluation": (
            503, {"detail": "Model evaluation report not available"},
        ),
    }))
    data, err = api.model_evaluation()
    assert err is not None
    assert err.kind == "unavailable"


def test_5xx_maps_to_server():
    api = _make_client(_json_handler({
        "/api/v1/health": (502, {"detail": "Upstream object storage error"}),
    }))
    data, err = api.health()
    assert err is not None
    assert err.kind == "server"
    assert err.status == 502


def test_network_error_maps_to_network():
    """Connection refused / DNS / timeout → ApiError(kind='network')."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    api = _make_client(handler)
    data, err = api.health()
    assert data is None
    assert err is not None
    assert err.kind == "network"
    assert err.status is None
    assert "ConnectError" in err.detail


def test_quality_summary_history_sends_correct_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={
            "total": 0, "limit": 50, "offset": 0,
            "dimension": "patients", "items": [],
        })

    api = _make_client(handler)
    data, err = api.quality_summary_history("patients", limit=50)
    assert err is None
    assert captured["params"] == {"dimension": "patients", "limit": "50", "offset": "0"}


def test_image_bytes_404_returns_error_not_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Radiography not found in MinIO: x"})

    api = _make_client(handler)
    data, err = api.image_bytes("x")
    assert data is None
    assert err is not None
    assert err.kind == "not_found"


# ---------------------------------------------------------------------------
# triage (feature triage-pacientes)
# ---------------------------------------------------------------------------

def test_create_triage_patient_maps_201_to_data():
    payload_recv = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/triage/patients":
            assert request.method == "POST"
            payload_recv.update(json.loads(request.content))
            return httpx.Response(201, json={
                "external_id": "TRIAGE-20260519-0001",
                "name": "Test",
                "gender": "M",
                "triage": {"level": "grave", "score": 1, "reasons": ["spo2_lt_92"]},
            })
        return httpx.Response(404, json={"detail": "not found"})

    api = _make_client(handler)
    data, err = api.create_triage_patient({"name": "Test", "vital_signs": {}})
    assert err is None
    assert data["triage"]["level"] == "grave"
    assert payload_recv["name"] == "Test"


def test_create_triage_patient_maps_422_to_validation_error():
    api = _make_client(_json_handler({
        "/api/v1/triage/patients": (422, {"detail": "field required"}),
    }))
    data, err = api.create_triage_patient({})
    assert data is None
    assert err is not None
    assert err.kind == "validation"
    assert err.status == 422


def test_create_triage_patient_maps_409_to_server_error():
    api = _make_client(_json_handler({
        "/api/v1/triage/patients": (409, {"detail": "retries exhausted"}),
    }))
    data, err = api.create_triage_patient({"name": "X"})
    assert data is None
    assert err is not None
    # 409 cae en "server" segun el ApiClient (no es 404/422/503)
    assert err.kind == "server"
    assert err.status == 409


def test_create_triage_patient_maps_503_to_unavailable():
    api = _make_client(_json_handler({
        "/api/v1/triage/patients": (503, {"detail": "mongo unreachable"}),
    }))
    data, err = api.create_triage_patient({"name": "X"})
    assert err is not None
    assert err.kind == "unavailable"


def test_create_triage_patient_maps_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    api = _make_client(handler)
    data, err = api.create_triage_patient({"name": "X"})
    assert data is None
    assert err is not None
    assert err.kind == "network"


def test_get_triage_rules_returns_data():
    api = _make_client(_json_handler({
        "/api/v1/triage/rules": (200, {
            "version": "1.0",
            "levels": {"grave": [], "medio": []},
        }),
    }))
    data, err = api.get_triage_rules()
    assert err is None
    assert data["version"] == "1.0"


def test_get_triage_rules_maps_503():
    api = _make_client(_json_handler({
        "/api/v1/triage/rules": (503, {"detail": "unavailable"}),
    }))
    data, err = api.get_triage_rules()
    assert err is not None
    assert err.kind == "unavailable"


# ---------------------------------------------------------------------------
# alerts + reports (Feature 15)
# ---------------------------------------------------------------------------

def test_get_alerts_maps_200():
    api = _make_client(_json_handler({
        "/api/v1/alerts": (200, {
            "items": [{
                "type": "triage_severe",
                "severity": "critical",
                "title": "Paciente grave",
                "detail": "x",
                "source": "patients.triage",
                "source_id": "P-1",
                "created_at": "2026-05-20T09:00:00+00:00",
            }],
            "total": 1,
            "generated_at": "2026-05-20T15:00:00+00:00",
            "threshold": 0.10,
            "window_start": "2026-05-19T15:00:00+00:00",
        }),
    }))
    data, err = api.get_alerts()
    assert err is None
    assert data["total"] == 1
    assert data["items"][0]["type"] == "triage_severe"


def test_get_alerts_passes_severity_param():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={
            "items": [], "total": 0,
            "generated_at": "2026-05-20T15:00:00+00:00",
            "threshold": 0.10,
            "window_start": "2026-05-19T15:00:00+00:00",
        })

    api = _make_client(handler)
    data, err = api.get_alerts(severity="critical")
    assert err is None
    assert captured["params"] == {"severity": "critical"}


def test_get_alerts_passes_since_param():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={
            "items": [], "total": 0,
            "generated_at": "2026-05-20T15:00:00+00:00",
            "threshold": 0.10,
            "window_start": "2026-05-01T00:00:00+00:00",
        })

    api = _make_client(handler)
    data, err = api.get_alerts(since="2026-05-01T00:00:00Z")
    assert err is None
    assert captured["params"]["since"] == "2026-05-01T00:00:00Z"


def test_get_alerts_maps_422():
    api = _make_client(_json_handler({
        "/api/v1/alerts": (422, {"detail": "invalid severity"}),
    }))
    data, err = api.get_alerts(severity="banana")
    assert data is None
    assert err is not None
    assert err.kind == "validation"


def test_get_alerts_maps_503():
    api = _make_client(_json_handler({
        "/api/v1/alerts": (503, {"detail": "mongo unreachable"}),
    }))
    data, err = api.get_alerts()
    assert err is not None
    assert err.kind == "unavailable"


def test_get_daily_report_maps_200():
    api = _make_client(_json_handler({
        "/api/v1/reports/daily": (200, {
            "date": "2026-05-20",
            "generated_at": "2026-05-20T15:00:00+00:00",
            "pipeline": {"runs_in_day": 1, "failed_in_day": 0, "last_run_of_day": None},
            "quality": {},
            "counts": {"patients_total": 0, "admissions_total": 0, "radiographies_total": 0},
            "triage": {"grave": 0, "medio": 0, "leve": 0, "in_day_total": 0},
            "alerts": [],
        }),
    }))
    data, err = api.get_daily_report(date="2026-05-20")
    assert err is None
    assert data["date"] == "2026-05-20"


def test_get_daily_report_passes_date_param():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={
            "date": "2026-05-20",
            "generated_at": "2026-05-20T15:00:00+00:00",
            "pipeline": {}, "quality": {}, "counts": {}, "triage": {},
            "alerts": [],
        })

    api = _make_client(handler)
    api.get_daily_report(date="2026-05-20")
    assert captured["params"] == {"date": "2026-05-20"}


def test_get_daily_report_maps_422():
    api = _make_client(_json_handler({
        "/api/v1/reports/daily": (422, {"detail": "invalid date"}),
    }))
    data, err = api.get_daily_report(date="bad")
    assert err is not None
    assert err.kind == "validation"
