# Design: Almacenamiento SQL complementario para metadatos del pipeline

> Spec: specs/sqlite-pipeline-metadata.md

## Decision arquitectonica

Se introduce **SQLite + SQLAlchemy** como almacen **complementario**
dedicado a:
- **`pipeline_runs`** (auditoria de ejecuciones)
- **`data_quality_summary`** (resumen agregado de calidad por run y
  dimension, base para dashboard e informes)

MongoDB **mantiene todo lo que ya tiene**: patients con admissions
embebidas, radiography metadata y `rejected_records` con `raw_data`
completo. MinIO mantiene los PNG. **SQLite no duplica nada de MongoDB**:
solo persiste datos que hoy no existen (los resumenes) o que son mas
naturales en SQL (los runs son tabla plana, perfecta para queries).

Reparto final de responsabilidades:

| Almacen | Tipo | Para que |
|---|---|---|
| **MongoDB** | NoSQL/documental | Datos clinicos jerarquicos: patients + admissions embebidas, radiography metadata, **rejected_records con `raw_data`** |
| **MinIO** | Object storage | Imagenes PNG |
| **SQLite + SQLAlchemy** | Relacional/tabular | Auditoria de runs + metricas agregadas para dashboard |

El enlace cross-DB es **soft**: `rejected_records` en MongoDB gana un
campo `pipeline_run_id` (string UUID que apunta a SQLite) y un indice
sobre ese campo. No hay integridad referencial cross-DB; SQLite es la
fuente de verdad de un run, MongoDB solo lo referencia.

**Los IDs en SQLite son UUID v4 propios de SQL** (`uuid.uuid4()` como
string TEXT). No se usa `bson.ObjectId` fuera de MongoDB. El campo que
devuelve la API cambia de tipo y de nombre: antes `_id` (alias Mongo,
ObjectId de 24 hex), ahora `id` (clave plana de SQLAlchemy, UUID v4 de
36 chars con guiones). Los modelos Pydantic, tests y documentacion se
actualizan en consecuencia.

## Cobertura explicita de admissions huerfanos

La cross-entity validation que detecta admissions cuyo
`patient_external_id` no existe entre los patients validos del batch
**sigue intacta** y se refuerza:

1. Los huerfanos siguen yendo a `rejected_records` en MongoDB con
   `rejection_reason = "orphan patient_external_id"` y `raw_data` completo
   (igual que hoy)
2. El nuevo `data_quality_summary` registra los huerfanos como parte de
   la dimension `admissions` (cuentan en `rejected`, no en `valid`)
3. Habra un test E2E que verifica que tras un run con huerfanos:
   - Aparecen filas en `rejected_records` (MongoDB) con motivo
     "orphan patient_external_id"
   - Aparece una fila en `data_quality_summary` (SQLite) para la
     dimension `admissions` con `rejected > 0` que incluye los huerfanos

El cambio de SQL **no oculta** el bug ni cambia su tratamiento: ambos
almacenes reflejan los huerfanos.

## Trazabilidad spec → componentes

| Requisito | Componente(s) | Archivos |
|-----------|--------------|----------|
| RF-1 (schema auto-creado) | `create_all_tables()` invocado en bootstrap | `src/pipeline/storage/sql_engine.py`, `src/pipeline/scripts/bootstrap.py` |
| RF-2 (orchestrator usa SQL para runs) | `SqlWriter` reemplaza los metodos de runs en orchestrator | `src/pipeline/storage/sql_writer.py`, `src/pipeline/orchestrator.py` |
| RF-3 (reinterpretado: rejected en Mongo + summary en SQL) | `rejected_records` sigue en Mongo con FK soft; nueva `data_quality_summary` en SQL para los agregados de calidad | `src/pipeline/storage/mongo_writer.py` (cambio menor), `src/pipeline/storage/sql_writer.py` |
| RF-4 (API transparente para `/pipeline/runs` + `/status`) | `SqlReader` con mismos contratos de lectura | `src/api/sql_reader.py`, `src/api/routers/pipeline.py` |
| RF-5 (persistencia entre reinicios) | Volumen Docker named `pipeline-db` | `docker-compose.yml` |
| RF-6 (watcher con SQL) | `watcher_daemon` usa `SqlWriter` via orchestrator | `src/pipeline/scripts/watcher_daemon.py` |
| RNF-1 (SQLAlchemy + SQLite, alineado con clase) | Toda la capa SQL | `src/pipeline/storage/sql_*` |
| RNF-4 (sin servicio Docker nuevo) | Embedded en los contenedores existentes | `docker-compose.yml` |
| CB-1..CB-5 | `SqlEngine` con WAL + manejo de errores explicito | `src/pipeline/storage/sql_engine.py`, `src/pipeline/storage/sql_writer.py` |
| Cobertura orphans | Test E2E que verifica rejected_records (Mongo) + data_quality_summary (SQL) | `tests/e2e/test_acceptance_criteria.py` |

