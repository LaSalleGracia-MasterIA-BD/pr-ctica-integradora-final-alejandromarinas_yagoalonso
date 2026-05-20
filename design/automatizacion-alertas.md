# Design: Automatizacion, alertas e informes operativos

> Spec: specs/automatizacion-alertas.md
> ADR relacionado: decisions/ADR-009-alertas-como-vista-derivada.md

## Decision arquitectonica

Cuatro principios de diseno:

1. **Alertas como vista derivada (read-side)**. Cero estado nuevo
   persistido. Se calculan al vuelo leyendo `pipeline_runs` (SQLite),
   `data_quality_summary` (SQLite) y `patients.triage` (MongoDB). Ver
   ADR-009.
2. **Reglas de produccion como funcion pura**. Mismo patron que el
   triaje (ADR-008): `evaluate(state) -> list[Alert]` vive en
   `src/api/alerts.py`, sin Mongo ni FastAPI, testeable trivialmente.
   Conecta con la **Sesion 07 de Yuri (sistemas basados en reglas:
   `ruleBasedSystem/`)**.
3. **Doble entry point con un solo builder**: el endpoint
   `GET /api/v1/reports/daily` y el script CLI
   `src/automation/daily_report.py` invocan **el mismo codigo**
   (`build_daily_report(date, state) -> dict`). El script renderiza
   ese dict a Markdown estable; el endpoint lo devuelve como JSON con
   `generated_at` dinamico. Cero duplicacion.
4. **Dashboard API-only** (ADR-007). Nueva vista llama al cliente
   HTTP; cero conexiones directas a almacenes.

**Doble ventana temporal**. Reglas iguales (RF-2), pero la ventana
varia segun el caller:
- `/alerts`: `[now - ALERT_WINDOW_HOURS, now]` o `[since, now]`.
- `/reports/daily` + script: `[start_of_day_UTC, end_of_day_UTC]`
  estricta del dia consultado.

La diferencia esta en QUE listas se pasan a `evaluate`; la funcion
en si NO conoce el reloj (asi se mantiene pura y reusable).

```
   Operador (medico) --HTTP--> Dashboard /Alertas (Streamlit)
                                    |
                                    | api_client.get_alerts()
                                    v
                            +----------------------+
                            |   API REST           |
                            |  GET /alerts         |
                            |  GET /reports/daily  |
                            +----------------------+
                              |       |       |
                          lee |   lee |   lee |
                              v       v       v
                          SQLite    SQLite    MongoDB
                       (pipeline_  (quality_  (patients.
                          runs)     summary)    triage)

  Operador (devops) --CLI--> python -m src.automation.daily_report
                                    |
                                    | usa MISMO builder
                                    v
                            docs/reports/YYYY-MM-DD.md (Markdown)
```

## Trazabilidad spec -> componentes

| Requisito | Componente(s) | Archivos |
|-----------|--------------|----------|
| RF-1, RF-3 (`GET /alerts`) | `src/api/routers/alerts.py` + `src/api/alerts.py` (funcion pura) | nuevo router + modulo |
| RF-2 (reglas de calculo) | `evaluate(state) -> list[Alert]` | `src/api/alerts.py` |
| RF-4 (`GET /reports/daily` con ventana del dia) | `src/api/routers/reports.py` + `src/api/reports.py::build_daily_report` + readers `_between` extendidos | nuevo router + modulo + extension de readers |
| RF-5 (script con Markdown idempotente) | `src/automation/daily_report.py::main` + `render_markdown` sin `generated_at` | nuevo modulo en `src/automation/` |
| RNF-6 (idempotencia byte-a-byte) | `render_markdown` deterministico (sin `now()`, sin sets sin orden) + test que llama 2 veces y compara hash | tests + render |
| RF-6 (vista dashboard) | `src/dashboard/views/alerts.py` + registro en `app.py` | nuevo + modificacion |
| RF-7 (api_client metodos) | `get_alerts()` y `get_daily_report()` | extension de `src/dashboard/api_client.py` |
| RF-8 (orden severity desc) | `evaluate` ordena antes de devolver | `src/api/alerts.py` |
| RNF-3 (cero estado nuevo) | Verificacion: no se tocan `sql_models.py` ni `init-db.js` | inspeccion del diff |
| RNF-5 (funcion pura) | `evaluate(state)` + tests sin Mongo/SQLite | `tests/api/test_alerts_rules.py` |
| RNF-6 (idempotencia script) | mismo state + misma fecha -> mismo Markdown | tests del script |

