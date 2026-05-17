"""Pipeline runs view.

RF-5: tabla paginada del historico de runs del pipeline.

Filtro por defecto: oculta `trigger_type=e2e-test` (runs generados
automaticamente por la suite de tests E2E con datasets vacios) para
que la vista de operacion ensene runs "reales" de bootstrap/watcher.
Toggle para mostrar los tecnicos sin esconder nada.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import show_api_error
from src.dashboard.config import CACHE_TTL_SECONDS


api: ApiClient = st.session_state["api_client"]


PAGE_SIZE = 20
# Pedimos hasta 200 runs y paginamos client-side para poder filtrar por
# trigger sin perdernos paginas. El total real es del orden de decenas
# en este proyecto; no hay riesgo de rendimiento.
FETCH_LIMIT = 200

TECHNICAL_TRIGGERS = {"e2e-test"}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_runs(_base_url: str, limit: int):
    return api.list_runs(limit=limit, offset=0)


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


show_technical = st.checkbox(
    "Mostrar runs tecnicos/de test",
    value=False,
    help=(
        "Por defecto se ocultan los runs con `trigger_type=e2e-test` "
        "(los crean los tests automaticos con datasets vacios). "
        "Activalo para auditar el historico completo sin filtros."
    ),
)


data, err = _cached_runs(api.base_url, limit=FETCH_LIMIT)
if err is not None:
    show_api_error(err, context="")
    st.stop()

all_items = (data or {}).get("items", [])
total_raw = (data or {}).get("total", 0)

# Filtrado por trigger
items_filtered = [
    r for r in all_items
    if show_technical or r.get("trigger_type") not in TECHNICAL_TRIGGERS
]
hidden_count = len(all_items) - len(items_filtered)

# Paginacion client-side sobre lo filtrado
total_visible = len(items_filtered)
last_page = max(1, (total_visible + PAGE_SIZE - 1) // PAGE_SIZE)

col_left, col_right = st.columns([3, 1])
with col_right:
    page = st.number_input(
        "Pagina",
        min_value=1,
        max_value=last_page,
        value=1,
        step=1,
        help=f"{PAGE_SIZE} runs por pagina",
    )
offset = int((page - 1) * PAGE_SIZE)
page_items = items_filtered[offset : offset + PAGE_SIZE]


if not page_items:
    if show_technical:
        st.info("Sin runs en esta pagina.")
    else:
        st.info(
            "Sin runs operativos en esta pagina. Si solo hay runs de test, "
            "activa el toggle de arriba para verlos."
        )
else:
    rows = []
    failed_runs = []
    for r in page_items:
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

    caption = (
        f"Total visible: {total_visible:,} de {total_raw:,} runs — "
        f"pagina {int(page)} de {last_page}."
    )
    if hidden_count > 0 and not show_technical:
        caption += f" Ocultos: {hidden_count} runs tecnicos/de test."
    st.caption(caption)

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
