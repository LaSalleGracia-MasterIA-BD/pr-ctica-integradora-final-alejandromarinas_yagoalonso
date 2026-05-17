# Spec: Almacenamiento SQL para metadatos del pipeline

> Estado: approved
> Ultima actualizacion: 2026-05-16

## Contexto y problema

El enunciado del proyecto pide "uso combinado de al menos dos tipos de
almacenamiento". El ejemplo del propio enunciado contempla un almacen
**estructurado** (SQL) + un almacen para **datos no estructurados** (MinIO
o MongoDB). Hoy el proyecto cumple "dos tipos" con MongoDB + MinIO, pero
la lectura estricta del enunciado y la asignatura de Big Data (Eric,
Bloque 7) presentan SQL como el almacen natural para datos
estructurados/transaccionales. Sin ese tercer tipo, una interpretacion
literal del evaluador puede argumentar que falta SQL.

Ademas, los **metadatos del pipeline** (cuando se ha ejecutado, con que
trigger, cuantos records procesados/rechazados, metricas de calidad por
dimension) son **tabulares planos** con esquema fijo, FK natural entre
ellos y casos de uso analiticos tipicos (agregaciones, joins, history
queries para el dashboard). Encajan mejor en un modelo relacional que
en una coleccion de documentos.

## Objetivo

Anadir un almacen SQL persistente al sistema para guardar los **metadatos
operativos del pipeline** (auditoria de ejecuciones + agregados de calidad
de datos), **complementando** sin desplazar la arquitectura existente:

- **MongoDB** sigue siendo dueno de los datos clinicos: `patients` (con
  `admissions` y `radiographies` embebidos) y `rejected_records` (con
  `raw_data` heterogeneo)
- **MinIO** sigue siendo dueno de los binarios (PNG de radiografias)
- **SQLite** estrena dos tablas: `pipeline_runs` (auditoria) y
  `data_quality_summary` (metricas agregadas para el dashboard)

El resultado es una arquitectura de **polyglot persistence** donde cada
tipo de dato vive en el almacen que mejor encaja con su forma y sus
patrones de acceso, sin duplicacion de fuente de verdad.

## Actores y alcance

- **Usuarios:**
  - Componentes internos: `PipelineOrchestrator`, `PipelineLauncher`,
    `bootstrap.py`, `watcher_daemon.py` (escriben metadatos)
  - API REST (lee metadatos para servir `/pipeline/runs`,
    `/pipeline/status`, `/pipeline/quality-summary`,
    `/pipeline/quality-summary/history`)
  - Evaluador del proyecto (consume la API y/o consulta los almacenes)

- **Dentro del alcance:**
  - Tabla SQL `pipeline_runs` (run_id UUID, trigger_type, started_at,
    finished_at, status, counts, error_message)
  - Tabla SQL `data_quality_summary` (FK a `pipeline_runs`, dimension,
    total, valid, rejected, rejection_rate, recorded_at)
  - Adaptacion de `PipelineOrchestrator` para que el ciclo de vida del
    run y los agregados de calidad vivan en SQL
  - Indice nuevo en `rejected_records.pipeline_run_id` (Mongo) para
    consultas por run cuando se quiere ir del summary a los rechazos
    crudos
  - Nuevos endpoints `GET /pipeline/quality-summary` y
    `GET /pipeline/quality-summary/history?dimension=...`
  - Cambio del formato de `id` en la respuesta de `/pipeline/runs` y
    `/pipeline/status`: pasa de hex ObjectId (24 chars) a UUID v4 string
    (36 chars)
  - Persistencia del fichero SQL en volumen Docker `pipeline-db`
  - Inicializacion automatica del schema al arrancar el sistema

- **Fuera del alcance:**
  - Mover `rejected_records` a SQL: se quedan en MongoDB porque
    `raw_data` es heterogeneo (cada motivo de rechazo lleva un payload
    distinto) y encaja en documental
  - Migrar `patients`, `admissions`, `radiographies` a SQL (siguen en
    MongoDB / MinIO)
  - Autenticacion/autorizacion para la BBDD SQL
  - Migraciones formales tipo Alembic (el schema es estatico, se crea
    con `Base.metadata.create_all`)

## Requisitos funcionales

- **RF-1:** Al arrancar el sistema, el schema SQL debe crearse
  automaticamente si no existe (tablas `pipeline_runs` y
  `data_quality_summary` con sus indices). Idempotente
