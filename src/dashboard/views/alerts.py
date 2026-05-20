"""Vista "Alertas" (Feature 15, RF-6).

Muestra las alertas operativas calculadas en tiempo real por
`GET /api/v1/alerts`:
  * pipeline_failed (high) — runs del ETL con status='failed' en la ventana.
  * data_quality_low (medium) — snapshots con rejection_rate sobre umbral.
  * triage_severe (critical) — pacientes triajeados como GRAVE en la ventana.

API-only (ADR-007): solo `api_client.get_alerts()`. Sin acceso directo
a almacenes de datos. Sin estado nuevo persistido (ADR-009).
"""
from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import show_api_error
from src.dashboard.config import CACHE_TTL_SECONDS


api: ApiClient = st.session_state["api_client"]


SEVERITY_COLORS = {
    "critical": "#DC2626",  # rojo
    "high": "#EA580C",       # naranja
    "medium": "#D97706",     # ambar
    "low": "#64748B",        # gris
}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_alerts(_base_url: str, severity_filter: str | None):
    return api.get_alerts(severity=severity_filter)


def _severity_chip_html(severity: str) -> str:
    color = SEVERITY_COLORS.get(severity, "#64748B")
    return (
        f'<span style="display:inline-block;padding:2px 8px;margin:0;'
        f'border-radius:12px;background:{color};color:#FFFFFF;'
        f'font-size:11px;font-weight:600;">{severity.upper()}</span>'
    )


def _short_dt(value: str | None) -> str:
    if not value:
        return "-"
    s = str(value)
    if len(s) >= 19:
        return s[:19].replace("T", " ")
    return s.replace("T", " ")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.title("Alertas")
st.caption(
    "Vista calculada en tiempo real desde pipeline_runs, "
    "data_quality_summary y patients.triage. Ventana por defecto: "
    "ultimas 24h. Sin estado nuevo persistido (ADR-009)."
)


col_filter, _col_spacer = st.columns([1, 3])
with col_filter:
    severity_filter = st.selectbox(
        "Filtrar por severidad",
        options=["(todas)", "critical", "high", "medium", "low"],
        index=0,
        help="Filtro server-side (query param `severity`).",
    )
selected = None if severity_filter == "(todas)" else severity_filter


data, err = _cached_alerts(api.base_url, selected)
if err is not None:
    show_api_error(err, context="/api/v1/alerts")
    st.stop()


items = (data or {}).get("items", [])
total = (data or {}).get("total", 0)
threshold = (data or {}).get("threshold")
window_start = (data or {}).get("window_start")


# -- Desglose por severity ----------------------------------------------
counts = Counter(a["severity"] for a in items)
cols = st.columns(4)
cols[0].metric("Critical", counts.get("critical", 0))
cols[1].metric("High", counts.get("high", 0))
cols[2].metric("Medium", counts.get("medium", 0))
cols[3].metric("Low", counts.get("low", 0))


st.caption(
    f"Total: {total}  ·  umbral calidad: {threshold}  ·  "
    f"ventana desde: {_short_dt(window_start)}"
)


# -- Lista de alertas ----------------------------------------------------
if not items:
    st.success("Sin alertas activas.")
else:
    rows = []
    for a in items:
        rows.append({
            "Severidad": a.get("severity", "?"),
            "Tipo": a.get("type", "?"),
            "Titulo": a.get("title", ""),
            "Origen": a.get("source", "?"),
            "ID origen": a.get("source_id") or "-",
            "Detectada": _short_dt(a.get("created_at")),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Detalle por alerta")
    for a in items:
        chip = _severity_chip_html(a.get("severity", "?"))
        header = (
            f"{chip} &nbsp;**{a.get('title', '')}**  ·  "
            f"`{a.get('source', '?')}` &middot; "
            f"`{a.get('source_id') or '-'}`"
        )
        st.markdown(header, unsafe_allow_html=True)
        st.code(a.get("detail", ""), language="text")


st.markdown("---")
if st.button("Recargar"):
    _cached_alerts.clear()
    st.rerun()
