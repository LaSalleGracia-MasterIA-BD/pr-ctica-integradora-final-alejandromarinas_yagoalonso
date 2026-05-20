# Tasks: Automatizacion, alertas e informes operativos

> Spec: specs/automatizacion-alertas.md
> Design: design/automatizacion-alertas.md
> ADR: decisions/ADR-009-alertas-como-vista-derivada.md

## Formato

Cada tarea sigue: `T### [P?] [US#?] descripcion con path concreto`

- `T###` — ID secuencial.
- `[P]` — paralelizable.
- `[US#]` — pertenece a esa user story.

## Regla TDD

Tests rojos de `evaluate` antes de implementarla. Tests del endpoint
antes del router. Tests del script antes del script.

## Tabla de tareas

| # | Tarea | Requisitos | Dependencias | Tamano | Estado |
|---|-------|-----------|-------------|--------|--------|
| T1 | Crear `decisions/ADR-009-alertas-como-vista-derivada.md` con contexto, decision (vista derivada vs persistencia), alternativas, consecuencias. Conecta con teoria del Master: sistemas basados en reglas (Yuri Sesion 07 `ruleBasedSystem`) + diseno de APIs FastAPI/SQLite/SQLAlchemy (Eric Bloque 7 `07-design-apis`). La separacion lectura/escritura se describe como patron interno del proyecto, no como teoria de clase | RF-1, RNF-3 | — | S | done (creado el 2026-05-20 en fase documental) |
| T2 | [US1] Escribir `tests/api/test_alerts_rules.py` con tests unitarios puros de `evaluate(state)`: 1 test por tipo de alerta (pipeline_failed, data_quality_low, triage_severe) + casos borde (CB-3 leve no genera, CB-4 umbral exacto no genera) + RF-8 (orden severity desc). Confirmar rojo | CA-10, RF-2, RF-8, RNF-5 | — | M | done |
| T3 | [US1] Implementar `src/api/alerts.py` con `@dataclass Alert`, `Severity`, `AlertType` y funcion pura `evaluate(failed_runs, quality_snapshots, severe_triage_patients, threshold) -> list[Alert]`. Hacer pasar T2 | RF-2, RF-8, RNF-5 | T2 | M | done |
| T4 | [P] Extender `src/api/models.py` con `AlertResponse`, `AlertsResponse`, `DailyReportResponse` (schemas Pydantic) | RF-1, RF-4 | — | S | done |
| T4b | [P] Extender `src/api/sql_reader.py` con: (1) `list_failed_runs_since(since)` y `list_quality_snapshots_since(since)` para `/alerts`; (2) `list_failed_runs_between(start, end)`, `list_runs_between(start, end)`, `list_quality_snapshots_between(start, end)` para el informe diario. Tests en `tests/api/test_sql_reader.py` verificando ambas familias + boundary del intervalo (inclusivo en start, inclusivo en end) | RF-1, RF-4 | — | M | done |
| T4c | [P] Extender `src/api/mongo_reader.py` con: (1) `list_severe_triage_patients_since(since)` para `/alerts`; (2) `list_severe_triage_patients_between(start, end)`, `list_triage_patients_between(start, end)`, `get_total_counts()` para el informe diario. Tests de integracion verificando ambas familias | RF-1, RF-4 | — | M | done |
| T4d | [P] Anadir helper `day_window_utc(day: date) -> tuple[datetime, datetime]` (probablemente en `src/api/reports.py` o helper dedicado). Devuelve `[00:00:00.000Z, 23:59:59.999999Z]` UTC. Test unitario puro | RF-4 | — | S | done |
| T5 | [US1] Escribir `tests/api/test_alerts_endpoint.py::test_get_alerts_empty_returns_zero` + tests para los 3 tipos de alerta + filtro por severity + 422 con severity invalida + uso de `since` query param | CA-1..CA-3, RF-1, RF-3 | T4 | M | done |
| T6 | [US1] Crear `src/api/routers/alerts.py` con `GET /api/v1/alerts`. Lee `ALERT_REJECTION_RATE_THRESHOLD` y `ALERT_WINDOW_HOURS` desde env, invoca a los readers extendidos (T4b/T4c), llama a `evaluate` (T3), serializa via schema (T4). Wire en `src/api/main.py`. Hacer pasar T5 | RF-1, RF-3, RF-8 | T3, T4, T4b, T4c, T5 | M | done |
| T7 | [US2] Escribir `tests/api/test_reports_builder.py` (builder + render puros) y `tests/api/test_reports_endpoint.py` (integracion). En `test_reports_endpoint.py` incluir: (a) date valida/invalida/sin date; (b) `test_report_uses_day_window_not_last_24h` — insertar evento ayer + anteayer, pedir `date=ayer`, anteayer NO debe aparecer; (c) `test_report_for_past_day_does_not_include_events_after_midnight`. En `test_reports_builder.py` incluir: (d) `test_render_markdown_does_not_include_generated_at`; (e) `test_render_markdown_is_deterministic` (assert por hash sha256 de 2 llamadas) | CA-4, CA-11, RF-4, RF-5, RNF-6 | T4, T4b, T4c, T4d | M | done |
| T8 | [US2] Implementar `src/api/reports.py` con: (a) `build_daily_report(day, failed_runs_in_day, runs_in_day, quality_snapshots_in_day, triage_patients_in_day, severe_triage_patients_in_day, counts_snapshot, threshold, generated_at=None) -> dict`; (b) `render_markdown(report) -> str` **deterministico** — NO incluye `generated_at`, lee solo del dict, listas con orden estable. Funciones puras, sin HTTP, sin `datetime.now()` en `render_markdown`. Hacer pasar T7 | RF-4, RF-5, RNF-6 | T3, T4, T4d, T7 | M | done |
| T9 | [US2] Crear `src/api/routers/reports.py` con `GET /api/v1/reports/daily?date=YYYY-MM-DD`. Lee state via readers `_between` (no `_since`), llama a `build_daily_report` con `day_window_utc(date)`, devuelve dict. Wire en `main.py`. Hacer pasar la parte de endpoint de T7 | RF-4 | T8 | S | done |
| T10 | [US2] Escribir `tests/automation/test_daily_report.py`: (a) `test_script_creates_markdown_file`; (b) `test_script_idempotent_same_day_same_state` — comparar `sha256` de 2 ejecuciones consecutivas sobre un dia **cerrado** (no hoy) con mismo estado; (c) `test_script_creates_reports_dir_if_missing` (CB-10); (d) `test_script_with_custom_output_path`. Usa tmp_path como `--output` | CA-5, CA-11, RF-5, RNF-6 | T8 | M | done |
| T11 | [US2] Implementar `src/automation/__init__.py` (vacio o con docstring) + `src/automation/daily_report.py` con CLI argparse, lee state via `MongoReader` + `SqlReader` con readers `_between`, invoca `build_daily_report` + `render_markdown` (sin `generated_at` en el fichero). Hacer pasar T10. Documentar en docstring que la idempotencia byte-a-byte aplica solo a dias cerrados (CB-7b) | RF-5, RNF-6, CB-7b, CB-10 | T8, T10 | M | done |
| T12 | [P] Extender `src/dashboard/api_client.py` con `get_alerts(since=None, severity=None)` y `get_daily_report(date=None)`. Tests en `tests/dashboard/test_api_client.py` con `httpx.MockTransport`: 200, 422, 503, network error | RF-7 | T6, T9 | S | done |
| T13 | [US3] Crear `src/dashboard/views/alerts.py`: 4 chips de conteo por severity, tabla/lista con color por severity, manejo de error con `show_api_error`, boton Recargar, mensaje "Sin alertas activas" si vacio. Cache `ttl=10s` con clave `_base_url` (mismo patron que las otras vistas) | RF-6, CA-6 | T12 | M | done |
| T14 | [US3] Registrar la nueva pagina en `src/dashboard/app.py` anadiendo `st.Page(str(_VIEWS_DIR / "alerts.py"), title="Alertas")` en la lista `pages`. Posicion sugerida: entre "Pipeline runs" y "Triaje" | RF-6 | T13 | S | done |
| T15 | Verificacion CA-8 + CA-9: `git diff --stat src/pipeline/storage/sql_models.py docker/mongo-init/init-db.js` debe ser vacio (cero estado nuevo, RNF-3). `grep -rE "pymongo\|^from minio\|sqlite3\|sqlalchemy" src/dashboard/` debe seguir devolviendo 0 ocurrencias | CA-8, CA-9 | T13, T14 | S | done |
| T16 | Smoke E2E manual con stack vivo: `docker compose up -d --build api dashboard`. Crear paciente grave via Triaje -> abrir vista Alertas -> verificar alerta `triage_severe`. Ejecutar `docker compose run --rm pipeline python -m src.automation.daily_report` -> verificar fichero en `docs/reports/`. Hacer `curl GET /api/v1/alerts` y `curl GET /api/v1/reports/daily` -> verificar 200 con JSON correcto | CA-1, CA-4, CA-5, CA-6 | T14, T11 | S | done |
| T17 | Documentacion viva (TODOS obligatorios): (a) `CHANGELOG.md` entrada Added con endpoints + vista + script + ADR-009; (b) `tasks/backlog.md` Features 5 y 6 a `done` (cubiertas por esta feature); (c) `tasks/triage-pacientes.md` referencia cruzada a alertas; (d) `docs/diario-ia.md` sesion 30 con casos donde corregir + lecciones; (e) `README.md` ejemplos curl de los 2 endpoints + comando del script + apartado de informes diarios; (f) **`docs/memoria-tecnica.md` OBLIGATORIO**: actualizar al menos cap 7 (API), cap 8 (Dashboard), cap 10 (Operacion/automatizacion), cap 9 (tabla ADRs con ADR-008 y ADR-009) y cap 12 (Resultados con cifras de tests actualizadas). La memoria estaba desactualizada respecto al triaje (Feature 14) y ahora tambien tiene que reflejar alertas/informes (Feature 15) | — | T15, T16 | M | done |

