"""Inyecta el CSS del dashboard desde un fichero estatico.

El CSS vive como fichero suelto en `src/dashboard/static/dashboard.css`
para mantenerlo auditable (linting CSS, diffs limpios, sin mezclar
HTML/CSS dentro de un literal Python gigante).

Esta funcion lo lee al arrancar `app.py` y lo inyecta una sola vez
via `st.markdown(unsafe_allow_html=True)`. Idempotente: re-llamarla
en cada rerun es seguro — el navegador deduplica reglas identicas.

Cubre: microinteracciones de sidebar, vista Inicio (saludo + barra
critica + chips de estado + numeros grandes + accesos rapidos),
Triaje (formulario + panel de prioridad), Alertas (lista priorizada),
Pacientes (cabecera de detalle) y Clasificador (imagen + panel de
prediccion).

Para recortar o ajustar estilos, editar el .css directamente.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st


_CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "dashboard.css"


def inject_sidebar_styles() -> None:
    """Lee `static/dashboard.css` y lo inyecta dentro de la pagina."""
    try:
        css = _CSS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Falla suave: si el fichero no esta, el dashboard sigue
        # funcionando aunque sin el tema visual del rediseno v2.
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


__all__ = ["inject_sidebar_styles"]
