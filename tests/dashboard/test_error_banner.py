"""Tests for the error banner mapping.

Streamlit is NOT imported here — we test `format_error` and `is_warning`
which are pure functions. The actual `show_api_error` (Streamlit
rendering) is exercised in the manual smoke (T15).
"""
from __future__ import annotations

import pytest

from src.dashboard.api_client import ApiError
from src.dashboard.components.error_banner import (
    CONTEXT_CLASSIFY,
    CONTEXT_MODEL_EVALUATION,
    format_error,
    is_warning,
)


def _err(kind, status=None, detail="") -> ApiError:
    return ApiError(kind=kind, status=status, detail=detail)


# ---------------------------------------------------------------------------
# format_error
# ---------------------------------------------------------------------------

def test_network_message():
    msg = format_error(_err("network", detail="ConnectError"))
    assert "API no disponible" in msg


def test_not_found_message():
    assert "Sin datos" in format_error(_err("not_found", status=404))


def test_validation_classify_context_mentions_min_size():
    msg = format_error(
        _err("validation", status=422, detail="Image too small"),
        context=CONTEXT_CLASSIFY,
    )
    assert "32x32" in msg or "32" in msg
    assert "radiografia" in msg.lower()


def test_validation_other_context_uses_generic_message():
    msg = format_error(
        _err("validation", status=422, detail="key vacia"),
        context="",
    )
    assert "invalidos" in msg.lower()
    assert "key vacia" in msg


def test_unavailable_classify_context_mentions_model_not_loaded():
    msg = format_error(_err("unavailable", status=503), context=CONTEXT_CLASSIFY)
    assert "modelo" in msg.lower()
    assert "no esta cargado" in msg.lower()


def test_unavailable_model_evaluation_context_mentions_report():
    msg = format_error(
        _err("unavailable", status=503), context=CONTEXT_MODEL_EVALUATION,
    )
    assert "evaluacion" in msg.lower() or "evaluación" in msg.lower()
    assert "no disponible" in msg.lower()


def test_server_4xx_message_uses_petitcion_invalida():
    msg = format_error(_err("server", status=400, detail="bad request"))
    assert "Peticion invalida" in msg
    assert "400" in msg


def test_server_5xx_message_uses_error_del_servidor():
    msg = format_error(_err("server", status=502, detail="bad gateway"))
    assert "Error del servidor" in msg
    assert "502" in msg


def test_server_without_status_handled_defensively():
    msg = format_error(_err("server", status=None, detail="exotic"))
    assert "Error del servidor" in msg


# ---------------------------------------------------------------------------
# is_warning
# ---------------------------------------------------------------------------

def test_is_warning_for_recoverable_kinds():
    assert is_warning(_err("not_found")) is True
    assert is_warning(_err("validation", status=422)) is True
    assert is_warning(_err("unavailable", status=503)) is True


def test_is_warning_false_for_critical_kinds():
    assert is_warning(_err("network")) is False
    assert is_warning(_err("server", status=500)) is False
