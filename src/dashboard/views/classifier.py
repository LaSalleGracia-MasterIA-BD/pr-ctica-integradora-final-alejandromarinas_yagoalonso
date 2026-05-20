"""Clasificador view.

RF-4 + RF-7b: dropdown de radiografias + visualizacion de la imagen +
boton "Clasificar" + sub-seccion de evaluacion detallada (recall por
clase + matriz de confusion) al final, compartiendo cache con Overview.

Manejo explicito de errores:
  - CB-7 (imagen dummy 1x1 → 422): mensaje + boton sigue habilitado
  - CB-4 (predictor_loaded=false): boton deshabilitado + warning
  - CB-5 (imagen no en MinIO): mensaje + boton sigue habilitado
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import (
    CONTEXT_CLASSIFY,
    CONTEXT_MODEL_EVALUATION,
    format_error,
    show_api_error,
)
from src.dashboard.config import CACHE_TTL_SECONDS


api: ApiClient = st.session_state["api_client"]


DEMO_KEY_PREFIX = "HOSP-DEMO-"
PRES_KEY_PREFIX = "HOSP-PRES-"

# Umbral por bytes para considerar una radiografia "clasificable" por
# el modelo (CB-7): las dummy 1x1 pesan ~67 bytes y la API las rechaza
# con 422. Una sintetica real (HOSP-DEMO) pesa ~40 KB y una del dataset
# Kaggle ~20-30 KB. Con 1024 bytes nos quedamos solo con las utiles
# y dejamos margen para PNGs pequenos validos en el futuro.
MIN_CLASSIFIABLE_BYTES = 1024

# Texto que se muestra DEBAJO de la imagen cuando la radiografia
# seleccionada es una sintetica generada por el bootstrap (no real).
# Sirve para que el evaluador/medico NO confunda la demo tecnica con
# evidencia clinica real.
SYNTHETIC_DEMO_NOTE = (
    " (imagen sintetica de demo — no es una radiografia real)"
)


def _is_synthetic_demo(key: str) -> bool:
    """True si la key pertenece al subset de imagenes sinteticas de demo."""
    return key.startswith(DEMO_KEY_PREFIX)


def _is_presentation(key: str) -> bool:
    """True si la key pertenece a HOSP-PRES-* (radiografias reales para demo)."""
    return key.startswith(PRES_KEY_PREFIX)


def _is_classifiable(item: dict) -> bool:
    """Heuristica por bytes: dummy 1x1 ~67 B, validas >= ~20 KB."""
    size = item.get("file_size_bytes") or 0
    return size >= MIN_CLASSIFIABLE_BYTES


def _sort_key(item: dict) -> tuple[int, str]:
    """Orden del dropdown: HOSP-PRES-* primero, luego HOSP-DEMO-*, luego resto."""
    key = item.get("minio_object_key", "")
    if _is_presentation(key):
        return (0, key)
    if _is_synthetic_demo(key):
        return (1, key)
    return (2, key)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_radiographies(_base_url: str):
    """Lista plana de radiografias (limit=500 — suficiente para la demo)."""
    return api.list_radiographies(limit=500, offset=0)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_health(_base_url: str):
    return api.health()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_image(_base_url: str, key: str):
    return api.image_bytes(key)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_model_evaluation(_base_url: str):
    """Comparte semantica con la vista Overview (TTL=60s)."""
    return api.model_evaluation()


def _order_keys_for_dropdown(items: list[dict], include_unclassifiable: bool) -> list[str]:
    """Lista de keys para el dropdown, filtrada y ordenada.

    Por defecto excluye las que el modelo rechaza (file_size_bytes < umbral).
    Orden: HOSP-PRES-* (reales) → HOSP-DEMO-* (sinteticas) → resto.
    """
    visible = [
        it for it in items
        if it.get("minio_object_key")
        and (include_unclassifiable or _is_classifiable(it))
    ]
    visible.sort(key=_sort_key)
    return [it["minio_object_key"] for it in visible]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.title("Clasificador de radiografias")
st.caption(
    "Selecciona una radiografia registrada en el sistema y pulsa "
    '"Clasificar" para que el modelo CNN devuelva la clase predicha + '
    "probabilidades."
)


# 1. Cargar lista de radiografias
radios_data, radios_err = _cached_radiographies(api.base_url)
if radios_err is not None:
    show_api_error(radios_err, context="")
    st.stop()

items = (radios_data or {}).get("items", [])
if not items:
    st.info("Sin radiografias en el sistema todavia.")
    st.stop()


# 2. Toggle para mostrar las dummy no clasificables (oculto por defecto)
show_unclassifiable = st.checkbox(
    "Mostrar imagenes no clasificables",
    value=False,
    help=(
        "Si lo activas, el dropdown incluye tambien las 17 dummy 1x1 "
        "del bootstrap. El modelo las rechaza con 422 (caso borde CB-7); "
        "util si quieres VER el mensaje de rechazo."
    ),
)

keys = _order_keys_for_dropdown(items, include_unclassifiable=show_unclassifiable)
if not keys:
    st.warning(
        "Sin radiografias clasificables. Activa 'Mostrar imagenes no "
        "clasificables' para ver las dummy o anade radiografias reales "
        "siguiendo `docs/runbooks/use-real-radiograph-for-demo.md`."
    )
    st.stop()


# 3. Tip contextual segun lo que hay disponible
n_pres = sum(1 for k in keys if _is_presentation(k))
n_demo = sum(1 for k in keys if _is_synthetic_demo(k))
if n_pres > 0:
    st.caption(
        f"**Tip:** dropdown ordenado con {n_pres} radiografias reales "
        f"(`HOSP-PRES-*`) primero, luego la sintetica `HOSP-DEMO-001`. "
        f"Usa las HOSP-PRES-* para la demo clinica."
    )
elif n_demo > 0:
    st.caption(
        "**Tip:** solo hay imagenes sinteticas de demo (`HOSP-DEMO-*`). "
        "Para subir radiografias reales (HOSP-PRES-*) sigue "
        "`docs/runbooks/use-real-radiograph-for-demo.md`."
    )

selected_key = st.selectbox("Radiografia", options=keys, index=0)


# 3. Health para CB-4
health_data, health_err = _cached_health(api.base_url)
model_loaded = bool(
    health_err is None
    and health_data
    and health_data.get("predictor_loaded")
)


# 4. Imagen
img_col, action_col = st.columns([2, 1])

with img_col:
    st.markdown("**Imagen seleccionada**")
    image_bytes, image_err = _cached_image(api.base_url, selected_key)
    if image_err is not None:
        show_api_error(image_err, context="")
    elif image_bytes:
        caption = selected_key
        if _is_synthetic_demo(selected_key):
            caption += SYNTHETIC_DEMO_NOTE
        st.image(image_bytes, caption=caption, use_column_width=True)
        if _is_synthetic_demo(selected_key):
            st.warning(
                "Estas viendo una **imagen sintetica de demo** generada "
                "por el bootstrap (`HOSP-DEMO-001`). Cualquier prediccion "
                "que devuelva el modelo NO es evidencia clinica: el patron "
                "de la imagen no corresponde a una radiografia real. "
                "Para una demo con valor clinico, usa una radiografia real "
                "siguiendo `docs/runbooks/use-real-radiograph-for-demo.md`."
            )


# 5. Resultado de clasificacion (mantenido en session_state)
_state_key = "classifier_result"


def _classify_action(key: str) -> None:
    """Llama POST /classify y guarda resultado/error en session_state."""
    data, err = api.classify(key)
    st.session_state[_state_key] = {
        "key": key,
        "data": data,
        "error": err,
    }


with action_col:
    st.markdown("**Accion**")
    if not model_loaded:
        st.warning(
            "El modelo de clasificacion no esta cargado. El boton "
            '"Clasificar" esta deshabilitado.'
        )
    st.button(
        "Clasificar",
        on_click=_classify_action,
        args=(selected_key,),
        disabled=not model_loaded,
        type="primary",
    )


# 6. Render del resultado (si existe y es de la key actual)
result = st.session_state.get(_state_key)
if result and result["key"] == selected_key:
    st.markdown("---")
    st.subheader("Resultado de la clasificacion")
    if result["error"] is not None:
        show_api_error(result["error"], context=CONTEXT_CLASSIFY)
    else:
        data = result["data"]
        predicted = data.get("predicted_class", "?")
        probabilities = data.get("probabilities", {})

        meta_cols = st.columns(4)
        meta_cols[0].metric("Clase predicha", value=predicted)
        meta_cols[1].markdown(
            f"**Version del modelo**\n\n`{data.get('model_version', '?')}`"
        )
        meta_cols[2].markdown(
            f"**Regla de decision**\n\n`{data.get('decision_rule', '?')}`"
        )
        predicted_at = data.get("predicted_at", "")
        if isinstance(predicted_at, str) and len(predicted_at) > 19:
            predicted_at = predicted_at[:19].replace("T", " ")
        meta_cols[3].markdown(f"**Cuando**\n\n`{predicted_at}`")

        # Bar chart de probabilidades
        if probabilities:
            df_probs = pd.DataFrame(
                [{"Clase": k, "Probabilidad": v} for k, v in probabilities.items()],
            ).sort_values("Probabilidad", ascending=True)
            fig = px.bar(
                df_probs,
                x="Probabilidad",
                y="Clase",
                orientation="h",
                color="Clase",
                color_discrete_map={
                    "Normal": "#15803D",
                    "Pneumonia": "#D97706",
                    "COVID-19": "#DC2626",
                },
            )
            fig.update_xaxes(range=[0, 1], tickformat=".0%")
            fig.update_layout(
                margin=dict(l=10, r=10, t=10, b=10),
                height=240,
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# RF-7b: Evaluacion del modelo — detalle
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("Evaluacion del modelo — detalle")
st.caption(
    "Metricas sobre el split de test (no se recalcula on-the-fly). "
    "El recall mas critico clinicamente es el de COVID-19 (falsos "
    "negativos = pacientes contagiosos clasificados como sanos)."
)

eval_data, eval_err = _cached_model_evaluation(api.base_url)
if eval_err is not None:
    show_api_error(eval_err, context=CONTEXT_MODEL_EVALUATION)
else:
    classes = eval_data.get("classes", ["Normal", "Pneumonia", "COVID-19"])
    per_class = eval_data.get("per_class", {})
    confusion = eval_data.get("confusion_matrix", [])

    # Tabla de recall por clase
    if per_class:
        rows = []
        for cls in classes:
            metrics = per_class.get(cls, {})
            rows.append({
                "Clase": cls,
                "Precision": f"{metrics.get('precision', 0):.4f}",
                "Recall": f"{metrics.get('recall', 0):.4f}",
                "F1": f"{metrics.get('f1', 0):.4f}",
                "Soporte": metrics.get("support", 0),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Matriz de confusion
    if confusion:
        cm_df = pd.DataFrame(confusion, index=classes, columns=classes)
        fig_cm = px.imshow(
            cm_df,
            text_auto=True,
            color_continuous_scale="Blues",
            labels={"x": "Predicha", "y": "Real", "color": "Casos"},
        )
        fig_cm.update_layout(
            margin=dict(l=10, r=10, t=30, b=10),
            height=420,
            title="Matriz de confusion (test split)",
        )
        st.plotly_chart(fig_cm, use_container_width=True)


# ---------------------------------------------------------------------------
# Recarga
# ---------------------------------------------------------------------------

st.markdown("---")
if st.button("Recargar"):
    _cached_radiographies.clear()
    _cached_health.clear()
    _cached_image.clear()
    _cached_model_evaluation.clear()
    st.session_state.pop(_state_key, None)
    st.rerun()
