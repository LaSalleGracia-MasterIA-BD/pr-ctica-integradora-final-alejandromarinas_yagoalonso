"""Vista Pacientes (rediseno UX fase 4).

Buscador prominente, tabla simple, detalle compacto. Sin grids
densos en la cabecera del detalle.

Cambios respecto a la version anterior:
  - Buscador como input grande arriba del listado (no a media pagina).
    Cuando hay valor, gana sobre la seleccion de la tabla.
  - Tabla con 5 columnas (external_id, nombre, edad, genero,
    admisiones); blood_type y radiografias se quitan de la tabla y
    pasan al detalle.
  - Detalle: header compacto en una linea (ID + nombre + edad / genero
    como meta), no 5 metric grandes en fila.
  - Admisiones y radiografias en expanders, igual que antes. Se quita
    el caption tecnico del top.

API-only: solo `list_patients` y `get_patient`. Sin escritura.
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

st.markdown(
    '<div class="lasalle-page-head">'
    '<h1>Pacientes</h1>'
    '<div class="lph-meta">Buscar por ID o consultar el detalle.</div>'
    '</div>',
    unsafe_allow_html=True,
)

# Buscador prominente
st.markdown("<div style='height: 14px'></div>", unsafe_allow_html=True)
search_id = st.text_input(
    "Buscar paciente",
    value="",
    placeholder="HOSP-000123, TRIAGE-20260519-0001 ...",
    label_visibility="collapsed",
).strip()


# Paginacion solo cuando NO hay busqueda activa
page = 1
if not search_id:
    p_col, _ = st.columns([1, 5])
    with p_col:
        page = st.number_input(
            "Pagina",
            min_value=1,
            value=1,
            step=1,
            label_visibility="collapsed",
            help=f"{PAGE_SIZE} pacientes por pagina",
        )

offset = int((page - 1) * PAGE_SIZE)


# ---------------------------------------------------------------------------
# Listado (cuando no hay busqueda activa)
# ---------------------------------------------------------------------------

selected_external_id: str | None = None
total = 0
last_page = 1

if not search_id:
    data, err = _cached_list(api.base_url, limit=PAGE_SIZE, offset=offset)
    if err is not None:
        show_api_error(err, context="")
        st.stop()

    items = data.get("items", []) if data else []
    total = data.get("total", 0) if data else 0
    last_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    if not items:
        st.markdown(
            '<div class="lasalle-empty">Sin pacientes en esta pagina.</div>',
            unsafe_allow_html=True,
        )
    else:
        rows = []
        for p in items:
            rows.append({
                "external_id": p.get("external_id"),
                "Nombre": p.get("name"),
                "Edad": p.get("age"),
                "Genero": p.get("gender"),
                "Admisiones": len(p.get("admissions") or []),
            })
        df = pd.DataFrame(rows)

        event = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="patients_table",
            column_config={
                "external_id": st.column_config.TextColumn(
                    "ID",
                    help="external_id en MongoDB",
                ),
            },
        )
        selected_rows = event.selection.rows if event and event.selection else []
        if selected_rows:
            idx = selected_rows[0]
            selected_external_id = rows[idx]["external_id"]

        st.caption(
            f"Pagina {int(page)} de {last_page} · {total:,} pacientes en total. "
            "Selecciona una fila para ver el detalle."
        )


# ---------------------------------------------------------------------------
# Detalle
# ---------------------------------------------------------------------------

effective_external_id = search_id or selected_external_id

if effective_external_id:
    st.markdown("<div style='height: 24px'></div>", unsafe_allow_html=True)

    detail, det_err = _cached_patient(api.base_url, effective_external_id)
    if det_err is not None:
        if det_err.kind == "not_found":
            st.markdown(
                f'<div class="lasalle-empty">No existe el paciente '
                f'<span class="mono">{effective_external_id}</span>.</div>',
                unsafe_allow_html=True,
            )
        else:
            show_api_error(det_err, context="")
    elif detail:
        # Cabecera compacta del paciente: nombre grande, meta en una linea
        name = detail.get("name") or "—"
        age = detail.get("age")
        gender = detail.get("gender") or "—"
        blood = detail.get("blood_type") or None
        ext_id = detail.get("external_id") or "?"

        meta_bits = [
            f'<span class="mono">{ext_id}</span>',
            f"{age} anos" if age is not None else None,
            f"genero {gender}",
        ]
        if blood:
            meta_bits.append(f"grupo {blood}")
        # Separadores tipograficos sutiles
        meta_html = ' <span style="color:#CBD5E1;">·</span> '.join(
            b for b in meta_bits if b
        )
        st.markdown(
            f'<div class="lasalle-patient-head">'
            f'<div class="lph-name">{name}</div>'
            f'<div class="lph-meta">{meta_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        admissions = detail.get("admissions") or []
        radios = detail.get("radiographies") or []

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
else:
    if not search_id:
        st.markdown("<div style='height: 14px'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="lasalle-empty">'
            'Selecciona un paciente en la tabla, o usa el buscador.'
            '</div>',
            unsafe_allow_html=True,
        )


# Recarga sutil al final
st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
if st.button("Recargar"):
    _cached_list.clear()
    _cached_patient.clear()
    st.rerun()
