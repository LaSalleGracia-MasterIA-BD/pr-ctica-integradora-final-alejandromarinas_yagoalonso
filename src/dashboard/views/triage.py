"""Vista Triaje (rediseno UX fase 2).

Objetivo: una pantalla limpia donde un operador rellena los datos
basicos + signos vitales del paciente y recibe una prioridad
calculada (grave / medio / leve) con motivos y una recomendacion
operativa generica. No sustituye a una decision medica.

Cambios respecto a la version anterior:
  - Formulario respirado por bloques verticales (datos basicos,
    constantes, sintomas / riesgo) sin packs densos de inputs.
  - Resultado simple: badge grande con la prioridad, motivos
    realmente disparados (no la lista de las 8 reglas marcadas /
    no marcadas) y recomendacion operativa.
  - Disclaimer presente pero sin gritar.
  - Fuera: `st.json` con el payload persistido, expander con todas
    las reglas vigentes a media pagina (queda como enlace plegado
    al final, opcional).

API-only: la unica llamada de escritura es
`POST /api/v1/triage/patients`. Se reusa el cliente existente; no
se toca el backend.
"""
from __future__ import annotations

from datetime import date as date_cls

import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import show_api_error


api: ApiClient = st.session_state["api_client"]


# ---------------------------------------------------------------------------
# Tablas locales: opciones, traducciones humanas, recomendaciones
# ---------------------------------------------------------------------------

_SYMPTOM_OPTIONS = [
    "alteracion_conciencia",
    "dolor_toracico_fuerte",
    "tos",
    "disnea",
    "fiebre",
]

_RISK_FACTOR_OPTIONS = [
    "epoc",
    "diabetes",
    "hipertension",
    "cardiopatia",
    "inmunosupresion",
    "embarazo",
]

# Traducciones humanas de los id de regla. El backend devuelve el id
# tecnico (p.ej. `oxygen_saturation_below_90`); aqui lo formateamos a
# castellano legible. Si llega un id nuevo no mapeado, se muestra tal
# cual (failsafe).
_RULE_LABELS = {
    # IDs reales del backend (src/api/triage.py).
    "spo2_lt_92": "Saturacion de oxigeno por debajo de 92 %",
    "fr_gt_30": "Frecuencia respiratoria por encima de 30 rpm",
    "fc_gt_130": "Frecuencia cardiaca por encima de 130 lpm",
    "pas_lt_90": "Tension sistolica por debajo de 90 mmHg",
    "temperature_above_or_equal_39_5": "Temperatura igual o superior a 39.5 C",
    "age_over_65_with_risk_factor": "Edad mayor de 65 con factor de riesgo",
    "critical_symptom_present": "Sintoma critico presente",
    "spo2_92_to_94": "Saturacion de oxigeno entre 92 y 94 %",
    "oxygen_saturation_90_to_93": "Saturacion de oxigeno entre 90 y 93 %",
    "temperature_38_to_39_4": "Temperatura entre 38.0 y 39.4 C",
    "heart_rate_above_100": "Frecuencia cardiaca por encima de 100 lpm",
}

# Recomendacion operativa generica por nivel. Texto deliberadamente
# neutro: no menciona ubicaciones (UCI, sala de reanimacion), ni roles
# concretos (medico de guardia), ni juicios clinicos (riesgo vital).
# El disclaimer permanente recuerda que esto NO sustituye una decision
# medica.
_RECOMMENDATIONS = {
    "grave": "Priorizar revision inmediata por profesional sanitario.",
    "medio": "Revision preferente y reevaluacion.",
    "leve": "Seguimiento segun evolucion.",
}


def _humanize_rule(rule_id: str) -> str:
    """Devuelve la version legible del id de regla, o el id si falta."""
    return _RULE_LABELS.get(rule_id, rule_id)


# ---------------------------------------------------------------------------
# Render: cabecera + disclaimer sutil
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="lasalle-page-head">'
    '<h1>Triaje</h1>'
    '<div class="lph-meta">Registrar paciente y asignar prioridad por reglas.</div>'
    '</div>',
    unsafe_allow_html=True,
)

