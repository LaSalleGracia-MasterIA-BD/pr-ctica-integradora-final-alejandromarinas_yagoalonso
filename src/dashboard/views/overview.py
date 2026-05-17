"""Overview view.

Implementa:
  - RF-1: 4 cards (patients/admissions/radiografias/modelo) + ultimo run
  - RF-7a: strip minimo de evaluacion (accuracy + macro-F1 + model_version)
  - RNF-7: auto-refresh cada 30s con st.fragment sobre cards + ultimo run.
           El strip de evaluacion vive FUERA del fragment (TTL 60s, ya cacheado)

Senales independientes (CB-4):
  - predictor_loaded de /health → chip "Modelo" + warning del bloque cards
  - 503 en /model/evaluation → strip de evaluacion sustituido por "Reporte no disponible"
"""
from __future__ import annotations

import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import (
    CONTEXT_MODEL_EVALUATION,
    show_api_error,
)
from src.dashboard.config import CACHE_TTL_SECONDS


api: ApiClient = st.session_state["api_client"]


# ---------------------------------------------------------------------------
# Helpers cacheados
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_health(_base_url: str):
    return api.health()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_counts(_base_url: str):
    p, p_err = api.count_patients()
    a, a_err = api.count_admissions()
    r, r_err = api.count_radiographies()
    return {
        "patients": (p, p_err),
        "admissions": (a, a_err),
        "radiographies": (r, r_err),
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_latest_run(_base_url: str):
    return api.latest_pipeline_run()


@st.cache_data(ttl=60, show_spinner=False)
def _cached_model_evaluation(_base_url: str):
    """TTL=60s (las metricas no cambian hasta reentrenar)."""
    return api.model_evaluation()


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.title("Resumen del sistema")
st.caption(
    "Vision general del estado actual del hospital. Se actualiza "
    "automaticamente cada 30 segundos."
)


@st.fragment(run_every=30)
def _render_live_block() -> None:
    """Cards + ultimo run. Se re-ejecuta cada 30s sin recargar el resto."""
    counts = _cached_counts(api.base_url)
    health_data, health_err = _cached_health(api.base_url)

    # --- 4 cards ---
    cols = st.columns(4)
    p, p_err = counts["patients"]
    cols[0].metric(
        "Pacientes",
        value=f"{p:,}" if p_err is None and p is not None else "—",
        help="Pacientes totales en MongoDB",
    )

    a, a_err = counts["admissions"]
    cols[1].metric(
        "Admisiones",
        value=f"{a:,}" if a_err is None and a is not None else "—",
        help="Admisiones embebidas en pacientes",
    )

    r, r_err = counts["radiographies"]
    cols[2].metric(
        "Radiografias",
        value=f"{r:,}" if r_err is None and r is not None else "—",
        help="Radiografias en el bucket MinIO",
    )

    if health_err is not None:
        cols[3].metric("Modelo", value="?", help="API no disponible")
    else:
        loaded = bool(health_data and health_data.get("predictor_loaded"))
        cols[3].metric(
            "Modelo",
            value="Cargado" if loaded else "No cargado",
            help="Indicador de `predictor_loaded` en /api/v1/health",
        )

    # Mostrar errores agregados (si los hay) — sin spammar 1 banner por count
    errs = [e for _, e in counts.values() if e is not None]
    if errs and health_err is None:
        show_api_error(errs[0], context="")

    # --- Ultimo run ---
    st.subheader("Ultimo pipeline run")
    run_data, run_err = _cached_latest_run(api.base_url)
    if run_err is not None:
        if run_err.kind == "not_found":
            st.info("Aun no hay runs registrados.")
        else:
            show_api_error(run_err, context="")
    else:
        run_cols = st.columns(5)
        run_cols[0].markdown(f"**Status**\n\n`{run_data.get('status', '?')}`")
        run_cols[1].markdown(f"**Trigger**\n\n`{run_data.get('trigger_type', '?')}`")
        started = run_data.get("started_at") or "—"
        if isinstance(started, str) and len(started) > 19:
            started = started[:19].replace("T", " ")
        run_cols[2].markdown(f"**Inicio**\n\n`{started}`")
        run_cols[3].metric("Procesados", value=run_data.get("records_processed", 0))
        run_cols[4].metric("Rechazados", value=run_data.get("records_rejected", 0))

        if run_data.get("status") == "failed" and run_data.get("error_message"):
            with st.expander("Ver error del run"):
                st.code(run_data["error_message"])


_render_live_block()


# ---------------------------------------------------------------------------
# RF-7a: strip minimo de evaluacion del modelo
# Fuera del fragment porque las metricas NO cambian hasta reentrenar.
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("Evaluacion del modelo")
st.caption(
    "Resumen sobre el split de test. El detalle completo (matriz de "
    "confusion + recall por clase) esta en la vista Clasificador."
)

eval_data, eval_err = _cached_model_evaluation(api.base_url)
if eval_err is not None:
    show_api_error(eval_err, context=CONTEXT_MODEL_EVALUATION)
else:
    eval_cols = st.columns(3)
    eval_cols[0].metric(
        "Accuracy",
        value=f"{eval_data.get('accuracy', 0):.3f}",
    )
    eval_cols[1].metric(
        "Macro-F1",
        value=f"{eval_data.get('macro_f1', 0):.3f}",
    )
    eval_cols[2].markdown(
        f"**Version del modelo**\n\n`{eval_data.get('model_version', '?')}`"
    )


# ---------------------------------------------------------------------------
# Boton de recarga manual
# ---------------------------------------------------------------------------

st.markdown("---")
if st.button("Recargar"):
    _cached_counts.clear()
    _cached_health.clear()
    _cached_latest_run.clear()
    _cached_model_evaluation.clear()
    st.rerun()
