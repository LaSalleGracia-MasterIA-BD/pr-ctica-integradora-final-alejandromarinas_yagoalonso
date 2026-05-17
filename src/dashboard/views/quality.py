"""Calidad de datos view.

RF-2: muestra el ultimo `quality-summary` por dimension + grafico
del historico de `rejection_rate` por dimension a lo largo de los runs.

Filtro por defecto: oculta snapshots con `total <= 100`. Esos vienen
de runs `e2e-test` (con CSVs vacios o de muy pocas filas) y enmascaran
el comportamiento real del pipeline. Toggle para verlos todos.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import show_api_error
from src.dashboard.config import CACHE_TTL_SECONDS


# Umbral por defecto: snapshots con menos de este total se consideran
# "ruido" (datasets vacios de tests, watcher con CSVs minimos).
RELEVANT_TOTAL_THRESHOLD = 100


api: ApiClient = st.session_state["api_client"]


# El "snapshot relevante" se calcula desde el historico filtrado (no
# usamos /quality-summary directo porque devuelve el ULTIMO sin importar
# si es de un test pequeño que enmascara la realidad).
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_history(_base_url: str, dimension: str, limit: int):
    return api.quality_summary_history(dimension, limit=limit)


def _relevant(rows: list[dict], show_all: bool) -> list[dict]:
    if show_all:
        return rows
    return [r for r in rows if (r.get("total") or 0) > RELEVANT_TOTAL_THRESHOLD]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.title("Calidad de datos")
st.caption(
    "Resumen de validacion del pipeline ETL. Mide cuantos registros "
    "fueron validos vs rechazados por dimension (pacientes / admisiones)."
)

show_all = st.checkbox(
    "Mostrar todos los snapshots (incluidos runs de test)",
    value=False,
    help=(
        f"Por defecto se ocultan los snapshots con total <= "
        f"{RELEVANT_TOTAL_THRESHOLD} (vienen de runs e2e-test con datasets "
        "vacios y enmascaran el comportamiento real del pipeline)."
    ),
)


# --- Snapshot ---
st.subheader("Ultimo snapshot relevante")
st.caption(
    "Snapshot mas reciente del pipeline tras procesar un dataset "
    "significativo. Los runs pequenos/de test se ocultan por claridad; "
    "activa el toggle para verlos."
)

# Para "snapshot relevante" pedimos historico (incluye todos los runs)
# y elegimos el mas reciente que cumpla el filtro. `latest_quality_summary`
# devolveria SIEMPRE el ultimo aunque sea de un test, lo cual confunde
# en demo. Por eso aqui agregamos manualmente.
latest_run_id: str | None = None
relevant_latest: list[dict] = []
hist_errors: list = []
hist_all: list[dict] = []
for dim in ("patients", "admissions"):
    rows, err = _cached_history(api.base_url, dim, limit=200)
    if err is not None:
        hist_errors.append(err)
        continue
    items = rows.get("items", []) if rows else []
    hist_all.extend(items)

if hist_errors:
    show_api_error(hist_errors[0], context="")
elif not hist_all:
    st.info("Aun no hay snapshots de calidad. Lanza el bootstrap primero.")
else:
    # Snapshot "relevante": el mas reciente con total > umbral. Si el toggle
    # esta activo, simplemente cogemos el ultimo de cada dimension.
    candidates = _relevant(hist_all, show_all=show_all)
    if not candidates:
        st.warning(
            f"Ningun snapshot supera el umbral de total > "
            f"{RELEVANT_TOTAL_THRESHOLD}. Activa el toggle para ver todos "
            "o lanza el bootstrap con un dataset real."
        )
    else:
        # Para cada dimension, coger el mas reciente que pase el filtro
        by_dim: dict[str, dict] = {}
        for it in sorted(candidates, key=lambda r: r.get("recorded_at") or "", reverse=True):
            d = it.get("dimension")
            if d and d not in by_dim:
                by_dim[d] = it
        latest_items = list(by_dim.values())
        latest_run_id = latest_items[0].get("pipeline_run_id") if latest_items else None
        df = pd.DataFrame(latest_items)
        df = df[["dimension", "total", "valid", "rejected", "rejection_rate", "recorded_at"]]
        df["rejection_rate"] = df["rejection_rate"].apply(lambda x: f"{x:.4f}")
        st.dataframe(df, use_container_width=True, hide_index=True)
        if latest_run_id:
            st.caption(f"pipeline_run_id: `{latest_run_id}`")


# --- Historico de rejection_rate ---
st.markdown("---")
st.subheader("Historico de rejection_rate por dimension")

filtered_hist = _relevant(hist_all, show_all=show_all)
histories = []
for it in filtered_hist:
    histories.append({
        "dimension": it.get("dimension"),
        "recorded_at": it.get("recorded_at"),
        "rejection_rate": it.get("rejection_rate"),
        "rejected": it.get("rejected"),
        "total": it.get("total"),
    })

if not histories:
    st.info(
        "Sin historico relevante. Si solo hay runs de test, activa el "
        "toggle de arriba para verlos."
    )
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
    _cached_history.clear()
    st.rerun()
