"""Vista Alertas (rediseno UX fase 3).

Lista priorizada por severidad. Cada fila se entiende sin abrirla:
que es, de donde viene, cuando. Sin KPIs encima, sin tablas duplicadas,
sin codigo crudo del detalle.

Cambios respecto a la version anterior:
  - Quitada la fila de 4 metric (Critical / High / Medium / Low).
    El conteo por severidad ya se ve en la propia lista. Si se quiere
    saber "cuantas hay" se cuenta a ojo, no hace falta una metrica
    dedicada.
  - Quitada la tabla pandas + el bloque "Detalle por alerta"
    duplicado mas abajo con `st.code(detail)`. Ahora cada alerta es
    una sola tarjeta horizontal con titulo, body y meta.
  - Filtro de severidad sigue presente, pero como segmento discreto
    arriba a la derecha del listado, no como input grande.
  - Card del informe diario reproducible: fuera. Vive en su CLI y
    en la memoria tecnica (ADR-009), no compite con las alertas.

API-only: solo `api_client.get_alerts()`. Sin escritura, sin estado
nuevo (ADR-009).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import show_api_error
from src.dashboard.config import CACHE_TTL_SECONDS


api: ApiClient = st.session_state["api_client"]


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

SEVERITY_LABEL = {
    "critical": "Critica",
    "high": "Alta",
    "medium": "Media",
    "low": "Baja",
}

TYPE_LABEL = {
    "triage_severe": "Triaje grave",
    "pipeline_failed": "Pipeline ETL fallido",
    "data_quality_low": "Calidad de datos baja",
}

# Traduccion de cada id de regla del triaje a una frase en castellano.
# Se usa al humanizar el body de una alerta `triage_severe`.
TRIAGE_RULE_LABEL = {
    "spo2_lt_92": "saturacion de oxigeno por debajo del umbral",
    "fr_gt_30": "frecuencia respiratoria por encima del umbral",
    "fc_gt_130": "frecuencia cardiaca por encima del umbral",
    "pas_lt_90": "presion sistolica por debajo del umbral",
    "temperature_above_or_equal_39_5": "temperatura igual o superior a 39.5 C",
    "age_over_65_with_risk_factor": "edad mayor de 65 con factor de riesgo",
    "critical_symptom_present": "sintoma critico presente",
    "spo2_92_to_94": "saturacion entre 92 y 94 por ciento",
    "oxygen_saturation_90_to_93": "saturacion entre 90 y 93 por ciento",
    "temperature_38_to_39_4": "temperatura entre 38.0 y 39.4 C",
    "heart_rate_above_100": "frecuencia cardiaca por encima de 100 lpm",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_alerts(_base_url: str, severity_filter: str | None):
    return api.get_alerts(severity=severity_filter)


def _short_dt(value: str | None) -> str:
    if not value:
        return "-"
    s = str(value)
    if len(s) >= 19:
        return s[:19].replace("T", " ")
    return s.replace("T", " ")


def _parse_iso(value: str | None) -> datetime:
    """ISO 8601 → datetime tz-aware. Si falla, devuelve datetime.min UTC."""
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _sort_alerts(items: list[dict]) -> list[dict]:
    """Ordena por (severidad asc, created_at desc).

    severidad: critical(0) > high(1) > medium(2) > low(3); las desconocidas
    al final. created_at se parsea como datetime tz-aware; si falla, va al
    final del bloque de su severidad.
    """
    return sorted(
        items,
        key=lambda a: (
            SEVERITY_ORDER.get(a.get("severity", "low"), 99),
            -_parse_iso(a.get("created_at")).timestamp(),
        ),
    )


def _humanize_type(t: str) -> str:
    return TYPE_LABEL.get(t, t.replace("_", " ").capitalize())


def _humanize_severity(s: str) -> str:
    return SEVERITY_LABEL.get(s, s.capitalize())


# ---------------------------------------------------------------------------
# Humanizacion del cuerpo de la alerta
# ---------------------------------------------------------------------------

_REASONS_RE = re.compile(r"reasons\s*=\s*\[([^\]]*)\]")
_REJECTION_RE = re.compile(
    r"rejection_rate\s*=\s*([0-9.]+).*?umbral\s*=\s*([0-9.]+).*?rechazados\s+([0-9]+)\s+de\s+([0-9]+)",
    re.IGNORECASE,
)


def _humanize_triage_reasons(detail: str) -> str:
    """Extrae la lista `reasons=[...]` y la traduce a frases en castellano."""
    m = _REASONS_RE.search(detail or "")
    if not m:
        return ""
    raw = m.group(1)
    # Items pueden venir entre comillas simples/dobles
    ids = [r.strip().strip("'\"") for r in raw.split(",") if r.strip()]
    pretty = [TRIAGE_RULE_LABEL.get(r, r.replace("_", " ")) for r in ids]
    if not pretty:
        return ""
    if len(pretty) == 1:
        return f"Motivo: {pretty[0]}."
    return "Motivos: " + "; ".join(pretty) + "."


def _humanize_quality(detail: str) -> str:
    """Convierte rejection_rate / umbral / contadores en una frase corta."""
    m = _REJECTION_RE.search(detail or "")
    if not m:
        return detail
    rate = float(m.group(1))
    threshold = float(m.group(2))
    rejected = int(m.group(3))
    total = int(m.group(4))
    return (
        f"Rechazados {rejected:,} de {total:,} ({rate*100:.1f} %), "
        f"por encima del umbral configurado ({threshold*100:.1f} %)."
    ).replace(",", ".")


def _humanize_body(alert: dict) -> str:
    """Devuelve un cuerpo corto y legible para la tarjeta de alerta.

    NUNCA devuelve strings tipo `reasons=[...]` o JSON crudo. Si no sabe
    interpretar el detalle del backend, devuelve una frase neutra.
    """
    atype = alert.get("type", "")
    detail = (alert.get("detail") or alert.get("body") or "").strip()

    if atype == "triage_severe":
        reasons = _humanize_triage_reasons(detail)
        if reasons:
            return f"Paciente triajeado como grave. {reasons}"
        return "Paciente triajeado como grave."

    if atype == "data_quality_low":
        head = "Calidad de datos baja"
        source_id = (alert.get("source_id") or "")
        # source_id viene como "<run-uuid>:<dataset>" → mostramos solo el dataset
        dataset = source_id.split(":", 1)[1] if ":" in source_id else ""
        if dataset:
            head = f"Calidad de datos baja en {dataset}"
        return f"{head}. {_humanize_quality(detail)}".strip()

    if atype == "pipeline_failed":
        # Si el backend mete `error_message=...; ...`, recortamos a la causa.
        match = re.search(r"error_message\s*=\s*(.+?)(?:;|$)", detail or "")
        cause = match.group(1).strip() if match else (detail or "Sin detalle")
        return f"Pipeline ETL fallido. Causa: {cause}"

    # Tipo desconocido: si el detalle parece tecnico, neutralizamos.
    if "=" in detail or "[" in detail or "{" in detail:
        return "Evento operativo. Consultar trazas tecnicas en pipeline runs."
    return detail or "Evento operativo sin detalle."


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="lasalle-page-head">'
    '<h1>Alertas</h1>'
    '<div class="lph-meta">Eventos operativos que requieren atencion ahora.</div>'
    '</div>',
    unsafe_allow_html=True,
)


# Filtro discreto a la derecha
head_col1, head_col2 = st.columns([3, 1])
with head_col2:
    severity_filter = st.selectbox(
        "Severidad",
        options=["Todas", "Critica", "Alta", "Media", "Baja"],
        index=0,
        label_visibility="collapsed",
    )
filter_map = {
    "Todas": None,
    "Critica": "critical",
    "Alta": "high",
    "Media": "medium",
    "Baja": "low",
}
selected = filter_map[severity_filter]


data, err = _cached_alerts(api.base_url, selected)
if err is not None:
    show_api_error(err, context="/api/v1/alerts")
    st.stop()


items = (data or {}).get("items", [])
items_sorted = _sort_alerts(items)


# ---------------------------------------------------------------------------
# Lista
# ---------------------------------------------------------------------------

if not items_sorted:
    if selected is None:
        st.markdown(
            '<div class="lasalle-empty lasalle-empty--ok">'
            'Sin alertas activas. El sistema esta operativo.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="lasalle-empty">'
            f'Sin alertas con severidad {severity_filter.lower()}.</div>',
            unsafe_allow_html=True,
        )
else:
    cards_html: list[str] = []
    for a in items_sorted:
        sev = a.get("severity", "low")
        sev_class = f"lalert lalert--{sev}"
        title = a.get("title", "").strip() or _humanize_type(a.get("type", ""))
        body = _humanize_body(a)
        source = a.get("source", "?")
        source_id = a.get("source_id") or "-"
        created = _short_dt(a.get("created_at"))
        cards_html.append(
            f'<article class="{sev_class}">'
            f'<div class="lalert-marker" aria-hidden="true"></div>'
            f'<div class="lalert-body">'
            f'<div class="lalert-head">'
            f'<span class="lalert-sev">{_humanize_severity(sev)}</span>'
            f'<span class="lalert-title">{title}</span>'
            f'</div>'
            f'<div class="lalert-text">{body}</div>'
            f'<div class="lalert-meta">'
            f'<span>{created}</span>'
            f'<span class="lalert-sep">·</span>'
            f'<span class="mono">{source}</span>'
            f'<span class="lalert-sep">·</span>'
            f'<span class="mono">{source_id}</span>'
            f'</div>'
            f'</div>'
            f'</article>'
        )
    st.markdown(
        '<div class="lasalle-alert-list">' + "".join(cards_html) + "</div>",
        unsafe_allow_html=True,
    )


# Pequeno control de recarga al final, sin protagonismo
st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
if st.button("Recargar"):
    _cached_alerts.clear()
    st.rerun()