- **RF-2:** `PipelineOrchestrator.run_from_files()` debe abrir un
  registro en `pipeline_runs` al iniciar (status=running) y cerrarlo al
  terminar (status=success/failed, con stats agregadas), persistido en
  SQLite — no en MongoDB
- **RF-3:** Tras una ejecucion exitosa del pipeline, el orchestrator
  debe persistir en `data_quality_summary` **una fila por dimension**
  (`patients`, `admissions`) con `total`, `valid`, `rejected` y
  `rejection_rate`. Las admissions **huerfanas** detectadas en
  cross-entity validation deben quedar reflejadas como rechazos en la
  dimension `admissions` del summary (NO se "evaporan")
- **RF-4:** Los endpoints HTTP deben:
  - `GET /api/v1/pipeline/runs` y `GET /api/v1/pipeline/status` leer
    de SQLite via `SqlReader`
  - `GET /api/v1/pipeline/quality-summary` devolver el snapshot mas
    reciente (una fila por dimension)
  - `GET /api/v1/pipeline/quality-summary/history?dimension=X` devolver
    el historico para una dimension con paginacion y `total` real
  - `POST /api/v1/pipeline/trigger` seguir disparando el ETL, ahora
    devolviendo `run_id` como UUID v4 string
- **RF-5:** El fichero SQL debe vivir en un volumen Docker named
  (`pipeline-db`) para sobrevivir a reinicios de contenedores. Solo
  `docker compose down -v` debe borrarlo
- **RF-6:** El bootstrap y el watcher deben usar el writer SQL para
  registrar sus runs (`trigger_type=bootstrap` / `trigger_type=watcher`)
  y persistir el summary de calidad de cada ejecucion

## Requisitos no funcionales

- **RNF-1:** La tecnologia SQL elegida debe coincidir con lo enseñado en
  el temario del Master (Eric, Bloque 7 — usa SQLAlchemy + SQLite)
- **RNF-2:** Tras la migracion, el tiempo de bootstrap end-to-end
  (`docker compose up` con BBDD vacia → sistema listo) debe seguir siendo
  menor de 60 segundos en una maquina de desarrollo media
- **RNF-3:** Los tests E2E existentes (CA-1..CA-8 del pipeline original)
  deben seguir pasando, adaptados al cambio de fuente de datos (runs
  ahora se leen de SQL, no de Mongo)
- **RNF-4:** No se anaden servicios Docker nuevos al compose por culpa
  de esta feature: la BBDD SQL es embedded, compartida via volumen named
  entre `pipeline`, `api` y `watcher`

## Casos borde y errores

- **CB-1:** El fichero SQL no existe en el arranque (primer `up`) → debe
  crearse automaticamente con su schema inicial
- **CB-2:** El fichero SQL existe pero con schema antiguo (incompatible)
  → arrancar debe fallar con un mensaje claro, no corromper datos
- **CB-3:** Se elimina o corrompe el fichero SQL en caliente → el
  siguiente acceso debe fallar con error explicito (no fallo silencioso)
- **CB-4:** El volumen donde vive el fichero SQL es de solo lectura → el
  contenedor que necesita escribir (o cualquier contenedor con SQLite en
  modo WAL, que crea sidecars `.wal`/`.shm`) debe fallar al arrancar con
  mensaje claro
- **CB-5:** Conflicto de concurrencia entre dos procesos escribiendo a la
  vez (ej. orchestrator del bootstrap y watcher detectando un batch
  simultaneamente) → SQLite en modo WAL debe gestionarlo, no deben
  perderse runs

## Dudas abiertas

- ~~¿Que motor SQL exactamente?~~ **RESUELTO:** **SQLite** porque se
  ensena en clase (Eric, Bloque 7), no requiere servicio Docker extra
  (es un fichero embedded) y es suficiente para el volumen del proyecto.
  PostgreSQL solo se menciona en el temario como referencia de
  produccion, no se ensena en ningun ejercicio
- ~~¿`rejected_records` se mueve a SQL?~~ **RESUELTO:** No. El
  `raw_data` de cada rechazo es heterogeneo (depende del motivo) y
  encaja en documental. Se queda en MongoDB con un indice nuevo sobre
  `pipeline_run_id` para joins logicos rapidos contra SQL
- ~~¿Tipo del PK en SQLite?~~ **RESUELTO:** UUID v4 string (`uuid.uuid4()`).
  No se usa `bson.ObjectId` para no acoplar SQL al concepto de BSON.
  La referencia cruzada `rejected_records.pipeline_run_id` en MongoDB se
  guarda tambien como string UUID