# Disclaimer permanente, discreto, justo debajo del titulo.
st.markdown(
    '<div class="lasalle-disclaimer">'
    'Esta clasificacion es orientativa. No sustituye una decision medica.'
    '</div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Formulario - respirado en bloques verticales
# ---------------------------------------------------------------------------

with st.form("triage_form", clear_on_submit=False):
    # --- Bloque 1: datos basicos -------------------------------------------
    st.markdown(
        '<div class="lasalle-form-section">Datos basicos</div>',
        unsafe_allow_html=True,
    )
    col_n, col_g, col_a = st.columns([3, 1, 1])
    with col_n:
        name = st.text_input("Nombre completo", value="", label_visibility="visible")
    with col_g:
        gender = st.selectbox("Genero", ["M", "F", "Other"])
    with col_a:
        age_value = st.number_input(
            "Edad",
            min_value=0,
            max_value=130,
            value=40,
            step=1,
        )

    # Espacio respirable entre bloques
    st.markdown("<div style='height: 18px'></div>", unsafe_allow_html=True)

    # --- Bloque 2: signos vitales -----------------------------------------
    st.markdown(
        '<div class="lasalle-form-section">Signos vitales</div>',
        unsafe_allow_html=True,
    )
    vrow1 = st.columns(3)
    with vrow1[0]:
        oxygen_saturation = st.number_input(
            "Saturacion de oxigeno (%)",
            min_value=0, max_value=100, value=98,
            help="Normal >= 95. Por debajo de 90 dispara prioridad grave.",
        )
    with vrow1[1]:
        temperature = st.number_input(
            "Temperatura (C)",
            min_value=30.0, max_value=45.0, value=36.8, step=0.1, format="%.1f",
            help="Normal 36.5-37.5. >= 39.5 dispara grave.",
        )
    with vrow1[2]:
        heart_rate = st.number_input(
            "Frecuencia cardiaca (lpm)",
            min_value=0, max_value=300, value=75,
            help="Normal 60-100.",
        )

    vrow2 = st.columns(3)
    with vrow2[0]:
        respiratory_rate = st.number_input(
            "Frecuencia respiratoria (rpm)",
            min_value=0, max_value=100, value=16,
            help="Normal 12-20. > 24 dispara grave.",
        )
    with vrow2[1]:
        systolic_bp = st.number_input(
            "Tension sistolica (mmHg)",
            min_value=0, max_value=300, value=120,
            help="Normal >= 90.",
        )
    with vrow2[2]:
        # Hueco vacio para mantener la cuadricula limpia
        st.markdown("&nbsp;", unsafe_allow_html=True)

    st.markdown("<div style='height: 18px'></div>", unsafe_allow_html=True)

    # --- Bloque 3: sintomas + factores de riesgo --------------------------
    st.markdown(
        '<div class="lasalle-form-section">Sintomas y factores de riesgo</div>',
        unsafe_allow_html=True,
    )
    sym_col, risk_col = st.columns(2)
    with sym_col:
        symptoms = st.multiselect(
            "Sintomas principales",
            _SYMPTOM_OPTIONS,
            default=[],
            help=(
                "Los marcados como criticos (alteracion de conciencia, "
                "dolor toracico fuerte) disparan prioridad grave."
            ),
        )
    with risk_col:
        risk_factors = st.multiselect(
            "Factores de riesgo (opcional)",
            _RISK_FACTOR_OPTIONS,
            default=[],
            help="Modifican la prioridad si se combinan con edad alta.",
        )

    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)
    submitted = st.form_submit_button(
        "Calcular prioridad",
        type="primary",
    )


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

def _render_result(patient: dict) -> None:
    triage = patient.get("triage") or {}
    level = (triage.get("level") or "").lower()
    reasons = triage.get("reasons") or []
    external_id = patient.get("external_id", "?")

    level_label = {"grave": "GRAVE", "medio": "MEDIO", "leve": "LEVE"}.get(
        level, level.upper() or "?"
    )
    recommendation = _RECOMMENDATIONS.get(level, "")
    panel_cls = level if level in {"grave", "medio", "leve"} else ""

    # Panel de prioridad — un solo bloque coloreado segun nivel
    reasons_html = ""
    if reasons:
        items = "".join(
            f"<li>{_humanize_rule(r)}</li>" for r in reasons
        )
        reasons_html = (
            '<div class="lpr-reasons-label">Motivos disparados</div>'
            f'<ul class="lpr-reasons-list">{items}</ul>'
        )
    else:
        reasons_html = (
            '<div class="lpr-reasons-label">Motivos</div>'
            '<div class="lpr-recommendation">Sin criterios de gravedad ni intermedios.</div>'
        )

    st.markdown(
        f'<div class="lasalle-priority {panel_cls}">'
        f'<div class="lpr-tag">Prioridad asignada</div>'
        f'<div class="lpr-level">{level_label}</div>'
        f'<div class="lpr-recommendation">{recommendation}</div>'
        f'{reasons_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Confirmacion sutil del id creado
    st.markdown(
        f'<div class="lasalle-volume-line" style="margin-top:10px;">'
        f'Paciente creado: <span class="mono">{external_id}</span> '
        f'(consultable en Pacientes).</div>',
        unsafe_allow_html=True,
    )


if submitted:
    if not name.strip():
        st.error("El nombre es obligatorio.")
    else:
        payload = {
            "name": name.strip(),
            "gender": gender,
            "age": int(age_value),
            "birth_date": None,
            "blood_type": None,
            "vital_signs": {
                "temperature_celsius": float(temperature),
                "oxygen_saturation": int(oxygen_saturation),
                "heart_rate": int(heart_rate),
                "respiratory_rate": int(respiratory_rate),
                "systolic_bp": int(systolic_bp),
            },
            "symptoms": list(symptoms),
            "risk_factors": list(risk_factors),
        }
        with st.spinner("Calculando prioridad..."):
            data, err = api.create_triage_patient(payload)

        if err is not None:
            show_api_error(err, context="/triage/patients")
        else:
            _render_result(data)


# ---------------------------------------------------------------------------
# Reglas vigentes - plegado al final, peso visual minimo (no es el foco)
# ---------------------------------------------------------------------------

with st.expander("Ver reglas de triaje vigentes", expanded=False):
    rules_data, rules_err = api.get_triage_rules()
    if rules_err is not None:
        show_api_error(rules_err, context="/triage/rules")
    else:
        st.caption(
            f"Version: {rules_data.get('version', '?')}. "
            "Cada paciente queda marcado con esta version en su documento."
        )
        levels = rules_data.get("levels", {})
        for level_name, rules in levels.items():
            st.markdown(f"**{level_name.upper()}**")
            for rule in rules:
                st.markdown(
                    f"- {_humanize_rule(rule['id'])}"
                    f" &nbsp;<span style='color:#94A3B8;font-family:monospace;"
                    f"font-size:0.85em;'>{rule['id']}</span>",
                    unsafe_allow_html=True,
                )
