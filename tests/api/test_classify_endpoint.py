"""Tests for the classification endpoints.

We mock the predictor and MinIO client (no real TF model needed at test
time) but use a real MongoDB for the persistence side, so the test
exercises the writer + reader contracts end-to-end.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

pymongo = pytest.importorskip("pymongo")
fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from minio.error import S3Error

from src.api.main import build_app
from src.pipeline.storage.mongo_writer import MongoWriter


TEST_DB_NAME = "hospital_test_classify"


# === Helpers =========================================================


class _FakePrediction:
    def __init__(self, predicted_class, probabilities, model_version):
        self.predicted_class = predicted_class
        self.probabilities = probabilities
        self.model_version = model_version


def _make_predictor(return_class: str = "Normal"):
    """Return a mock Predictor that returns a known result."""
    predictor = MagicMock()
    predictor.model_version = "test-v1.0"
    predictor.predict.return_value = _FakePrediction(
        predicted_class=return_class,
        probabilities={"Normal": 0.7, "Pneumonia": 0.2, "COVID-19": 0.1},
        model_version="test-v1.0",
    )
    return predictor


def _make_minio_with_bytes(image_bytes: bytes):
    minio = MagicMock()
    minio.download_bytes.return_value = image_bytes
    return minio


def _make_minio_missing_key():
    minio = MagicMock()
    err = S3Error(
        code="NoSuchKey",
        message="not found",
        resource="x",
        request_id="r",
        host_id="h",
        response=MagicMock(),
    )
    minio.download_bytes.side_effect = err
    return minio


# === Fixtures =======================================================


@pytest.fixture
def mongo_writer():
    w = MongoWriter(
        host=os.environ["MONGO_HOST"],
        port=int(os.environ.get("MONGO_PORT", "27017")),
        db_name=TEST_DB_NAME,
    )
    w.db.patients.drop()
    yield w
    w.db.patients.drop()
    w.close()


@pytest.fixture
def app_with_predictor(mongo_writer):
    """App with a working predictor + mongo writer/reader. MinIO injected per-test."""
    app = build_app(mongo_db_name=TEST_DB_NAME, pipeline_launcher=None)
    app.state.predictor = _make_predictor()
    # Replace the real mongo_writer (which the lifespan would have built
    # against the real env) with our test-scoped one so writes land in
    # the test database.
    if hasattr(app.state, "mongo_writer"):
        try:
            app.state.mongo_writer.close()
        except Exception:
            pass
    app.state.mongo_writer = mongo_writer
    return app


# === Tests POST /classify ===========================================


def test_classify_returns_503_when_no_predictor(mongo_writer):
    app = build_app(mongo_db_name=TEST_DB_NAME, pipeline_launcher=None)
    app.state.predictor = None
    app.state.mongo_writer = mongo_writer
    client = TestClient(app)

    response = client.post(
        "/api/v1/radiographies/classify",
        json={"minio_object_key": "HOSP-1/x.png"},
    )

    assert response.status_code == 503
    assert "not loaded" in response.json()["detail"].lower()


def test_classify_returns_422_when_key_is_empty(app_with_predictor):
    client = TestClient(app_with_predictor)

    response = client.post(
        "/api/v1/radiographies/classify",
        json={"minio_object_key": ""},
    )

    assert response.status_code == 422


def test_classify_returns_404_when_minio_key_missing(app_with_predictor, mongo_writer):
    mongo_writer.bulk_upsert_patients([{"external_id": "HOSP-1", "name": "X"}])
    mongo_writer.add_radiography_to_patient("HOSP-1", {"minio_object_key": "HOSP-1/x.png"})
    app_with_predictor.state.minio_client = _make_minio_missing_key()
    client = TestClient(app_with_predictor)

    response = client.post(
        "/api/v1/radiographies/classify",
        json={"minio_object_key": "HOSP-1/x.png"},
    )

    assert response.status_code == 404
    assert "minio" in response.json()["detail"].lower()


def test_classify_returns_422_when_image_is_corrupt(app_with_predictor, mongo_writer):
    from src.ml.preprocessing import InvalidImageError

    mongo_writer.bulk_upsert_patients([{"external_id": "HOSP-1", "name": "X"}])
    mongo_writer.add_radiography_to_patient("HOSP-1", {"minio_object_key": "HOSP-1/x.png"})

    bad_predictor = MagicMock()
    bad_predictor.predict.side_effect = InvalidImageError("Image too small (1x1)")
    app_with_predictor.state.predictor = bad_predictor
    app_with_predictor.state.minio_client = _make_minio_with_bytes(b"corrupt-bytes")
    client = TestClient(app_with_predictor)

    response = client.post(
        "/api/v1/radiographies/classify",
        json={"minio_object_key": "HOSP-1/x.png"},
    )

    assert response.status_code == 422
    assert "small" in response.json()["detail"].lower() or "cannot" in response.json()["detail"].lower()


def test_classify_returns_404_when_radiography_not_in_any_patient(
    app_with_predictor, mongo_writer,
):
    """The key downloads fine but no patient owns it → can't persist."""
    app_with_predictor.state.minio_client = _make_minio_with_bytes(b"\x89PNG...")
    client = TestClient(app_with_predictor)

    response = client.post(
        "/api/v1/radiographies/classify",
        json={"minio_object_key": "orphan/x.png"},
    )

    assert response.status_code == 404
    assert "patient" in response.json()["detail"].lower()