> **Sobre la reinterpretacion de RF-3**: la spec original decia "rechazados
> en SQL con FK a pipeline_runs". Tras el design se mantiene
> `rejected_records` en MongoDB (donde `raw_data` JSON heterogeneo encaja
> mejor) y se anade `data_quality_summary` en SQL para los agregados.
> El enlace conceptual (que era "FK") pasa a ser una soft reference por
> string UUID + indice en MongoDB. Cambio reflejado en el changelog de
> la spec.

## Componentes

### SqlEngine (nuevo)
- **Responsabilidad:** crear el engine SQLAlchemy con configuracion
  correcta para SQLite multi-thread (watcher) y multi-proceso.
  Aplica `PRAGMA journal_mode=WAL` para concurrencia.
- **Requisitos que cubre:** RNF-1, CB-5
- **Archivos:** `src/pipeline/storage/sql_engine.py`
- **API publica:**
  - `get_sql_engine_from_env() -> Engine`
  - `get_sql_session_factory(engine) -> sessionmaker`
  - `create_all_tables(engine) -> None`

### Modelos SQLAlchemy (nuevo)
- **Responsabilidad:** definir las tablas como clases declarativas.
- **Requisitos que cubre:** RF-1
- **Archivos:** `src/pipeline/storage/sql_models.py`
- **Clases:** `Base`, `PipelineRunRow`, `DataQualitySummaryRow`

### SqlWriter (nuevo)
- **Responsabilidad:** operaciones de escritura sobre SQLite. Reemplaza
  `start_pipeline_run` y `finish_pipeline_run` que estaban en
  `MongoWriter`. Anade `write_quality_summary`.
- **Requisitos que cubre:** RF-2, RF-3 (reinterpretado), RF-6
- **Archivos:** `src/pipeline/storage/sql_writer.py`
- **API publica:**
  - `start_pipeline_run(trigger_type: str) -> str` (genera UUID y devuelve)
  - `finish_pipeline_run(run_id: str, status, stats, error_message)`
  - `write_quality_summary(run_id: str, summaries: list[dict])`
  - `ping() -> bool`
  - `close()`
- **Factory:** `get_sql_writer_from_env() -> SqlWriter`

### SqlReader (nuevo)
- **Responsabilidad:** lectura para la API.
- **Requisitos que cubre:** RF-4
- **Archivos:** `src/api/sql_reader.py`
- **API publica:**
  - `list_pipeline_runs(limit, offset) -> list[dict]`
  - `latest_pipeline_run() -> dict | None`
  - `count_pipeline_runs() -> int`
  - `latest_quality_summary() -> list[dict]` (ultimas filas agrupadas por
    el ultimo run)
  - `quality_summary_history(dimension, limit, offset) -> list[dict]`
  - `close()`

### QualitySummaryBuilder (nuevo)
- **Responsabilidad:** transformar los conteos del orchestrator (validos
  por dimension, rechazados por dimension, huerfanos) en la lista de
  dicts lista para persistir en `data_quality_summary`.
- **Archivos:** `src/pipeline/processors/quality_summary.py`
- **API publica:**
  - `build(*, patients_total, patients_valid, patients_rejected,
    admissions_total, admissions_valid, admissions_rejected,
    admissions_orphans) -> list[dict]`