- ~~¿Donde vive el fichero `.db`?~~ **RESUELTO:** `/app/data/db/hospital.db`
  dentro del contenedor, montado como volumen Docker named `pipeline-db`
  para persistencia, compartido entre `pipeline`, `api` y `watcher`. Se
  monta `rw` en los tres servicios (incluida la API) porque WAL crea
  sidecars `.wal` y `.shm` en el mismo directorio
- ~~¿Mantenemos los metodos viejos de `MongoWriter`?~~ **RESUELTO:** Se
  eliminan `start_pipeline_run`, `finish_pipeline_run` (movidos a
  `SqlWriter`) y se cambia la firma de `write_rejected` para aceptar
  `pipeline_run_id` como string UUID en lugar de `ObjectId`. Sin periodo
  de compatibilidad

## Criterios de aceptacion

- [ ] **CA-1** (RF-1, CB-1): Al arrancar `docker compose up` desde cero
  (con volumen SQL limpio), el sistema crea automaticamente el schema y
  las tablas `pipeline_runs` y `data_quality_summary` quedan accesibles
  para writes y reads
- [ ] **CA-2** (RF-2, RF-6): Tras el bootstrap automatico, hay
  exactamente un registro en `pipeline_runs` con `trigger_type=bootstrap`
  y `status=success`, con `records_processed` y `records_rejected`
  reflejando lo realmente persistido
- [ ] **CA-3** (RF-3): Tras el bootstrap, `data_quality_summary` contiene
  una fila por dimension (`patients`, `admissions`) con conteos
  coherentes. La dimension `admissions.rejected` incluye los huerfanos
  detectados en cross-entity validation. **Cross-check Mongo↔SQL:** el
  numero de huerfanos en `rejected_records` (Mongo) para un `pipeline_run_id`
  concreto es <= `admissions.rejected` del summary para ese mismo run
- [ ] **CA-4** (RF-4): `GET /api/v1/pipeline/runs` devuelve los runs
  ordenados por `started_at` descendente con paginacion (`total`, `limit`,
  `offset`, `items`). `id` es un UUID v4 string (36 chars)
- [ ] **CA-5** (RF-4): `GET /api/v1/pipeline/status` devuelve el run mas
  reciente con todos los campos (`id`, `trigger_type`, `status`, timestamps,
  counts, `error_message`)
- [ ] **CA-6** (RF-4): `GET /api/v1/pipeline/quality-summary` devuelve la
  ultima snapshot (una fila por dimension del run mas reciente que tenga
  summary). `GET /api/v1/pipeline/quality-summary/history?dimension=X`
  devuelve la historia paginada para esa dimension, con `total` que
  refleja el numero **real** de filas en la base para esa dimension
  (no `len(items)` de la pagina)
- [ ] **CA-7** (RF-5): Tras `docker compose stop && docker compose start`
  (sin `-v`), los runs y los summaries registrados antes siguen
  disponibles via API. Tras `docker compose down -v`, todo se borra
  (volumen `pipeline-db` incluido)
- [ ] **CA-8** (RF-6): Cuando el watcher procesa un batch, el run queda
  registrado en SQL con `trigger_type=watcher` y `data_quality_summary`
  tiene filas asociadas a ese run

## Changelog

| Fecha | Cambio | Motivo | Fase |
|-------|--------|--------|------|
| 2026-05-16 | Creacion inicial | Cubrir lectura estricta del enunciado y alinear con Bloque 7 de Eric (SQLAlchemy + SQLite) | spec |
| 2026-05-16 | Dudas cerradas, spec aprobada | Volumen `pipeline-db` montado en `/app/data/db/hospital.db`; metodos viejos de MongoWriter se eliminan sin compat | spec |
| 2026-05-16 | RF-3 reinterpretado tras design | `rejected_records` sigue en MongoDB con `raw_data` JSON; la nueva tabla `data_quality_summary` en SQLite cubre los agregados de calidad para el dashboard. Soft reference Mongo→SQLite por string UUID + indice nuevo en `rejected_records.pipeline_run_id`. Motivo: `raw_data` heterogeneo encaja mejor en documental, y los agregados son lo que realmente necesita el dashboard | design |
| 2026-05-16 | Spec reescrita end-to-end (objetivo, alcance, RF, CA) | Tras la implementacion completa, las primeras secciones aun describian la version inicial ("rejected_records a SQL"). Se alinean con la arquitectura real para que evaluador y futuras sesiones lean lo entregado, no la propuesta inicial | post-build |