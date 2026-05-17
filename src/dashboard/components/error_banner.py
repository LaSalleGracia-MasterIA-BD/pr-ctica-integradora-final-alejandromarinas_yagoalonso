"""Centralised error banner for the dashboard.

Maps `ApiError.kind` (+ optional context like '/classify' or
'/model/evaluation') to a Spanish, user-facing message. Streamlit
rendering is delegated to `show_api_error` so views never construct
the message themselves.
"""
from __future__ import annotations

from typing import Optional

from src.dashboard.api_client import ApiError


# Contexts the dashboard cares about (used to disambiguate `validation`
# and `unavailable` kinds).
CONTEXT_CLASSIFY = "/classify"
CONTEXT_MODEL_EVALUATION = "/model/evaluation"


def format_error(err: ApiError, context: str = "") -> str:
    """Return the human-readable text for an ApiError, in Spanish.

    Mapping documented in design + spec (CB-1..CB-7).
    """
    if err.kind == "network":
        return "API no disponible. Revisa que el contenedor `api` este arriba."

    if err.kind == "not_found":
        return "Sin datos disponibles."

    if err.kind == "validation":
        if context == CONTEXT_CLASSIFY:
            return (
                "Imagen demasiado pequena o invalida. Usa una radiografia "
                "real (>=32x32 px)."
            )
        return f"Parametros invalidos: {err.detail}"

    if err.kind == "unavailable":
        if context == CONTEXT_CLASSIFY:
            return "El modelo de clasificacion no esta cargado en este despliegue."
        if context == CONTEXT_MODEL_EVALUATION:
            return (
                "Reporte de evaluacion no disponible "
                "(modelo nunca entrenado o `metrics.json` ausente)."
            )
        return f"Servicio no disponible (HTTP 503): {err.detail}"

    # `server` bucket: distinguir 4xx vs 5xx por el status
    if err.kind == "server":
        if err.status is not None and 400 <= err.status < 500:
            return f"Peticion invalida (HTTP {err.status}): {err.detail}"
        if err.status is not None:
            return f"Error del servidor (HTTP {err.status}): {err.detail}"
        return f"Error del servidor: {err.detail}"

    # Should be unreachable; defensive
    return f"Error inesperado: {err.detail}"  # pragma: no cover


def is_warning(err: ApiError) -> bool:
    """A few error kinds are 'recoverable' for the user (warning vs error)."""
    return err.kind in {"not_found", "unavailable", "validation"}


def show_api_error(err: ApiError, context: str = "") -> None:
    """Render an ApiError as a Streamlit banner.

    Lazy-import streamlit so this module is testable without it.
    """
    import streamlit as st

    text = format_error(err, context)
    if is_warning(err):
        st.warning(text)
    else:
        st.error(text)


__all__ = [
    "CONTEXT_CLASSIFY",
    "CONTEXT_MODEL_EVALUATION",
    "format_error",
    "is_warning",
    "show_api_error",
]
