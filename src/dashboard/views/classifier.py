"""Vista Clasificador (rediseno UX fase 5).

Imagen mas protagonista, resultado claro, detalle del modelo plegado.

Cambios respecto a la version anterior:
  - Imagen full-width arriba (no compartiendo fila con la columna de
    accion). Boton "Clasificar" justo debajo.
  - Resultado simplificado: clase predicha grande + horizontal probs.
    Sin grid de 4 metric (clase / version / regla / cuando) — la
    version, la regla de decision y el timestamp pasan a una linea
    meta debajo.
  - La regla `covid_threshold_*` se muestra de forma legible
    ("Umbral COVID-19: 0.35"), no como id tecnico.
  - Bloque "Tip contextual" y captions tecnicos densos sustituidos
    por una linea breve cuando aplica.
  - Sub-seccion de evaluacion del modelo (recall + matriz de
    confusion) plegada en un expander al final, no abierta por
    defecto.
  - `use_column_width=True` (deprecado en Streamlit reciente)
    sustituido por `use_container_width=True`.

API-only: `list_radiographies`, `health`, `image_bytes`, `classify`,
`model_evaluation`. Sin escritura adicional, sin tocar backend.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import (
    CONTEXT_CLASSIFY,
    CONTEXT_MODEL_EVALUATION,
    show_api_error,
)
from src.dashboard.config import CACHE_TTL_SECONDS


api: ApiClient = st.session_state["api_client"]


DEMO_KEY_PREFIX = "HOSP-DEMO-"
PRES_KEY_PREFIX = "HOSP-PRES-"
MIN_CLASSIFIABLE_BYTES = 1024


# ---------------------------------------------------------------------------
# Helpers de orden / filtrado
# ---------------------------------------------------------------------------

def _is_synthetic_demo(key: str) -> bool:
    return key.startswith(DEMO_KEY_PREFIX)


def _is_presentation(key: str) -> bool:
    return key.startswith(PRES_KEY_PREFIX)


def _is_classifiable(item: dict) -> bool:
    return (item.get("file_size_bytes") or 0) >= MIN_CLASSIFIABLE_BYTES


def _sort_key(item: dict) -> tuple[int, str]:
    key = item.get("minio_object_key", "")
    if _is_presentation(key):
        return (0, key)
    if _is_synthetic_demo(key):
        return (1, key)
    return (2, key)


def _humanize_decision_rule(rule_id: str | None) -> str:
    """Vuelve legible el id tecnico de la regla de decision."""
    if not rule_id:
        return "—"
    # `covid_threshold_0.35` → "Umbral COVID-19: 0.35"
    if rule_id.startswith("covid_threshold_"):
        try:
            value = rule_id.split("_", 2)[2]
            return f"Umbral COVID-19: {value}"
        except IndexError:
            pass
    return rule_id


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_radiographies(_base_url: str):
    return api.list_radiographies(limit=500, offset=0)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_health(_base_url: str):
    return api.health()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_image(_base_url: str, key: str):
    return api.image_bytes(key)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_model_evaluation(_base_url: str):
    return api.model_evaluation()


def _order_keys(items: list[dict], include_unclassifiable: bool) -> list[str]:
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

st.markdown(
    '<div class="lasalle-page-head">'
    '<h1>Clasificador</h1>'
    '<div class="lph-meta">Inferencia Normal / Pneumonia / COVID-19 sobre una radiografia registrada.</div>'
    '</div>',
    unsafe_allow_html=True,
)


# Lista de radiografias
radios_data, radios_err = _cached_radiographies(api.base_url)
if radios_err is not None:
    show_api_error(radios_err, context="")
    st.stop()

items = (radios_data or {}).get("items", [])
if not items:
    st.markdown(
        '<div class="lasalle-empty">Sin radiografias en el sistema.</div>',
        unsafe_allow_html=True,
    )
    st.stop()


# Selector + toggle, compactos en una sola fila
sel_col, toggle_col = st.columns([3, 1])

with toggle_col:
    show_unclassifiable = st.checkbox(
        "Mostrar no clasificables",
        value=False,
        help=(
            "Incluye en el dropdown las imagenes dummy 1x1 del bootstrap. "
            "El modelo las rechaza con 422 (CB-7)."
        ),
    )

keys = _order_keys(items, include_unclassifiable=show_unclassifiable)
if not keys:
    st.markdown(
        '<div class="lasalle-empty">'
        'Sin radiografias clasificables. Activa "Mostrar no clasificables" '
        'para ver las dummy.'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

with sel_col:
    selected_key = st.selectbox(
        "Radiografia",
        options=keys,
        index=0,
        label_visibility="collapsed",
    )


# Health para CB-4
health_data, health_err = _cached_health(api.base_url)
model_loaded = bool(
    health_err is None
    and health_data
    and health_data.get("predictor_loaded")
)


# ---------------------------------------------------------------------------
# Imagen (mas protagonista) + boton clasificar debajo
# ---------------------------------------------------------------------------

st.markdown("<div style='height: 14px'></div>", unsafe_allow_html=True)

# Centrar la imagen en una columna mas estrecha que la pagina, para que
# se vea grande pero no desbordada. Streamlit no soporta `max-width` en
# `st.image`, asi que envolvemos en columnas con espaciador a ambos lados.
img_l, img_c, img_r = st.columns([1, 6, 1])
with img_c:
    image_bytes, image_err = _cached_image(api.base_url, selected_key)
    if image_err is not None:
        show_api_error(image_err, context="")
    elif image_bytes:
        # Streamlit 1.39 (la del Dockerfile.dashboard) NO acepta
        # `use_container_width` en `st.image` — ese kwarg llego en
        # 1.40. Usamos `use_column_width=True` (aun no deprecado del
        # todo en 1.39) y el efecto visual es el mismo dentro de la
        # columna central img_c.
        st.image(image_bytes, use_column_width=True)
        if _is_synthetic_demo(selected_key):
            st.markdown(
                '<div class="lasalle-disclaimer">'
                'Imagen sintetica de demo. La prediccion no es evidencia clinica.'
                '</div>',
                unsafe_allow_html=True,
            )
        # Caption sutil con el object key
        st.markdown(
            f'<div class="lasalle-img-caption mono">{selected_key}</div>',
            unsafe_allow_html=True,
        )


# Accion: boton centrado debajo de la imagen
st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)

if not model_loaded:
    st.markdown(
        '<div class="lasalle-disclaimer">'
        'El modelo de clasificacion no esta cargado.'
        '</div>',
        unsafe_allow_html=True,
    )


_state_key = "classifier_result"


def _classify_action(key: str) -> None:
    data, err = api.classify(key)
    st.session_state[_state_key] = {"key": key, "data": data, "error": err}


_btn_l, _btn_c, _btn_r = st.columns([2, 1, 2])
with _btn_c:
    st.button(
        "Clasificar imagen",
        on_click=_classify_action,
        args=(selected_key,),
        disabled=not model_loaded,
        type="primary",
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

result = st.session_state.get(_state_key)
if result and result["key"] == selected_key:
    st.markdown("<div style='height: 24px'></div>", unsafe_allow_html=True)
    if result["error"] is not None:
        show_api_error(result["error"], context=CONTEXT_CLASSIFY)
    else:
        data = result["data"] or {}
        predicted = data.get("predicted_class", "?")
        probabilities = data.get("probabilities", {})
        predicted_at = data.get("predicted_at", "")
        if isinstance(predicted_at, str) and len(predicted_at) > 19:
            predicted_at = predicted_at[:19].replace("T", " ")

        pred_class_for_css = {
            "Normal": "normal",
            "Pneumonia": "pneumonia",
            "COVID-19": "covid",
        }.get(predicted, "neutral")

        decision_rule_human = _humanize_decision_rule(data.get("decision_rule"))
        model_version = data.get("model_version", "?")

        st.markdown(
            f'<div class="lasalle-prediction {pred_class_for_css}">'
            f'<div class="lpd-label">Prediccion</div>'
            f'<div class="lpd-class">{predicted}</div>'
            f'<div class="lpd-meta">'
            f'<span class="mono">{model_version}</span>'
            f'<span class="lpd-sep">·</span>'
            f'<span>{decision_rule_human}</span>'
            f'<span class="lpd-sep">·</span>'
            f'<span class="mono">{predicted_at}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Probabilidades como bar chart horizontal compacto
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
                    "Normal": "#4B8A5A",
                    "Pneumonia": "#C47A1F",
                    "COVID-19": "#C44141",
                },
            )
            fig.update_xaxes(range=[0, 1], tickformat=".0%")
            fig.update_layout(
                margin=dict(l=10, r=10, t=10, b=10),
                height=200,
                showlegend=False,
                xaxis_title=None,
                yaxis_title=None,
                plot_bgcolor="#FFFFFF",
                paper_bgcolor="#FFFFFF",
            )
            st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Detalle del modelo - plegado
# ---------------------------------------------------------------------------

st.markdown("<div style='height: 18px'></div>", unsafe_allow_html=True)
with st.expander("Ver detalle del modelo", expanded=False):
    eval_data, eval_err = _cached_model_evaluation(api.base_url)
    if eval_err is not None:
        show_api_error(eval_err, context=CONTEXT_MODEL_EVALUATION)
    else:
        classes = eval_data.get("classes", ["Normal", "Pneumonia", "COVID-19"])
        per_class = eval_data.get("per_class", {})
        confusion = eval_data.get("confusion_matrix", [])

        # Resumen breve arriba
        accuracy = eval_data.get("accuracy") or 0
        macro_f1 = eval_data.get("macro_f1") or 0
        model_version = eval_data.get("model_version") or "?"
        st.markdown(
            f'<div class="lasalle-model-summary">'
            f'<strong>Accuracy</strong> <span class="mono">{accuracy:.3f}</span> '
            f'&nbsp; <strong>Macro-F1</strong> <span class="mono">{macro_f1:.3f}</span> '
            f'&nbsp; <strong>Version</strong> <span class="mono">{model_version}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Recall por clase
        if per_class:
            rows = []
            for cls in classes:
                metrics = per_class.get(cls, {})
                rows.append({
                    "Clase": cls,
                    "Precision": f"{metrics.get('precision', 0):.3f}",
                    "Recall": f"{metrics.get('recall', 0):.3f}",
                    "F1": f"{metrics.get('f1', 0):.3f}",
                    "Soporte": metrics.get("support", 0),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption(
                "El recall mas critico clinicamente es el de COVID-19: "
                "un falso negativo equivale a un paciente contagioso "
                "clasificado como sano."
            )

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
                height=380,
                title="Matriz de confusion (test split)",
            )
            st.plotly_chart(fig_cm, use_container_width=True)


# Recarga
st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)
if st.button("Recargar"):
    _cached_radiographies.clear()
    _cached_health.clear()
    _cached_image.clear()
    _cached_model_evaluation.clear()
    st.session_state.pop(_state_key, None)
    st.rerun()
