# Tasks: Almacenamiento SQL complementario para metadatos del pipeline

> Spec: specs/sqlite-pipeline-metadata.md
> Design: design/sqlite-pipeline-metadata.md

## Tareas

| # | Tarea | Requisitos | Dependencias | Tamaño | Estado |
|---|-------|-----------|-------------|--------|--------|
| T1 | Infraestructura SQL: `SqlEngine` (engine + sessionmaker + `create_all_tables` con WAL + check_same_thread=False) + modelos SQLAlchemy declarativos (`PipelineRunRow`, `DataQualitySummaryRow`) + anadir `sqlalchemy` a `requirements-pipeline.txt` + volumen named `pipeline-db` en docker-compose. Tests unitarios del engine | RF-1, RNF-1, RNF-4, CB-5 | — | M | done |
| T2 | `SqlWriter`: `start_pipeline_run` (genera UUID), `finish_pipeline_run`, `write_quality_summary`, `ping`, `close`, factory `get_sql_writer_from_env`. Tests unitarios | RF-2, RF-3 (reinterpretado), RF-6 | T1 | M | done |
| T3 | `QualitySummaryBuilder`: funcion pura `build(*, patients_total, patients_valid, patients_rejected, admissions_total, admissions_valid, admissions_rejected, admissions_orphans)`. Tests unitarios (incluido caso con orphans, caso `total=0` que no debe dar NaN) | RF-3 (reinterpretado), cobertura orphans | — | S | done |
| T4 | `MongoWriter` refactor: eliminar `start_pipeline_run` y `finish_pipeline_run`; `write_rejected` acepta `pipeline_run_id: str` en lugar de `ObjectId`. Adaptar tests unitarios existentes | RF-3 (reinterpretado) | — | S | done |
| T5 | `MongoReader` refactor: eliminar `list_pipeline_runs` y `latest_pipeline_run`. Adaptar tests | RF-4 | — | S | done |
| T6 | `docker/mongo-init/init-db.js`: anadir indice no-unico en `rejected_records.pipeline_run_id`; eliminar la creacion de la coleccion `pipeline_runs` y sus indices (ya no aplica) | RF-3 (reinterpretado) | — | S | done |
| T7 | `PipelineOrchestrator` refactor: constructor `__init__(spark, mongo_writer, sql_writer, ...)`; mover `start_pipeline_run` y `finish_pipeline_run` a `sql_writer`; `write_rejected` sigue contra `mongo_writer` (string run_id); tras success llama `QualitySummaryBuilder.build` + `sql_writer.write_quality_summary`. Tests unitarios actualizados (incluida persistencia del summary) | RF-2, RF-3 (reinterpretado), cobertura orphans | T1, T2, T3, T4 | M | done |
| T8 | `PipelineLauncher` refactor: crear `sql_writer` ademas del `mongo_writer`; inyectar ambos al orchestrator; `start_run` pasa por `sql_writer` (devuelve UUID). Tests | RF-2, RF-4 | T2, T7 | S | done |
| T9 | `bootstrap.py`: crear engine SQL al inicio + `create_all_tables`; instanciar `sql_writer` y pasarlo al orchestrator. Verificacion: `docker compose up` desde cero crea el schema y registra el run en SQLite | RF-1, RF-2, RF-5, RF-6, CB-1 | T1, T2, T7 | S | done |
| T10 | `watcher_daemon.py`: instanciar `sql_writer` y pasarlo al orchestrator. Verificacion: dropear CSVs y comprobar que el run aparece en SQLite con `trigger_type=watcher` | RF-2, RF-6 | T2, T7 | S | done |
| T11 | `SqlReader`: `list_pipeline_runs`, `latest_pipeline_run`, `count_pipeline_runs`, `latest_quality_summary`, `quality_summary_history`, `close`. Tests unitarios | RF-4 | T1 | M | done |
| T12 | API refactor: `src/api/main.py` instancia `sql_reader` en el lifespan; `routers/pipeline.py` lee de `sql_reader` para `/runs` y `/status`; nuevos endpoints `GET /pipeline/quality-summary` y `GET /pipeline/quality-summary/history`; actualizar modelo Pydantic `PipelineRun.id` (UUID string en vez de ObjectId); actualizar tests del router | RF-4 | T11 | M | done |
| T13 | Tests E2E actualizados: `test_acceptance_criteria.py` lee runs y rejected de los almacenes correctos; **nuevo test que verifica que orphans van a rejected_records (MongoDB) Y a data_quality_summary (SQLite) con conteos coherentes**; `test_watcher_integration.py` verifica el run en SQLite | RF-3 (reinterpretado), cobertura orphans, CA-1..CA-8 | T9, T10, T12 | M | done |
| T14 | Verificacion end-to-end con `docker compose down -v && docker compose up`: smoke test contra datos reales, comprobar que los numeros cuadran entre `rejected_records` (Mongo) y `data_quality_summary` (SQLite), inspeccionar el fichero `.db` con `docker exec ... sqlite3 ... ".tables"` y queries de agregacion | RF-5, CA-1..CA-8 | T13 | S | done |
| T15 | Documentacion viva: CHANGELOG (entrada en Changed sobre polyglot persistence), README (mencionar SQLite + endpoints quality-summary), diario IA (sesion nueva), lessons.md (lecciones del cambio). Actualizar `tasks/backlog.md` con estado de la feature | — | T14 | S | done |

