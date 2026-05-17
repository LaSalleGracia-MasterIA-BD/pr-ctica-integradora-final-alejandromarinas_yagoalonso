"""Wrapper around pymongo with hospital-specific write operations."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import MongoClient, UpdateOne

from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)


class MongoWriter:
    def __init__(self, host: str, port: int, db_name: str) -> None:
        self._client: MongoClient = MongoClient(host=host, port=port)
        self.db = self._client[db_name]

    def close(self) -> None:
        self._client.close()

    def ping(self) -> bool:
        """Verify the MongoDB server is reachable. Raises on failure."""
        self._client.admin.command("ping")
        return True

    def bulk_upsert_patients(self, records: list[dict]) -> dict[str, int]:
        """Upsert patients by external_id. Safe with empty input."""
        if not records:
            return {"upserted": 0, "modified": 0}

        now = datetime.now(timezone.utc)
        ops = []
        for record in records:
            payload = {**record, "updated_at": now}
            ops.append(
                UpdateOne(
                    {"external_id": record["external_id"]},
                    {
                        "$set": payload,
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            )

        result = self.db.patients.bulk_write(ops, ordered=False)
        stats = {
            "upserted": len(result.upserted_ids),
            "modified": result.modified_count,
        }
        logger.info(
            "Patients bulk upsert: %d upserted, %d modified",
            stats["upserted"],
            stats["modified"],
        )
        return stats

    def bulk_upsert_patients_with_admissions(
        self,
        patients: list[dict],
        admissions: list[dict],
    ) -> dict[str, int]:
        """Upsert patients and embed their admissions as a subdocument array.

        Note: the `admissions` array is fully replaced on each upsert. Callers
        must pass the complete set of admissions per patient in the same batch,
        which matches how our ETL processes whole CSV files at a time. This
        keeps re-runs idempotent (CB-4, CA-6).
        """
        if not patients:
            return {"upserted": 0, "modified": 0}

        grouped: dict[str, list[dict]] = {}
        for admission in admissions:
            pid = admission.get("patient_external_id")
            if pid:
                grouped.setdefault(pid, []).append(admission)

        now = datetime.now(timezone.utc)
        ops = []
        for patient in patients:
            external_id = patient["external_id"]
            patient_admissions = grouped.get(external_id, [])
            payload = {
                **patient,
                "admissions": patient_admissions,
                "updated_at": now,
            }
            ops.append(
                UpdateOne(
                    {"external_id": external_id},
                    {
                        "$set": payload,
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            )

        result = self.db.patients.bulk_write(ops, ordered=False)
        stats = {
            "upserted": len(result.upserted_ids),
            "modified": result.modified_count,
        }
        logger.info(
            "Patients+admissions bulk upsert: %d upserted, %d modified (%d admissions embedded)",
            stats["upserted"],
            stats["modified"],
            len(admissions),
        )
        return stats

    def add_radiography_to_patient(
        self, external_id: str, radiography: dict[str, Any]
    ) -> bool:
        """Add a radiography metadata dict to the patient's array, idempotently.

        Returns True if the patient exists (regardless of whether the entry was
        new or already present), False if no patient with that external_id
        exists. Re-adding the same `minio_object_key` for the same patient is a
        no-op, which is required by CB-4 (running the pipeline twice must not
        create duplicates).
        """
        if self.db.patients.count_documents({"external_id": external_id}, limit=1) == 0:
            return False

        object_key = radiography["minio_object_key"]
        self.db.patients.update_one(
            {
                "external_id": external_id,
                "radiographies.minio_object_key": {"$ne": object_key},
            },
            {
                "$push": {"radiographies": radiography},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )
        return True

    def set_radiography_classification(
        self,
        minio_object_key: str,
        classification: dict[str, Any],
    ) -> bool:
        """Persist a classification result on a specific radiography subdoc.

        The signature takes only the `minio_object_key` because that is what
        the HTTP endpoint receives. We do NOT require `patient_external_id`:
        Mongo locates the right patient through the array filter on the key.

        Returns `result.matched_count > 0` (NOT `modified_count`). Re-running
        the same classification with an identical payload leaves the document
        unchanged but is still a successful operation: `matched_count > 0`
        distinguishes "no such radiography in any patient" (False → 404 at
        the API layer) from "found and applied even if identical" (True → 200).
        """
        result = self.db.patients.update_one(
            {"radiographies.minio_object_key": minio_object_key},
            {
                "$set": {
                    "radiographies.$[r].classification": classification,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            array_filters=[{"r.minio_object_key": minio_object_key}],
        )
        return result.matched_count > 0

    def write_rejected(self, records: list[dict], pipeline_run_id: str) -> int:
        """Persist rejected rows. `pipeline_run_id` is a string UUID coming
        from SQLite (soft cross-DB reference; no FK enforcement). See ADR-004."""
        if not records:
            return 0
        now = datetime.now(timezone.utc)
        payload = [
            {**record, "pipeline_run_id": pipeline_run_id, "created_at": now}
            for record in records
        ]
        result = self.db.rejected_records.insert_many(payload)
        logger.info(
            "Stored %d rejected records for run %s",
            len(result.inserted_ids),
            pipeline_run_id,
        )
        return len(result.inserted_ids)


def get_mongo_writer_from_env(db_name: str | None = None) -> MongoWriter:
    return MongoWriter(
        host=os.environ["MONGO_HOST"],
        port=int(os.environ.get("MONGO_PORT", "27017")),
        db_name=db_name or os.environ["MONGO_DB"],
    )
