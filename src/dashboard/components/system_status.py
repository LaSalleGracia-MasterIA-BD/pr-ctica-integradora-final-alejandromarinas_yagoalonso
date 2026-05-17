"""Persistent system status footer for the sidebar.

Three chips: API, Modelo, Ultimo run. Visible across all 5 views so the
evaluator always knows the health of the stack at a glance. Encajado
con el encuadre "Centro de Control Hospitalario" del producto.

Comparte llamada `health()` + `latest_pipeline_run()` con las vistas
gracias al cache de Streamlit (`st.cache_data(ttl=10s)` en
`_status_payload`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.dashboard.api_client import ApiClient


COLOR_OK = "#15803D"        # verde
COLOR_WARN = "#D97706"      # ambar
COLOR_CRIT = "#DC2626"      # rojo
COLOR_NEUTRAL = "#64748B"   # gris para "desconocido"


@dataclass(frozen=True)
class Chip:
    label: str
    value: str
    color: str


def _api_chip(health_data: Optional[dict], health_err) -> Chip:
    if health_err is not None:
        return Chip(label="API", value="caida", color=COLOR_CRIT)
    return Chip(label="API", value="ok", color=COLOR_OK)


def _model_chip(health_data: Optional[dict], health_err) -> Chip:
    if health_err is not None:
        return Chip(label="Modelo", value="?", color=COLOR_NEUTRAL)
    loaded = bool(health_data and health_data.get("predictor_loaded"))
    if loaded:
        return Chip(label="Modelo", value="cargado", color=COLOR_OK)
    return Chip(label="Modelo", value="no cargado", color=COLOR_CRIT)


def _run_chip(run_data: Optional[dict], run_err) -> Chip:
    if run_err is not None:
        # 404 = no hay runs aun. Otra cosa = problema real
        if getattr(run_err, "kind", None) == "not_found":
            return Chip(label="Ultimo run", value="sin runs", color=COLOR_NEUTRAL)
        return Chip(label="Ultimo run", value="?", color=COLOR_NEUTRAL)
    status = (run_data or {}).get("status", "?")
    if status == "success":
        return Chip(label="Ultimo run", value="success", color=COLOR_OK)
    if status == "failed":
        return Chip(label="Ultimo run", value="failed", color=COLOR_CRIT)
    if status == "running":
        return Chip(label="Ultimo run", value="running", color=COLOR_WARN)
    return Chip(label="Ultimo run", value=str(status), color=COLOR_NEUTRAL)


def build_chips(api_client: ApiClient) -> list[Chip]:
    """Build the 3 chips. Pure (no Streamlit), so it is testable."""
    health_data, health_err = api_client.health()
    run_data, run_err = api_client.latest_pipeline_run()
    return [
        _api_chip(health_data, health_err),
        _model_chip(health_data, health_err),
        _run_chip(run_data, run_err),
    ]


def _chip_html(chip: Chip) -> str:
    """Minimal HTML span for the chip — sin CSS complejo, una linea."""
    # `unsafe_allow_html=True` se usa solo aqui y con esta funcion.
    return (
        f'<span style="display:inline-block;padding:2px 8px;margin:2px 4px 2px 0;'
        f'border-radius:12px;background:{chip.color};color:#FFFFFF;font-size:12px;'
        f'font-weight:500;">{chip.label}: {chip.value}</span>'
    )


def render_system_status(api_client: ApiClient) -> None:
    """Render the 3 chips inside the current Streamlit container (typically sidebar)."""
    import streamlit as st

    @st.cache_data(ttl=10, show_spinner=False)
    def _cached_chips(_client_id: str) -> list[Chip]:
        # Cache key uses base_url so a second sidebar render reuses the result
        return build_chips(api_client)

    chips = _cached_chips(api_client.base_url)
    st.markdown("---")
    st.caption("Estado del sistema")
    html = "".join(_chip_html(c) for c in chips)
    st.markdown(html, unsafe_allow_html=True)


__all__ = [
    "Chip",
    "COLOR_OK",
    "COLOR_WARN",
    "COLOR_CRIT",
    "COLOR_NEUTRAL",
    "build_chips",
    "render_system_status",
]