Tamanos: S (< 1h) | M (1-4h) | L (> 4h, considerar dividir)
Estados: pending | in-progress | done | blocked

## Detalle por tarea

### T1: Infraestructura SQL base
- `src/pipeline/storage/sql_engine.py`:
  - `get_sql_engine_from_env() -> Engine` (lee `SQLITE_PATH` con default `/app/data/db/hospital.db`)
  - Configuracion: `connect_args={"check_same_thread": False}` + `PRAGMA journal_mode=WAL` (event listener `connect`)
  - `get_sql_session_factory(engine) -> sessionmaker`
  - `create_all_tables(engine)` idempotente
- `src/pipeline/storage/sql_models.py`:
  - `Base` declarativo
  - `PipelineRunRow` (id TEXT PK, trigger_type, started_at, finished_at nullable, status, records_processed, records_rejected, images_processed, error_message)
  - `DataQualitySummaryRow` (id INT PK autoincrement, pipeline_run_id TEXT FK, dimension, total, valid, rejected, rejection_rate, recorded_at)
  - Indices declarados en `__table_args__`
- `requirements-pipeline.txt`: anadir `sqlalchemy==2.0.x`
- `docker-compose.yml`:
  - `volumes:` anadir `pipeline-db:`
  - Volumen montado en los servicios (rw en pipeline+watcher, ro en api) — preparado pero la inicializacion real del fichero la hace T9
- Tests: `tests/pipeline/test_sql_engine.py` (creacion engine, WAL activo via `PRAGMA journal_mode` query, create_all idempotente)
- **Verificacion:** `docker compose build pipeline && docker compose run --rm --entrypoint "" pipeline pytest tests/pipeline/test_sql_engine.py`

### T2: SqlWriter
- `src/pipeline/storage/sql_writer.py`:
  - `class SqlWriter`: encapsula sesion, expone metodos
  - `start_pipeline_run(trigger_type) -> str`: genera `str(uuid.uuid4())`, INSERT, devuelve el UUID
  - `finish_pipeline_run(run_id, status, stats, error_message)`: UPDATE WHERE id=run_id
  - `write_quality_summary(run_id, summaries: list[dict])`: bulk INSERT con `recorded_at=now`
  - `ping() -> bool`: `SELECT 1`
  - `close()`: cierra session
  - `get_sql_writer_from_env() -> SqlWriter`
- Tests `tests/pipeline/test_sql_writer.py`:
  - `test_start_pipeline_run_returns_uuid_and_persists`
  - `test_finish_pipeline_run_updates_status_and_stats`
  - `test_finish_with_invalid_run_id_logs_warning_no_crash`
  - `test_write_quality_summary_persists_all_dimensions`
  - `test_write_quality_summary_respects_fk_to_run`
  - `test_ping_returns_true`

### T3: QualitySummaryBuilder
- `src/pipeline/processors/quality_summary.py`:
  - `build(*, patients_total, patients_valid, patients_rejected, admissions_total, admissions_valid, admissions_rejected, admissions_orphans) -> list[dict]`
  - Devuelve `[{dimension: "patients", total, valid, rejected, rejection_rate}, {dimension: "admissions", total, valid, rejected: rejected_total_incluyendo_orphans, rejection_rate}]`
  - Edge case: `total=0` → `rejection_rate=0.0` (no NaN)
- Tests `tests/pipeline/test_quality_summary.py`:
  - `test_build_with_clean_data` (rejected=0, rate=0)
  - `test_build_includes_orphans_in_admissions_rejected`
  - `test_build_with_total_zero_returns_zero_rate_not_nan`
  - `test_build_returns_one_entry_per_dimension`

### T4: MongoWriter refactor
- `src/pipeline/storage/mongo_writer.py`:
  - Eliminar metodos: `start_pipeline_run`, `finish_pipeline_run`
  - `write_rejected(records, pipeline_run_id: str)`: cambiar firma. El payload guardado conserva el campo `pipeline_run_id` pero ahora como string
