"""Tests for the system status chips (pure logic, no Streamlit)."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.dashboard.api_client import ApiError
from src.dashboard.components.system_status import (
    COLOR_CRIT,
    COLOR_NEUTRAL,
    COLOR_OK,
    COLOR_WARN,
    build_chips,
)


def _client_with(health, run):
    """Build a MagicMock ApiClient with predetermined responses."""
    client = MagicMock()
    client.health.return_value = health
    client.latest_pipeline_run.return_value = run
    return client


def test_chips_all_green_when_everything_ok():
    client = _client_with(
        health=({"status": "ok", "predictor_loaded": True}, None),
        run=({"status": "success", "trigger_type": "bootstrap"}, None),
    )
    chips = build_chips(client)
    assert [c.label for c in chips] == ["API", "Modelo", "Ultimo run"]
    assert all(c.color == COLOR_OK for c in chips)


def test_api_chip_red_when_network_error():
    client = _client_with(
        health=(None, ApiError(kind="network", status=None, detail="boom")),
        run=(None, ApiError(kind="network", status=None, detail="boom")),
    )
    chips = build_chips(client)
    api_chip = next(c for c in chips if c.label == "API")
    assert api_chip.color == COLOR_CRIT
    assert "caida" in api_chip.value


def test_model_chip_red_when_predictor_not_loaded():
    client = _client_with(
        health=({"status": "ok", "predictor_loaded": False}, None),
        run=({"status": "success"}, None),
    )
    chips = build_chips(client)
    model_chip = next(c for c in chips if c.label == "Modelo")
    assert model_chip.color == COLOR_CRIT
    assert "no cargado" in model_chip.value


def test_run_chip_amber_when_running():
    client = _client_with(
        health=({"status": "ok", "predictor_loaded": True}, None),
        run=({"status": "running"}, None),
    )
    chips = build_chips(client)
    run_chip = next(c for c in chips if c.label == "Ultimo run")
    assert run_chip.color == COLOR_WARN


def test_run_chip_red_when_failed():
    client = _client_with(
        health=({"status": "ok", "predictor_loaded": True}, None),
        run=({"status": "failed", "error_message": "boom"}, None),
    )
    chips = build_chips(client)
    run_chip = next(c for c in chips if c.label == "Ultimo run")
    assert run_chip.color == COLOR_CRIT


def test_run_chip_neutral_when_no_runs_yet():
    """A 404 on /pipeline/status means there are no runs yet — not a failure."""
    client = _client_with(
        health=({"status": "ok", "predictor_loaded": True}, None),
        run=(None, ApiError(kind="not_found", status=404, detail="no runs")),
    )
    chips = build_chips(client)
    run_chip = next(c for c in chips if c.label == "Ultimo run")
    assert run_chip.color == COLOR_NEUTRAL
    assert "sin runs" in run_chip.value
