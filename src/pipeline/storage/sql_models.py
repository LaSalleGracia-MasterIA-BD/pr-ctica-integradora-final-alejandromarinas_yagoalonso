"""Modelos declarativos de SQLAlchemy para los metadatos del pipeline.

En SQLite viven dos tablas (ver ADR-004 sobre la justificacion de la
persistencia poliglota):
  * `pipeline_runs`: una fila por ejecucion del pipeline (audit log)
  * `data_quality_summary`: contadores agregados por dimension y por
    run, usados por el dashboard

Los identificadores son UUID en string generados con `uuid.uuid4()`. NO
usamos bson.ObjectId aqui: SQLite no debe depender conceptualmente de
BSON. La referencia blanda desde `rejected_records.pipeline_run_id` de
MongoDB tambien es un UUID en string — no hay FK cross-DB, solo un
enlace logico.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarativa para el schema SQL del hospital."""


class PipelineRunRow(Base):
    __tablename__ = "pipeline_runs"

    id = Column(String, primary_key=True)  # uuid.uuid4() como str
    trigger_type = Column(String, nullable=False)  # 'manual' | 'bootstrap' | 'watcher'
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False)  # 'running' | 'success' | 'failed'
    records_processed = Column(Integer, nullable=False, default=0)
    records_rejected = Column(Integer, nullable=False, default=0)
    images_processed = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_pipeline_runs_started_at", "started_at"),
    )


class DataQualitySummaryRow(Base):
    __tablename__ = "data_quality_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id = Column(
        String, ForeignKey("pipeline_runs.id"), nullable=False
    )
    dimension = Column(String, nullable=False)  # 'patients' | 'admissions' | ...
    total = Column(Integer, nullable=False)
    valid = Column(Integer, nullable=False)
    rejected = Column(Integer, nullable=False)
    rejection_rate = Column(Float, nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_dq_summary_run_id", "pipeline_run_id"),
        Index("ix_dq_summary_dimension", "dimension", "recorded_at"),
    )