- **Devuelve:** lista de dicts, uno por dimension, con campos
  `{dimension, total, valid, rejected, rejection_rate}`. La dimension
  `admissions` incluye los orphans en `rejected` (no son una dimension
  separada).

### MongoWriter (cambios MINIMOS)
- **Responsabilidad:** sin cambios funcionales sobre patients, admissions
  y rejected_records. Pierde los metodos de runs y cambia el tipo de
  `pipeline_run_id` en `write_rejected`.
- **Archivos:** `src/pipeline/storage/mongo_writer.py`
- **Cambios concretos:**
  - Eliminar `start_pipeline_run()` y `finish_pipeline_run()`
  - `write_rejected(records, pipeline_run_id: str)` — tipo del id pasa
    de `ObjectId` a `str` (UUID string que viene de SQLite). El payload
    persistido es identico
  - `add_radiography_to_patient`, `bulk_upsert_patients_with_admissions`,
    `ping`: **sin cambios**

### Indice nuevo en MongoDB
- En `docker/mongo-init/init-db.js`:
  - Crear indice no-unico en `rejected_records.pipeline_run_id` para
    consultas eficientes "todos los rechazos de un run"

### MongoReader (cambios)
- **Archivos:** `src/api/mongo_reader.py`
- **Cambios:**
  - Eliminar `list_pipeline_runs()`
  - Eliminar `latest_pipeline_run()`
  - El resto (patients, admissions, radiographies): sin cambios

### PipelineOrchestrator (modificado)
- **Responsabilidad:** coordina el ETL. Recibe ahora **ambos writers**.
- **Archivos:** `src/pipeline/orchestrator.py`
- **Cambios:**
  - Constructor: `__init__(spark, mongo_writer, sql_writer, ...)`
  - `start_pipeline_run` / `finish_pipeline_run` van contra `sql_writer`
  - `write_rejected` sigue contra `mongo_writer` (con `pipeline_run_id`
    como string)
  - Tras la persistencia de patients y rejected, calcula stats por
    dimension y llama
    `quality_summary.build(...)` → `sql_writer.write_quality_summary(...)`
  - El log final del run incluye las filas de quality_summary persistidas

### PipelineLauncher (modificado)
- **Archivos:** `src/api/pipeline_launcher.py`
- **Cambios:** crea `sql_writer` ademas del `mongo_writer`. `start_run`
  pasa por `sql_writer` (devuelve UUID string).

### Bootstrap / Watcher daemon (modificados)
- **Archivos:** `src/pipeline/scripts/bootstrap.py`,
  `src/pipeline/scripts/watcher_daemon.py`
- **Cambios:**
  - `bootstrap.py`: al inicio, crea el engine SQL y llama
    `create_all_tables(engine)`. Luego instancia `sql_writer` para
    pasarlo al orchestrator
  - `watcher_daemon.py`: instancia `sql_writer` ademas del `mongo_writer`

### API — nuevos endpoints y cambio del identificador del run

**Endpoints existentes con cambio interno (mismo contrato del cliente excepto formato del identificador):**
- `GET /api/v1/pipeline/runs` — ahora lee de SQLite
- `GET /api/v1/pipeline/status` — ahora lee de SQLite
- `POST /api/v1/pipeline/trigger` — `start_run` en SQLite, devuelve UUID

**Endpoints nuevos para el dashboard:**
- `GET /api/v1/pipeline/quality-summary` — ultimo resumen agrupado por dimension
- `GET /api/v1/pipeline/quality-summary/history?dimension=patients&limit=30` —
  serie temporal paginada con `total` real (count por dimension)

**Cambio del identificador del run en respuestas:**
- Antes: campo `_id`, valor `ObjectId` de 24 chars hex (alias del `_id`
  de MongoDB)
- Despues: campo `id`, valor UUID v4 de 36 chars con guiones
  (ej. `"550e8400-e29b-41d4-a716-446655440000"`). El nombre se simplifica
  porque ya no estamos delante de un documento Mongo — la fuente es
  SQLAlchemy y `id` es el nombre natural del PK
- Afecta a `PipelineRun` (Pydantic), `PipelineTriggerResponse.run_id`,
  tests E2E y unit que verifican el formato, documentacion (README,
  CHANGELOG)

