"""Triaje view (RF-9 de feature triage-pacientes).

Formulario para dar de alta a un paciente nuevo con signos vitales y
sintomas, y obtener un nivel de prioridad **grave / medio / leve**
calculado por las reglas en `src/api/triage.py` (ver ADR-008).

Disclaimer permanente: asistencia al triaje, NO diagnostico ni decision
medica vinculante. Los umbrales son academicos simplificados.

Dashboard API-only (ADR-007): la vista NO toca MongoDB; envia el payload
al endpoint `POST /api/v1/triage/patients` y renderiza el resultado.
"""
from __future__ import annotations

from datetime import date as date_cls

import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import format_error, show_api_error


api: ApiClient = st.session_state["api_client"]


_LEVEL_COLOR = {
    "grave": "#DC2626",
    "medio": "#D97706",
    "leve": "#15803D",
}

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


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.title("Triaje")
st.caption(
    "Alta manual de paciente con asignacion de prioridad mediante reglas. "
    "Asistencia al triaje, **no diagnostico ni decision medica vinculante**."
)


def _render_triage_result(patient: dict) -> None:
    triage = patient.get("triage") or {}
    level = triage.get("level", "?")
    color = _LEVEL_COLOR.get(level, "#64748B")

    st.markdown(
        f"""
        <div style="background:{color}; color:white; padding:24px;
                    border-radius:8px; font-size:1.5em; font-weight:600;
                    margin: 12px 0;">
            Nivel: {level.upper()}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"Paciente creado: `{patient.get('external_id', '?')}` "
        f"(triaje persistido en MongoDB; consultable en la vista Pacientes)."
    )

    reasons = triage.get("reasons") or []
    score = triage.get("score", 0)
    st.markdown(f"**Reglas disparadas (score = {score}):**")
    if reasons:
        for r in reasons:
            st.markdown(f"- `{r}`")
    else:
        st.markdown(
            "- *Sin criterios de gravedad ni intermedios. Paciente clasificado leve.*"
        )

    with st.expander("Ver detalles persistidos", expanded=False):
        st.json(triage)


with st.form("triage_form"):
    st.subheader("Datos del paciente")
    col_demo, col_vitals = st.columns(2)

    with col_demo:
        st.markdown("**Demograficos**")
        name = st.text_input("Nombre completo", value="")
        gender = st.selectbox("Genero", ["M", "F", "Other"])
        use_birth_date = st.checkbox(
            "Indicar fecha de nacimiento (en lugar de edad)", value=False,
        )
        birth_date_value: date_cls | None = None
        age_value: int | None = None
        if use_birth_date:
            birth_date_value = st.date_input(
                "Fecha de nacimiento",
                value=date_cls(1980, 1, 1),
                min_value=date_cls(1900, 1, 1),
                max_value=date_cls.today(),
            )
        else:
            age_value = st.number_input(
                "Edad (anos)", min_value=0, max_value=130, value=40, step=1,
            )
        blood_type = st.text_input("Grupo sanguineo (opcional)", value="")

    with col_vitals:
        st.markdown("**Signos vitales**")
        temperature = st.number_input(
            "Temperatura (Celsius)", min_value=30.0, max_value=45.0,
            value=36.8, step=0.1, format="%.1f",
        )
        oxygen_saturation = st.number_input(
            "Saturacion de oxigeno (%)", min_value=0, max_value=100, value=98,
        )
        heart_rate = st.number_input(
            "Frecuencia cardiaca (lpm)", min_value=0, max_value=300, value=75,
        )
        respiratory_rate = st.number_input(
            "Frecuencia respiratoria (rpm)", min_value=0, max_value=100, value=16,
        )
        systolic_bp = st.number_input(
            "Tension sistolica (mmHg)", min_value=0, max_value=300, value=120,
        )

    st.markdown("---")
    symptoms = st.multiselect(
        "Sintomas principales (los marcados como criticos disparan grave)",
        _SYMPTOM_OPTIONS,
        default=[],
    )
    risk_factors = st.multiselect(
        "Factores de riesgo (opcional, no afectan a las reglas v1.0)",
        _RISK_FACTOR_OPTIONS,
        default=[],
    )

    submitted = st.form_submit_button("Calcular y crear paciente")


if submitted:
    if not name.strip():
        st.error("El nombre es obligatorio.")
    else:
        payload = {
            "name": name.strip(),
            "gender": gender,
            "blood_type": blood_type.strip() or None,
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
        if use_birth_date and birth_date_value is not None:
            payload["birth_date"] = birth_date_value.isoformat()
            payload["age"] = None
        else:
            payload["age"] = int(age_value) if age_value is not None else None
            payload["birth_date"] = None

        with st.spinner("Calculando triaje y creando paciente..."):
            data, err = api.create_triage_patient(payload)

        if err is not None:
            show_api_error(err, context="/triage/patients")
            st.caption(f"Detalle: {format_error(err, '/triage/patients')}")
        else:
            _render_triage_result(data)


st.markdown("---")
with st.expander("Reglas vigentes (`GET /api/v1/triage/rules`)", expanded=False):
    rules_data, rules_err = api.get_triage_rules()
    if rules_err is not None:
        show_api_error(rules_err, context="/triage/rules")
    else:
        st.caption(
            f"Version de reglas: **{rules_data.get('version', '?')}**. "
            "Cualquier paciente clasificado bajo esta version queda "
            "marcado con `rules_version` en su documento."
        )
        levels = rules_data.get("levels", {})
        for level_name, rules in levels.items():
            color = _LEVEL_COLOR.get(level_name, "#64748B")
            st.markdown(
                f"<span style='color:{color}; font-weight:600;'>{level_name.upper()}</span>",
                unsafe_allow_html=True,
            )
            for rule in rules:
                st.markdown(f"- `{rule['id']}` — {rule['description']}")
        notes = rules_data.get("notes")
        if notes:
            st.caption(notes)
