"""End-to-end test of the radiography classification flow.

Skipped cleanly when the API reports `predictor_loaded=False` (no model
artefact on disk) so the suite runs green even before T9 (real training)
has been executed.

The fixture image is at least 32x32 (CB-7 forbids smaller). We deliberately
do NOT reuse the 17 dummy PNGs of the bootstrap because they are 1x1.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import pytest
from PIL import Image

pymongo = pytest.importorskip("pymongo")


E2E_PATIENT_ID = f"HOSP-E2E-{uuid.uuid4().hex[:6].upper()}"


def _png_64x64_bytes(color: int = 128) -> bytes:
    img = Image.new("L", (64, 64), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def predictor_ready(http, api_url):
    """Skip the test cleanly if the API reports no model loaded."""
    r = http.get(f"{api_url}/api/v1/health")
    if r.status_code != 200:
        pytest.skip(f"API health endpoint returned {r.status_code}")
    body = r.json()
    if not body.get("predictor_loaded", False):
        pytest.skip(
            "API reports predictor_loaded=False — train the model with "
            "`docker compose run --rm pipeline python -m src.ml.train` first"
        )


@pytest.fixture
def valid_radiography(mongo_db, minio_client):
    """Insert a patient + upload a valid PNG to MinIO, yield the key.

    Cleanup removes the patient and the MinIO object after the test.
    """
    radiography_key = f"{E2E_PATIENT_ID}/sample.png"
    image_bytes = _png_64x64_bytes()

    # Upload to MinIO via the raw minio client (the e2e fixture provides it)
    minio_client.put_object(
        "radiographies",
        radiography_key,
        data=io.BytesIO(image_bytes),
        length=len(image_bytes),
        content_type="image/png",
    )

    # Insert patient with the radiography reference
    mongo_db.patients.insert_one({
        "external_id": E2E_PATIENT_ID,
        "name": "E2E Test Patient",
        "radiographies": [{
            "minio_object_key": radiography_key,
            "original_filename": "sample.png",
            "file_size_bytes": len(image_bytes),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "classification": None,
        }],
    })

    yield radiography_key

    # Cleanup
    try:
        minio_client.remove_object("radiographies", radiography_key)
    except Exception:
        pass
    mongo_db.patients.delete_one({"external_id": E2E_PATIENT_ID})


def test_classify_endpoint_returns_prediction_and_persists(
    http, api_url, mongo_db, predictor_ready, valid_radiography,
):
    """POST /classify → 200 with classification body; persisted in Mongo."""
    key = valid_radiography

    response = http.post(
        f"{api_url}/api/v1/radiographies/classify",
        json={"minio_object_key": key},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["minio_object_key"] == key
    assert body["predicted_class"] in {"Normal", "Pneumonia", "COVID-19"}
    assert set(body["probabilities"].keys()) == {"Normal", "Pneumonia", "COVID-19"}
    assert abs(sum(body["probabilities"].values()) - 1.0) < 1e-3
    assert body["model_version"]
    assert body["decision_rule"] == "covid_threshold_0.35"

    # Persisted in Mongo (decision rule travels with the row)
    doc = mongo_db.patients.find_one({"external_id": E2E_PATIENT_ID})
    radio = doc["radiographies"][0]
    assert radio["classification"]["predicted_class"] == body["predicted_class"]
    assert radio["classification"]["decision_rule"] == "covid_threshold_0.35"


def test_get_classification_after_classify(
    http, api_url, predictor_ready, valid_radiography,
):
    """After POST /classify, GET /classification returns the same payload."""
    key = valid_radiography

    post_resp = http.post(
        f"{api_url}/api/v1/radiographies/classify",
        json={"minio_object_key": key},
    )
    assert post_resp.status_code == 200
    post_body = post_resp.json()

    get_resp = http.get(
        f"{api_url}/api/v1/radiographies/classification",
        params={"key": key},
    )
    assert get_resp.status_code == 200
    get_body = get_resp.json()

    assert get_body["minio_object_key"] == key
    assert get_body["predicted_class"] == post_body["predicted_class"]
    assert get_body["model_version"] == post_body["model_version"]
    assert get_body["decision_rule"] == post_body["decision_rule"]


def test_get_classification_returns_404_before_classify(
    http, api_url, predictor_ready, valid_radiography,
):
    """A freshly uploaded radiography with no classification yet → 404."""
    key = valid_radiography

    response = http.get(
        f"{api_url}/api/v1/radiographies/classification",
        params={"key": key},
    )

    assert response.status_code == 404


def test_classify_returns_404_for_missing_minio_key(
    http, api_url, predictor_ready,
):
    """A key that does not exist anywhere → 404 from the MinIO download step."""
    response = http.post(
        f"{api_url}/api/v1/radiographies/classify",
        json={"minio_object_key": "no/such/key.png"},
    )

    assert response.status_code == 404
