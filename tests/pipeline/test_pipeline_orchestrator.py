"""Tests for PipelineOrchestrator: end-to-end coordination of the ETL flow."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

pyspark = pytest.importorskip("pyspark", reason="PySpark not installed")

from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.spark_session import get_spark_session
from src.pipeline.storage.mongo_writer import MongoWriter


TEST_DB_NAME = "hospital_test_t9"


@pytest.fixture(scope="module")
def spark():
    session = get_spark_session(app_name="test-orchestrator", master="local[2]")
    yield session
    session.stop()


@pytest.fixture
def mongo_writer():
    import os
    w = MongoWriter(
        host=os.environ["MONGO_HOST"],
        port=int(os.environ.get("MONGO_PORT", "27017")),
        db_name=TEST_DB_NAME,
    )
    w.db.patients.drop()
    w.db.pipeline_runs.drop()
    w.db.rejected_records.drop()
    yield w
    w.db.patients.drop()
    w.db.pipeline_runs.drop()
    w.db.rejected_records.drop()
    w.close()


@pytest.fixture
def orchestrator(spark, mongo_writer) -> PipelineOrchestrator:
    return PipelineOrchestrator(spark=spark, mongo_writer=mongo_writer)


def _write_patients_csv(path: Path, rows: list[list[str]]) -> None:
    header = ["external_id", "name", "birth_date", "gender", "blood_type"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _write_admissions_csv(path: Path, rows: list[list[str]]) -> None:
    header = [
        "patient_external_id", "admission_date", "discharge_date",
        "department", "diagnosis_code", "diagnosis_description", "status",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_orchestrator_runs_full_etl_and_writes_to_mongodb(
    orchestrator: PipelineOrchestrator, mongo_writer: MongoWriter, tmp_path: Path
):
    patients_csv = tmp_path / "patients.csv"
    admissions_csv = tmp_path / "admissions.csv"

    _write_patients_csv(patients_csv, [
        ["HOSP-000001", "Ana Garcia", "1980-05-12", "F", "A+"],
        ["HOSP-000002", "Luis Perez", "1975-03-22", "M", "O-"],
    ])
    _write_admissions_csv(admissions_csv, [
        ["HOSP-000001", "2025-03-10", "2025-03-15", "UCI", "J18.9",
         "Pneumonia", "discharged"],
        ["HOSP-000001", "2025-06-01", "", "Urgencias", "U07.1",
         "COVID-19", "admitted"],
        ["HOSP-000002", "2025-04-05", "", "Cardiologia", "I21.9",
         "Heart attack", "admitted"],
    ])

    result = orchestrator.run_from_files(
        patients_csv=patients_csv,
        admissions_csv=admissions_csv,
    )

    assert result.status == "success"
    assert mongo_writer.db.patients.count_documents({}) == 2

    ana = mongo_writer.db.patients.find_one({"external_id": "HOSP-000001"})
    assert ana["name"] == "Ana Garcia"
    assert ana["age"] is not None
    assert len(ana["admissions"]) == 2
    assert {adm["diagnosis_category"] for adm in ana["admissions"]} == {
        "Pneumonia", "COVID-19"
    }


def test_orchestrator_stores_rejected_rows(
    orchestrator: PipelineOrchestrator, mongo_writer: MongoWriter, tmp_path: Path
):
    patients_csv = tmp_path / "patients.csv"
    admissions_csv = tmp_path / "admissions.csv"

    _write_patients_csv(patients_csv, [
        ["HOSP-000001", "Ana", "1980-05-12", "F", "A+"],
        ["HOSP-000002", "", "1975-03-22", "M", "O-"],          # rejected: missing name
        ["HOSP-000003", "Luis", "12/05/1980", "M", "B+"],      # rejected: bad birth_date
    ])
    _write_admissions_csv(admissions_csv, [
        ["HOSP-000001", "2025-03-10", "", "UCI", "J18.9", "Pneumonia", "admitted"],
    ])

    result = orchestrator.run_from_files(
        patients_csv=patients_csv,
        admissions_csv=admissions_csv,
    )

    assert result.records_rejected >= 2
    rejected_docs = list(mongo_writer.db.rejected_records.find({"pipeline_run_id": result.run_id}))
    reasons = {doc["rejection_reason"] for doc in rejected_docs}
    assert "missing name" in reasons
    assert "invalid birth_date" in reasons


def test_orchestrator_is_idempotent_on_same_input(
    orchestrator: PipelineOrchestrator, mongo_writer: MongoWriter, tmp_path: Path
):
    """CA-6: running the pipeline twice with the same data must not duplicate rows."""
    patients_csv = tmp_path / "patients.csv"
    admissions_csv = tmp_path / "admissions.csv"

    _write_patients_csv(patients_csv, [
        ["HOSP-000001", "Ana", "1980-05-12", "F", "A+"],
    ])
    _write_admissions_csv(admissions_csv, [
        ["HOSP-000001", "2025-03-10", "", "UCI", "J18.9", "Pneumonia", "admitted"],
    ])

    orchestrator.run_from_files(patients_csv=patients_csv, admissions_csv=admissions_csv)
    orchestrator.run_from_files(patients_csv=patients_csv, admissions_csv=admissions_csv)

    assert mongo_writer.db.patients.count_documents({}) == 1
    ana = mongo_writer.db.patients.find_one({"external_id": "HOSP-000001"})
    assert len(ana["admissions"]) == 1


def test_orchestrator_registers_pipeline_run_with_stats(
    orchestrator: PipelineOrchestrator, mongo_writer: MongoWriter, tmp_path: Path
):
    patients_csv = tmp_path / "patients.csv"
    admissions_csv = tmp_path / "admissions.csv"

    _write_patients_csv(patients_csv, [
        ["HOSP-000001", "Ana", "1980-05-12", "F", "A+"],
        ["HOSP-000002", "Luis", "1975-03-22", "M", "O-"],
    ])
    _write_admissions_csv(admissions_csv, [
        ["HOSP-000001", "2025-03-10", "", "UCI", "J18.9", "Pneumonia", "admitted"],
    ])

    result = orchestrator.run_from_files(
        patients_csv=patients_csv,
        admissions_csv=admissions_csv,
        trigger_type="manual",
    )

    run_doc = mongo_writer.db.pipeline_runs.find_one({"_id": result.run_id})
    assert run_doc is not None
    assert run_doc["status"] == "success"
    assert run_doc["trigger_type"] == "manual"
    assert run_doc["finished_at"] is not None
    assert run_doc["records_processed"] >= 2


def test_orphan_admissions_are_rejected_with_clear_reason(
    orchestrator: PipelineOrchestrator, mongo_writer: MongoWriter, tmp_path: Path
):
    """Admissions whose patient_external_id does not exist in this batch must
    end up in rejected_records with motive 'orphan patient_external_id'."""
    patients_csv = tmp_path / "patients.csv"
    admissions_csv = tmp_path / "admissions.csv"

    _write_patients_csv(patients_csv, [
        ["HOSP-000001", "Ana", "1980-05-12", "F", "A+"],
    ])
    _write_admissions_csv(admissions_csv, [
        ["HOSP-000001", "2025-03-10", "", "UCI", "J18.9", "Pneumonia", "admitted"],
        # Format is valid (HOSP-NNNNNN) but the patient does not exist
        ["HOSP-999999", "2025-04-05", "", "Urgencias", "I21.9", "MI", "admitted"],
    ])

    result = orchestrator.run_from_files(
        patients_csv=patients_csv,
        admissions_csv=admissions_csv,
    )

    orphan_docs = list(mongo_writer.db.rejected_records.find({
        "pipeline_run_id": result.run_id,
        "rejection_reason": "orphan patient_external_id",
    }))
    assert len(orphan_docs) == 1
    assert orphan_docs[0]["raw_data"]["patient_external_id"] == "HOSP-999999"

    # The orphan admission must NOT be embedded in any patient
    ana = mongo_writer.db.patients.find_one({"external_id": "HOSP-000001"})
    assert len(ana["admissions"]) == 1
    assert ana["admissions"][0]["patient_external_id"] == "HOSP-000001"


def test_stats_count_only_persisted_records_not_orphans(
    orchestrator: PipelineOrchestrator, mongo_writer: MongoWriter, tmp_path: Path
):
    """records_processed must reflect what actually got persisted, not the raw input."""
    patients_csv = tmp_path / "patients.csv"
    admissions_csv = tmp_path / "admissions.csv"

    _write_patients_csv(patients_csv, [
        ["HOSP-000001", "Ana", "1980-05-12", "F", "A+"],
    ])
    _write_admissions_csv(admissions_csv, [
        ["HOSP-000001", "2025-03-10", "", "UCI", "J18.9", "Pneumonia", "admitted"],
        ["HOSP-999998", "2025-04-05", "", "Urgencias", "I21.9", "MI", "admitted"],
        ["HOSP-999999", "2025-05-05", "", "UCI", "J18.9", "Pneumonia", "admitted"],
    ])

    result = orchestrator.run_from_files(
        patients_csv=patients_csv,
        admissions_csv=admissions_csv,
    )

    # 1 patient + 1 valid admission embedded = 2 persisted
    assert result.records_processed == 2
    # 2 orphans went to rejected_records
    assert result.records_rejected == 2


def test_orchestrator_marks_run_as_failed_on_exception(
    orchestrator: PipelineOrchestrator, mongo_writer: MongoWriter, tmp_path: Path
):
    """CB-5: if a downstream step fails, the run must be flagged as failed."""
    missing_csv = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError):
        orchestrator.run_from_files(
            patients_csv=missing_csv,
            admissions_csv=missing_csv,
        )

    # The run should have been started and marked as failed
    runs = list(mongo_writer.db.pipeline_runs.find({}))
    failed = [r for r in runs if r["status"] == "failed"]
    assert len(failed) >= 1
    assert failed[-1]["error_message"] is not None
