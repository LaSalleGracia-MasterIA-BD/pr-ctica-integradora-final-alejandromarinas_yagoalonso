# Sistema Inteligente de Soporte Hospitalario

Sistema de IA para el hospital **laSalle Health Center** que clasifica radiografias de torax, procesa datos clinicos a escala con un pipeline Big Data y expone los resultados via API REST.

Proyecto final del Master en AI & Big Data.

## Equipo

- Alejandro Marinas
- Yago

## Stack

| Componente | Tecnologia | Estado |
|---|---|---|
| Pipeline de datos | PySpark 3.5.1 | ✅ Implementado |
| BBDD NoSQL (documental) | MongoDB 7 | ✅ Implementado |
| BBDD relacional (metadatos pipeline) | SQLite + SQLAlchemy 2.0 | ✅ Implementado |
| Almacenamiento de objetos | MinIO (S3-compatible) | ✅ Implementado |
| API REST | FastAPI + Uvicorn | ✅ Implementado |
| Deep Learning | Keras / TensorFlow 2.16 (CNN: Conv2D + MaxPooling2D + Dropout + Flatten + Dense + softmax, con EarlyStopping) — ver ADR-005 | ✅ Implementado |
| Dashboard | Streamlit 1.36 + Plotly 5.22 + Pandas 2.2 (imagen Docker independiente ~240 MB) — ver ADR-007 | ✅ Implementado |
| Infraestructura | Docker + Docker Compose | ✅ Implementado |

> **Polyglot persistence (ADR-004):** cada dato vive donde su forma encaja.
> MongoDB es dueno de `patients` (con `admissions` y `radiographies` embebidas) y `rejected_records` con `raw_data` heterogeneo. SQLite es dueno de `pipeline_runs` (auditoria) y `data_quality_summary` (metricas). MinIO guarda los PNG.

## Requisitos previos

- Docker Desktop (o Docker Engine + Docker Compose v2)
- Puertos libres: `8000` (API), `8501` (Dashboard Streamlit), `27017` (MongoDB), `9000` y `9001` (MinIO)
- ~4 GB de RAM libres (PySpark en JVM)

## Arranque

Clona el repositorio y ejecuta:

```bash
docker compose up
```

Con ese unico comando, el sistema queda listo en menos de 1 minuto:

1. **MongoDB** y **MinIO** se levantan con sus volumenes persistentes
2. Se inicializa la base de datos `hospital` (colecciones e indices unicos)
3. Se crean los buckets de MinIO (`radiographies`, `raw-backups`)
4. El servicio `pipeline` ejecuta el bootstrap:
   - Crea el schema de **SQLite** (`pipeline_runs` + `data_quality_summary`) en el volumen `pipeline-db`
   - Sincroniza las 17 radiografias de ejemplo (`data/raw/images/`) al bucket `radiographies`
   - Si MongoDB esta vacio, ejecuta el **pipeline ETL completo** sobre los CSVs de ejemplo (`patients.csv` + `admissions.csv`) y deja **4.745 pacientes** y **8.569 admissions** procesados. Registra el run en SQLite con sus metricas de calidad
   - Genera una **radiografia sintetica de demo** (`HOSP-DEMO-001`, fixture tecnico — no es una radiografia real) para que la vista Clasificador del dashboard tenga al menos una imagen clasificable out-of-the-box. Para una demo con valor clinico ante profesores, sustituirla por una imagen real del dataset siguiendo `docs/runbooks/use-real-radiograph-for-demo.md` (`data/raw/images-demo/README.md`)
   - Verifica conectividad con MongoDB
5. La **API REST** arranca en `localhost:8000` con datos servibles (incluyendo dos endpoints nuevos para el dashboard: `GET /radiographies/image?key=...` y `GET /model/evaluation`)
6. El **Dashboard Streamlit** arranca en `localhost:8501` consumiendo la API
7. El servicio **watcher** se queda escuchando `data/incoming/`: dropear ahi `patients.csv` + `admissions.csv` dispara automaticamente el ETL y mueve los ficheros a `data/incoming/processed/`

Cuando veas la linea `=== Bootstrap complete. System is ready. ===` el sistema esta listo.

El bootstrap es **idempotente**: re-ejecutar `docker compose up` no vuelve a procesar lo que ya esta.

### Acceso al sistema