## Componentes

### `src/api/alerts.py` (nuevo, **logica pura**)

**Responsabilidad:** definir el tipo `Alert` (dataclass o TypedDict) y
las funciones puras de evaluacion. **No** abre conexiones; recibe el
"estado" como dict de listas.

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Severity = Literal["critical", "high", "medium", "low"]
AlertType = Literal["pipeline_failed", "data_quality_low", "triage_severe"]

@dataclass(frozen=True)
class Alert:
    type: AlertType
    severity: Severity
    title: str
    detail: str
    source: str       # "pipeline_runs" | "data_quality_summary" | "patients.triage"
    source_id: str | None
    created_at: datetime


def evaluate(
    failed_runs: list[dict],
    quality_snapshots: list[dict],
    severe_triage_patients: list[dict],
    threshold: float = 0.10,
) -> list[Alert]:
    """Funcion pura: convierte lecturas crudas en alertas.

    No filtra por ventana temporal: eso es responsabilidad del
    `state_loader` (que sí pasa por Mongo/SQLite y aplica los filtros
    de `since` antes de pasar las listas aqui).

    `threshold` aplica solo a `data_quality_low`.
    """
    alerts: list[Alert] = []

    for run in failed_runs:
        alerts.append(Alert(
            type="pipeline_failed",
            severity="high",
            title=f"Run del pipeline fallido ({run.get('trigger_type', '?')})",
            detail=run.get("error_message") or "Sin mensaje de error",
            source="pipeline_runs",
            source_id=run["id"],
            created_at=run["started_at"],
        ))

    for snap in quality_snapshots:
        if snap["rejection_rate"] > threshold:
            alerts.append(Alert(
                type="data_quality_low",
                severity="medium",
                title=f"Calidad de datos baja en {snap['dimension']}",
                detail=(
                    f"rejection_rate={snap['rejection_rate']:.4f} > "
                    f"umbral={threshold:.2f}; rechazados {snap['rejected']} de "
                    f"{snap['total']}"
                ),
                source="data_quality_summary",
                source_id=f"{snap['pipeline_run_id']}:{snap['dimension']}",
                created_at=snap["recorded_at"],
            ))

    for patient in severe_triage_patients:
        triage = patient.get("triage", {})
        alerts.append(Alert(
            type="triage_severe",
            severity="critical",
            title=f"Paciente triajeado como GRAVE",
            detail=(
                f"reasons={triage.get('reasons', [])}; "
                f"name={patient.get('name', '?')}"
            ),
            source="patients.triage",
            source_id=patient["external_id"],
            created_at=triage["triaged_at"],
        ))

    # Orden: severity DESC (critical > high > medium > low), luego created_at DESC
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: (severity_order[a.severity], -a.created_at.timestamp()))
    return alerts
```

### `src/api/routers/alerts.py` (nuevo)

**Responsabilidad:** exponer `GET /api/v1/alerts`. Llama a los readers
(Mongo + SQL), pasa los datos a `evaluate`, devuelve JSON.

```python
router = APIRouter(prefix="/api/v1", tags=["alerts"])

DEFAULT_THRESHOLD = float(os.environ.get("ALERT_REJECTION_RATE_THRESHOLD", "0.10"))
DEFAULT_WINDOW_HOURS = int(os.environ.get("ALERT_WINDOW_HOURS", "24"))

@router.get("/alerts")
def get_alerts(
    request: Request,
    since: datetime | None = Query(None),
    severity: Severity | None = Query(None),
) -> dict:
    """RF-1, RF-3, RF-8."""
    now = datetime.now(timezone.utc)
    window_start = since or (now - timedelta(hours=DEFAULT_WINDOW_HOURS))

    sql_reader = request.app.state.sql_reader
    mongo_reader = request.app.state.mongo_reader

    failed_runs = sql_reader.list_failed_runs_since(window_start)
    quality_snapshots = sql_reader.list_quality_snapshots_since(window_start)
    severe_patients = mongo_reader.list_severe_triage_patients_since(window_start)

    alerts = evaluate(
        failed_runs, quality_snapshots, severe_patients,
        threshold=DEFAULT_THRESHOLD,
    )

    if severity is not None:
        alerts = [a for a in alerts if a.severity == severity]

    return {
        "items": [asdict(a) for a in alerts],
        "total": len(alerts),
        "generated_at": now.isoformat(),
        "threshold": DEFAULT_THRESHOLD,
        "window_start": window_start.isoformat(),
    }
