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
| Dashboard | Streamlit 1.39 + Plotly 5.22 + Pandas 2.2 (imagen Docker independiente ~240 MB) — ver ADR-007 | ✅ Implementado |
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

# Triaje: alta manual de paciente con asignacion de prioridad (grave/medio/leve)
curl -X POST http://localhost:8000/api/v1/triage/patients \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Paciente Test",
       "gender": "M",
       "age": 65,
       "vital_signs": {
         "temperature_celsius": 38.5,
         "oxygen_saturation": 88,
         "heart_rate": 110,
         "respiratory_rate": 22,
         "systolic_bp": 100
       },
       "symptoms": ["tos", "disnea"],
       "risk_factors": ["epoc"]
     }'

# Ver las reglas de triaje vigentes (RF-8)
curl http://localhost:8000/api/v1/triage/rules

# Alertas activas calculadas en tiempo real (Feature 15, ADR-009)
# Tipos: pipeline_failed (high), data_quality_low (medium), triage_severe (critical)
curl http://localhost:8000/api/v1/alerts

# Filtro por severidad (server-side)
curl "http://localhost:8000/api/v1/alerts?severity=critical"

# Informe diario del dia consultado (ventana estricta [00:00, 23:59:59.999] UTC)
curl "http://localhost:8000/api/v1/reports/daily?date=2026-05-20"
```

### Generar el informe diario en Markdown (CLI reproducible)

```bash
# Mismo estado + misma fecha => mismo Markdown byte-a-byte (sha256 identico).
# "Automatizacion" en este proyecto = comando reproducible, NO scheduler.
docker compose exec api python -m src.automation.daily_report --date 2026-05-20

# Custom output
docker compose exec api python -m src.automation.daily_report \
  --date 2026-05-20 --output /tmp/informe.md
```

El fichero se escribe en `docs/reports/YYYY-MM-DD.md` por defecto. El
Markdown NO incluye `generated_at` ni nada dinamico — solo datos del
dia consultado — para garantizar idempotencia byte-a-byte (RNF-6 +
CA-11 de la Feature 15). El JSON del endpoint si lleva `generated_at`
dinamico como metadato.

## Ejecutar los tests

```bash
docker compose run --rm --entrypoint "" pipeline pytest tests -v
```

Suite de **417 tests verdes + 1 skip esperado** distribuidos en:
- tests de **pipeline, API, integracion y E2E** que se ejecutan en la
  imagen `hospital-pipeline` (incluye los E2E con stack vivo y los del
  watcher);
- tests **unit del dashboard** en la imagen `hospital-dashboard`
  (`ApiClient` con `httpx.MockTransport`, `error_banner`,
  `system_status`).

La feature de triaje (`POST /api/v1/triage/patients` + sistema basado
en reglas) **anadio 70 tests nuevos** al total (reglas + endpoint +
E2E + writer + cliente HTTP). La Feature 15 (alertas + informe diario)
**anadio otros 60 tests**: 13 unitarios puros de `evaluate`, 11 del
builder + render deterministas, 17 de los dos endpoints
(`/alerts` + `/reports/daily`), 5 del helper `day_window_utc`, 6 del
CLI con verificacion sha256 byte-a-byte y 8 del cliente HTTP nuevo
(`get_alerts` + `get_daily_report`).

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
├── sdd/                           # Indice explicativo del flujo SDD y trazabilidad
├── tasks/
│   ├── backlog.md                 # Roadmap del proyecto completo
│   ├── pipeline-datos.md          # Tareas T1-T12 del pipeline
│   └── lessons.md                 # Patrones a evitar / decisiones / cosas que funcionan
├── docs/
│   ├── memoria-tecnica.md         # Memoria tecnica final del proyecto (17 capitulos)
│   ├── diario-ia.md               # Diario de desarrollo con IA (entregable obligatorio)
│   ├── model-evaluation/          # Reporte clinico del modelo (metricas, matriz, curvas)
│   ├── presentation/              # Slides reveal.js + fallback Markdown offline
│   └── runbooks/                  # Procedimientos operativos (descarga, demo real, presentacion)
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
│   ├── dashboard/                 # Visualizacion Streamlit (implementado, ver ADR-007)
│   └── automation/                # Script CLI informe diario reproducible (Feature 15, ver ADR-009)
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
├── docker-compose.yml             # 7 servicios: mongodb, minio, minio-init, pipeline, api, watcher, dashboard
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

La carpeta `sdd/` resume el flujo usado y enlaza la evidencia principal:
`sdd/README.md`, `sdd/flujo.md`, `sdd/trazabilidad.md` y
`sdd/agentes-y-herramientas.md` (skills aplicadas, templates instanciados,
roles cubiertos y reglas operativas).

## Estado del proyecto

**Pipeline de datos:** 12/12 tareas completadas (T1-T12). Ver `tasks/pipeline-datos.md` para el detalle.

**Polyglot persistence (SQLite + SQLAlchemy):** 15/15 tareas completadas. Ver `tasks/sqlite-pipeline-metadata.md` y ADR-004.

**Clasificacion de radiografias (Keras/TensorFlow):** 16/16 tareas completadas. Ver `tasks/clasificacion-radiografias.md`, ADR-005, ADR-006 y ADR-010. Modelo entrenado en `data/models/radiography_classifier.keras` (~21 MB, commiteado) + reporte clinico en `docs/model-evaluation/`. Metricas finales sobre test split (1.515 imagenes) con la regla operativa `covid_threshold_0.35`: accuracy=0.8766, macro-F1=0.8594, recall Normal=0.890, Pneumonia=0.926, **COVID-19=0.820** (baseline argmax descartado: 0.695). Trazabilidad completa en ADR-010 y `docs/model-evaluation/threshold-analysis.md`.

**Tests:** 417 verdes + 1 skip esperado.

**Roadmap completo:** ver `tasks/backlog.md`. Pendientes principales:
- ~~Dashboard de visualizacion~~ ✅ **Implementado** (Streamlit en
  `http://localhost:8501`, 7 vistas + barra persistente de estado del
  sistema, ver `specs/dashboard.md`, `design/dashboard.md`, ADR-007)
- ~~Automatizaciones de alertas e informes~~ ✅ **Implementado**
  (Feature 15: `GET /api/v1/alerts` + `GET /api/v1/reports/daily` +
  CLI `daily_report.py` idempotente + vista dashboard "Alertas",
  ver `specs/automatizacion-alertas.md`, `design/automatizacion-alertas.md`,
  ADR-009)
- ~~Memoria tecnica~~ ✅ **Versión final** en `docs/memoria-tecnica.md` (17 capitulos, incluye etica/legal y reflexion critica como capitulos 13-14)
- ~~Presentacion final~~ ✅ **Completada** en `docs/presentation/` (13 slides reveal.js + fallback Markdown offline + guion en notas del presentador + preflight y plan B)