def test_classify_succeeds_and_persists(app_with_predictor, mongo_writer):
    mongo_writer.bulk_upsert_patients([{"external_id": "HOSP-1", "name": "X"}])
    mongo_writer.add_radiography_to_patient("HOSP-1", {"minio_object_key": "HOSP-1/x.png"})
    app_with_predictor.state.predictor = _make_predictor("COVID-19")
    app_with_predictor.state.minio_client = _make_minio_with_bytes(b"valid-png-bytes")
    client = TestClient(app_with_predictor)

    response = client.post(
        "/api/v1/radiographies/classify",
        json={"minio_object_key": "HOSP-1/x.png"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["predicted_class"] == "COVID-19"
    assert body["minio_object_key"] == "HOSP-1/x.png"
    assert body["model_version"] == "test-v1.0"
    assert set(body["probabilities"].keys()) == {"Normal", "Pneumonia", "COVID-19"}

    # Persisted in Mongo
    doc = mongo_writer.db.patients.find_one({"external_id": "HOSP-1"})
    radio = doc["radiographies"][0]
    assert radio["classification"]["predicted_class"] == "COVID-19"
    assert radio["classification"]["model_version"] == "test-v1.0"


# === Tests GET /classification ======================================


def test_get_classification_returns_persisted(app_with_predictor, mongo_writer):
    mongo_writer.bulk_upsert_patients([{"external_id": "HOSP-2", "name": "Y"}])
    mongo_writer.add_radiography_to_patient("HOSP-2", {"minio_object_key": "HOSP-2/x.png"})
    mongo_writer.set_radiography_classification("HOSP-2/x.png", {
        "predicted_class": "Pneumonia",
        "probabilities": {"Normal": 0.1, "Pneumonia": 0.8, "COVID-19": 0.1},
        "predicted_at": datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
        "model_version": "test-v1.0",
    })

    client = TestClient(app_with_predictor)
    response = client.get(
        "/api/v1/radiographies/classification",
        params={"key": "HOSP-2/x.png"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["predicted_class"] == "Pneumonia"
    assert body["minio_object_key"] == "HOSP-2/x.png"


def test_get_classification_returns_404_when_not_classified(
    app_with_predictor, mongo_writer,
):
    mongo_writer.bulk_upsert_patients([{"external_id": "HOSP-3", "name": "Z"}])
    mongo_writer.add_radiography_to_patient("HOSP-3", {"minio_object_key": "HOSP-3/x.png"})

    client = TestClient(app_with_predictor)
    response = client.get(
        "/api/v1/radiographies/classification",
        params={"key": "HOSP-3/x.png"},
    )

    assert response.status_code == 404


def test_get_classification_returns_404_for_missing_key(app_with_predictor):
    client = TestClient(app_with_predictor)
    response = client.get(
        "/api/v1/radiographies/classification",
        params={"key": "no/such/key.png"},
    )

    assert response.status_code == 404


def test_get_classification_returns_422_for_empty_key(app_with_predictor):
    client = TestClient(app_with_predictor)
    response = client.get(
        "/api/v1/radiographies/classification",
        params={"key": ""},
    )

    assert response.status_code == 422