Tamanos: S (< 1h) | M (1-4h) | L (> 4h, considerar dividir)
Estados: pending | in-progress | done | blocked

**Estado final (2026-05-20):** T1-T17 todas en `done`. 60 tests nuevos
verde (alerts rules + endpoint + reports builder + endpoint + time
window + script CLI con sha256 byte-a-byte + cliente HTTP). Suite
total del proyecto: 404 verde + 1 skip esperado. Smoke real
verificado: paciente grave inyectado via /triage/patients aparece en
/api/v1/alerts; dos ejecuciones consecutivas del CLI con `--date
2026-05-20` -> hash sha256 identico. Features 5 y 6 del backlog
cerradas como `done`.

## Fases

### Fase 1 — Decision arquitectonica (sin `[US#]`) — completada

T1 (ADR-009) — `decisions/ADR-009-alertas-como-vista-derivada.md`
creado y aceptado el 2026-05-20. La fase de implementacion empieza
directamente en la Fase 2.

### Fase 2 — Foundational (sin `[US#]`)

T4 + T4b + T4c + T4d (schemas + readers extendidos `_since`/`_between`
+ helper `day_window_utc`). `[P]` entre si.

### Fase 3 — US-1 (P1) MVP: endpoint /alerts (todas con `[US1]`)