```

### `src/api/reports.py` (nuevo, **builder puro**)

**Responsabilidad:** dos funciones puras:

1. `build_daily_report(date, state) -> dict` arma la estructura JSON
   del informe diario sobre la ventana del dia.
2. `render_markdown(report) -> str` renderiza el dict a Markdown
   **byte-a-byte estable**: NO incluye `generated_at` ni ningun otro
   campo dependiente del reloj.

```python
def build_daily_report(
    day: date,
    failed_runs_in_day: list[dict],
    runs_in_day: list[dict],
    quality_snapshots_in_day: list[dict],
    triage_patients_in_day: list[dict],     # todos los triajes del dia
    severe_triage_patients_in_day: list[dict],  # subset grave (para alerts)
    counts_snapshot: dict,                  # contadores totales al cierre
    threshold: float,
    generated_at: datetime | None = None,   # solo para el JSON; None = ahora
) -> dict:
    """Estructura definida en spec RF-4.

    `generated_at` es opcional: el endpoint HTTP lo deja en None (se
    rellena al serializar); el script CLI llama a `render_markdown`
    que NO lo lee, asi que da igual su valor para el fichero.
    """
    triage_counts = _count_triage_by_level(triage_patients_in_day)
    alerts = evaluate(
        failed_runs_in_day,
        quality_snapshots_in_day,
        severe_triage_patients_in_day,
        threshold=threshold,
    )
    return {
        "date": day.isoformat(),
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
        "pipeline": {
            "last_run_of_day":  _last_or_none(runs_in_day),
            "runs_in_day":      len(runs_in_day),
            "failed_in_day":    len(failed_runs_in_day),
        },
        "quality":  _quality_summary_per_dimension(quality_snapshots_in_day),
        "counts":   counts_snapshot,
        "triage": {
            **triage_counts,
            "in_day_total": sum(triage_counts.values()),
        },
        "alerts":   [asdict(a) for a in alerts],
    }


def render_markdown(report: dict) -> str:
    """Renderiza el dict a Markdown determinista.

    NO incluye `generated_at` (para garantizar idempotencia byte-a-byte:
    misma fecha + mismo estado -> mismo fichero, sin importar cuando
    se ejecute el script).

    Secciones:
      # Informe diario - YYYY-MM-DD
      ## Pipeline
      ## Calidad de datos
      ## Conteos
      ## Triaje
      ## Alertas
    """
    lines = [f"# Informe diario — {report['date']}", ""]
    # NO se incluye generated_at en el Markdown — ver RNF-6.
    lines.append("## Pipeline")
    # ... secciones con datos deterministas del report
    return "\n".join(lines) + "\n"
```

**Garantia de idempotencia (RNF-6 + CA-11):**

- `render_markdown` lee solo del dict que recibe; no llama a `datetime.now()`.
- Listas que se renderizan estan ordenadas por claves estables (timestamps,
  ids). Sin sets ni dicts iterados sin orden.
- Tests verifican que dos llamadas a `render_markdown(report)` con el
  mismo dict producen exactamente la misma string.

### `src/api/routers/reports.py` (nuevo)

```python
router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

@router.get("/daily")
def get_daily_report(
    request: Request,
    date: str | None = Query(None),
) -> dict:
    """RF-4: informe del dia consultado, ventana estricta
    [00:00, 23:59:59.999] UTC. No reutiliza la ventana de /alerts."""
    target_date = parse_date_or_today(date)        # 422 si invalida
    start, end = day_window_utc(target_date)
    sql_reader = request.app.state.sql_reader
    mongo_reader = request.app.state.mongo_reader

    # Lecturas para la ventana del dia
    runs_in_day              = sql_reader.list_runs_between(start, end)
    failed_runs_in_day       = sql_reader.list_failed_runs_between(start, end)
    quality_snapshots_in_day = sql_reader.list_quality_snapshots_between(start, end)
    triage_in_day            = mongo_reader.list_triage_patients_between(start, end)
    severe_in_day            = mongo_reader.list_severe_triage_patients_between(start, end)
    counts_snapshot          = mongo_reader.get_total_counts()

    return build_daily_report(
        target_date,
        failed_runs_in_day=failed_runs_in_day,
        runs_in_day=runs_in_day,
        quality_snapshots_in_day=quality_snapshots_in_day,
        triage_patients_in_day=triage_in_day,
        severe_triage_patients_in_day=severe_in_day,
        counts_snapshot=counts_snapshot,
        threshold=DEFAULT_THRESHOLD,
        # generated_at: el builder usa now() si es None — el JSON sale
        # con timestamp dinamico, pero el render_markdown lo ignora.
    )
