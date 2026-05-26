"""Entrypoint de Streamlit para el dashboard del hospital.

Navegacion en dos bloques (rediseno UX fase 1):

  Operacion         Sistema
  - Inicio          - Calidad de datos
  - Triaje          - Pipeline runs
  - Alertas
  - Pacientes
  - Clasificador

La sidebar usa `st.navigation({...})` con secciones, lo que Streamlit
1.36+ renderiza como cabeceras de grupo. El CSS adicional (microinter-
acciones + tratamiento visual del bloque "Sistema") se inyecta una sola
vez via `inject_sidebar_styles()`.

El footer de la sidebar mantiene los 3 chips de estado del sistema
persistentes en todas las vistas (`render_system_status`).

UI en castellano, sin emojis (convencion ASCII del repo).
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.sidebar_styles import inject_sidebar_styles
from src.dashboard.components.system_status import render_system_status
from src.dashboard.config import API_BASE_URL, API_TIMEOUT_SECONDS


st.set_page_config(
    page_title="Hospital laSalle",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS de la sidebar + de la vista Inicio. Idempotente: se puede llamar
# en cada rerun. Debe ir ANTES de st.navigation para que afecte al
# primer render del menu lateral.
inject_sidebar_styles()


# Una ApiClient por sesion, reutilizada entre reruns
if "api_client" not in st.session_state:
    st.session_state["api_client"] = ApiClient(
        base_url=API_BASE_URL,
        timeout=API_TIMEOUT_SECONDS,
    )


# Resuelve la ruta a views/ relativa a este fichero para que la
# navegacion funcione tanto dentro del contenedor
# (/app/src/dashboard/...) como desde cualquier otro sitio si alguien
# ejecuta `streamlit run src/dashboard/app.py`. Mismo patron que el
# `app.py` anterior — robusto frente a cwd arbitrario.
#
# `st.navigation(dict)` renderiza el nombre de cada grupo como cabecera
# en la sidebar (Streamlit >= 1.36).
# Orden dentro de "Operacion": el flujo natural de turno
#   inicio -> triaje -> alertas -> pacientes -> clasificador
# Los items de "Sistema" son herramientas de diagnostico tecnico y
# pasan a un bloque atenuado debajo (ver `static/dashboard.css`).
_VIEWS_DIR = Path(__file__).resolve().parent / "views"

pages = {
    "Operacion": [
        st.Page(str(_VIEWS_DIR / "overview.py"),   title="Inicio", default=True),
        st.Page(str(_VIEWS_DIR / "triage.py"),     title="Triaje"),
        st.Page(str(_VIEWS_DIR / "alerts.py"),     title="Alertas"),
        st.Page(str(_VIEWS_DIR / "patients.py"),   title="Pacientes"),
        st.Page(str(_VIEWS_DIR / "classifier.py"), title="Clasificador"),
    ],
    "Sistema": [
        st.Page(str(_VIEWS_DIR / "quality.py"), title="Calidad de datos"),
        st.Page(str(_VIEWS_DIR / "runs.py"),    title="Pipeline runs"),
    ],
}

# Brand de la sidebar: cabecera pequena con nombre del producto. Se
# inserta ANTES de la navegacion para que aparezca arriba del todo.
with st.sidebar:
    st.markdown(
        '<div class="lasalle-brand">'
        '<div class="lasalle-brand-mark"></div>'
        '<div class="lasalle-brand-text">'
        '<div class="lasalle-brand-name">laSalle Health</div>'
        '<div class="lasalle-brand-sub">Centro de control</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# Ejecuta la pagina seleccionada
st.navigation(pages).run()

# Footer persistente de la sidebar con los 3 chips de estado del
# sistema (API / Modelo / Ultimo run). Se renderiza en cada pagina.
with st.sidebar:
    render_system_status(st.session_state["api_client"])
