"""SQLAlchemy declarative models for pipeline metadata.

Two tables live in SQLite (see ADR-004 for the polyglot persistence rationale):
  * `pipeline_runs`: one row per pipeline execution (audit log)
  * `data_quality_summary`: aggregated counts per dimension per run, used by
    the dashboard

Identifiers are plain string UUIDs generated with `uuid.uuid4()`. We do NOT
use bson.ObjectId here: SQLite should not depend conceptually on BSON. The
soft reference from MongoDB's `rejected_records.pipeline_run_id` is also a
string UUID — no cross-DB FK enforcement, just a logical link.
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
    """Declarative base for the hospital SQL schema."""


class PipelineRunRow(Base):
    __tablename__ = "pipeline_runs"

    id = Column(String, primary_key=True)  # uuid.uuid4() as str
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
