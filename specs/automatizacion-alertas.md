# Spec: Automatizacion, alertas e informes operativos

> Estado: approved
> Ultima actualizacion: 2026-05-20

## Contexto y problema

El enunciado del proyecto pide explicitamente dos cosas que hoy estan
parciales (Features 5 y 6 del backlog):

- **Automatizacion de procesos**: "generacion automatica de informes",
  "envio de alertas ante eventos relevantes", "procesamiento automatico
  de nuevos datos".
- **Monitorizacion y calidad de datos**: "logging centralizado",
  "validacion de calidad de datos", **"alertas o notificaciones ante
  fallos en el procesamiento (puede ser un log, un email simulado o una
  entrada en el dashboard)"**.

El proyecto ya cubre:

- Watcher como servicio Docker (procesamiento automatico de CSVs que
  caen en `data/incoming/`).
- Logging centralizado (`src/pipeline/logging_config.py`).
- Validacion + `rejected_records` + `data_quality_summary`.

Lo que **falta** es la capa de **observabilidad accionable** sobre
todo eso: que un operador del hospital pueda ver de un vistazo si hay
runs fallidos, calidad de datos baja o pacientes triajeados como
graves, sin necesidad de leer logs o ejecutar queries.

El enunciado deja claro que la solucion puede ser "una entrada en el
dashboard" — no exige sistema de notificaciones externo. Mantener el
alcance dentro de teoria del Master: sistemas basados en reglas
aplicados a metricas operativas, mas un script reproducible para
informes manuales. Sin scheduler real, sin servicios externos.

## Objetivo

Cerrar **Features 5 y 6** del backlog (de partial a done) anadiendo
tres piezas pequenas que cumplen el enunciado:

1. Endpoint REST `GET /api/v1/alerts` que devuelve las **alertas
   activas calculadas en tiempo real** a partir de datos existentes
   (sin almacenar histórico nuevo).
2. Generacion de **informe diario** en Markdown (endpoint que devuelve
   JSON estructurado + script CLI que lo renderiza a fichero).
3. **Vista "Alertas"** nueva en el dashboard que consume el endpoint
   anterior y muestra las alertas con color por severidad.

## Actores y alcance

**Usuarios:**

- Operador del dashboard (medico, residente, evaluador): consulta
  alertas activas; revisa informe del dia.
- API REST: punto de entrada unico (dashboard sigue siendo API-only,
  ADR-007).
- Operador del sistema (devops, evaluador): genera el informe diario
  ejecutando un comando reproducible.

**Dentro del alcance:**

- Endpoint `GET /api/v1/alerts` con calculo on-demand desde:
  - `pipeline_runs` (SQLite) — runs con `status=failed`.
  - `data_quality_summary` (SQLite) — snapshots con `rejection_rate`
    sobre un umbral.
  - `patients.triage` (MongoDB) — pacientes triajeados como `grave`.
- Endpoint `GET /api/v1/reports/daily?date=YYYY-MM-DD` que devuelve un
  JSON con resumen del dia.
- Script CLI `src/automation/daily_report.py` que llama internamente al
  mismo builder + renderiza Markdown en `docs/reports/YYYY-MM-DD.md`.
- Vista nueva `src/dashboard/views/alerts.py`, registrada en `app.py`.
- Tests: unitarios del calculo (funcion pura), de endpoint, del
  generador de informe y del cliente HTTP del dashboard.
- Configuracion via env vars (`ALERT_REJECTION_RATE_THRESHOLD` con
  default 0.10, `ALERT_WINDOW_HOURS` con default 24).
- Documentacion: README con ejemplo curl + comando del script;
  `CHANGELOG.md`, `tasks/backlog.md`, `docs/diario-ia.md`.

**Fuera del alcance:**

- Persistencia de alertas (tabla `alerts` o coleccion nueva): se decide
  expresamente NO crearla. Las alertas son una **vista derivada**
  calculada al vuelo desde las fuentes existentes (ver ADR-009).
- Scheduler real (cron, Celery, APScheduler, Airflow): fuera del
  temario y fuera del alcance del enunciado. El informe diario se
  ejecuta manualmente y se documenta como automatizacion
  **reproducible**, no automatizada por reloj.
