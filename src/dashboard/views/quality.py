"""Calidad de datos view.

RF-2: muestra el ultimo `quality-summary` por dimension + grafico
del historico de `rejection_rate` por dimension a lo largo de los runs.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import show_api_error
from src.dashboard.config import CACHE_TTL_SECONDS


api: ApiClient = st.session_state["api_client"]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_latest_summary(_base_url: str):
    return api.latest_quality_summary()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_history(_base_url: str, dimension: str, limit: int):
    return api.quality_summary_history(dimension, limit=limit)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.title("Calidad de datos")
st.caption(
    "Resumen de validacion del pipeline ETL. Mide cuantos registros "
    "fueron validos vs rechazados por dimension (patients / admissions)."
)


# --- Snapshot ---
st.subheader("Ultimo snapshot")
latest_data, latest_err = _cached_latest_summary(api.base_url)

if latest_err is not None:
    show_api_error(latest_err, context="")
elif not latest_data or not latest_data.get("items"):
    st.info("Aun no hay snapshots de calidad. Lanza el bootstrap primero.")
else:
    items = latest_data["items"]
    df = pd.DataFrame(items)
    df = df[["dimension", "total", "valid", "rejected", "rejection_rate"]]
    df["rejection_rate"] = df["rejection_rate"].apply(lambda x: f"{x:.4f}")
    st.dataframe(df, use_container_width=True, hide_index=True)


# --- Historico de rejection_rate ---
st.markdown("---")
st.subheader("Historico de rejection_rate por dimension")

histories = []
for dim in ("patients", "admissions"):
    rows, err = _cached_history(api.base_url, dim, limit=100)
    if err is not None:
        show_api_error(err, context="")
        continue
    items = rows.get("items", []) if rows else []
    for it in items:
        histories.append({
            "dimension": it.get("dimension"),
            "recorded_at": it.get("recorded_at"),
            "rejection_rate": it.get("rejection_rate"),
            "rejected": it.get("rejected"),
            "total": it.get("total"),
        })

if not histories:
    st.info("Sin historico de calidad todavia.")
else:
    df_hist = pd.DataFrame(histories)
    df_hist["recorded_at"] = pd.to_datetime(df_hist["recorded_at"], errors="coerce")
    df_hist = df_hist.sort_values("recorded_at")

    fig = px.line(
        df_hist,
        x="recorded_at",
        y="rejection_rate",
        color="dimension",
        markers=True,
        title=None,
        labels={
            "recorded_at": "Fecha",
            "rejection_rate": "Tasa de rechazo",
            "dimension": "Dimension",
        },
        color_discrete_map={
            "patients": "#2563EB",
            "admissions": "#15803D",
        },
    )
    fig.update_yaxes(tickformat=".2%")
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=380)
    st.plotly_chart(fig, use_container_width=True)


st.markdown("---")
if st.button("Recargar"):
    _cached_latest_summary.clear()
    _cached_history.clear()
    st.rerun()
