"""Pacientes view.

RF-3: tabla paginada (server-side via limit/offset) + detalle del
paciente seleccionado con admissions y radiografias embebidas.
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
def _cached_list(_base_url: str, limit: int, offset: int):
    return api.list_patients(limit=limit, offset=offset)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_patient(_base_url: str, external_id: str):
    return api.get_patient(external_id)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.title("Pacientes")
st.caption(
    "Lista paginada de pacientes registrados en MongoDB. Cada paciente "
    "trae sus admisiones y radiografias embebidas."
)


# Paginacion en sidebar de la pagina (no en el sidebar global del app)
col_left, col_right = st.columns([3, 1])
with col_right:
    page = st.number_input(
        "Pagina",
        min_value=1,
        value=1,
        step=1,
        help=f"{PAGE_SIZE} pacientes por pagina",
    )
offset = int((page - 1) * PAGE_SIZE)

with col_left:
    st.markdown(f"**Pacientes — pagina {int(page)}**")

data, err = _cached_list(api.base_url, limit=PAGE_SIZE, offset=offset)
if err is not None:
    show_api_error(err, context="")
    st.stop()

items = data.get("items", []) if data else []
total = data.get("total", 0) if data else 0

selected_external_id: str | None = None

if not items:
    st.info("Sin pacientes en esta pagina.")
else:
    rows = []
    for p in items:
        rows.append({
            "external_id": p.get("external_id"),
            "name": p.get("name"),
            "age": p.get("age"),
            "gender": p.get("gender"),
            "blood_type": p.get("blood_type"),
            "admissions": len(p.get("admissions") or []),
            "radiografias": len(p.get("radiographies") or []),
        })
    df = pd.DataFrame(rows)

    # Tabla con seleccion de fila (Streamlit 1.30+). Al pulsar una fila,
    # `event.selection.rows` contiene su indice; usamos eso para abrir
    # el detalle automaticamente (RF-3, sin input manual).
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="patients_table",
    )
    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        idx = selected_rows[0]
        selected_external_id = rows[idx]["external_id"]

    last_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    st.caption(
        f"Total: {total:,} pacientes — pagina {int(page)} de {last_page}. "
        "Haz click en una fila para ver el detalle del paciente."
    )


# --- Detalle ---
st.markdown("---")
st.subheader("Detalle del paciente seleccionado")

if not selected_external_id:
    st.info("Selecciona un paciente en la tabla para ver su detalle.")
else:
    detail, det_err = _cached_patient(api.base_url, selected_external_id)
    if det_err is not None:
        if det_err.kind == "not_found":
            st.info(f"No existe el paciente `{selected_external_id}`.")
        else:
            show_api_error(det_err, context="")
    elif detail:
        cols = st.columns(5)
        cols[0].markdown(f"**ID**\n\n`{detail.get('external_id')}`")
        cols[1].markdown(f"**Nombre**\n\n{detail.get('name') or '—'}")
        cols[2].metric("Edad", value=detail.get("age") or "—")
        cols[3].markdown(f"**Genero**\n\n{detail.get('gender') or '—'}")
        cols[4].markdown(f"**Grupo sanguineo**\n\n{detail.get('blood_type') or '—'}")

        admissions = detail.get("admissions") or []
        with st.expander(f"Admisiones ({len(admissions)})", expanded=False):
            if admissions:
                df_adm = pd.DataFrame([
                    {
                        "Fecha ingreso": a.get("admission_date"),
                        "Fecha alta": a.get("discharge_date"),
                        "Departamento": a.get("department"),
                        "Categoria": a.get("diagnosis_category"),
                        "Descripcion": a.get("diagnosis_description"),
                        "Status": a.get("status"),
                    }
                    for a in admissions
                ])
                st.dataframe(df_adm, use_container_width=True, hide_index=True)
            else:
                st.caption("Sin admisiones.")

        radios = detail.get("radiographies") or []
        with st.expander(f"Radiografias ({len(radios)})", expanded=False):
            if radios:
                df_rad = pd.DataFrame([
                    {
                        "Object key": r.get("minio_object_key"),
                        "Fichero": r.get("original_filename"),
                        "Tamano (bytes)": r.get("file_size_bytes"),
                        "Clase predicha": (
                            r.get("classification") or {}
                        ).get("predicted_class") if isinstance(r.get("classification"), dict)
                        else None,
                    }
                    for r in radios
                ])
                st.dataframe(df_rad, use_container_width=True, hide_index=True)
            else:
                st.caption("Sin radiografias.")


st.markdown("---")
if st.button("Recargar"):
    _cached_list.clear()
    _cached_patient.clear()
    st.rerun()
