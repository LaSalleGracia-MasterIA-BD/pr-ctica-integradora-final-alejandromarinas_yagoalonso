"""Banner de error centralizado para el dashboard.

Mapea `ApiError.kind` (+ contexto opcional como '/classify' o
'/model/evaluation') a un mensaje en castellano orientado a usuario
final. El render con Streamlit se delega en `show_api_error`, asi las
vistas nunca construyen el mensaje por su cuenta.
"""
from __future__ import annotations

from typing import Optional

from src.dashboard.api_client import ApiError


# Contextos relevantes para el dashboard (se usan para desambiguar los
# kinds `validation` y `unavailable`).
CONTEXT_CLASSIFY = "/classify"
CONTEXT_MODEL_EVALUATION = "/model/evaluation"


def format_error(err: ApiError, context: str = "") -> str:
    """Devuelve el texto legible para un ApiError, en castellano.

    Mapeo documentado en design + spec (CB-1..CB-7).
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

    # bucket `server`: distinguir 4xx vs 5xx segun el status
    if err.kind == "server":
        if err.status is not None and 400 <= err.status < 500:
            return f"Peticion invalida (HTTP {err.status}): {err.detail}"
        if err.status is not None:
            return f"Error del servidor (HTTP {err.status}): {err.detail}"
        return f"Error del servidor: {err.detail}"

    # No deberia alcanzarse; defensivo
    return f"Error inesperado: {err.detail}"  # pragma: no cover


def is_warning(err: ApiError) -> bool:
    """Algunos kinds de error son 'recuperables' para el usuario (warning vs error)."""
    return err.kind in {"not_found", "unavailable", "validation"}


def show_api_error(err: ApiError, context: str = "") -> None:
    """Renderiza un ApiError como banner de Streamlit.

    Importa streamlit de forma lazy para que el modulo sea testeable sin el.
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
