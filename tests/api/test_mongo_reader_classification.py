"""Tests for MongoReader.get_radiography_classification."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

pymongo = pytest.importorskip("pymongo")

from src.api.mongo_reader import MongoReader
from src.pipeline.storage.mongo_writer import MongoWriter


TEST_DB_NAME = "hospital_test_classification_reader"


@pytest.fixture
def writer():
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
def reader():
    r = MongoReader(
        host=os.environ["MONGO_HOST"],
        port=int(os.environ.get("MONGO_PORT", "27017")),
        db_name=TEST_DB_NAME,
    )
    yield r
    r.close()


def _payload(cls: str = "Normal") -> dict:
    return {
        "predicted_class": cls,
        "probabilities": {"Normal": 0.7, "Pneumonia": 0.2, "COVID-19": 0.1},
        "predicted_at": datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
        "model_version": "test-v1.0",
    }


def test_get_classification_returns_persisted_object(writer, reader):
    writer.bulk_upsert_patients([{"external_id": "HOSP-R1", "name": "Ana"}])
    writer.add_radiography_to_patient("HOSP-R1", {"minio_object_key": "HOSP-R1/x.png"})
    writer.set_radiography_classification("HOSP-R1/x.png", _payload("COVID-19"))

    result = reader.get_radiography_classification("HOSP-R1/x.png")

    assert result is not None
    assert result["predicted_class"] == "COVID-19"
    assert "probabilities" in result
    assert result["model_version"] == "test-v1.0"


def test_get_classification_returns_none_when_not_classified(writer, reader):
    writer.bulk_upsert_patients([{"external_id": "HOSP-R2", "name": "Bob"}])
    writer.add_radiography_to_patient("HOSP-R2", {"minio_object_key": "HOSP-R2/x.png"})

    result = reader.get_radiography_classification("HOSP-R2/x.png")

    assert result is None


def test_get_classification_returns_none_for_missing_key(writer, reader):
    result = reader.get_radiography_classification("no/such/key.png")

    assert result is None
