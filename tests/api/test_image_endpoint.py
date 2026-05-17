"""Tests for GET /api/v1/radiographies/image?key=...

The image endpoint is a thin proxy of MinIO bytes used by the dashboard
to render radiographies in the Classifier view. It does NOT touch Mongo
nor classify; it just returns `image/png` bytes.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

pymongo = pytest.importorskip("pymongo")
fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from minio.error import S3Error

from src.api.main import build_app


TEST_DB_NAME = "hospital_test_image_endpoint"


@pytest.fixture
def app_with_minio_mock():
    """Build app with mocked MinIO client; mongo_writer not needed by this endpoint."""
    app = build_app(mongo_db_name=TEST_DB_NAME, pipeline_launcher=None)
    app.state.minio_client = MagicMock()
    return app


def _no_such_key_error() -> S3Error:
    """Construct an S3Error that mimics a missing-key response from MinIO."""
    return S3Error(
        code="NoSuchKey",
        message="The specified key does not exist.",
        resource="x",
        request_id="r",
        host_id="h",
        response=MagicMock(),
    )


def _generic_s3_error() -> S3Error:
    return S3Error(
        code="InternalError",
        message="boom",
        resource="x",
        request_id="r",
        host_id="h",
        response=MagicMock(),
    )


def test_image_returns_png_bytes_and_content_type(app_with_minio_mock):
    png_bytes = b"\x89PNG\r\n\x1a\nFAKE_IMAGE_DATA"
    app_with_minio_mock.state.minio_client.download_bytes.return_value = png_bytes
    client = TestClient(app_with_minio_mock)

    response = client.get(
        "/api/v1/radiographies/image",
        params={"key": "HOSP-000001/HOSP-000001_xray1.png"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == png_bytes
    # The endpoint must call the MinIO client with the radiographies bucket
    app_with_minio_mock.state.minio_client.download_bytes.assert_called_once()


def test_image_returns_404_when_minio_key_missing(app_with_minio_mock):
    app_with_minio_mock.state.minio_client.download_bytes.side_effect = _no_such_key_error()
    client = TestClient(app_with_minio_mock)

    response = client.get(
        "/api/v1/radiographies/image",
        params={"key": "no/such/key.png"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_image_returns_502_on_unexpected_s3_error(app_with_minio_mock):
    app_with_minio_mock.state.minio_client.download_bytes.side_effect = _generic_s3_error()
    client = TestClient(app_with_minio_mock)

    response = client.get(
        "/api/v1/radiographies/image",
        params={"key": "HOSP-000001/HOSP-000001_xray1.png"},
    )

    assert response.status_code == 502
    assert "object storage" in response.json()["detail"].lower()


def test_image_returns_422_when_key_is_empty(app_with_minio_mock):
    client = TestClient(app_with_minio_mock)

    response = client.get("/api/v1/radiographies/image", params={"key": ""})

    assert response.status_code == 422


def test_image_returns_422_when_key_is_missing(app_with_minio_mock):
    client = TestClient(app_with_minio_mock)

    response = client.get("/api/v1/radiographies/image")

    assert response.status_code == 422


def test_image_does_not_touch_mongo(app_with_minio_mock):
    """Sanity: the endpoint must NOT depend on mongo_reader or mongo_writer."""
    png_bytes = b"\x89PNG\r\n\x1a\nDATA"
    app_with_minio_mock.state.minio_client.download_bytes.return_value = png_bytes
    # Wipe mongo_reader/writer to prove the endpoint does not need them
    app_with_minio_mock.state.mongo_reader = None
    app_with_minio_mock.state.mongo_writer = None
    client = TestClient(app_with_minio_mock)

    response = client.get(
        "/api/v1/radiographies/image",
        params={"key": "HOSP-000001/HOSP-000001_xray1.png"},
    )

    assert response.status_code == 200