- Tests `tests/pipeline/test_mongo_writer.py`:
  - Eliminar tests de start/finish
  - Actualizar `test_write_rejected_*` para usar `pipeline_run_id` como string

### T5: MongoReader refactor
- `src/api/mongo_reader.py`:
  - Eliminar `list_pipeline_runs`
  - Eliminar `latest_pipeline_run`
- Tests `tests/api/...`: limpiar los tests que ejerciten esos metodos (los nuevos para esa funcionalidad estan en T11/T12)

### T6: init-db.js de MongoDB
- `docker/mongo-init/init-db.js`:
  - Anadir `db.rejected_records.createIndex({pipeline_run_id: 1})` (no-unico)
  - Eliminar `db.createCollection('pipeline_runs')` y sus indices
- **Verificacion:** tras `docker compose down -v && up`, en mongosh: `db.rejected_records.getIndexes()` muestra el indice nuevo; `db.getCollectionNames()` no incluye `pipeline_runs`

### T7: PipelineOrchestrator refactor
- `src/pipeline/orchestrator.py`:
  - Constructor: anadir parametro `sql_writer: SqlWriter`
  - `run_from_files`:
    - `run_id` (str) viene de `sql_writer.start_pipeline_run()` o del parametro opcional
    - Tras `bulk_upsert_patients_with_admissions` y `write_rejected`, calcular stats por dimension y llamar a `QualitySummaryBuilder.build(...)` + `sql_writer.write_quality_summary(run_id, summary)`
    - `sql_writer.finish_pipeline_run(run_id, status, stats, error_message)` reemplaza la llamada anterior a `mongo_writer`
  - `_split_orphan_admissions` ya devuelve `(valid, orphans)`; usar `len(orphans)` para el builder
- Tests `tests/pipeline/test_pipeline_orchestrator.py`:
  - Fixtures actualizadas: dos writers
  - Mantener todos los tests anteriores (orphans, idempotencia, fallos)
  - Nuevo test: `test_orchestrator_persists_quality_summary_on_success`

### T8: PipelineLauncher refactor
- `src/api/pipeline_launcher.py`:
  - Crear `sql_writer` (factory desde env)
  - `start_run` pasa por `sql_writer`
  - `execute` pasa `sql_writer` al orchestrator
- Tests: actualizar `tests/api/test_pipeline_endpoints.py` para mockear el launcher con dos writers

### T9: bootstrap.py
- `src/pipeline/scripts/bootstrap.py`:
  - Al inicio: `engine = get_sql_engine_from_env(); create_all_tables(engine)`
  - Instanciar `sql_writer = get_sql_writer_from_env()`
  - Pasarlo al `PipelineOrchestrator` cuando ejecute el ETL inicial
  - Logging: anadir linea sobre el schema SQL creado
- **Verificacion:** `docker compose down -v && docker compose up -d`: el contenedor pipeline crea el fichero `/app/data/db/hospital.db` y lo deja con las tablas

### T10: watcher_daemon.py
- `src/pipeline/scripts/watcher_daemon.py`:
  - Instanciar `sql_writer = get_sql_writer_from_env()` ademas del mongo_writer existente
  - Pasarlo al `PipelineOrchestrator`
- **Verificacion:** dropear CSVs en `data/incoming/`, esperar al watcher, comprobar:
  - `sqlite3 .../hospital.db "SELECT * FROM pipeline_runs WHERE trigger_type='watcher'"`
  - `sqlite3 .../hospital.db "SELECT * FROM data_quality_summary WHERE pipeline_run_id=<id>"`

### T11: SqlReader
- `src/api/sql_reader.py`:
  - `list_pipeline_runs(limit, offset) -> list[dict]` (orden DESC por started_at)
  - `latest_pipeline_run() -> dict | None`
  - `count_pipeline_runs() -> int`
  - `latest_quality_summary() -> list[dict]` (todas las filas del ultimo run)
  - `quality_summary_history(dimension, limit, offset) -> list[dict]`
  - `close()`
  - `get_sql_reader_from_env() -> SqlReader`
- Tests `tests/api/test_sql_reader.py`: cobertura completa de los 5 metodos

### T12: API refactor + nuevos endpoints
- `src/api/main.py`:
  - En el lifespan, crear `sql_reader` ademas de `mongo_reader`
  - `app.state.sql_reader = sql_reader`
  - Cerrar `sql_reader` al shutdown