```

### `src/api/sql_reader.py` (extension)

Cinco metodos nuevos. Familia `_since` para el endpoint `/alerts`
(ventana abierta por la derecha hasta ahora) y familia `_between` para
el informe diario (ventana cerrada del dia):

```python
def list_failed_runs_since(self, since: datetime) -> list[dict]:
    """Pipeline runs con status='failed' y started_at >= since.
    Usado por GET /alerts."""

def list_quality_snapshots_since(self, since: datetime) -> list[dict]:
    """Snapshots de data_quality_summary con recorded_at >= since.
    Usado por GET /alerts."""

def list_failed_runs_between(
    self, start: datetime, end: datetime,
) -> list[dict]:
    """Runs con status='failed' y started_at en [start, end].
    Usado por GET /reports/daily + daily_report.py."""

def list_runs_between(
    self, start: datetime, end: datetime,
) -> list[dict]:
    """Runs con started_at en [start, end] (cualquier status).
    Usado para `pipeline.runs_in_day` del informe."""

def list_quality_snapshots_between(
    self, start: datetime, end: datetime,
) -> list[dict]:
    """Snapshots con recorded_at en [start, end].
    Usado por GET /reports/daily + daily_report.py."""
```

### `src/api/mongo_reader.py` (extension)

Cuatro metodos nuevos, misma logica de doble familia:

```python
def list_severe_triage_patients_since(
    self, since: datetime,
) -> list[dict]:
    """Pacientes con triage.level='grave' y triage.triaged_at >= since.
    Usado por GET /alerts."""

def list_severe_triage_patients_between(
    self, start: datetime, end: datetime,
) -> list[dict]:
    """Pacientes con triage.level='grave' y triage.triaged_at en
    [start, end]. Usado por GET /reports/daily + daily_report.py."""

def list_triage_patients_between(
    self, start: datetime, end: datetime,
) -> list[dict]:
    """Pacientes con triage.triaged_at en [start, end], cualquier
    nivel. Usado para contar grave/medio/leve del dia en el informe."""

def get_total_counts(self) -> dict:
    """Snapshot al instante de count(patients), count(admissions),
    count(radiographies). Usado por GET /reports/daily.counts."""