- Email real o notificaciones push: fuera de alcance segun enunciado
  ("puede ser un log, un email simulado o una entrada en el dashboard"
  — elegimos la entrada en el dashboard).
- Estado de "alerta leida / no leida" (sin persistencia, no aplica).
- Configuracion en vivo de los umbrales desde la UI: se hace via env
  var, recarga al reiniciar la API. Suficiente para el alcance.
- Sistemas de monitorizacion externos (Prometheus, Grafana,
  observability stack): fuera del temario.

## User Stories

### US-1 — Ver alertas activas en el dashboard (Prioridad: P1)

**Como** operador del hospital
**Quiero** abrir el dashboard y ver inmediatamente si hay alertas
activas (runs fallidos, calidad de datos baja, pacientes graves)
**Para** reaccionar rapido sin tener que leer logs ni hacer queries

**Por que esta prioridad:** es el caso de uso central que pide el
enunciado ("una entrada en el dashboard"). Si esto no funciona, no
hemos cubierto Feature 6 (monitorizacion).

**Test independiente:** dado que MongoDB tiene un paciente con
`triage.level=grave` reciente, al abrir `GET /api/v1/alerts` la
respuesta incluye una alerta tipo `triage_severe` con `severity=critical`
y el `external_id` del paciente.

**Escenarios de aceptacion:**

1. **Dado** un run del pipeline con `status=failed` y `started_at`
   dentro de la ventana de alertas, **cuando** se llama a
   `GET /api/v1/alerts`, **entonces** la respuesta contiene una alerta
   tipo `pipeline_failed` con `severity=high` y `source_id=<run_id>`.
2. **Dado** un snapshot de `data_quality_summary` con
   `rejection_rate > ALERT_REJECTION_RATE_THRESHOLD` (default 0.10),
   **cuando** se llama al endpoint, **entonces** la respuesta contiene
   una alerta tipo `data_quality_low` con `severity=medium`.
3. **Dado** un paciente con `triage.level=grave` y `triage.triaged_at`
   dentro de la ventana, **cuando** se llama al endpoint, **entonces**
   la respuesta contiene una alerta tipo `triage_severe` con
   `severity=critical` y `source_id=<external_id>`.
4. **Dado** un sistema con cero condiciones de alerta, **cuando** se
   llama al endpoint, **entonces** `items=[]` y `total=0`.

---

### US-2 — Generar informe diario reproducible (Prioridad: P2)

**Como** operador del hospital o evaluador del proyecto
**Quiero** ejecutar un comando que genere un informe del dia en
formato Markdown legible
**Para** archivarlo, compartirlo o revisarlo offline

**Por que esta prioridad:** cubre el bullet "generacion automatica de
informes" del enunciado. Lo enmarcamos como automatizacion
**reproducible** (un comando, mismo resultado siempre) en lugar de
"programada" (no requiere scheduler).

**Test independiente:** ejecutar
`python -m src.automation.daily_report --date 2026-05-20` produce el
fichero `docs/reports/2026-05-20.md` con las secciones esperadas.

**Escenarios de aceptacion:**

1. **Dado** un dia con runs del pipeline + triajes + alertas activas,
   **cuando** se ejecuta el script, **entonces** se crea un Markdown
   con secciones: `## Pipeline`, `## Calidad de datos`, `## Conteos`,
   `## Triaje`, `## Alertas`.
2. **Dado** un dia sin actividad, **cuando** se ejecuta el script,
   **entonces** se crea el Markdown con secciones presentes y los
   contadores en cero / mensajes claros ("sin runs hoy").
3. **Dado** que existe el endpoint, `GET /api/v1/reports/daily?date=...`
   devuelve el mismo JSON estructurado que el script usa internamente
   para renderizar el Markdown.

---

### US-3 — Vista "Alertas" en el dashboard (Prioridad: P1)

**Como** operador del hospital
**Quiero** una vista dedicada en el dashboard con todas las alertas
activas, agrupadas por severidad
**Para** auditar rapidamente el estado del sistema

**Por que esta prioridad:** una entrada simple en Overview no cubre el
caso de uso bien (Overview ya esta lleno); una vista propia mantiene
la coherencia con el resto del dashboard.

**Test independiente:** smoke manual — abrir `/alerts` en el dashboard
muestra las alertas activas con su color de severidad.