## Modelo de datos

### SQLite — Tablas (2)

```
pipeline_runs
├── id                  TEXT PRIMARY KEY      -- UUID v4 (uuid.uuid4() str)
├── trigger_type        TEXT NOT NULL         -- 'manual' | 'bootstrap' | 'watcher'
├── started_at          DATETIME NOT NULL
├── finished_at         DATETIME              -- nullable mientras status='running'
├── status              TEXT NOT NULL         -- 'running' | 'success' | 'failed'
├── records_processed   INTEGER NOT NULL DEFAULT 0
├── records_rejected    INTEGER NOT NULL DEFAULT 0
├── images_processed    INTEGER NOT NULL DEFAULT 0
└── error_message       TEXT

Indices:
  ix_pipeline_runs_started_at    (started_at DESC)


data_quality_summary
├── id                  INTEGER PRIMARY KEY AUTOINCREMENT
├── pipeline_run_id     TEXT NOT NULL         -- FK -> pipeline_runs.id
├── dimension           TEXT NOT NULL         -- 'patients' | 'admissions' (extensible)
├── total               INTEGER NOT NULL
├── valid               INTEGER NOT NULL
├── rejected            INTEGER NOT NULL      -- incluye orphans en la dimension admissions
├── rejection_rate      REAL NOT NULL         -- rejected / total (0..1, NaN si total=0)
├── recorded_at         DATETIME NOT NULL
└── FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_runs(id)

Indices:
  ix_dq_summary_run_id     (pipeline_run_id)
  ix_dq_summary_dimension  (dimension, recorded_at DESC)
```

### MongoDB — Sin cambios estructurales mayores

```
patients (sin cambio)

rejected_records  -- cambio MENOR: tipo de pipeline_run_id
├── _id                ObjectId
├── pipeline_run_id    String  -- ANTES ObjectId; AHORA string UUID de SQLite
├── source_file        String
├── rejection_reason   String
├── raw_data           Object  -- JSON heterogeneo
└── created_at         ISODate

Indices nuevos:
  ix_rejected_records_pipeline_run_id    (pipeline_run_id)  -- NUEVO
```

La coleccion `pipeline_runs` que existe hoy en MongoDB **se elimina**
(su responsabilidad va a SQLite). Si quedan datos antiguos de pruebas,
no se migran: el sistema arranca limpio.

### MinIO — Sin cambios

## Contratos de datos

### Datos de entrada (a SQL)

| Operacion | Que recibe | Validaciones | Comportamiento en fallo |
|-----------|-----------|-------------|-------------------------|
| `SqlWriter.start_pipeline_run(trigger_type)` | trigger_type string | `trigger_type in {manual, bootstrap, watcher}` | Excepcion propagada |
| `SqlWriter.finish_pipeline_run(run_id, status, stats)` | UUID existente | UPDATE WHERE id=run_id; si no existe → log warning + 0 filas |
| `SqlWriter.write_quality_summary(run_id, summaries)` | UUID + list[dict] | FK valida; cada dict requiere `dimension`, `total`, `valid`, `rejected`, `rejection_rate` |

### Datos de salida (de la API)

| Endpoint | Formato del response | Cambio |
|---|---|---|
| `GET /pipeline/runs` | `{"total": N, "limit": L, "offset": O, "items": [{"id": "uuid", "trigger_type": "...", "status": "...", ...}]}` | Campo `_id` (ObjectId) → `id` (UUID v4 string) |
| `GET /pipeline/status` | `{"id": "uuid", "status": "success", ...}` | Mismo cambio de campo/tipo |
| `POST /pipeline/trigger` | `{"run_id": "uuid", "status": "accepted", "message": "..."}` | `run_id` ahora es UUID v4 string |
| `GET /pipeline/quality-summary` | `{"items": [{"dimension": "patients", "total": N, "valid": V, "rejected": R, "rejection_rate": 0.05, "pipeline_run_id": "uuid", "recorded_at": "..."}, {"dimension": "admissions", ...}]}` | NUEVO |
| `GET /pipeline/quality-summary/history?dimension=patients&limit=30` | `{"dimension": "patients", "total": N_total_para_dimension, "limit": L, "offset": O, "items": [...]}`. `total` cuenta TODAS las filas para la dimension, no `len(items)` | NUEVO |