- `src/api/routers/pipeline.py`:
  - `list_runs` y `pipeline_status` leen de `app.state.sql_reader` en vez de `mongo_reader`
  - Nuevos endpoints:
    - `GET /api/v1/pipeline/quality-summary` → `sql_reader.latest_quality_summary()`
    - `GET /api/v1/pipeline/quality-summary/history?dimension=X&limit=N&offset=O` → `sql_reader.quality_summary_history(...)`
- `src/api/models.py`:
  - `PipelineRun.id`: cambiar tipo/validacion para UUID string (24→36 chars con guiones)
  - Nuevos modelos: `QualitySummaryItem`, `QualitySummaryResponse`, `QualitySummaryHistoryItem`, `QualitySummaryHistoryPage`
- Tests `tests/api/test_pipeline_endpoints.py`: actualizar fixture; tests nuevos de los endpoints quality-summary

### T13: Tests E2E
- `tests/e2e/test_acceptance_criteria.py`:
  - Adaptar tests que tocaban `mongo_db.pipeline_runs` a SQL (via API o conexion SQLite)
  - **NUEVO test** `test_orphans_appear_in_both_rejected_and_quality_summary`:
    - Verifica que tras el bootstrap hay >0 filas en `rejected_records` (Mongo) con `rejection_reason=orphan patient_external_id`
    - Verifica que la dimension `admissions` en `data_quality_summary` (SQL) tiene `rejected >= n_orphans`
    - Comprueba coherencia: el conteo total de rejected en summary cuadra con el conteo de rejected_records de Mongo
- `tests/e2e/test_watcher_integration.py`:
  - Tras el watcher procesar el batch, verificar que la fila aparece en `pipeline_runs` (SQL) con `trigger_type=watcher`
  - Verificar que `data_quality_summary` tiene filas para ese run

### T14: Verificacion end-to-end con datos reales
- `docker compose down -v && docker compose up`
- Esperar al bootstrap (`Bootstrap complete. System is ready.`)
- Smoke tests:
  - `curl /api/v1/pipeline/status` → run de bootstrap, status=success
  - `curl /api/v1/pipeline/quality-summary` → 2 dimensiones (patients, admissions)
  - `docker exec hospital-api sqlite3 /app/data/db/hospital.db ".tables"` → 2 tablas
  - `docker exec hospital-api sqlite3 /app/data/db/hospital.db "SELECT dimension, total, valid, rejected, rejection_rate FROM data_quality_summary ORDER BY recorded_at DESC LIMIT 2"`
- Cuadrar numeros: `rejected` para admissions en summary == rows en Mongo `rejected_records` con `source_file=admissions.csv`
- Reiniciar el stack sin `-v` y verificar persistencia (CA-6 del SQL)

### T15: Documentacion viva
- `CHANGELOG.md`: entrada en `Changed` describiendo polyglot persistence + breaking change del formato `_id`
- `README.md`: tabla de stack incluir SQLite + nuevos endpoints
- `docs/diario-ia.md`: sesion nueva al final con prompts, decisiones, aciertos, lecciones
- `tasks/lessons.md`: nuevas entradas (UUID vs ObjectId, polyglot persistence)
- `tasks/backlog.md`: feature 13 a `done`
- `tasks/sqlite-pipeline-metadata.md`: marcar todas las tareas como `done`

## Grafo de dependencias

```
T1 (infra SQL)──────┬──→ T2 (SqlWriter) ─────────┬──→ T7 (orchestrator) ──┬──→ T9 (bootstrap)──┐
                    │                              │                      │                    │
                    └──→ T11 (SqlReader) ──→ T12 (API) ──┐                ├──→ T10 (watcher)───┤
                                                          │                │                    │
T3 (quality builder) ────────────────────────────────────┴─→ ─────────────┘                    │
T4 (MongoWriter refactor) ──────────────────────────────────────────────────────────────────────┤
T5 (MongoReader refactor) ──────────────────────────────────────────────────────────────────────┤
T6 (init-db.js) ────────────────────────────────────────────────────────────────────────────────┤
T8 (PipelineLauncher) ──→ via T7+T2 ──────────────────────────────────────────────────────────  │
                                                                                                 │
                                                                                                 ▼
                                                                                            T13 (E2E)
                                                                                                 │
                                                                                                 ▼
                                                                                            T14 (smoke real)
                                                                                                 │
                                                                                                 ▼
                                                                                            T15 (docs)
```

## Ruta critica

T1 → T2 → T7 → T9 → T13 → T14 → T15

Paralelizable con la ruta critica:
- T3, T4, T5, T6 pueden hacerse en cualquier momento antes de T7
- T11 puede arrancarse en paralelo con T2 (ambos solo dependen de T1)
- T12 espera a T11
- T8 espera a T7 y T2 (cableado del launcher)
- T10 espera a T7 y T2 (cableado del watcher)