**Escenarios de aceptacion:**

1. **Dado** el dashboard arrancado, **cuando** se navega a la vista
   "Alertas", **entonces** se ve una tabla o lista con las alertas
   activas leidas via `GET /api/v1/alerts`.
2. **Dado** cero alertas activas, **cuando** se navega a la vista,
   **entonces** se muestra un mensaje claro tipo "Sin alertas activas".
3. **Dado** que la API esta caida, **cuando** se navega a la vista,
   **entonces** se muestra el banner de error (`show_api_error`) y el
   resto del dashboard sigue funcionando (RNF-4 del dashboard).

## Requisitos funcionales

- **RF-1:** Existe un endpoint `GET /api/v1/alerts` que devuelve, en
  JSON, todas las **alertas activas calculadas en tiempo real**
  a partir de las fuentes existentes (sin tabla nueva). Estructura
  de cada alerta:
  ```
  {
    "type": "pipeline_failed | data_quality_low | triage_severe",
    "severity": "critical | high | medium | low",
    "title": "string corto",
    "detail": "string descriptivo",
    "source": "pipeline_runs | data_quality_summary | patients.triage",
    "source_id": "string opcional (run_id, external_id, ...)",
    "created_at": "ISO datetime UTC del evento original"
  }
  ```
  El response envuelve la lista:
  ```
  { "items": [...], "total": N, "generated_at": "ISO UTC" }
  ```

- **RF-2:** Las reglas de calculo de alertas (funcion pura
  `evaluate(failed_runs, quality_snapshots, severe_triage_patients,
  threshold) -> list[Alert]`) son:
  - `pipeline_failed`: una alerta por cada run en `failed_runs` (que ya
    viene filtrado por `status=failed` y por ventana). `severity=high`.
  - `data_quality_low`: por cada snapshot de `quality_snapshots` (que
    ya viene filtrado por ventana) cuya `rejection_rate > threshold`.
    `threshold` por defecto = `ALERT_REJECTION_RATE_THRESHOLD` (0.10).
    Una alerta por (dimension, pipeline_run_id). `severity=medium`.
  - `triage_severe`: una alerta por cada paciente en
    `severe_triage_patients` (que ya viene filtrado por
    `triage.level=grave` y por ventana). `severity=critical`.

  La funcion `evaluate` NO conoce el reloj ni la ventana: solo aplica
  las reglas sobre las listas que recibe. Esto permite reutilizarla
  con dos ventanas distintas:
  - **Endpoint `/alerts`**: ventana `[now() - ALERT_WINDOW_HOURS, now()]`
    o la que indique el query param `since`.
  - **Endpoint `/reports/daily` y script `daily_report.py`**: ventana
    estricta del dia `[YYYY-MM-DDT00:00:00Z, YYYY-MM-DDT23:59:59.999Z]`.

  La diferencia esta en QUE listas se pasan a `evaluate`, no en la
  funcion en si.

- **RF-3:** El endpoint acepta query params opcionales:
  - `since` (ISO datetime UTC): sobreescribe la ventana por defecto.
    Si esta presente, se ignora `ALERT_WINDOW_HOURS`.
  - `severity` (string): si esta presente, filtra resultados por
    severidad. Valores invalidos -> 422.