### Glosario

| Termino | Definicion | NO significa |
|---------|-----------|--------------|
| `run_id` | Identificador unico de una ejecucion, UUID v4 string | No es `bson.ObjectId` |
| `dimension` (en quality_summary) | Tipo de entidad evaluada: `patients`, `admissions` | No es columna del CSV |
| `rejection_rate` | `rejected / total` en el rango `[0, 1]` | No es porcentaje 0..100 |
| Soft reference cross-DB | String que apunta a otra BBDD sin integridad referencial constraint | No tiene FK enforcement; es responsabilidad del codigo |
| Polyglot persistence | Patron de varios tipos de BBDD complementarios | No es duplicacion |

## Flujo del run (post-cambio)

```
1. TRIGGER (bootstrap / watcher / POST /trigger)
       │
2. SqlWriter.start_pipeline_run(trigger_type) → INSERT en SQLite, devuelve UUID
       │
3. PipelineOrchestrator ejecuta:
   ├── Lee CSVs (PySpark)
   ├── Valida (DataValidator)
   ├── Limpia (DataCleaner)
   ├── Transforma (DataTransformer)
   ├── Cross-entity validation (orphan admissions) ← bug fix CONSERVADO
   ├── MongoWriter.bulk_upsert_patients_with_admissions()    → MongoDB
   └── MongoWriter.write_rejected(rejected, run_id_str)       → MongoDB (run_id string)
       │
4. QualitySummaryBuilder.build(patients_stats, admissions_stats, orphans)
   → list[{dimension, total, valid, rejected, rejection_rate}]
       │
5. SqlWriter.write_quality_summary(run_id, summary)   → INSERT en SQLite
       │
6. SqlWriter.finish_pipeline_run(run_id, status, stats) → UPDATE en SQLite
```

## Servicios Docker

| Servicio | Acceso a SQLite | Cambio |
|----------|-----------------|--------|
| mongodb | NO | sin cambios estructurales — solo nuevo indice en init-db.js |
| minio | NO | sin cambios |
| minio-init | NO | sin cambios |
| **pipeline** (bootstrap) | rw — crea schema + inserta primer run + summary | volumen `pipeline-db` montado en `/app/data/db` |
| **watcher** | rw — escribe runs/summaries nuevos | volumen `pipeline-db` montado |
| **api** | ro — solo lectura | volumen `pipeline-db` montado |

Volumen named: `pipeline-db`.

### Inicializacion del schema

- `bootstrap.py` llama `create_all_tables(engine)` al inicio
- Es idempotente: `CREATE TABLE IF NOT EXISTS`
- Los servicios `api` y `watcher` arrancan despues del bootstrap
  (`depends_on: service_completed_successfully`), asi que cuando abren
  el engine el schema ya existe

## Trade-offs

| Decision | Alternativa descartada | Razon |
|----------|----------------------|-------|
| `rejected_records` se QUEDA en MongoDB | Moverlo a SQLite | `raw_data` heterogeneo encaja mejor en documental; mover dividiria el modelo de "fallos del pipeline" entre dos almacenes sin ganancia |
| Anadir `data_quality_summary` en SQLite | Calcular agregados on-the-fly al consultar | Pre-agregar permite queries instantaneas en el dashboard. Es caching legitimo, no duplicacion |
| UUID v4 como PK en SQLite | `bson.ObjectId` o INT autoincrement | UUID es el estandar para PKs string en SQL. Aliñacion con principio "SQLite no depende conceptualmente de BSON". El cambio de nombre del campo (`_id` Mongo → `id` SQL) y de formato (ObjectId → UUID) se asume |
| Solo 2 tablas (runs + quality_summary) | 3 tablas (anadir `pipeline_metrics` clave-valor) | KISS. Si en el futuro hace falta un metric-name-value libre, se anade |
| Dashboard consume API | Dashboard abre SQLite directo | Separation of concerns: SQLite es detalle de implementacion. La API es el contrato estable |
| Soft reference `pipeline_run_id: string` en Mongo + indice | FK real cross-DB | No existen FKs cross-DB. Indice mitiga el coste de las queries de "rejected por run" |
| SQLite embedded | PostgreSQL como servicio | Lo enseña Eric en Bloque 7; cero overhead Docker |
| SQLAlchemy ORM declarativo | SQL raw via `sqlite3` | Idem temario |
| `PRAGMA journal_mode=WAL` | Default rollback journal | Lecturas concurrentes con escritura |
| `check_same_thread=False` | Default True | Watcher tiene threads de watchdog observer |
| Schema init en bootstrap | Init en cada engine factory | Un solo sitio responsable, evita race conditions |
| Named volume `pipeline-db` | Bind mount al host | Mas limpio; inspeccionable con `docker exec ... sqlite3` |
| Eliminar metodos viejos de `MongoWriter` | Mantenerlos por compat | Sin produccion antigua, evita deuda |

