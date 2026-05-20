"""Streamlit entrypoint for the hospital dashboard.

Views via `st.navigation`:
  - Overview
  - Calidad de datos
  - Pacientes
  - Triaje
  - Alertas
  - Clasificador
  - Pipeline runs

The sidebar footer hosts a persistent system-status strip (3 chips:
API, Modelo, Ultimo run) rendered on every page so the operator never
loses sight of the stack health.

UI in Spanish, no emojis (ASCII convention).
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.system_status import render_system_status
from src.dashboard.config import API_BASE_URL, API_TIMEOUT_SECONDS


st.set_page_config(
    page_title="Hospital laSalle",
    layout="wide",
    initial_sidebar_state="expanded",
)


# One ApiClient per session, reused across reruns
if "api_client" not in st.session_state:
    st.session_state["api_client"] = ApiClient(
        base_url=API_BASE_URL,
        timeout=API_TIMEOUT_SECONDS,
    )


# Resolve the views/ directory relative to this file so navigation works
# both inside the container (/app/src/dashboard/...) and from anywhere
# else if someone runs `streamlit run src/dashboard/app.py`.
_VIEWS_DIR = Path(__file__).resolve().parent / "views"

pages = [
    st.Page(
        str(_VIEWS_DIR / "overview.py"),
        title="Overview",
        default=True,
    ),
    st.Page(
        str(_VIEWS_DIR / "quality.py"),
        title="Calidad de datos",
    ),
    st.Page(
        str(_VIEWS_DIR / "patients.py"),
        title="Pacientes",
    ),
    st.Page(
        str(_VIEWS_DIR / "triage.py"),
        title="Triaje",
    ),
    st.Page(
        str(_VIEWS_DIR / "alerts.py"),
        title="Alertas",
    ),
    st.Page(
        str(_VIEWS_DIR / "classifier.py"),
        title="Clasificador",
    ),
    st.Page(
        str(_VIEWS_DIR / "runs.py"),
        title="Pipeline runs",
    ),
]

# Run the selected page
st.navigation(pages).run()

# Persistent system-status footer in the sidebar (renders on every page)
with st.sidebar:
    render_system_status(st.session_state["api_client"])