- **RF-4:** Existe un endpoint `GET /api/v1/reports/daily?date=YYYY-MM-DD`
  que devuelve un JSON estructurado con resumen **del dia pedido**.

  Ventana temporal del informe: dado `date=YYYY-MM-DD`, el informe usa
  estrictamente la ventana `[YYYY-MM-DDT00:00:00Z, YYYY-MM-DDT23:59:59.999Z]`
  (UTC). **Todos los conteos y listados se calculan dentro de esa
  ventana**, NO sobre "ultimas 24h desde ahora". Estructura:
  ```
  {
    "date": "YYYY-MM-DD",
    "generated_at": "ISO UTC",
    "pipeline": { "last_run_of_day": {...}, "runs_in_day": N, "failed_in_day": N },
    "quality":  { "patients": {...}, "admissions": {...} },
    "counts":   {
      "patients_total":      N,    # snapshot al cierre del dia
      "admissions_total":    N,
      "radiographies_total": N
    },
    "triage":   { "grave": N, "medio": N, "leve": N, "in_day_total": N },
    "alerts":   [ ...alertas del dia (eventos generadores dentro de la ventana)... ]
  }
  ```
  - `pipeline.runs_in_day` cuenta runs con `started_at` dentro de la
    ventana del dia; `failed_in_day` los que cumplen `status=failed`.
  - `quality` toma los snapshots de `data_quality_summary` cuyo
    `recorded_at` cae dentro de la ventana. Si hay varios snapshots
    por dimension, se devuelve el ultimo del dia para cada una.
  - `triage.grave/medio/leve` cuentan pacientes cuyo `triage.triaged_at`
    cae dentro de la ventana.
  - `alerts` reutiliza la **misma funcion pura `evaluate`** (RF-2),
    pero alimentada con eventos cuyo `created_at` cae dentro de la
    ventana del dia. Las alertas del informe son por tanto un
    **snapshot historico** del dia, no la lista "activa ahora".
  - `generated_at` registra **cuando se calculo el informe** (puede
    diferir del dia consultado). Esto NO compromete la idempotencia
    del Markdown porque ese campo no se incluye en el render (RF-5).

  Si `date` se omite, usa la fecha actual UTC. Si `date` esta mal
  formada -> 422.

- **RF-5:** Existe un script CLI `src/automation/daily_report.py`
  invocable con:
  ```
  python -m src.automation.daily_report [--date YYYY-MM-DD] [--output PATH]
  ```
  El script:
  - Calcula internamente el mismo JSON que devuelve el endpoint RF-4
    (sin pasar por HTTP — usa `MongoReader` + `SqlReader` directamente).
  - Renderiza el JSON a Markdown con secciones humanas.
  - Escribe el fichero en `docs/reports/YYYY-MM-DD.md` (o en `--output`
    si se especifica).
  - El Markdown generado debe ser **byte-a-byte estable** a igualdad
    de (estado del sistema + fecha solicitada). En particular:
    * **`generated_at` NO se incluye en el Markdown** (solo en el JSON
      del endpoint). El render usa unicamente datos del propio dia.
    * El orden de las listas es determinista (por timestamps + ids
      estables).
    * Cualquier diferencia byte-a-byte tras dos ejecuciones consecutivas
      con mismo `--date` y mismo estado del sistema es un bug.
  - Distinguir claramente:
    * **Endpoint** `/reports/daily`: devuelve JSON que SI lleva
      `generated_at` dinamico (informa del momento de calculo). No
      esta sujeto a idempotencia byte-a-byte.
    * **Script** `daily_report.py`: produce Markdown determinista,
      apto para `git diff` entre ejecuciones.

- **RF-6:** Existe una **vista nueva "Alertas"** en el dashboard
  (`src/dashboard/views/alerts.py`) registrada en `src/dashboard/app.py`.
  Contenido:
  - Carga alertas via `api_client.get_alerts()` con cache `ttl=10s`.
  - Muestra el conteo total + desglose por severity en chips.
  - Tabla/lista de alertas con color por severity (rojo critical,
    naranja high, ambar medium, gris low) + `title`, `detail`,
    `source`, `created_at`.
  - Botón "Recargar" manual.
  - Mensaje claro si no hay alertas: "Sin alertas activas".
  - Manejo de errores con `show_api_error` (banner) — la vista NO casca
    si la API no responde.

- **RF-7:** El cliente HTTP del dashboard (`src/dashboard/api_client.py`)
  gana dos metodos nuevos:
  - `get_alerts(since=None, severity=None) -> ResultJson`
  - `get_daily_report(date=None) -> ResultJson`

- **RF-8:** Las alertas se devuelven ordenadas por
  `severity DESC, created_at DESC` (critical primero, mas reciente
  primero dentro de cada severity).

## Requisitos no funcionales

- **RNF-1:** El endpoint `GET /api/v1/alerts` responde en menos de
  1 segundo sobre el dataset actual (~4.745 pacientes + ~hist runs).
  No hay calculos pesados: son count + find sobre datos ya indexados.
- **RNF-2:** Las alertas son **read-only**: el endpoint no muta nada.
- **RNF-3:** Cero estado nuevo persistido. No se anaden tablas SQL ni
  colecciones Mongo nuevas. Las alertas se calculan al vuelo desde las
  fuentes existentes (ver ADR-009).
