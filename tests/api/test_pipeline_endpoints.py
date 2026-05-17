"""Integration tests for the pipeline endpoints (POST /trigger, GET /runs...).

After ADR-004, pipeline_runs + data_quality_summary live in SQLite, so
these tests seed data via SqlWriter rather than MongoDB.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pymongo = pytest.importorskip("pymongo")
fastapi = pytest.importorskip("fastapi")
sqlalchemy = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient

from src.api.main import build_app
from src.api.sql_reader import SqlReader
from src.pipeline.storage.mongo_writer import MongoWriter
from src.pipeline.storage.sql_engine import (
    create_all_tables,
    get_sql_engine_from_env,
)
from src.pipeline.storage.sql_writer import SqlWriter


TEST_DB_NAME = "hospital_test_t10_pipeline"


@pytest.fixture
def mongo_writer():
    w = MongoWriter(
        host=os.environ["MONGO_HOST"],
        port=int(os.environ.get("MONGO_PORT", "27017")),
        db_name=TEST_DB_NAME,
    )
    w.db.patients.drop()
    w.db.rejected_records.drop()
    yield w
    w.db.patients.drop()
    w.db.rejected_records.drop()
    w.close()


@pytest.fixture
def sql_writer(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test_endpoints.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    engine = get_sql_engine_from_env()
    create_all_tables(engine)
    writer = SqlWriter(engine)
    yield writer
    writer.close()


@pytest.fixture
def client(mongo_writer: MongoWriter, sql_writer: SqlWriter) -> TestClient:
    app = build_app(mongo_db_name=TEST_DB_NAME, pipeline_launcher=None)
    # Override the SQLite reader to point at the test database. `build_app`
    # already constructed one from SQLITE_PATH via the monkeypatched env, but
    # we re-bind defensively so the test is robust to import ordering.
    app.state.sql_reader = SqlReader(sql_writer._engine)
    return TestClient(app)


def _finish(writer: SqlWriter, run_id: str, *, status: str,
            processed: int = 0, rejected: int = 0,
            error_message: str | None = None) -> None:
    writer.finish_pipeline_run(
        run_id,
        status=status,
        stats={
            "records_processed": processed,
            "records_rejected": rejected,
            "images_processed": 0,
        },
        error_message=error_message,
    )


def test_list_runs_empty_when_no_runs(client: TestClient):
    response = client.get("/api/v1/pipeline/runs")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_list_runs_returns_stored_runs_newest_first(
    client: TestClient, sql_writer: SqlWriter
):
    older = sql_writer.start_pipeline_run(trigger_type="manual")
    _finish(sql_writer, older, status="success", processed=100, rejected=5)
    newer = sql_writer.start_pipeline_run(trigger_type="manual")
    _finish(sql_writer, newer, status="failed", error_message="something broke")

    response = client.get("/api/v1/pipeline/runs")
    assert response.status_code == 200
    body = response.json()
    items = body["items"]
    assert body["total"] == 2
    assert len(items) == 2
    # Newest first
    assert items[0]["status"] == "failed"
    assert items[1]["status"] == "success"
    assert items[1]["records_processed"] == 100
    # IDs are UUID strings, not 24-char ObjectId hex
    assert len(items[0]["id"]) == 36


def test_pipeline_status_returns_last_run(
    client: TestClient, sql_writer: SqlWriter
):
    run_id = sql_writer.start_pipeline_run(trigger_type="watcher")
    _finish(sql_writer, run_id, status="success", processed=42)

    response = client.get("/api/v1/pipeline/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["records_processed"] == 42
    assert body["trigger_type"] == "watcher"


def test_pipeline_status_returns_404_when_no_runs(client: TestClient):
    response = client.get("/api/v1/pipeline/status")
    assert response.status_code == 404


def test_quality_summary_returns_empty_when_no_data(client: TestClient):
    response = client.get("/api/v1/pipeline/quality-summary")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_quality_summary_returns_latest_snapshot(
    client: TestClient, sql_writer: SqlWriter
):
    run_id = sql_writer.start_pipeline_run(trigger_type="manual")
    sql_writer.write_quality_summary(run_id, [
        {"dimension": "patients", "total": 100, "valid": 95, "rejected": 5, "rejection_rate": 0.05},
        {"dimension": "admissions", "total": 80, "valid": 78, "rejected": 2, "rejection_rate": 0.025},
    ])

    response = client.get("/api/v1/pipeline/quality-summary")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    by_dim = {row["dimension"]: row for row in items}
    assert by_dim["patients"]["rejected"] == 5
    assert by_dim["admissions"]["total"] == 80


def test_quality_summary_history_filters_by_dimension(
    client: TestClient, sql_writer: SqlWriter
):
    r1 = sql_writer.start_pipeline_run(trigger_type="manual")
    sql_writer.write_quality_summary(r1, [
        {"dimension": "patients", "total": 100, "valid": 95, "rejected": 5, "rejection_rate": 0.05},
        {"dimension": "admissions", "total": 80, "valid": 78, "rejected": 2, "rejection_rate": 0.025},
    ])
    r2 = sql_writer.start_pipeline_run(trigger_type="watcher")
    sql_writer.write_quality_summary(r2, [
        {"dimension": "patients", "total": 110, "valid": 100, "rejected": 10, "rejection_rate": 0.0909},
    ])

    response = client.get(
        "/api/v1/pipeline/quality-summary/history?dimension=patients&limit=10"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dimension"] == "patients"
    assert all(item["dimension"] == "patients" for item in body["items"])
    assert len(body["items"]) == 2


def test_quality_summary_history_total_reflects_all_rows_not_just_page(
    client: TestClient, sql_writer: SqlWriter
):
    """Regression: `total` must be the count of ALL rows for the dimension,
    not the size of the returned page. Caller-driven pagination needs this
    to know how many more pages exist.
    """
    # Seed 4 patients rows + 1 admissions row across multiple runs
    for _ in range(4):
        rid = sql_writer.start_pipeline_run(trigger_type="manual")
        sql_writer.write_quality_summary(rid, [
            {"dimension": "patients", "total": 1, "valid": 1, "rejected": 0,
             "rejection_rate": 0.0},
        ])
    rid_extra = sql_writer.start_pipeline_run(trigger_type="watcher")
    sql_writer.write_quality_summary(rid_extra, [
        {"dimension": "admissions", "total": 1, "valid": 1, "rejected": 0,
         "rejection_rate": 0.0},
    ])

    # Request just 1 item per page — total must still report all 4
    response = client.get(
        "/api/v1/pipeline/quality-summary/history?dimension=patients&limit=1"
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["total"] == 4, (
        f"total deberia ser 4 (todas las filas de 'patients'), no {body['total']}"
    )

    # And for a dimension with no rows yet, total is 0 (not a crash)
    empty = client.get(
        "/api/v1/pipeline/quality-summary/history?dimension=images&limit=10"
    )
    assert empty.status_code == 200
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []
