"""Acceso de lectura a las colecciones MongoDB del hospital.

Se mantiene separado de `MongoWriter` para que las superficies de lectura
y escritura puedan evolucionar de forma independiente. La gestion de la
conexion a Mongo refleja a la del writer.
"""
from __future__ import annotations

import os
from datetime import datetime

from pymongo import MongoClient


class MongoReader:
    def __init__(self, host: str, port: int, db_name: str) -> None:
        self._client: MongoClient = MongoClient(host=host, port=port)
        self.db = self._client[db_name]

    def close(self) -> None:
        self._client.close()

    # -- Pacientes ----------------------------------------------------------

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

    # -- Ingresos -----------------------------------------------------------

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

    # -- Radiografias -------------------------------------------------------

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

    # NOTA: las lecturas de pipeline_runs se movieron a `src/api/sql_reader.py` (ADR-004).

    # -- Clasificacion de radiografias -------------------------------------

    def get_radiography_classification(self, minio_object_key: str) -> dict | None:
        """Devuelve la clasificacion persistida de una radiografia, o None.

        Usado por GET /api/v1/radiographies/classification?key=... para
        servir el resultado cacheado sin reinferir. Devuelve None tanto
        cuando la key no existe en ningun paciente como cuando existe pero
        su `classification` es nulo.
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

    # -- Alertas y reportes operativos (Feature 15, ADR-009) ---------------

    def list_severe_triage_patients_since(self, since: datetime) -> list[dict]:
        """Pacientes con triage.level='grave' y triage.triaged_at >= since.

        Usado por GET /api/v1/alerts. Ventana abierta por la derecha.
        """
        cursor = (
            self.db.patients.find(
                {
                    "triage.level": "grave",
                    "triage.triaged_at": {"$gte": since},
                },
                {"_id": 0},
            )
            .sort("triage.triaged_at", -1)
        )
        return list(cursor)

    def list_severe_triage_patients_between(
        self, start: datetime, end: datetime,
    ) -> list[dict]:
        """Pacientes con triage.level='grave' y triage.triaged_at en
        [start, end] (ambos inclusivos). Usado por GET /reports/daily +
        src/automation/daily_report.py."""
        cursor = (
            self.db.patients.find(
                {
                    "triage.level": "grave",
                    "triage.triaged_at": {"$gte": start, "$lte": end},
                },
                {"_id": 0},
            )
            .sort("triage.triaged_at", 1)  # orden ascendente = determinista
        )
        return list(cursor)

    def list_triage_patients_between(
        self, start: datetime, end: datetime,
    ) -> list[dict]:
        """Pacientes con triage.triaged_at en [start, end], cualquier
        nivel. Usado para contar grave/medio/leve del dia."""
        cursor = (
            self.db.patients.find(
                {"triage.triaged_at": {"$gte": start, "$lte": end}},
                {"_id": 0},
            )
            .sort("triage.triaged_at", 1)
        )
        return list(cursor)

    def get_total_counts(self) -> dict:
        """Snapshot al instante de contadores totales: patients,
        admissions (embebidos) y radiographies (embebidas). Usado por
        GET /api/v1/reports/daily.counts."""
        patients = self.count_patients()
        admissions = self.count_admissions()
        radiographies = self.count_radiographies()
        return {
            "patients_total": patients,
            "admissions_total": admissions,
            "radiographies_total": radiographies,
        }


def get_mongo_reader_from_env(db_name: str | None = None) -> MongoReader:
    return MongoReader(
        host=os.environ["MONGO_HOST"],
        port=int(os.environ.get("MONGO_PORT", "27017")),
        db_name=db_name or os.environ["MONGO_DB"],
    )
