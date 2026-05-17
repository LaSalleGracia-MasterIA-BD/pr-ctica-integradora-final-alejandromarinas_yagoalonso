"""Tests for QualitySummaryBuilder."""
from __future__ import annotations

from src.pipeline.processors.quality_summary import build


def test_build_returns_one_entry_per_dimension():
    out = build(
        patients_total=10,
        patients_valid=10,
        patients_rejected=0,
        admissions_total=20,
        admissions_valid=20,
        admissions_rejected=0,
        admissions_orphans=0,
    )
    dimensions = {row["dimension"] for row in out}
    assert dimensions == {"patients", "admissions"}


def test_build_with_clean_data_yields_zero_rejection_rate():
    out = build(
        patients_total=10,
        patients_valid=10,
        patients_rejected=0,
        admissions_total=20,
        admissions_valid=20,
        admissions_rejected=0,
        admissions_orphans=0,
    )
    for row in out:
        assert row["rejected"] == 0
        assert row["rejection_rate"] == 0.0


def test_build_includes_orphans_in_admissions_rejected():
    """Orphans MUST count as rejected admissions — not as a separate dimension."""
    out = build(
        patients_total=10,
        patients_valid=10,
        patients_rejected=0,
        admissions_total=100,
        admissions_valid=80,
        admissions_rejected=15,  # rule-based rejections
        admissions_orphans=5,    # cross-entity rejections
    )
    by_dim = {row["dimension"]: row for row in out}
    # 15 rule-based + 5 orphans = 20 rejected admissions
    assert by_dim["admissions"]["rejected"] == 20
    assert by_dim["admissions"]["valid"] == 80
    assert by_dim["admissions"]["total"] == 100
    assert by_dim["admissions"]["rejection_rate"] == 0.20


def test_build_with_total_zero_returns_zero_rate_not_nan():
    """Defensive: a run with no patients must not blow up with NaN/ZeroDiv."""
    out = build(
        patients_total=0,
        patients_valid=0,
        patients_rejected=0,
        admissions_total=0,
        admissions_valid=0,
        admissions_rejected=0,
        admissions_orphans=0,
    )
    for row in out:
        assert row["rejection_rate"] == 0.0


def test_build_keys_match_db_schema():
    """The dicts returned must have the same keys the SqlWriter expects."""
    out = build(
        patients_total=5,
        patients_valid=4,
        patients_rejected=1,
        admissions_total=10,
        admissions_valid=8,
        admissions_rejected=1,
        admissions_orphans=1,
    )
    expected_keys = {"dimension", "total", "valid", "rejected", "rejection_rate"}
    for row in out:
        assert set(row.keys()) == expected_keys
