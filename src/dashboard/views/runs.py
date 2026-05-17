"""Pipeline runs view.

RF-5: tabla paginada del historico de runs del pipeline.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import show_api_error
from src.dashboard.config import CACHE_TTL_SECONDS


api: ApiClient = st.session_state["api_client"]


PAGE_SIZE = 20


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_runs(_base_url: str, limit: int, offset: int):
    return api.list_runs(limit=limit, offset=offset)


def _status_badge(status: str) -> str:
    # Sin CSS, solo prefijo ascii del badge para la tabla
    return {
        "success": "[OK] success",
        "failed":  "[FAIL] failed",
        "running": "[..] running",
    }.get(status, status or "?")


def _short_dt(value) -> str:
    if not value:
        return "—"
    s = str(value)
    if len(s) > 19:
        return s[:19].replace("T", " ")
    return s.replace("T", " ")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.title("Pipeline runs")
st.caption(
    "Historico de ejecuciones del ETL (bootstrap + watcher + manual). "
    "Mas reciente arriba. Los runs fallidos llevan `error_message`."
)


col_left, col_right = st.columns([3, 1])
with col_right:
    page = st.number_input(
        "Pagina",
        min_value=1,
        value=1,
        step=1,
        help=f"{PAGE_SIZE} runs por pagina",
    )
offset = int((page - 1) * PAGE_SIZE)


data, err = _cached_runs(api.base_url, limit=PAGE_SIZE, offset=offset)
if err is not None:
    show_api_error(err, context="")
    st.stop()

items = (data or {}).get("items", [])
total = (data or {}).get("total", 0)

if not items:
    st.info("Sin runs en esta pagina.")
else:
    rows = []
    failed_runs = []
    for r in items:
        rows.append({
            "Inicio": _short_dt(r.get("started_at")),
            "Fin": _short_dt(r.get("finished_at")),
            "Trigger": r.get("trigger_type", "?"),
            "Status": _status_badge(r.get("status", "?")),
            "Procesados": r.get("records_processed", 0),
            "Rechazados": r.get("records_rejected", 0),
            "ID": r.get("id", "")[:8] + "…" if r.get("id") else "",
        })
        if r.get("status") == "failed":
            failed_runs.append(r)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    last_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    st.caption(f"Total: {total:,} runs — pagina {int(page)} de {last_page}")

    if failed_runs:
        st.markdown("---")
        st.subheader("Detalles de runs fallidos en esta pagina")
        for r in failed_runs:
            err_msg = r.get("error_message", "")
            with st.expander(
                f"[FAIL] {_short_dt(r.get('started_at'))} — {r.get('id', '?')[:12]}…",
                expanded=False,
            ):
                st.code(err_msg or "(sin mensaje de error)")


st.markdown("---")
if st.button("Recargar"):
    _cached_runs.clear()
    st.rerun()
