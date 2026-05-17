"""Tests for GET /api/v1/model/evaluation.

The endpoint reads `metrics.json` from disk and returns it. 503 when
the file is missing (no evaluation report yet); 500 when the file is
corrupt.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pymongo = pytest.importorskip("pymongo")
fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from src.api.main import build_app


TEST_DB_NAME = "hospital_test_model_eval"


@pytest.fixture
def app(monkeypatch):
    """Build app with pipeline_launcher disabled to avoid Spark setup."""
    app = build_app(mongo_db_name=TEST_DB_NAME, pipeline_launcher=None)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _write_valid_metrics(path: Path) -> dict:
    """Write a minimal metrics.json mirroring src/ml/evaluate.py output."""
    payload = {
        "accuracy": 0.8719,
        "macro_f1": 0.8456,
        "per_class": {
            "Normal":    {"precision": 0.90, "recall": 0.93, "f1": 0.91, "support": 1019},
            "Pneumonia": {"precision": 0.83, "recall": 0.93, "f1": 0.88, "support": 135},
            "COVID-19":  {"precision": 0.81, "recall": 0.70, "f1": 0.75, "support": 361},
        },
        "confusion_matrix": [[944, 17, 58], [7, 126, 2], [101, 9, 251]],
        "hyperparameters": {"seed": 42, "epochs_max": 35, "learning_rate": 0.0001},
        "model_version": "v1.0-test",
        "classes": ["Normal", "Pneumonia", "COVID-19"],
    }
    path.write_text(json.dumps(payload))
    return payload


def test_evaluation_returns_200_with_metrics(client, tmp_path, monkeypatch):
    metrics_path = tmp_path / "metrics.json"
    payload = _write_valid_metrics(metrics_path)
    monkeypatch.setenv("MODEL_EVALUATION_PATH", str(metrics_path))

    response = client.get("/api/v1/model/evaluation")

    assert response.status_code == 200
    body = response.json()
    assert body["accuracy"] == payload["accuracy"]
    assert body["macro_f1"] == payload["macro_f1"]
    assert set(body["per_class"].keys()) == {"Normal", "Pneumonia", "COVID-19"}
    assert body["confusion_matrix"] == payload["confusion_matrix"]
    assert body["model_version"] == payload["model_version"]


def test_evaluation_returns_503_when_file_missing(client, tmp_path, monkeypatch):
    missing_path = tmp_path / "does_not_exist.json"
    monkeypatch.setenv("MODEL_EVALUATION_PATH", str(missing_path))

    response = client.get("/api/v1/model/evaluation")

    assert response.status_code == 503
    detail = response.json()["detail"].lower()
    assert "not available" in detail or "missing" in detail


def test_evaluation_returns_500_when_json_corrupt(client, tmp_path, monkeypatch):
    corrupt_path = tmp_path / "metrics.json"
    corrupt_path.write_text("not a valid json {{{{")
    monkeypatch.setenv("MODEL_EVALUATION_PATH", str(corrupt_path))

    response = client.get("/api/v1/model/evaluation")

    assert response.status_code == 500
    assert "corrupt" in response.json()["detail"].lower()


def test_evaluation_response_has_canonical_class_order(client, tmp_path, monkeypatch):
    """Sanity: the response includes `classes` in the project's canonical order."""
    metrics_path = tmp_path / "metrics.json"
    _write_valid_metrics(metrics_path)
    monkeypatch.setenv("MODEL_EVALUATION_PATH", str(metrics_path))

    response = client.get("/api/v1/model/evaluation")

    assert response.status_code == 200
    assert response.json()["classes"] == ["Normal", "Pneumonia", "COVID-19"]