| Servicio | URL | Credenciales |
|---|---|---|
| **Dashboard** (Streamlit) | `http://localhost:8501` | sin auth (dev) |
| **API REST** | `http://localhost:8000` | sin auth (dev) |
| Docs interactivas (Swagger) | `http://localhost:8000/docs` | — |
| MongoDB | `mongodb://localhost:27017` (BD `hospital`) | sin auth (dev) |
| MinIO API | `http://localhost:9000` | `minioadmin` / `minioadmin123` |
| MinIO consola web | `http://localhost:9001` | `minioadmin` / `minioadmin123` |

### Ejemplos de uso de la API

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Listar pacientes (paginado)
curl "http://localhost:8000/api/v1/patients?limit=5"

# Detalle de un paciente con sus admissions embebidas
curl http://localhost:8000/api/v1/patients/HOSP-000000

# Listar admissions (flatten)
curl "http://localhost:8000/api/v1/admissions?limit=10"

# Metadatos de radiografias
curl "http://localhost:8000/api/v1/radiographies?limit=5"

# Estado del ultimo run del pipeline
curl http://localhost:8000/api/v1/pipeline/status

# Historico de runs
curl http://localhost:8000/api/v1/pipeline/runs

# Disparar el pipeline manualmente (re-procesa los CSVs)
curl -X POST http://localhost:8000/api/v1/pipeline/trigger

# Calidad de datos del ultimo run (una fila por dimension: patients, admissions)
curl http://localhost:8000/api/v1/pipeline/quality-summary

# Historico de calidad para una dimension concreta
curl "http://localhost:8000/api/v1/pipeline/quality-summary/history?dimension=admissions&limit=10"

# Clasificar una radiografia (devuelve clase + probabilidades y persiste en Mongo)
curl -X POST http://localhost:8000/api/v1/radiographies/classify \
     -H "Content-Type: application/json" \
     -d '{"minio_object_key": "HOSP-000001/HOSP-000001_xray1.png"}'

# Leer la clasificacion persistida sin re-inferir
curl "http://localhost:8000/api/v1/radiographies/classification?key=HOSP-000001/HOSP-000001_xray1.png"
```

## Ejecutar los tests

```bash
docker compose run --rm --entrypoint "" pipeline pytest tests -v
```

Suite de **275 tests** distribuidos:
- **218** unit + integracion en `hospital-pipeline` (incluye los 10 nuevos
  para `GET /radiographies/image` y `GET /model/evaluation`)
- **33** unit en `hospital-dashboard` (`ApiClient` con `httpx.MockTransport`,
  `error_banner`, `system_status`)
- **24** E2E con stack vivo (incluye smoke del dashboard healthcheck)

1 test se salta cuando se ejecuta dentro del contenedor `pipeline` (el
watcher E2E necesita rw sobre `data/incoming/`). Los tests E2E de
clasificacion se saltan si la API reporta `predictor_loaded=false`
(sin modelo entrenado en `data/models/`).

## Detener el sistema

```bash
docker compose down        # Para los contenedores (conserva volumenes)
docker compose down -v     # Para y borra TODOS los volumenes: mongo-data, minio-data y pipeline-db (SQLite)
```

## Estructura del repositorio

```
├── specs/                         # Especificaciones por feature (SDD)
├── design/                        # Arquitectura por feature
├── decisions/                     # ADRs (decisiones tecnicas)
├── tasks/
│   ├── backlog.md                 # Roadmap del proyecto completo
│   ├── pipeline-datos.md          # Tareas T1-T12 del pipeline
│   └── lessons.md                 # Patrones a evitar / decisiones / cosas que funcionan
├── docs/
│   ├── diario-ia.md               # Diario de desarrollo con IA (entregable obligatorio)
│   └── runbooks/
│       └── download-radiography-dataset.md
├── src/
│   ├── api/                       # FastAPI (main, routers, models, mongo_reader, sql_reader)
│   ├── pipeline/                  # Pipeline ETL completo
│   │   ├── ingesters/             # CSVIngester + ImageIngester
│   │   ├── processors/            # DataValidator + DataCleaner + DataTransformer + QualitySummaryBuilder
│   │   ├── storage/               # MongoWriter + MinIOClient + SqlWriter + SqlEngine + modelos SQLAlchemy
│   │   ├── scripts/               # bootstrap, generadores de datos, watcher_daemon
│   │   ├── orchestrator.py        # PipelineOrchestrator (E→T→L, runs en SQL, rejected en Mongo)
│   │   └── watcher.py             # IncomingFilesWatcher
│   ├── ml/                        # Modelo clasificacion radiografias (Keras/TF, CNN — implementado)
│   ├── dashboard/                 # Visualizacion (pendiente)
│   └── automation/                # Alertas e informes (pendiente)
├── tests/
│   ├── api/                       # Tests de la API (endpoints + readers)
│   ├── pipeline/                  # Tests unitarios + integracion del pipeline
│   └── e2e/                       # Tests E2E (CA-1..CA-8 + watcher + huerfanos)
├── data/
│   ├── raw/                       # Fixtures sinteticos committeados (read-only)
│   │   ├── patients.csv           # 5.150 filas (5.000 + duplicados)
│   │   ├── admissions.csv         # 10.000 filas
│   │   └── images/                # 17 PNGs dummy
│   ├── incoming/                  # Cola del watcher (rw)
│   └── db/                        # Punto de montaje para `pipeline-db` (SQLite)
├── docker/                        # Scripts de inicializacion (Mongo, MinIO)
├── docker-compose.yml             # 6 servicios: mongodb, minio, minio-init, pipeline, api, watcher
├── Dockerfile.pipeline            # Imagen comun para pipeline + api + watcher
├── requirements-pipeline.txt      # Incluye PySpark + pymongo + minio + SQLAlchemy + FastAPI + watchdog
└── pyproject.toml                 # Configuracion de pytest
```

## Datos incluidos en el repositorio

`data/raw/` contiene datos sinteticos generados con [Faker](https://faker.readthedocs.io) y commiteados al repo para que el arranque sea **completamente reproducible y offline**:

- `patients.csv`: 5.000 pacientes (con ~5% de casos borde: nulos, duplicados, fechas malformadas)
- `admissions.csv`: 10.000 ingresos (con referencias huerfanas intencionadas)
- `images/`: 17 PNGs dummy con la convencion `HOSP-NNNNNN_xrayN.png`

Para regenerar los datos:

```bash
docker compose run --rm --entrypoint "" pipeline python -m src.pipeline.scripts.generate_data --seed 42
docker compose run --rm --entrypoint "" pipeline python -m src.pipeline.scripts.generate_dummy_images --seed 42
```

El **dataset real** de radiografias (para entrenar el modelo ML) no esta en el repo por tamano. Ver `docs/runbooks/download-radiography-dataset.md`.

## Pipeline ETL — descripcion

```
patients.csv ─┐
              ├─→ CSVIngester (PySpark)
