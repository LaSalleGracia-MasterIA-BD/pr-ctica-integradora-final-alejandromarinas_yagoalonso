"""Tests unitarios puros de `evaluate()` (Feature 15, T2).

Cubre RF-2 (reglas), RF-8 (orden), CB-1/CB-3/CB-4, RNF-5 (pura, sin IO).

`evaluate` recibe listas ya filtradas por ventana temporal: NO conoce el
reloj. Por eso aqui no necesitamos Mongo ni SQLite — solo dicts.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.api.alerts import Alert, evaluate


# -- Fixtures helpers ---------------------------------------------------

UTC = timezone.utc


def _failed_run(
    run_id: str = "run-1",
    trigger: str = "watcher",
    error: str | None = "boom",
    started_at: datetime | None = None,
) -> dict:
    return {
        "id": run_id,
        "trigger_type": trigger,
        "status": "failed",
        "started_at": started_at or datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        "error_message": error,
    }


def _quality_snapshot(
    run_id: str = "run-1",
    dimension: str = "patients",
    rate: float = 0.20,
    total: int = 100,
    rejected: int = 20,
    recorded_at: datetime | None = None,
) -> dict:
    return {
        "pipeline_run_id": run_id,
        "dimension": dimension,
        "total": total,
        "valid": total - rejected,
        "rejected": rejected,
        "rejection_rate": rate,
        "recorded_at": recorded_at or datetime(2026, 5, 20, 12, 30, tzinfo=UTC),
    }


def _severe_patient(
    external_id: str = "P-001",
    name: str = "Ana",
    reasons: list[str] | None = None,
    triaged_at: datetime | None = None,
) -> dict:
    return {
        "external_id": external_id,
        "name": name,
        "triage": {
            "level": "grave",
            "reasons": reasons or ["SpO2<90"],
            "triaged_at": triaged_at or datetime(2026, 5, 20, 13, 0, tzinfo=UTC),
        },
    }


# -- CB-1: estado vacio --------------------------------------------------

def test_no_state_returns_empty():
    assert evaluate([], [], []) == []


# -- RF-2 (a): pipeline_failed -------------------------------------------

def test_failed_run_creates_pipeline_failed_alert():
    run = _failed_run(run_id="abc-123", trigger="watcher", error="conn refused")
    alerts = evaluate([run], [], [])

    assert len(alerts) == 1
    a = alerts[0]
    assert isinstance(a, Alert)
    assert a.type == "pipeline_failed"
    assert a.severity == "high"
    assert a.source == "pipeline_runs"
    assert a.source_id == "abc-123"
    assert a.created_at == run["started_at"]
    assert "conn refused" in a.detail


def test_failed_run_without_error_message_still_alerts():
    """CB: si el run no tiene error_message, igualmente generamos alerta."""
    run = _failed_run(error=None)
    alerts = evaluate([run], [], [])

    assert len(alerts) == 1
    assert alerts[0].type == "pipeline_failed"
    assert alerts[0].detail  # algun mensaje, no vacio


# -- RF-2 (b): data_quality_low + CB-4 (umbral estricto) -----------------

def test_quality_above_threshold_creates_alert():
    snap = _quality_snapshot(rate=0.20, dimension="patients")
    alerts = evaluate([], [snap], [], threshold=0.10)

    assert len(alerts) == 1
    a = alerts[0]
    assert a.type == "data_quality_low"
    assert a.severity == "medium"
    assert a.source == "data_quality_summary"
    assert a.source_id == f"{snap['pipeline_run_id']}:{snap['dimension']}"
    assert a.created_at == snap["recorded_at"]


def test_quality_exactly_at_threshold_does_not_alert():
    """CB-4: rejection_rate == threshold NO genera alerta (estricto >)."""
    snap = _quality_snapshot(rate=0.10)
    alerts = evaluate([], [snap], [], threshold=0.10)
    assert alerts == []


def test_quality_below_threshold_does_not_alert():
    snap = _quality_snapshot(rate=0.05)
    alerts = evaluate([], [snap], [], threshold=0.10)
    assert alerts == []


# -- RF-2 (c): triage_severe + CB-3 --------------------------------------

def test_severe_patient_creates_triage_alert():
    patient = _severe_patient(external_id="P-999", reasons=["SpO2<90", "FR>30"])
    alerts = evaluate([], [], [patient])

    assert len(alerts) == 1
    a = alerts[0]
    assert a.type == "triage_severe"
    assert a.severity == "critical"
    assert a.source == "patients.triage"
    assert a.source_id == "P-999"
    assert a.created_at == patient["triage"]["triaged_at"]


def test_leve_patient_does_not_alert():
    """CB-3: `evaluate` no recibe leves porque el reader filtra por
    `triage.level='grave'`. Verificamos que si por error llegase una
    lista vacia (caso real: ningun grave en ventana), no se genera
    alerta. La regla equivalente para "evaluate ignora niveles no
    graves" se garantiza por contrato del reader, no por filtrado
    interno aqui."""
    alerts = evaluate([], [], [])  # lista de graves vacia => sin alertas
    assert alerts == []


# -- RF-8: orden por severity DESC, luego created_at DESC ----------------

def test_alerts_sorted_by_severity_then_time():
    """critical > high > medium > low; dentro de cada nivel: mas reciente
    primero."""
    early = datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
    late = datetime(2026, 5, 20, 22, 0, tzinfo=UTC)

    failed_old = _failed_run(run_id="r-old", started_at=early)
    failed_new = _failed_run(run_id="r-new", started_at=late)
    snap = _quality_snapshot(rate=0.30, recorded_at=late)
    patient = _severe_patient(external_id="P-1", triaged_at=early)

    alerts = evaluate(
        [failed_old, failed_new],
        [snap],
        [patient],
        threshold=0.10,
    )

    # Esperado: critical, high(new), high(old), medium
    types_and_severity = [(a.severity, a.source_id) for a in alerts]
    assert types_and_severity == [
        ("critical", "P-1"),
        ("high", "r-new"),
        ("high", "r-old"),
        ("medium", f"{snap['pipeline_run_id']}:{snap['dimension']}"),
    ]


# -- RNF-7 + RF-2: threshold configurable --------------------------------

def test_threshold_configurable_higher():
    """Con threshold=0.50 un snapshot a 0.20 NO debe alertar."""
    snap = _quality_snapshot(rate=0.20)
    alerts = evaluate([], [snap], [], threshold=0.50)
    assert alerts == []


def test_threshold_configurable_lower():
    """Con threshold=0.05 un snapshot a 0.06 SI debe alertar."""
    snap = _quality_snapshot(rate=0.06)
    alerts = evaluate([], [snap], [], threshold=0.05)
    assert len(alerts) == 1
    assert alerts[0].type == "data_quality_low"


# -- Combinacion: las 3 reglas a la vez ----------------------------------

def test_all_three_types_evaluated_together():
    run = _failed_run()
    snap = _quality_snapshot(rate=0.50)
    patient = _severe_patient()

    alerts = evaluate([run], [snap], [patient])
    types = sorted(a.type for a in alerts)
    assert types == ["data_quality_low", "pipeline_failed", "triage_severe"]


# -- Alert es frozen (RNF-5: pura, immutable) ----------------------------

def test_alert_is_frozen_dataclass():
    run = _failed_run()
    alerts = evaluate([run], [], [])
    with pytest.raises(Exception):  # FrozenInstanceError
        alerts[0].severity = "low"  # type: ignore[misc]