- **RNF-4:** El dashboard sigue **API-only** (ADR-007). La vista
  "Alertas" llama unicamente al cliente HTTP; cero conexiones directas
  a MongoDB/SQLite/MinIO.
- **RNF-5:** La logica de calculo de alertas vive como **funcion pura**
  `evaluate(state) -> list[Alert]` en `src/api/alerts.py`, separada de
  la capa de lectura. Tests unitarios sin Mongo ni SQLite.
- **RNF-6:** El **Markdown** producido por `daily_report.py` es
  **byte-a-byte estable** a igualdad de (estado del sistema + fecha
  solicitada). Cualquier diferencia tras una segunda ejecucion del
  script en las mismas condiciones es un bug.

  Aplica **solo al Markdown**, NO al JSON del endpoint
  `/reports/daily`: el endpoint puede llevar `generated_at` dinamico
  como metadato. Para garantizar la estabilidad del Markdown, el
  render NO incluye campos dependientes del momento de ejecucion;
  todo el contenido depende exclusivamente del dia solicitado y del
  estado de las fuentes.
- **RNF-7:** Los umbrales (`ALERT_REJECTION_RATE_THRESHOLD` default
  0.10, `ALERT_WINDOW_HOURS` default 24) son configurables via env var.
  En tests se sobreescriben para reproducir condiciones.
- **RNF-8:** Conexion con la teoria del Master: las alertas son
  **reglas de produccion** (IF-THEN deterministas) aplicadas a
  metricas operativas. Misma familia que el sistema de triaje
  (ADR-008) y la Sesion 07 de Modelos de IA (sistemas basados en
  reglas).

## Casos borde y errores

- **CB-1:** No hay datos en ninguna fuente (BBDD limpia post `down -v`):
  el endpoint devuelve `items=[]`, `total=0`. No casca.
- **CB-2:** Un run con `status=running` muy antiguo (>24h): NO se
  reporta como `pipeline_failed` (la regla solo cuenta `status=failed`).
- **CB-3:** Un paciente con `triage.level=leve`: NO genera alerta.
- **CB-4:** Un snapshot con `rejection_rate` justo igual al umbral
  (0.10): NO genera alerta (regla es estrictamente mayor que).
- **CB-5:** `since` en el query string con formato invalido: 422.
- **CB-6:** `date` en el endpoint de reports con formato invalido: 422.
- **CB-7:** `date` futura: la API acepta y devuelve el reporte con
  contadores en cero. No es un error.
- **CB-7b:** `date` del informe coincide con el dia en curso: la
  ventana es `[YYYY-MM-DDT00:00:00Z, now()]` truncada al final del
  dia. El reporte aun cambiara si llegan nuevos eventos hasta la
  medianoche, asi que el Markdown del **dia en curso** NO es
  estrictamente idempotente — solo lo es para dias **cerrados**
  (date < hoy). Documentado como comportamiento esperado.
- **CB-8:** MongoDB o SQLite no disponibles: la API responde 503 con
  mensaje claro.
- **CB-9:** El script `daily_report.py` corre sin las env vars de
  Mongo: error claro de arranque con mensaje que explica que falta
  configurar el entorno.
- **CB-10:** Si la carpeta `docs/reports/` no existe, el script la
  crea antes de escribir.

## Dudas abiertas

Ninguna. Decidido con Alejandro en la revision del 2026-05-20:

1. **Endpoint vs script**: ambos. El endpoint devuelve JSON (consumible
   por dashboard o terceros). El script usa internamente el mismo
   builder y produce el Markdown.
2. **Vista nueva en dashboard**: si (no bloque en Overview).
3. **Persistencia de alertas**: NO. Vista derivada (ADR-009).
4. **Scheduler**: NO. Manual + reproducible.
5. **Umbral de calidad**: 0.10 por defecto, env configurable.
6. **Ventana temporal de `/alerts`**: 24h por defecto, env configurable,
   query param `since` la sobreescribe.
7. **Ventana del informe diario**: estricta del dia
   `[start_of_day_UTC, end_of_day_UTC]`. NO se reutiliza la ventana de
   `/alerts`. Ver RF-4.