```

**Ventana del informe diario:**

```python
def day_window_utc(day: date) -> tuple[datetime, datetime]:
    """Devuelve [00:00:00.000Z, 23:59:59.999999Z] UTC para `day`.
    Usado por el endpoint y el script."""
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end
```

### `src/automation/daily_report.py` (nuevo, **CLI**)

```python
"""CLI reproducible para generar el informe diario en Markdown.

Uso:
    python -m src.automation.daily_report                      # hoy
    python -m src.automation.daily_report --date 2026-05-20    # fecha
    python -m src.automation.daily_report --date X --output Y  # destino

NO arranca FastAPI. Lee directamente via MongoReader + SqlReader y
llama al mismo `build_daily_report` que usa el endpoint HTTP.

Sin scheduler: la ejecucion es manual; la automatizacion consiste en
que el comando es **reproducible** (mismo estado -> mismo fichero).
"""
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    start, end = day_window_utc(args.date)

    # Lecturas via factorias del proyecto (no via HTTP)
    sql_reader = get_sql_reader_from_env()
    mongo_reader = get_mongo_reader_from_env()
    try:
        state = {
            "failed_runs_in_day":            sql_reader.list_failed_runs_between(start, end),
            "runs_in_day":                   sql_reader.list_runs_between(start, end),
            "quality_snapshots_in_day":      sql_reader.list_quality_snapshots_between(start, end),
            "triage_patients_in_day":        mongo_reader.list_triage_patients_between(start, end),
            "severe_triage_patients_in_day": mongo_reader.list_severe_triage_patients_between(start, end),
            "counts_snapshot":               mongo_reader.get_total_counts(),
        }
    finally:
        sql_reader.close()
        mongo_reader.close()

    report = build_daily_report(
        args.date,
        threshold=float(os.environ.get("ALERT_REJECTION_RATE_THRESHOLD", "0.10")),
        **state,
    )
    md = render_markdown(report)   # determinista, sin generated_at

    output = args.output or Path(f"docs/reports/{args.date.isoformat()}.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(md, encoding="utf-8")
    print(f"OK: informe escrito en {output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

**Sobre idempotencia:** el script invoca a `render_markdown(report)`,
que NO lee el reloj. El `generated_at` que arrastra `report` se ignora
en el render. Resultado: mismo `--date` + mismo estado del sistema ->
mismo fichero byte-a-byte. Para el dia en curso (`date >= today`) la
estabilidad es solo respecto al estado actual: si llegan nuevos eventos
hasta medianoche, el fichero del dia en curso ira cambiando (CB-7b).

### Schemas Pydantic — extension de `src/api/models.py`

```python
class AlertResponse(BaseModel):
    type: Literal["pipeline_failed", "data_quality_low", "triage_severe"]
    severity: Literal["critical", "high", "medium", "low"]
    title: str
    detail: str
    source: str
    source_id: str | None = None
    created_at: datetime

class AlertsResponse(BaseModel):
    items: list[AlertResponse]
    total: int
    generated_at: datetime
    threshold: float
    window_start: datetime

class DailyReportResponse(BaseModel):
    date: str
    generated_at: datetime
    pipeline: dict
    quality: dict
    counts: dict
    triage: dict
    alerts: list[AlertResponse]
```

### `src/dashboard/views/alerts.py` (nuevo)

**Estructura:**

```python
st.title("Alertas")
st.caption("Vista calculada en tiempo real desde pipeline_runs, "
           "data_quality_summary y patients.triage.")

# Cache 10s, mismo patron que las otras vistas
@st.cache_data(ttl=10, show_spinner=False)
def _cached_alerts(_base_url):
    return api.get_alerts()

data, err = _cached_alerts(api.base_url)
if err:
    show_api_error(err, context="/alerts")
elif not data["items"]:
    st.success("Sin alertas activas.")
else:
    # Conteo por severity
    counts = Counter(a["severity"] for a in data["items"])
    cols = st.columns(4)
    cols[0].metric("Critical", counts.get("critical", 0))
    cols[1].metric("High",     counts.get("high", 0))
    cols[2].metric("Medium",   counts.get("medium", 0))
    cols[3].metric("Low",      counts.get("low", 0))

    # Tabla con colores
    for alert in data["items"]:
        _render_alert(alert)

if st.button("Recargar"):
    _cached_alerts.clear()
    st.rerun()
```

`_render_alert` usa un `st.markdown` con `unsafe_allow_html=True` y un
span de color por severity (mismo patron que `system_status.py` ya
existente).

### `src/dashboard/api_client.py` (extension)

```python
def get_alerts(
    self,
    since: str | None = None,
    severity: str | None = None,
) -> ResultJson:
    params = {}
    if since:
        params["since"] = since
    if severity:
        params["severity"] = severity
    return self._request_json("GET", "/api/v1/alerts", params=params)

def get_daily_report(self, date: str | None = None) -> ResultJson:
    params = {"date": date} if date else {}
    return self._request_json("GET", "/api/v1/reports/daily", params=params)
```

### `src/dashboard/app.py` — registro

Una linea nueva entre `runs.py` y `triage.py` (o donde encaje):

```python
st.Page(str(_VIEWS_DIR / "alerts.py"), title="Alertas"),
```

## Modelo de datos

**Cero cambios en el modelo persistido.**

- Las alertas son una **vista calculada** desde:
  - `pipeline_runs` (tabla SQLite existente).
  - `data_quality_summary` (tabla SQLite existente).
  - `patients.triage` (campo embebido en MongoDB, ya existente desde
    Feature 14).

- Cero tablas SQL nuevas, cero colecciones Mongo nuevas, cero indices
  nuevos. Esto es verificable con `git diff` sobre
  `src/pipeline/storage/sql_models.py` y `docker/mongo-init/init-db.js`.

## Contratos de datos

### Datos de entrada — `GET /api/v1/alerts`

| Parametro | Tipo | Obligatorio | Validaciones | Que pasa si falla |
|---|---|---|---|---|
| `since` | ISO datetime UTC | no | parseable | 422 |
| `severity` | enum critical/high/medium/low | no | enum | 422 |

### Datos de salida — `AlertsResponse`

Definido en `src/api/models.py`. Estructura en RF-1 / spec.

### Datos de entrada — `GET /api/v1/reports/daily`

| Parametro | Tipo | Obligatorio | Validaciones | Que pasa si falla |
|---|---|---|---|---|
| `date` | YYYY-MM-DD | no (default hoy UTC) | ISO date parseable | 422 |

### Glosario

| Termino | Definicion |
|---|---|
| **Alerta** | Objeto JSON calculado on-demand que describe una condicion observable del sistema en este momento |
| **Vista derivada** | Datos que se calculan a partir de fuentes existentes sin persistirse (ver ADR-009) |
| **Ventana de alertas** | Intervalo `[now - ALERT_WINDOW_HOURS, now]` que limita la antiguedad de los eventos considerados |
| **Severity** | Nivel de prioridad de la alerta: `critical > high > medium > low` |

## Trade-offs

| Decision | Alternativa descartada | Razon |
|---|---|---|
| Alertas como vista derivada (read-only, sin persistir) | Tabla `alerts` en SQLite con estado leida/no leida | Cero superficie de estado nuevo; las fuentes ya tienen lo necesario. Encaja con la separacion lectura/escritura interna del proyecto (`MongoReader`/`MongoWriter`, `SqlReader`/`SqlWriter` — ADR-004). Si fuera produccion real, se reabriria. Ver ADR-009 |
| Funcion pura `evaluate(state)` separada del IO | Logica mezclada con queries en el router | Tests unitarios triviales (mismo patron que ADR-008 triaje) |
| Endpoint + script comparten builder | Codigo duplicado en HTTP y CLI | DRY; el script no requiere arrancar la API |
| Script ejecutable manual, sin scheduler | cron / Celery / APScheduler / Airflow | Fuera de temario y fuera del alcance; el enunciado pide automatizacion **reproducible**, no programada |
| Markdown como formato del informe | PDF (matplotlib + reportlab), HTML | Markdown se lee en GitHub, en VSCode y en cualquier editor. Sin dependencias nuevas. Renderizable a PDF si hace falta |
| Vista nueva "Alertas" | Bloque dentro de Overview | Overview ya esta cargado; las alertas necesitan espacio propio para tabla + filtros. Vista propia mantiene coherencia con las otras 6 vistas |
| `unsafe_allow_html` para chips de color | Streamlit nativo + emojis | Misma convencion ya usada por `system_status.py`. Cero emojis (convencion del repo) |

## Plan de tests

- `tests/api/test_alerts_rules.py` — **unitarios puros** (funcion `evaluate`):
  - `test_failed_run_creates_pipeline_failed_alert`
  - `test_quality_above_threshold_creates_alert`
  - `test_quality_exactly_at_threshold_does_not_alert` (CB-4)
  - `test_severe_patient_creates_triage_alert`
  - `test_leve_patient_does_not_alert` (CB-3)
  - `test_no_state_returns_empty` (CB-1)
  - `test_alerts_sorted_by_severity_then_time` (RF-8)
  - `test_threshold_configurable`

- `tests/api/test_alerts_endpoint.py` — **integracion con Mongo + SQLite**:
  - `test_get_alerts_empty_returns_zero`
  - `test_get_alerts_with_failed_run`
  - `test_get_alerts_with_severe_triage_patient`
  - `test_get_alerts_filter_by_severity`
  - `test_get_alerts_invalid_severity_returns_422`
  - `test_get_alerts_with_since_overrides_default_window`

- `tests/api/test_reports_endpoint.py`:
  - `test_get_daily_report_today`
  - `test_get_daily_report_specific_date`
  - `test_get_daily_report_invalid_date_returns_422`
  - `test_report_includes_all_sections`
  - `test_report_uses_day_window_not_last_24h`: insertar un run failed
    AYER y otro ANTEAYER; pedir `date=ayer` -> solo aparece el de ayer
    en `failed_runs_in_day`. El de anteayer no debe colarse aunque
    este dentro de "ultimas 24h desde ahora".
  - `test_report_for_past_day_does_not_include_events_after_midnight`:
    insertar evento a las 00:01 del dia siguiente; pedir el dia
    anterior -> ese evento NO aparece.

- `tests/api/test_reports_builder.py` — **builder + render puros**:
  - `test_build_daily_report_aggregates_correctly`
  - `test_render_markdown_does_not_include_generated_at` (RNF-6)
  - `test_render_markdown_is_deterministic`: llamar 2 veces con el
    mismo dict -> mismo string exacto (assert por igualdad o hash).
  - `test_render_markdown_lists_are_ordered_stable`: cambiar el orden
    de las entradas de entrada -> mismo Markdown (porque el render
    ordena por clave estable).

- `tests/automation/test_daily_report.py` — **script CLI**:
  - `test_script_creates_markdown_file`
  - `test_script_idempotent_same_day_same_state` (CA-11, RNF-6):
    ejecutar 2 veces con `--date <dia_cerrado>` y comparar
    `sha256(fichero1) == sha256(fichero2)`.
  - `test_script_creates_reports_dir_if_missing` (CB-10)
  - `test_script_with_custom_output_path`

- `tests/dashboard/test_api_client.py` — **extension**:
  - `test_get_alerts_maps_200`
  - `test_get_alerts_maps_422_to_validation_error`
  - `test_get_alerts_maps_503`
  - `test_get_daily_report_maps_200`
  - `test_get_daily_report_maps_422`

**Cobertura objetivo:** funcion pura `evaluate` al 100%. Endpoint
cubierto al menos por los 3 tipos de alerta. Script cubierto al menos
por creacion + idempotencia.

## Riesgos del diseno

| Riesgo | Probabilidad | Impacto | Mitigacion |
|---|---|---|---|
| Latencia del endpoint si crecen las colecciones | Baja en demo, alta en prod | Medio | Indices ya existen (started_at en pipeline_runs, recorded_at en quality, external_id en patients). Para volumen real se reabriria con persistencia (ADR-009 lo deja documentado) |
| Conteo de triajes graves en ventana de 24h crece sin parar | Media en demo larga | Bajo | Limitado por la ventana temporal; en demo academica no es problema |
| El script `daily_report.py` falla si faltan env vars | Alta primera ejecucion | Bajo | Mensaje claro + documentacion en runbook |
| Dashboard cachea alertas con `ttl=10s` y el operador no ve cambios al instante | Media | Bajo | Boton "Recargar" + ttl corto |
| Markdown del informe se vuelve dificil de leer si hay muchos datos | Baja | Bajo | Secciones colapsables si es necesario (mejora futura) |

## Estimacion de tamano

- `src/api/alerts.py`: ~80 lineas
- `src/api/reports.py`: ~120 lineas
- `src/api/routers/alerts.py`: ~50 lineas
- `src/api/routers/reports.py`: ~60 lineas
- `src/automation/daily_report.py`: ~120 lineas
- `src/api/sql_reader.py` extension: ~30 lineas
- `src/api/mongo_reader.py` extension: ~30 lineas
- Schemas en `models.py`: ~40 lineas
- `src/dashboard/views/alerts.py`: ~100 lineas
- `src/dashboard/api_client.py` extension: ~20 lineas
- `src/dashboard/app.py`: 1 linea
- Tests (4 ficheros nuevos + 2 extensiones): ~350 lineas
- ADR-009: ~120 lineas

**Total estimado:** ~1.100 lineas. Tamano **M** (1-3 dias de
implementacion, similar al triaje).

## Notas para fases siguientes

- Si en el futuro hace falta histórico de alertas (auditoria,
  reportes a posteriori, "cuantas alertas critical hubo el mes
  pasado"), se reabre ADR-009: anadir tabla `alerts` en SQLite con
  `alert_id, type, severity, source, source_id, created_at, raised_at,
  resolved_at` y migrar el endpoint a leer de ahi.
- Si en el futuro hace falta notificacion push, valorar webhook simple
  (POST a una URL configurable) — fuera de scope actual.
- El template del Markdown vive embebido en `render_markdown`. Si crece
  o se quiere personalizar, mover a Jinja2 (fuera de alcance).
