"""Read-side access to the hospital MongoDB collections.

Kept separate from `MongoWriter` so read and write surfaces can evolve
independently (CQRS-light). Mongo connection management mirrors the writer.
"""
from __future__ import annotations

import os

from pymongo import MongoClient


class MongoReader:
    def __init__(self, host: str, port: int, db_name: str) -> None:
        self._client: MongoClient = MongoClient(host=host, port=port)
        self.db = self._client[db_name]

    def close(self) -> None:
        self._client.close()

    # -- Patients -----------------------------------------------------------

    def count_patients(self) -> int:
        return self.db.patients.count_documents({})

    def list_patients(self, limit: int, offset: int) -> list[dict]:
        cursor = (
            self.db.patients.find({}, {"_id": 0})
            .sort("external_id", 1)
            .skip(offset)
            .limit(limit)
        )
        return list(cursor)

    def find_patient(self, external_id: str) -> dict | None:
        return self.db.patients.find_one({"external_id": external_id}, {"_id": 0})

    # -- Admissions ---------------------------------------------------------

    def count_admissions(self) -> int:
        pipeline = [
            {"$project": {"n": {"$size": {"$ifNull": ["$admissions", []]}}}},
            {"$group": {"_id": None, "total": {"$sum": "$n"}}},
        ]
        docs = list(self.db.patients.aggregate(pipeline))
        return docs[0]["total"] if docs else 0

    def list_admissions(self, limit: int, offset: int) -> list[dict]:
        pipeline = [
            {"$unwind": "$admissions"},
            {"$sort": {"external_id": 1, "admissions.admission_date": 1}},
            {"$skip": offset},
            {"$limit": limit},
            {"$replaceRoot": {"newRoot": "$admissions"}},
        ]
        return list(self.db.patients.aggregate(pipeline))

    # -- Radiographies ------------------------------------------------------

    def count_radiographies(self) -> int:
        pipeline = [
            {"$project": {"n": {"$size": {"$ifNull": ["$radiographies", []]}}}},
            {"$group": {"_id": None, "total": {"$sum": "$n"}}},
        ]
        docs = list(self.db.patients.aggregate(pipeline))
        return docs[0]["total"] if docs else 0

    def list_radiographies(self, limit: int, offset: int) -> list[dict]:
        pipeline = [
            {"$unwind": "$radiographies"},
            {"$addFields": {
                "radiographies.patient_external_id": "$external_id",
            }},
            {"$sort": {"radiographies.minio_object_key": 1}},
            {"$skip": offset},
            {"$limit": limit},
            {"$replaceRoot": {"newRoot": "$radiographies"}},
        ]
        return list(self.db.patients.aggregate(pipeline))

    # NOTE: pipeline_runs reads moved to `src/api/sql_reader.py` (ADR-004).

    # -- Radiography classification ----------------------------------------

    def get_radiography_classification(self, minio_object_key: str) -> dict | None:
        """Return the persisted classification for a radiography, or None.

        Used by GET /api/v1/radiographies/classification?key=... to serve
        the cached result without re-inferring. None is returned both when
        the key does not exist in any patient and when it exists but its
        `classification` is null.
        """
        pipeline = [
            {"$unwind": "$radiographies"},
            {"$match": {"radiographies.minio_object_key": minio_object_key}},
            {"$project": {"_id": 0, "classification": "$radiographies.classification"}},
            {"$limit": 1},
        ]
        docs = list(self.db.patients.aggregate(pipeline))
        if not docs:
            return None
        classification = docs[0].get("classification")
        return classification if classification else None


def get_mongo_reader_from_env(db_name: str | None = None) -> MongoReader:
    return MongoReader(
        host=os.environ["MONGO_HOST"],
        port=int(os.environ.get("MONGO_PORT", "27017")),
        db_name=db_name or os.environ["MONGO_DB"],
    )
