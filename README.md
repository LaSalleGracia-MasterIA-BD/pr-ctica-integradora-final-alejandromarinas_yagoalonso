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
| BBDD NoSQL | MongoDB 7 | ✅ Implementado |
| Almacenamiento de objetos | MinIO (S3-compatible) | ✅ Implementado |
| API REST | FastAPI + Uvicorn | ✅ Implementado |
| Deep Learning | Keras / TensorFlow (CNN: Conv2D + MaxPooling2D + Dropout + Dense, con EarlyStopping) | 🚧 Pendiente |
| Dashboard | Streamlit | 🚧 Pendiente |
| Infraestructura | Docker + Docker Compose | ✅ Implementado |

## Requisitos previos

- Docker Desktop (o Docker Engine + Docker Compose v2)
- Puertos libres: `8000` (API), `27017` (MongoDB), `9000` y `9001` (MinIO)
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
   - Sincroniza las 17 radiografias de ejemplo (`data/raw/images/`) al bucket `radiographies`
   - Si MongoDB esta vacio, ejecuta el **pipeline ETL completo** sobre los CSVs de ejemplo (`patients.csv` + `admissions.csv`) y deja **4.745 pacientes** y **8.569 admissions** procesados
   - Verifica conectividad con MongoDB
5. La **API REST** arranca en `localhost:8000` ya con datos servibles

Cuando veas la linea `=== Bootstrap complete. System is ready. ===` el sistema esta listo.

El bootstrap es **idempotente**: re-ejecutar `docker compose up` no vuelve a procesar lo que ya esta.

### Acceso al sistema

| Servicio | URL | Credenciales |
|---|---|---|
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
```

## Ejecutar los tests

```bash
docker compose run --rm --entrypoint "" pipeline pytest tests -v
```

Suite de **125 tests** unitarios + de integracion contra MongoDB/MinIO reales + E2E sobre los 8 criterios de aceptacion de la spec.

## Detener el sistema

```bash
docker compose down        # Para los contenedores (conserva volumenes)
docker compose down -v     # Para y borra TODOS los datos (MongoDB + MinIO)
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
│   ├── api/                       # FastAPI (main, routers, models, mongo_reader)
│   ├── pipeline/                  # Pipeline ETL completo
│   │   ├── ingesters/             # CSVIngester + ImageIngester
│   │   ├── processors/            # DataValidator + DataCleaner + DataTransformer
│   │   ├── storage/               # MongoWriter + MinIOClient
│   │   ├── scripts/               # bootstrap, generadores de datos, watcher
│   │   ├── orchestrator.py        # PipelineOrchestrator (T9)
│   │   └── watcher.py             # IncomingFilesWatcher (T9)
│   ├── ml/                        # Modelo clasificacion radiografias (pendiente)
│   ├── dashboard/                 # Visualizacion (pendiente)
│   └── automation/                # Alertas e informes (pendiente)
├── tests/
│   ├── api/                       # 12 tests de la API
│   └── pipeline/                  # 98 tests del pipeline
├── data/raw/                      # Fixtures sinteticos committeados
│   ├── patients.csv               # 5.150 filas (5.000 + duplicados)
│   ├── admissions.csv             # 10.000 filas
│   └── images/                    # 17 PNGs dummy
├── docker/                        # Scripts de inicializacion (Mongo, MinIO)
├── docker-compose.yml             # 5 servicios: mongodb, minio, minio-init, pipeline, api
├── Dockerfile.pipeline            # Imagen comun para pipeline + api
├── requirements-pipeline.txt
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

**Tests:** 125 verdes (98 unit del pipeline + 12 API + 14 E2E sobre criterios de aceptacion + 1 regresion).

**Roadmap completo:** ver `tasks/backlog.md`. Pendientes principales:
- Modelo de clasificacion de radiografias (Keras/TensorFlow)
- Dashboard de visualizacion (Streamlit)
- Automatizaciones (alertas + informes; el watcher esta como modulo, no como servicio del compose)
- Memoria tecnica + presentacion final