admissions ───┘             ↓
                       DataValidator ──→ rejected_records (MongoDB)
                            ↓
                       DataCleaner (dedup, trim)
                            ↓
                       DataTransformer (edad, categoria diagnostico)
                            ↓
                       MongoWriter (upsert con admissions embebidas)
                            ↓
                       MongoDB: 4.745 patients + 8.569 admissions
images/*.png ─→ ImageIngester (validacion PNG signature) ──→ MinIO bucket radiographies
```

Cada ejecucion queda registrada en `pipeline_runs` con stats (`records_processed`, `records_rejected`, `started_at`, `finished_at`, `status`).

## Metodologia

Desarrollo dirigido por especificacion (SDD). Cada feature pasa por:
`spec → design → tasks → implementacion → validacion`.

Artefactos en `specs/` y `design/`. Backlog en `tasks/backlog.md`. Decisiones tecnicas en `decisions/` (ADRs).

## Estado del proyecto

**Pipeline de datos:** 12/12 tareas completadas (T1-T12). Ver `tasks/pipeline-datos.md` para el detalle.

**Polyglot persistence (SQLite + SQLAlchemy):** 15/15 tareas completadas. Ver `tasks/sqlite-pipeline-metadata.md` y ADR-004.

**Clasificacion de radiografias (Keras/TensorFlow):** 16/16 tareas completadas. Ver `tasks/clasificacion-radiografias.md`, ADR-005 y ADR-006. Modelo entrenado en `data/models/radiography_classifier.keras` (~21 MB, commiteado) + reporte clinico en `docs/model-evaluation/`. Metricas finales (test split de 1.515 imagenes): accuracy=0.872, macro-F1=0.846, recall Normal=0.93, Pneumonia=0.93, COVID-19=0.70.

**Tests:** 208 verdes + 1 skip.

**Roadmap completo:** ver `tasks/backlog.md`. Pendientes principales:
- ~~Dashboard de visualizacion~~ ✅ **Implementado** (Streamlit en
  `http://localhost:8501`, 5 vistas + barra persistente de estado del
  sistema, ver `specs/dashboard.md`, `design/dashboard.md`, ADR-007)
- Automatizaciones de alertas e informes (el watcher YA esta como servicio real en el compose; queda pendiente el flujo de alertas)
- Memoria tecnica + presentacion final