## Plan de tests (resumen — detalle en /tareas)

| Nivel | Archivo | Que valida |
|-------|---------|------------|
| Unit | `tests/pipeline/test_sql_engine.py` (nuevo) | engine se crea, WAL activo, create_all idempotente |
| Unit | `tests/pipeline/test_sql_writer.py` (nuevo) | start/finish run, write_quality_summary, ping |
| Unit | `tests/pipeline/test_quality_summary.py` (nuevo) | builder genera summary correcto, incluyendo orphans en `admissions.rejected` |
| Unit | `tests/api/test_sql_reader.py` (nuevo) | list runs, latest, count, quality summary |
| Unit | `tests/pipeline/test_pipeline_orchestrator.py` (modificado) | orchestrator inyectado con dos writers; persiste summary tras finish |
| Unit | `tests/api/test_pipeline_endpoints.py` (modificado) | nuevos endpoints quality-summary; fixture usa SqlReader |
| Unit | `tests/pipeline/test_mongo_writer.py` (modificado) | `write_rejected` acepta `run_id` como string |
| E2E | `tests/e2e/test_acceptance_criteria.py` (modificado) | runs en SQLite; rejected en Mongo con string id; **orphans en rejected_records Y en data_quality_summary** |
| E2E | `tests/e2e/test_watcher_integration.py` (modificado) | el run del watcher aparece en SQLite |

## Riesgos identificados

1. **Soft reference Mongo→SQLite puede quedar huerfana** si se borra un
   run de SQLite. Mitigacion: por contrato no borramos runs (auditoria
   append-only). Documentar la regla.

2. **`data_quality_summary` crece linealmente con los runs**. Para 1 run
   por dia con 2 dimensiones son ~730 filas/año. Trivial. Documentado
   como limitacion.

3. **Concurrencia bootstrap vs watcher** (CB-5): el bootstrap termina
   antes de que el watcher arranque (`depends_on:
   service_completed_successfully`). SQLite con WAL permite varias
   lecturas + una escritura sin bloqueo apreciable.

4. **Breaking change del identificador del run en el API**: campo `_id`
   (ObjectId, 24 hex) → `id` (UUID v4, 36 chars con guiones). Como no
   hay clientes externos, asumido. Se anota en CHANGELOG. Tests, modelos
   Pydantic y documentacion se actualizan en las tareas.

5. **Tapar el bug de orphan admissions**: explicitamente NO. El test E2E
   verifica que orphans van a rejected_records (Mongo) Y al
   data_quality_summary (SQL) con conteos coherentes.

## Cambios en la spec a registrar en su changelog

- **RF-3 reinterpretado:** `rejected_records` SIGUE en MongoDB con su
  `raw_data` JSON. El concepto de "agregados de calidad consultables en
  SQL" se cubre con la nueva tabla `data_quality_summary` (no con la
  tabla `rejected_records` en SQL como decia el draft inicial). La FK
  conceptual a `pipeline_runs` la mantiene `data_quality_summary`; los
  `rejected_records` de Mongo tienen una soft reference (string).
- Motivo: "alineacion con principio polyglot persistence — `raw_data`
  heterogeneo es mas natural en documental; agregados tabulares son mas
  naturales en SQL".
