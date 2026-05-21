"""Vista Inicio (rediseno UX fase 1).

Pantalla de turno: una sola pregunta, "es hay algo que requiera mi
atencion ahora?". Si no hay nada urgente, atajos a las tres tareas
habituales (triaje, buscar paciente, clasificar radiografia).

Composicion (de arriba abajo):
  1. Saludo + meta de turno
  2. Barra de alerta critica - solo si hay alertas active+critical
  3. Linea de estado (API / Modelo / Pipeline)
  4. Actividad de hoy - 4 numeros grandes (sin cards)
  5. Accesos rapidos - 3 page_link como bloques anchos

Se descartan respecto a la version anterior (intencional):
  - 4 KPIs totales (patients / admissions / radiografias / modelo)
  - Strip de evaluacion del modelo
  - Detalle del ultimo pipeline run (vive ya en "Pipeline runs")
  - Auto-refresh con st.fragment (la pagina es mas ligera ahora;
    el operador refresca con el navegador o con el boton "Recargar")

Nota sobre "Actividad de hoy":
La API actual NO expone un endpoint agregado de triajes por nivel
(solo POST /triage/patients). Mientras eso no exista, los 4 numeros se
componen con los datos derivables del endpoint `/alerts` (que SI
distingue tres severidades: critical / high / medium) + un contador de
runs del pipeline. Cuando exista `GET /api/v1/triage/today` se sustituye
la composicion sin tocar el resto de la vista.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

from src.dashboard.api_client import ApiClient
from src.dashboard.components.error_banner import show_api_error
from src.dashboard.config import CACHE_TTL_SECONDS


# Mismo patron que app.py: rutas absolutas para que `st.page_link`
# enganche con las paginas registradas independientemente del cwd.
_VIEWS_DIR = Path(__file__).resolve().parent


api: ApiClient = st.session_state["api_client"]


# ---------------------------------------------------------------------------
# Helpers cacheados
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_health(_base_url: str):
    return api.health()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_latest_run(_base_url: str):
    return api.latest_pipeline_run()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_alerts(_base_url: str):
    """Trae todas las alertas activas, agrupa por severidad en cliente.

    El endpoint `/api/v1/alerts` devuelve un dict con `items`, `total`,
    `generated_at`, `threshold`, `window_start`. Lo desempaquetamos aqui
    para que el resto de la vista trabaje sobre una lista plana.
    """
    data, err = api.get_alerts()
    if err is not None:
        return {"err": err}
    items = (data or {}).get("items", [])
    by_sev: dict[str, int] = {"critical": 0, "high": 0, "medium": 0}
    criticals = []
    for alert in items:
        sev = alert.get("severity")
        if sev in by_sev:
            by_sev[sev] += 1
        if sev == "critical":
            criticals.append(alert)
    return {
        "by_sev": by_sev,
        "total": len(items),
        "critical_items": criticals,
        "err": None,
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_volume(_base_url: str) -> dict[str, int | None]:
    """Pide los `total` de pacientes, admisiones y radiografias.

    Cada endpoint sopporta `limit=1&offset=0` y devuelve `total`, asi
    que con 3 llamadas tenemos el volumen del sistema sin paginar.
    Si alguna falla, ese contador se devuelve como None para que la
    UI lo pinte como '-'.
    """
    result: dict[str, int | None] = {"patients": None, "admissions": None, "radiographies": None}
    p_data, p_err = api.list_patients(limit=1, offset=0)
    if p_err is None and isinstance(p_data, dict):
        result["patients"] = p_data.get("total")
    a_data, a_err = api.list_admissions(limit=1, offset=0)
    if a_err is None and isinstance(a_data, dict):
        result["admissions"] = a_data.get("total")
    r_data, r_err = api.list_radiographies(limit=1, offset=0)
    if r_err is None and isinstance(r_data, dict):
        result["radiographies"] = r_data.get("total")
    return result


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_runs_today(_base_url: str) -> int | None:
    """Cuenta los runs iniciados en las ultimas 24h (proxy de "hoy")."""
    data, err = api.list_runs(limit=50, offset=0)
    if err is not None:
        return None
    runs = (data or {}).get("items") or data or []
    if not isinstance(runs, list):
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    count = 0
    for run in runs:
        started = run.get("started_at") if isinstance(run, dict) else None
        if not started:
            continue
        # ISO 8601 con o sin 'Z'
        try:
            ts = datetime.fromisoformat(started.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                count += 1
        except ValueError:
            continue
    return count


# ---------------------------------------------------------------------------
# Pequenas utilidades de render (HTML inline minimo)
# ---------------------------------------------------------------------------

def _greeting(now: datetime) -> str:
    h = now.hour
    if 6 <= h < 13:
        return "Buenos dias"
    if 13 <= h < 21:
        return "Buenas tardes"
    return "Buenas noches"


_MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _format_date_es(now: datetime) -> str:
    """%d de %B%-style date en castellano sin depender del locale del SO."""
    return f"{now.day} de {_MONTHS_ES[now.month - 1]}"


def _shift_label(now: datetime) -> str:
    h = now.hour
    if 7 <= h < 15:
        return "turno manana"
    if 15 <= h < 23:
        return "turno tarde"
    return "turno noche"


def _render_critical_bar(criticals: list[dict]) -> None:
    """Barra horizontal coral si hay alertas criticas activas.

    El resumen prioriza el `title` (humano) sobre `detail/body/message`.
    Si solo hay disponible un `detail` con apariencia tecnica
    (`reasons=[...]`, JSON, contadores con `=`) se sustituye por la
    etiqueta neutra "ver detalle en Alertas" para no escupir strings
    crudos en la cabecera de Inicio.
    """
    n = len(criticals)
    if n == 0:
        return

    def _looks_technical(text: str) -> bool:
        t = (text or "")
        return any(tok in t for tok in ("=", "[", "{", ";"))

    def _summary_for(alert: dict) -> str:
        title = (alert.get("title") or "").strip()
        if title:
            return title
        for key in ("detail", "body", "message"):
            v = (alert.get(key) or "").strip()
            if v and not _looks_technical(v):
                # Cortar antes del primer guion largo si existe
                head = v.split(" - ")[0].split(" — ")[0].strip()
                if head:
                    return head
        return ""

    summary_parts = [s for s in (_summary_for(a) for a in criticals[:3]) if s]
    summary = " · ".join(summary_parts) if summary_parts else "ver detalle en Alertas"
    if n > 3:
        summary += f" · y {n - 3} mas"

    plural = "alertas criticas" if n != 1 else "alerta critica"
    st.markdown(
        f'<div class="lasalle-critical-bar" role="alert">'
        f'<span class="lcb-dot" aria-hidden="true"></span>'
        f'<div class="lcb-msg">'
        f'<strong>{n} {plural}</strong>'
        f'<span class="lcb-detail">{summary}</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_status_line(
    health_err, predictor_loaded: bool | None,
    run_data: dict | None, run_err,
) -> None:
    """Una linea con 3 chips: API / Modelo / Pipeline."""

    # API chip
    if health_err is not None:
        api_cls, api_val = "fail", "caida"
    else:
        api_cls, api_val = "", "operativo"

    # Modelo chip
    if health_err is not None:
        model_cls, model_val = "warn", "desconocido"
    elif predictor_loaded:
        model_cls, model_val = "", "cargado"
    else:
        model_cls, model_val = "fail", "no cargado"

    # Pipeline chip
    if run_err is not None:
        if getattr(run_err, "kind", None) == "not_found":
            pipe_cls, pipe_val = "warn", "sin runs"
        else:
            pipe_cls, pipe_val = "warn", "desconocido"
    else:
        status = (run_data or {}).get("status", "")
        if status == "success":
            pipe_cls, pipe_val = "", "ok"
        elif status == "failed":
            pipe_cls, pipe_val = "fail", "fallo"
        elif status == "running":
            pipe_cls, pipe_val = "warn", "en curso"
        else:
            pipe_cls, pipe_val = "warn", str(status) or "desconocido"

    st.markdown(
        f'<div class="lasalle-status-line">'
        f'<span class="lsl-chip"><span class="lsl-dot {api_cls}"></span>'
        f'<span class="lsl-label">API</span><span class="lsl-val">{api_val}</span></span>'
        f'<span class="lsl-chip"><span class="lsl-dot {model_cls}"></span>'
        f'<span class="lsl-label">Modelo</span><span class="lsl-val">{model_val}</span></span>'
        f'<span class="lsl-chip"><span class="lsl-dot {pipe_cls}"></span>'
        f'<span class="lsl-label">Pipeline</span><span class="lsl-val">{pipe_val}</span></span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

now = datetime.now()
shift = _shift_label(now)

# Cabecera
st.markdown(
    f'<div class="lasalle-greeting">'
    f'<h1>{_greeting(now)}</h1>'
    f'<div class="lg-meta">{_format_date_es(now)} · {shift} · '
    f'<span class="mono">{now.strftime("%H:%M")}</span></div>'
    f'</div>',
    unsafe_allow_html=True,
)

# Linea discreta de volumen del sistema. NO son KPIs grandes — es
# contexto secundario para que al entrar se vea "el sistema esta vivo
# y tiene N datos cargados". Si algun endpoint falla, ese contador
# aparece como '-' (no rompe la vista).
volume = _cached_volume(api.base_url)


def _fmt_volume_number(n: int | None) -> str:
    if n is None:
        return "—"
    # Separador de miles tipo es-ES, sin depender del locale del SO
    return f"{n:,}".replace(",", ".")


st.markdown(
    f'<div class="lasalle-volume-line">'
    f'<span class="mono">{_fmt_volume_number(volume["patients"])}</span> pacientes '
    f'<span class="lvl-sep">·</span> '
    f'<span class="mono">{_fmt_volume_number(volume["admissions"])}</span> admisiones '
    f'<span class="lvl-sep">·</span> '
    f'<span class="mono">{_fmt_volume_number(volume["radiographies"])}</span> radiografias'
    f'</div>',
    unsafe_allow_html=True,
)

# Datos para la barra y los chips
alerts_payload = _cached_alerts(api.base_url)
health_data, health_err = _cached_health(api.base_url)
run_data, run_err = _cached_latest_run(api.base_url)
predictor_loaded = (
    bool(health_data and health_data.get("predictor_loaded"))
    if health_err is None
    else None
)

# 1) Barra critica - solo si la API responde y hay criticas
if alerts_payload.get("err") is None:
    _render_critical_bar(alerts_payload.get("critical_items", []))
elif alerts_payload["err"].kind != "network":
    # Errores duros del endpoint /alerts: se muestran como banner
    # (errores de red ya los reportan los chips de estado)
    show_api_error(alerts_payload["err"], context="")

# 2) Linea de estado
_render_status_line(health_err, predictor_loaded, run_data, run_err)


# 3) Actividad de hoy ------------------------------------------------------

st.markdown(
    '<div class="lasalle-section-label">Actividad de hoy</div>',
    unsafe_allow_html=True,
)

by_sev = alerts_payload.get("by_sev", {"critical": 0, "high": 0, "medium": 0})
runs_24h = _cached_runs_today(api.base_url)


def _stat_card_html(label: str, value: object, mod: str = "") -> str:
    """Card compacta con label uppercase + numero grande. `mod` aplica
    color al numero (critical / warn / muted)."""
    cls = f"lasalle-stat-card {mod}".strip()
    val = value if value is not None else "—"
    return (
        f'<div class="{cls}">'
        f'<div class="lsc-label">{label}</div>'
        f'<div class="lsc-value">{val}</div>'
        f'</div>'
    )


_n_crit  = by_sev.get("critical", 0)
_n_high  = by_sev.get("high", 0)
_n_med   = by_sev.get("medium", 0)
_n_runs  = runs_24h

a_cols = st.columns(4)
with a_cols[0]:
    st.markdown(
        _stat_card_html("Alertas criticas", _n_crit, "critical" if _n_crit else "muted"),
        unsafe_allow_html=True,
    )
with a_cols[1]:
    st.markdown(
        _stat_card_html("Alertas altas", _n_high, "critical" if _n_high else "muted"),
        unsafe_allow_html=True,
    )
with a_cols[2]:
    st.markdown(
        _stat_card_html("Alertas medias", _n_med, "warn" if _n_med else "muted"),
        unsafe_allow_html=True,
    )
with a_cols[3]:
    st.markdown(
        _stat_card_html("Pipeline runs (24h)", _n_runs, "muted"),
        unsafe_allow_html=True,
    )


# 4) Accesos rapidos -------------------------------------------------------

st.markdown(
    '<div class="lasalle-section-label">Accesos rapidos</div>',
    unsafe_allow_html=True,
)
st.markdown('<div class="lasalle-quick-actions">', unsafe_allow_html=True)

qa_cols = st.columns(3)
with qa_cols[0]:
    st.page_link(str(_VIEWS_DIR / "triage.py"),     label="Nuevo triaje")
with qa_cols[1]:
    st.page_link(str(_VIEWS_DIR / "patients.py"),   label="Buscar paciente")
with qa_cols[2]:
    st.page_link(str(_VIEWS_DIR / "classifier.py"), label="Clasificar radiografia")

st.markdown("</div>", unsafe_allow_html=True)


# 5) Recargar (sutil, al final) -------------------------------------------

st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
if st.button("Recargar", use_container_width=False):
    _cached_health.clear()
    _cached_latest_run.clear()
    _cached_alerts.clear()
    _cached_runs_today.clear()
    st.rerun()