8. **Idempotencia**: aplica al Markdown del script (RF-5, RNF-6, CA-11),
   no al JSON del endpoint `/reports/daily` (que lleva `generated_at`
   dinamico).

## Criterios de aceptacion

- [ ] **CA-1** (RF-1, US-1): `GET /api/v1/alerts` devuelve 200 con
  estructura `{items, total, generated_at}` en el dataset actual.
- [ ] **CA-2** (RF-2, US-1): Insertar un paciente con
  `triage.level=grave` reciente -> aparece como alerta
  `triage_severe`, `severity=critical`. Lo mismo con `pipeline_failed`
  y `data_quality_low`.
- [ ] **CA-3** (RF-3): Query param `severity=critical` filtra
  correctamente; `severity=invalid` -> 422.
- [ ] **CA-4** (RF-4): `GET /api/v1/reports/daily?date=YYYY-MM-DD`
  devuelve JSON con todas las secciones definidas en RF-4.
- [ ] **CA-5** (RF-5, US-2): `python -m src.automation.daily_report
  --date YYYY-MM-DD` crea `docs/reports/YYYY-MM-DD.md` con secciones
  presentes. Segunda ejecucion: mismo contenido.
- [ ] **CA-6** (RF-6, US-3): La vista "Alertas" del dashboard renderiza
  las alertas con colores; sin alertas, mensaje claro; API caida,
  banner de error.
- [ ] **CA-7** (RF-7): `api_client.get_alerts()` y `get_daily_report()`
  funcionan con `httpx.MockTransport` (tests unitarios).
- [ ] **CA-8** (RNF-3): No se anade ninguna tabla SQL nueva ni
  coleccion Mongo nueva. Verificable inspeccionando el diff: cero
  cambios en `src/pipeline/storage/sql_models.py` ni en
  `docker/mongo-init/init-db.js`.
- [ ] **CA-9** (RNF-4): Cero imports de `pymongo`, `minio`, `sqlite3`,
  `sqlalchemy` en `src/dashboard/`.
- [ ] **CA-10** (RNF-5): Tests unitarios de `evaluate(state)` pasan sin
  Mongo ni SQLite (funcion pura).
- [ ] **CA-11** (RNF-6): Ejecutar el script dos veces con la misma
  fecha produce **el Markdown byte-a-byte igual** (a igualdad de
  estado del sistema). Verificable con `hashlib.sha256` o `diff` del
  fichero entre ejecuciones. La idempotencia aplica **solo al
  Markdown**, NO al JSON del endpoint (cuyo `generated_at` puede
  variar entre llamadas).

## Asunciones

- El sistema es academico. La latencia del endpoint y el tamano del
  dataset estan controlados: el calculo on-demand es viable. En un
  hospital real con millones de eventos se replantearia hacia un
  sistema de eventos persistido (fuera de alcance).
- Las alertas son "vistas" del estado actual, no notificaciones
  push. Si el operador no abre el dashboard, no se entera. Esto
  encaja con el alcance ("entrada en el dashboard").
- Los umbrales por defecto son razonables para el dataset sintetico
  actual. Si se cambia el dataset, se ajustan via env var.

## Changelog

| Fecha | Cambio | Motivo | Fase |
|-------|--------|--------|------|
| 2026-05-20 | Creacion inicial (draft) | Cerrar Features 5 y 6 del backlog cumpliendo enunciado: alertas + informes operativos sin servicios externos | spec |
| 2026-05-20 | Aprobada + ajustes pre-implementacion | Revision con Alejandro: (a) RF-4 endpoint `/reports/daily` usa ventana estricta del dia `[00:00, 23:59:59.999]`, NO reutiliza las ultimas 24h desde ahora; (b) RF-5 + RNF-6 + CA-11 aclaran que la idempotencia byte-a-byte aplica solo al Markdown (sin `generated_at` en el render), no al JSON del endpoint; (c) RF-2 reformulada: `evaluate` es funcion pura que NO conoce el reloj, recibe listas ya filtradas; (d) CB-7b documenta que el Markdown del dia en curso no es estrictamente idempotente; (e) conexion con teoria del Master clarificada: reglas IF-THEN (Yuri Sesion 07) y FastAPI/SQLite/API (Eric Bloque 7) como referencias de clase, "separacion lectura/escritura" como patron interno del proyecto | spec |