T2 (test rojo) -> T3 (evaluate) -> T5 (test endpoint) -> T6 (router).

**Checkpoint:** `curl /api/v1/alerts` devuelve la lista correcta con los
3 tipos de alerta.

### Fase 4 — US-2 (P2): informe diario (todas con `[US2]`)

T7 (test builder + endpoint) -> T8 (builder + render_markdown) ->
T9 (router) -> T10 (test script) -> T11 (script CLI).

**Checkpoint:** `python -m src.automation.daily_report` genera el
Markdown.

### Fase 5 — US-3 (P1): vista dashboard (todas con `[US3]`)

T12 (api_client) -> T13 (vista) -> T14 (registro).

**Checkpoint:** vista /alerts del dashboard muestra alertas activas.

### Fase 6 — Cierre

T15 (verificaciones) -> T16 (smoke real) -> T17 (docs vivas).

## Reglas de paralelizacion

- `T4`, `T4b`, `T4c` son `[P]` entre si (3 modulos distintos sin
  dependencias cruzadas).
- `T12` es `[P]` respecto a T13 (cliente HTTP no depende de la vista).
- Tests rojos antes que codigo: T2 antes que T3, T5 antes que T6,
  T7 antes que T8/T9, T10 antes que T11.

## Ruta critica

**T4 + T4b + T4c + T4d -> T2 -> T3 -> T5 -> T6 -> T13 -> T14 -> T16**

Atajo de US-1 + US-3 (endpoint + vista). US-2 (informe) corre en
paralelo desde T7.

## Estimacion total

| Fase | Tamano | Tiempo |
|---|---|---|
| Fase 1 (ADR-009) | S | 30-45 min |
| Fase 2 (schemas + readers + helper) | S+M+M+S | 2-3 h |
| Fase 3 (US-1: /alerts) | M+M+M+M | 4-5 h |
| Fase 4 (US-2: informe) | M+M+S+M+M | 4-5 h |
| Fase 5 (US-3: vista) | S+M+S | 2-3 h |
| Fase 6 (cierre) | S+S+S | 1-2 h |

**Total estimado:** 13-18 horas. Tamano feature: **M** (1-3 dias).

## Notas

- Mismo patron TDD que la feature de triaje (ADR-008). Tests puros
  primero, codigo despues. Una vez verde `evaluate`, el router casi
  se escribe solo.
- Cero servicios nuevos en docker-compose. Cero dependencias nuevas en
  `requirements-pipeline.txt`. El script CLI usa lo que ya hay.
- Al cerrar T17, **Features 5 y 6 del backlog pasan a `done`** (era el
  objetivo: cerrar lo unico realmente pendiente del enunciado).
- La carpeta `src/automation/` deja de estar vacia con T11. La de
  `tests/automation/` deja de estar vacia con T10. **No se limpian ni
  se modifican carpetas vacias** en este ciclo (la limpieza queda como
  chore aparte tras cerrar la feature).
- **T17 es obligatoria** en su totalidad — incluido el bloque (f) de
  actualizar `docs/memoria-tecnica.md`. La memoria estaba desactualizada
  con el triaje (Feature 14) y, sin esta tarea, se quedaria tambien
  sin reflejar la Feature 15. La memoria es entregable obligatorio del
  enunciado: no puede quedarse atras.
- **Idempotencia del informe** (RNF-6, CA-11): aplica al Markdown del
  script para **dias cerrados** (`date < today`). El dia en curso es
  un caso documentado (CB-7b) donde el Markdown va cambiando segun
  llegan eventos hasta medianoche. Los tests usan un dia cerrado.
- **Conexion con teoria del Master en ADR-009**: sistemas basados en
  reglas (Yuri Sesion 07) + diseno de APIs FastAPI/SQLite (Eric Bloque
  7). La separacion lectura/escritura interna del proyecto es patron
  propio, no se vende como teoria de clase.
