# Changelog

Todas las entregas notables de este proyecto, en orden cronologico inverso.
Formato basado en [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- **Feature 15 — Automatizacion, alertas e informes operativos
  (cierra Features 5 y 6 del backlog):** capa de observabilidad
  accionable sobre el pipeline + calidad + triajes ya existentes.
  Cumple el enunciado ("entrada en el dashboard ante eventos
  relevantes" + "generacion automatica de informes") sin servicios
  externos (cero scheduler, cero email, cero Prometheus).
  - **`GET /api/v1/alerts`** — alertas activas calculadas en tiempo
    real desde 3 fuentes existentes (sin estado nuevo persistido,
    ver `decisions/ADR-009-alertas-como-vista-derivada.md`):
    `pipeline_runs.status='failed'` (high), `data_quality_summary
    .rejection_rate > umbral` (medium), `patients.triage.level=grave`
    (critical). Query params: `since` (override ventana), `severity`
    (filtro server-side). Response: `{items, total, generated_at,
    threshold, window_start}`. Configurable via env:
    `ALERT_REJECTION_RATE_THRESHOLD` (default 0.10),
    `ALERT_WINDOW_HOURS` (default 24).
  - **`GET /api/v1/reports/daily?date=YYYY-MM-DD`** — informe
    estructurado JSON del dia consultado. **Ventana estricta**
    `[00:00, 23:59:59.999]` UTC: NO reutiliza la ventana de
    `/alerts`. Secciones: pipeline (runs del dia, failed del dia,
    ultimo run), quality (snapshots por dimension), counts
    (snapshot total), triage (grave/medio/leve del dia), alerts
    (calculadas con la misma `evaluate` que `/alerts`).
  - **`src/api/alerts.py`** — funcion pura
    `evaluate(failed_runs, quality_snapshots, severe_triage_patients,
    threshold) -> list[Alert]` con dataclass frozen `Alert`. Mismo
    patron que el triaje (ADR-008): NO conoce el reloj ni el IO,
    aplica las 3 reglas IF-THEN y ordena por
    `severity DESC, created_at DESC`. Conexion con la **Sesion 07
    de Yuri (sistemas basados en reglas, `ruleBasedSystem/`)**.
  - **`src/api/reports.py`** — builder + render puros
    (`build_daily_report` + `render_markdown`). El render NO incluye
    `generated_at` ni nada dependiente del reloj: garantiza
    idempotencia byte-a-byte (RNF-6 + CA-11) del Markdown del
    script. El JSON del endpoint si lleva `generated_at` dinamico
    como metadato.
  - **`src/api/time_window.py`** — helper `day_window_utc(day)` que
    devuelve `(start, end)` UTC del dia. Centralizado para evitar
    drift entre endpoint y CLI.
  - **`src/automation/daily_report.py`** — CLI reproducible
    (`python -m src.automation.daily_report --date YYYY-MM-DD
    [--output PATH]`) que llama internamente al mismo
    `build_daily_report` (DRY) y escribe el Markdown determinista
    en `docs/reports/YYYY-MM-DD.md`. Sin scheduler:
    "automatizacion" = comando reproducible byte-a-byte.
  - **`src/api/sql_reader.py`** — 5 metodos nuevos: familia `_since`
    para `/alerts` (ventana abierta) + familia `_between` para
    `/reports/daily` (ventana cerrada del dia). Cero tablas nuevas.
  - **`src/api/mongo_reader.py`** — 4 metodos nuevos: misma logica
    de doble familia + `get_total_counts()` para el snapshot del
    informe.
  - **`src/api/models.py`** — schemas `AlertResponse`,
    `AlertsResponse`, `DailyReportResponse`.
  - **Dashboard**: vista nueva **"Alertas"** en
    `src/dashboard/views/alerts.py` (4 chips por severity + tabla +
    detalle por alerta con chip de color + boton "Recargar" +
    filtro server-side). API-only (ADR-007): cero imports de
    pymongo/sqlite/sqlalchemy/minio en `src/dashboard/`. Registrada
    en `src/dashboard/app.py::st.navigation` entre "Triaje" y
    "Clasificador". `api_client` con 2 metodos nuevos: `get_alerts`,
    `get_daily_report`.
  - **60 tests nuevos**: 13 unitarios puros de `evaluate`
    (`tests/api/test_alerts_rules.py`), 11 del builder + render
    deterministas (`tests/api/test_reports_builder.py`), 10 del
    endpoint `/alerts` (`tests/api/test_alerts_endpoint.py`), 7 del
    endpoint `/reports/daily` (`tests/api/test_reports_endpoint.py`),
    5 del helper `day_window_utc` (`tests/api/test_time_window.py`),
    6 del CLI con verificacion sha256 byte-a-byte
    (`tests/automation/test_daily_report.py`), 8 del cliente HTTP
    nuevo (`tests/dashboard/test_api_client.py`). **Total suite
    proyecto: 404 verde** + 1 skip esperado.
    Smoke real verificado con `docker compose` (paciente grave
    inyectado via `/triage/patients` -> alerta `triage_severe`
    aparece en `/alerts`; 2 ejecuciones consecutivas de
    `daily_report` con `--date 2026-05-20` -> sha256 identico).
  - **ADR-009**: justifica la decision de "alertas como vista
    derivada" en lugar de tabla `alerts` con estado leida/no leida.
    Documenta cuando se reabriria (auditoria + retrospectiva
    historica).

- **Feature 14 — Triaje de pacientes en alta manual (sistema basado en reglas):**
  endpoint REST `POST /api/v1/triage/patients` que recibe demograficos +
  signos vitales + sintomas, evalua reglas explicitas (ver
  `decisions/ADR-008-triaje-basado-en-reglas.md`) y persiste el paciente
  en el dataset operativo `patients` de MongoDB con un campo `triage`
  embebido (`level: grave|medio|leve`, `score`, `reasons`,
  `triaged_at`, `source: manual_triage`, `rules_version: 1.0`).
  - **`src/api/triage.py`**: funcion pura `evaluate(payload) -> TriageResult`
    sin dependencias de Mongo ni FastAPI. 6 reglas grave + 5 reglas medio
    (umbrales academicos simplificados, conectados con la teoria de
    Modelos de IA del Master; ver ADR-008).
  - **`src/api/routers/triage.py`**: orquesta validacion Pydantic +
    reglas + persistencia. Genera `external_id` con formato
    `TRIAGE-YYYYMMDD-NNNN` y usa **`MongoWriter.insert_patient`**
    (`insert_one`, NO upsert) — el alta manual nunca actualiza un
    paciente existente. Retry con `TRIAGE_MAX_RETRIES=5` ante
    `DuplicateKeyError`; 409 tras agotar reintentos.
  - **`src/pipeline/storage/mongo_writer.py`**: metodo nuevo
    `insert_patient(doc) -> str` que propaga `DuplicateKeyError` sin
    intentar resolverlo (responsabilidad del router).
  - **`src/api/models.py`**: schemas `VitalSigns`, `TriageInfo`,
    `TriagePatientRequest` (con `@model_validator` que exige
    birth_date o age) y `class TriagePatientResponse(Patient): ...`
    (clase explicita heredando para mejor OpenAPI). Campo
    `triage: TriageInfo | None = None` anadido a `Patient` para que
    no se descarte con `extra="ignore"`.
  - **`GET /api/v1/triage/rules`**: documenta la version de reglas
    vigente (RF-8). Sirve como auto-documentacion del sistema.
  - **Dashboard**: vista nueva **"Triaje"** en
    `src/dashboard/views/triage.py` (formulario con demograficos +
    signos vitales + sintomas multiselect + factores de riesgo +
    visualizacion del resultado con color por nivel + expander con
    las reglas vigentes). Dashboard sigue API-only (ADR-007).
    Registrada en `src/dashboard/app.py::st.navigation` entre
    "Pacientes" y "Clasificador".
  - **70 tests nuevos**: 34 unitarios de reglas
    (`tests/api/test_triage_rules.py`, cubren las 6 reglas grave +
    5 reglas medio + casos borde de fronteras 91/92/94/95, 30/31
    fr, 130/131 fc, 89/90 sbp, 38.9/39.0 temp); 21 de endpoint
    (`tests/api/test_triage_endpoint.py`: 3 niveles + validaciones
    422 incluyendo birth_date invalida, birth_date futura, name solo
    espacios; formato del external_id; cupo diario 9999 -> 409;
    CA-5 GET /patients tras crear); 2 de `insert_patient`
    (`tests/pipeline/test_mongo_writer.py`); 6 E2E con stack vivo
    (`tests/e2e/test_triage_e2e.py`: incluye verificacion real
    paginando hasta la ultima pagina usando `total`); 7 de
    `api_client` con `httpx.MockTransport`
    (`tests/dashboard/test_api_client.py`). **Total proyecto: 344
    tests verdes** + 1 skip esperado (antes 275).
  - **ADR-008**: justifica reglas vs ML (no hay dataset etiquetado
    con severidad `grave|medio|leve` disponible; reglas son
    auditables y conectan con la teoria del Master sobre sistemas
    basados en reglas). El proyecto contiene ahora ambos paradigmas:
    ML para radiografias (donde si hay dataset) y reglas para triaje
    (donde no lo hay).
  - Disclaimer permanente en la UI: "asistencia al triaje, no
    diagnostico ni decision medica vinculante". Umbrales academicos
    simplificados, NO validados clinicamente.
  - **Mejora demo en vista Pacientes**: anadido buscador opcional
    por `external_id` que coexiste con la seleccion por fila. Util
    tras crear un paciente en la vista Triaje para comprobar al
    instante que esta persistido en Mongo.

- **Feature 4 — Dashboard de visualizacion (Streamlit, puerto 8501):**
  centro de control hospitalario que consume exclusivamente la API REST
  (sin acceso directo a MongoDB/SQLite/MinIO). Ver ADR-007.
  - **5 vistas**: Overview (cards + ultimo run + strip de evaluacion +
    auto-refresh 30s), Calidad de datos (snapshot + historico
    rejection_rate por dimension con Plotly), Pacientes (lista
    paginada server-side + detalle con admissions y radiografias
    embebidos), Clasificador (dropdown ordenado con HOSP-DEMO-001
    primero + imagen + clasificar + sub-seccion de evaluacion detallada
    con matriz de confusion heatmap), Pipeline runs (tabla paginada +
    detalle de fallos)
  - **Barra persistente de estado del sistema** en el sidebar (chips
    API + Modelo + Ultimo run) visible desde cualquier vista
  - **2 endpoints API nuevos**:
    `GET /api/v1/radiographies/image?key=...` (proxy de bytes PNG de
    MinIO para que el dashboard renderice radiografias siendo API-only)
    y `GET /api/v1/model/evaluation` (lee `metrics.json` y lo devuelve
    como JSON; 503 si falta)
  - **Imagen Docker `hospital-dashboard:latest` independiente** (~240
    MB sin TF/PySpark/Java/Pillow), construye en ~50s, arranca en
    <15s. Tema visual via `.streamlit/config.toml` (paleta sobria
    Linear-like, primaryColor `#2563EB`, sin emojis, sin CSS complejo)
  - **`HOSP-DEMO-001`**: el bootstrap genera una radiografia sintetica
    256x256 (numpy + Pillow + ImageDraw) y la sube al bucket. Mitiga
    CB-7 (las 17 dummy del bootstrap son 1x1 y la API las rechaza).
    Origen/licencia documentados en `data/raw/images-demo/README.md`
  - **Manejo de errores explicito** (`ApiError(kind, status, detail)`
    + `components/error_banner.py`): network → "API no disponible";
    422 en /classify → "Imagen demasiado pequena"; 503 en /classify
    vs /model/evaluation son **dos senales distintas** (modelo no
    cargado vs reporte ausente)
  - **Cache `st.cache_data(ttl=10s)`** en todas las queries GET,
    `ttl=60s` en `/model/evaluation` (las metricas no cambian hasta
    reentrenar); POST `/classify` no se cachea
  - **57 tests nuevos**: 10 unitarios para los 2 endpoints API +
    15 unitarios del `ApiClient` (con `httpx.MockTransport`, sin red) +
    12 unitarios del `error_banner` + 6 unitarios del `system_status` +
    2 E2E del dashboard. **Total proyecto: 275 tests verdes** (218
    pipeline + integration + 33 dashboard + 24 E2E)
  - Smoke real verificado: las 5 vistas responden 200, `HOSP-DEMO-001`
    se clasifica como "Normal" con probabilidad 0.95 (la imagen
    sintetica no tiene patron clinico real, el modelo solo demuestra
    el flujo end-to-end). CB-1 verificado: con `docker compose stop
    api`, el dashboard sigue respondiendo `200 OK` y los chips del
    sidebar pasan a rojo

- **Feature 2 — Clasificacion de radiografias (Keras/TensorFlow):**
  Modelo CNN propio (~1.8M params, ~7-8 MB en disco) que clasifica
  radiografias de torax en `Normal` / `Pneumonia` / `COVID-19`. Arquitectura
  literal del Bloque 6 del Master (ADR-005): 4 bloques `Conv2D padding="same"
  + MaxPool` (filters 32/64/128/128), Dropout 0.5, Flatten, Dense(64)+ReLU,
  Dropout 0.3, Dense(3) + softmax. Input 224x224x1 grayscale. Sin transfer
  learning ni horizontal flip (alteraria semantica anatomica).
  - **Dataset:** COVID-19 Radiography Database (Kaggle). 15.153 imagenes
    usadas (3.616 COVID + 10.192 Normal + 1.345 Viral Pneumonia).
    `Lung_Opacity` se descarta (no encaja en clasificacion triple)
  - **Split estratificado 80/10/10 con seed=42.** Regla estricta:
    `train→fit`, `val→callbacks` (EarlyStopping, ModelCheckpoint),
    `test→reporte final`. El modelo nunca ve test durante el entrenamiento
  - **Modulo `src/ml/`:** `dataset.py` (discovery + splits), `preprocessing.py`
    (mismo pipeline en train y serve, evita train-serve skew), `model.py`,
    `evaluate.py`, `train.py` (CLI), `predictor.py` (thread-safe con Lock)
  - **API:** `POST /api/v1/radiographies/classify` (body con
    `minio_object_key`) → 200/404/422/503; `GET /api/v1/radiographies/classification?key=...`
    → 200/404/422. Mongo persiste objeto con `predicted_class`, `probabilities`,
    `predicted_at`, `model_version` (no string plano). Indice nuevo en
    `radiographies.minio_object_key`. `MongoWriter.set_radiography_classification`
    devuelve `matched_count > 0` (no `modified_count`) → idempotencia
    correcta con payload identico
  - **Predictor cargado al arrancar la API** (lifespan); si falta el
    artefacto, la API arranca igualmente y los endpoints de classify
    devuelven 503 (CB-4). `HealthResponse` gana `predictor_loaded: bool`
  - **Reporte:** `docs/model-evaluation/{report.md,metrics.json,confusion_matrix.png,learning_curves.png}`
    con accuracy, macro-F1, precision/recall/F1 por clase con foco en
    recall COVID/Pneumonia, matriz de confusion 3x3, curvas de aprendizaje
    y **analisis clinico cualitativo** (CA-3): los FN COVID son el error
    mas grave (paciente contagioso clasificado como sano)
  - **TensorFlow 2.16.1** + `scikit-learn` 1.5.0 + `matplotlib` 3.9.0 +
    `pillow` 10.3.0 anadidos a la imagen `hospital-pipeline` compartida
    (ADR-006: una sola imagen para todo el stack)
  - **Refactor de volumenes Docker:** `./data:/app/data:ro` global se
    descompone en submontajes especificos (`data/raw:ro`, `data/models:rw`
    en pipeline / `:ro` en api, `pipeline-db:rw`). `.gitignore` excluye
    `data/raw/covid_radiography/` (1.5 GB) y permite commitear
    `data/models/*.keras` y `*.meta.json` si caben en 50 MB
  - **Test E2E** con fixture 64x64 generado al vuelo (NO usa las dummy
    1x1 del bootstrap porque las rechazaria CB-7 con 422). Skip limpio
    si `GET /health` reporta `predictor_loaded=false`
  - **Metricas finales (test split, 1.515 imagenes):**
    - **Accuracy: 0.8719** (vs 0.6726 baseline degenerado en el primer intento)
    - **Macro-F1: 0.8456** (vs 0.33 random)
    - **Recall por clase:** Normal=0.926, Pneumonia=0.933, COVID-19=0.695
    - **Precision por clase:** Normal=0.897, Pneumonia=0.829, COVID-19=0.807
    - Modelo: 21 MB, 35 epochs (no llego a plateau, EarlyStopping no corto)
    - Hiperparametros finales: lr=1e-4, class_weight=sqrt, dropout=(0.3, 0.3),
      sin horizontal flip en augmentation, seed=42
    - Limitacion documentada en el reporte clinico: 110/361 COVID-19 se
      clasifican como Normal o Pneumonia (FN COVID 30%). El modelo se
      entrega como **asistencia diagnostica**, no como diagnostico final
  - **Sanity checks documentados en `scripts/ml_diagnostics.py`** (overfit
    tiny subset, montage visual, mapping de clases, validacion del
    artefacto). El primer entrenamiento dio un modelo degenerado (predecia
    todo Normal); los sanity checks confirmaron que NO habia bug en
    preprocesado/labels/modelo y que el problema era de hiperparametros
    (LR=1e-3 demasiado alto + class_weight=3.76 demasiado agresivo). Tras
    ajustar a LR=1e-4 + class_weight=sqrt el modelo aprendio bien
- ADR-005: CNN custom desde cero, sin transfer learning (alineacion con
  el Bloque 6 del Master)
- ADR-006: TensorFlow en la imagen `hospital-pipeline` compartida (frente
  a imagen `hospital-ml` separada)

- Estructura inicial del proyecto SDD (specs, design, tasks, decisions, docs)
- Backlog con features identificadas del enunciado
- Spec, design y tasks aprobados del pipeline de datos (12 tareas)
- ADR-001: Decision de stack tecnologico (PySpark + PyTorch + FastAPI)
- ADR-002: MongoDB como BBDD principal (en lugar de PostgreSQL)
- Repositorio en GitHub (publico): MarinasAlejandro/lasalle-hospital
- Diario de desarrollo con IA (docs/diario-ia.md)
- **T1 (Infraestructura base):** docker-compose.yml con MongoDB 7 + MinIO funcionando
  - Script de inicializacion de MongoDB (DB hospital, colecciones, indices)
  - Script de inicializacion de buckets MinIO
  - Variables de entorno en .env
- **T2 (Configuracion PySpark + logging):**
  - `src/pipeline/logging_config.py` — logging centralizado con formato estandar
  - `src/pipeline/spark_session.py` — factory de SparkSession configurable por env
  - `src/pipeline/scripts/verify_pyspark.py` — smoke test del contenedor
  - `Dockerfile.pipeline` con python:3.11-slim + default-jre-headless + PySpark 3.5.1
  - `pyproject.toml` con configuracion de pytest (pythonpath, testpaths)
  - Servicio `pipeline` en docker-compose con depends_on condicionales
  - 9 tests unitarios pasando dentro del contenedor (5 logging + 4 Spark)
- **T3 (Generador de datos simulados):**
  - `src/pipeline/scripts/generate_data.py` con Faker (es_ES)
  - CSVs realistas: 5.000 pacientes + 10.000 ingresos, codigos ICD-10, departamentos hospitalarios
  - Casos borde intencionados: nulos (~5%), duplicados (~3%), fechas malformadas, huerfanos
  - Generacion determinista con seed para tests reproducibles
  - 7 tests unitarios anadidos (total 16 tests pasando)
- **T4 (Storage layer):**
  - `src/pipeline/storage/minio_client.py` — wrapper sobre minio-py (ensure_bucket, upload_file/bytes, download_file, exists, list_objects, remove_object)
  - `src/pipeline/storage/mongo_writer.py` — wrapper sobre pymongo (bulk_upsert_patients idempotente, add_radiography_to_patient idempotente, ping, start/finish_pipeline_run, write_rejected)
  - Factories `get_minio_client_from_env` y `get_mongo_writer_from_env` que leen variables del entorno
  - 15 tests de integracion contra MongoDB y MinIO reales (total 31 tests pasando dentro del contenedor)
- **T5 (Ingesta de CSVs):**
  - `src/pipeline/ingesters/csv_ingester.py` — lee CSVs a DataFrames PySpark
  - Valida que existan las columnas requeridas (levanta `MissingColumnsError` en caso contrario)
  - Acepta columnas en cualquier orden, preserva todas las filas (la validacion fila a fila queda para T7)
  - Anade columna `_source_file` para trazabilidad
  - 9 tests unitarios con CSVs temporales (total 40 tests pasando)
  - Smoke test con los 5.150 + 10.000 CSVs reales de T3 verificado
- **T6 (Ingesta de imagenes):**
  - `src/pipeline/ingesters/image_ingester.py` — lee PNGs, valida signature PNG, sube a MinIO con metadatos
  - Convencion de nombres `{patient_external_id}_{suffix}.png` (ej. `HOSP-000001_xray1.png`)
  - CB-2 cubierto: imagenes corruptas/invalidas se loguean y omiten sin crashear
  - Object key deterministico: `{patient_id}/{filename}` (subidas idempotentes — MinIO sobreescribe)
  - Metodo `ingest_file()` para ingestar una sola imagen (usado por el bootstrap)
  - `src/pipeline/scripts/generate_dummy_images.py` para generar PNGs validos minimos para tests y demos
  - `docs/runbooks/download-radiography-dataset.md` con instrucciones para descargar el dataset real de Kaggle cuando se entrene el modelo
  - 7 tests de integracion contra MinIO real (total 47 tests pasando)
- **Arranque con un unico comando (`docker compose up`):**
  - `src/pipeline/scripts/bootstrap.py` corre al arrancar el servicio pipeline: verifica fixtures en `data/raw/`, sincroniza radiografias a MinIO (skip selectivo basado en filenames) y comprueba conectividad con MongoDB
  - Dockerfile.pipeline con CMD `bootstrap` en lugar de `verify_pyspark`
  - Servicio `pipeline` en docker-compose con `restart: "no"`, `depends_on` condicional a `minio-init` completo y volumen `./data:/app/data:ro`
  - `data/raw/patients.csv`, `data/raw/admissions.csv` y 17 PNGs dummy committeados al repo (~1MB) para arranque offline, determinista y reproducible
- **Configuracion portable sin `.env`:**
  - Todas las variables del docker-compose con defaults (`${VAR:-default}`). Arranca en cualquier maquina sin crear `.env`
  - `.env.example` committeado como referencia opcional
- **Tests con skip limpio:**
  - `tests/pipeline/conftest.py` con hook que detecta disponibilidad de MongoDB/MinIO por TCP y hace skip de los tests de integracion cuando no estan accesibles (evita `KeyError` y errores de setup)
- **T7 (Validacion y limpieza PySpark):**
  - `src/pipeline/processors/data_validator.py` con `DataValidator`: separa filas validas de rechazadas con motivo (`rejection_reason`). Reglas first-failure-wins
  - Validacion de pacientes: external_id `HOSP-NNNNNN`, name no vacio, birth_date ISO, gender M/F/Other, blood_type en set valido
  - Validacion de ingresos: patient_external_id, admission_date ISO, department no vacio, status admitted/discharged/transferred
  - `src/pipeline/processors/data_cleaner.py` con `DataCleaner`: trim whitespace y dedup via `dropDuplicates(subset=...)` por external_id (pacientes) o por (patient_external_id, admission_date, department) (ingresos)
  - 13 tests unitarios con schemas PySpark explicitos (total 67 tests pasando)
  - Smoke test contra datos reales: 5.150 patients -> 4.886 validos + 264 rechazados (121 fecha mala, 72 nombre vacio, 71 gender invalido). 10.000 admissions -> 9.507 validos + 493 rechazados
- **T8 (Transformacion PySpark):**
  - `src/pipeline/processors/data_transformer.py` con `DataTransformer`
  - `enrich_patients`: anade columna `age` con calculo mes-a-mes (meses_entre / 12 redondeado abajo). Acepta `reference_date` para tests deterministas
  - `enrich_admissions`: anade `diagnosis_category` mapeando codigos ICD-10 a {COVID-19, Pneumonia, Other, Unknown} alineado con la clasificacion triple del proyecto
  - Agregaciones: `admissions_by_department`, `admissions_by_month` (yyyy-MM), `admissions_by_diagnosis_category`
  - 15 tests unitarios (total 85 tests pasando)
  - Smoke test end-to-end contra datos reales: categorias COVID-19/Pneumonia/Other al 9.7%/19.5%/70.8% (cuadra con 1/10, 2/10, 7/10 de los ICD-10 de T3). Departamentos equilibrados. Piramide de edad realista
- **T9 (Orquestador + watcher):**
  - `src/pipeline/orchestrator.py` con `PipelineOrchestrator`: coordina E→T→L (ingesta, validacion, limpieza, transformacion, carga a MongoDB). Registra cada ejecucion en `pipeline_runs` con stats y gestiona fallos (CB-5) marcando el run como `failed` con mensaje de error
  - `MongoWriter.bulk_upsert_patients_with_admissions`: upsert de pacientes con admissions embebidas como subdocumentos (modelo NoSQL). Sobrescribe el array en cada batch — idempotente para reruns del mismo CSV
  - `src/pipeline/watcher.py` con `IncomingFilesWatcher`: usa `watchdog` para monitorizar `data/incoming/`, dispara el callback cuando llegan `patients.csv` + `admissions.csv` y mueve los ficheros procesados a `data/incoming/processed/`
  - `watchdog==4.0.0` anadido a requirements-pipeline.txt
  - 11 tests nuevos (5 orchestrator + 4 watcher + 2 nuevos mongo_writer). Total 98 tests pasando
  - Smoke test end-to-end contra datos reales: 14.249 records procesados (4.745 patients + 9.504 admissions embebidas) + 757 rechazados. Distribucion natural de admissions por paciente
- **Auditoria interna del codigo — 4 bloqueantes arreglados:**
  - **API `/radiographies` ahora devuelve datos reales:** el bootstrap solo subia las imagenes a MinIO pero descartaba el retorno de `ImageIngester`. Ahora persiste los metadatos en MongoDB (embebidos en `patients.radiographies` via `add_radiography_to_patient`, idempotente). 17 radiografias atadas a sus patients tras `docker compose up`
  - **`POST /api/v1/pipeline/trigger` operativo:** el endpoint devolvia 503 porque la app real se construia sin `pipeline_launcher`. Nuevo modulo `src/api/pipeline_launcher.py` con `PipelineLauncher` (start_run sincrono + execute como BackgroundTask). `build_app` lo crea por defecto, configurable a `None` en tests
  - **Orchestrator robusto frente a fallos al iniciar:** `start_pipeline_run()` movido dentro del `try`, con fallback que loguea pero no propaga si Mongo tampoco puede registrar el run fallido. `run_id` ahora opcional en `run_from_files` (acepta uno existente del launcher para no duplicar runs)
  - **Test de regresion CB-5/MinIO:** nuevo test que verifica que `ImageIngester` con MinIO inalcanzable NO devuelve metadatos como si todo hubiera ido bien (no silent failure)
- **T12 (Tests E2E sobre criterios de aceptacion):**
  - `tests/e2e/test_acceptance_criteria.py` con un test por cada CA-1..CA-8 de la spec
  - `tests/e2e/conftest.py` con fixtures para MongoDB, MinIO y API que hacen skip limpio si los servicios no estan accesibles
  - 14 tests pasando (1+ por cada criterio): CA-1 patients en MongoDB, CA-2 radiografias en MinIO con object keys correctos, CA-3 rejected_records con motivos, CA-4 enriquecimiento (age + diagnosis_category), CA-5 API sirviendo todo, CA-6 idempotencia (sin duplicados + run twice), CA-7 stack operativo, CA-8 fallos explicitos no silenciosos
  - Ahora el proyecto tiene **124 tests verdes** total (98 unit + 12 API + 14 E2E)
- **T11 (Docker Compose completo + bootstrap end-to-end):**
  - `bootstrap.py` ampliado: tras sincronizar radiografias a MinIO, ejecuta el pipeline ETL completo (PySpark) si MongoDB esta vacio. Idempotente (skip si ya hay patients)
  - `docker compose up` (un solo comando) deja el sistema completo operativo en menos de 1 minuto: MongoDB + MinIO + 4.745 patients procesados + 8.569 admissions + 17 radiografias en MinIO + API REST sirviendo
  - Re-arranque (warm restart) en ~1 segundo (skips idempotentes)
  - README actualizado con la realidad: ejemplos curl de la API, tabla de URLs/credenciales, descripcion del flujo ETL, estructura completa, estado del proyecto al dia
- **T10 (API REST con FastAPI):**
  - `src/api/main.py` con `build_app()` (factory testable) y lifespan moderno (asynccontextmanager)
  - `src/api/mongo_reader.py` con `MongoReader` (CQRS-light: separado del writer) con operaciones de lectura + unwind para admissions/radiografias flattenadas
  - `src/api/models.py` con schemas Pydantic V2 (Patient, Admission, Radiography, PipelineRun, pages paginadas)
  - Routers: `data.py` (GET /patients, /patients/{id}, /admissions, /radiographies) y `pipeline.py` (GET /pipeline/runs, /pipeline/status, POST /pipeline/trigger con BackgroundTasks)
  - `/api/v1/health` para healthchecks
  - Servicio `api` en docker-compose reutilizando la misma imagen del pipeline + CMD de uvicorn. Health check HTTP
  - `fastapi==0.111.0`, `uvicorn[standard]==0.30.0`, `httpx==0.27.0` anadidos
  - 12 tests nuevos (7 data + 4 pipeline + 1 health) con TestClient contra MongoDB real. **Total 110 tests pasando**
  - Smoke test end-to-end con stack real (`docker compose up`): API responde con 4.745 patients, 8.569 admissions, pipeline status recupera el run anterior con sus stats (14.249 processed, 757 rejected)

### Changed

- **Polyglot persistence: SQLite + SQLAlchemy anadido como capa relacional complementaria (ADR-004)**.
  MongoDB sigue siendo dueno de `patients` (con `admissions` y `radiographies` embebidas) y `rejected_records` con `raw_data` completo. MinIO sigue siendo dueno de los PNG. SQLite estrena dos tablas: `pipeline_runs` (auditoria de cada ejecucion del ETL) y `data_quality_summary` (metricas agregadas por dimension). Motivacion: alineamiento con el Bloque 7 del Master (SQLAlchemy + SQLite usados en clase con Eric) y demostrar dominio del modelo relacional ademas del documental.

  **Breaking changes:**
  - Identificador del run en las respuestas de la API: antes campo `_id` (alias de Mongo, ObjectId de 24 hex), ahora campo `id` (clave plana de SQLAlchemy, UUID v4 de 36 chars con guiones). Afecta a `PipelineRun` (Pydantic), `GET /api/v1/pipeline/runs`, `GET /api/v1/pipeline/status` y al `run_id` que devuelve `POST /api/v1/pipeline/trigger`. La referencia cruzada `rejected_records.pipeline_run_id` en MongoDB tambien se guarda ahora como UUID string (soft cross-DB reference, sin FK enforcement)
  - Los endpoints `/api/v1/pipeline/runs` y `/api/v1/pipeline/status` leen ahora de SQLite via `SqlReader` (antes de MongoDB)
  - Nuevos endpoints: `GET /api/v1/pipeline/quality-summary` (snapshot por dimension del ultimo run) y `GET /api/v1/pipeline/quality-summary/history?dimension=...&limit=...&offset=...` (historico paginado con `total` real, count por dimension, no `len(items)` de la pagina)

  El bug fix de admissions huerfanas se mantiene cubierto en ambos almacenes: el huerfano va a `rejected_records` (Mongo) Y se contabiliza en `data_quality_summary.admissions.rejected` (SQL). Volumen Docker named `pipeline-db` montado en pipeline+watcher+api, con WAL mode habilitado para concurrencia (montado `rw` tambien en API porque WAL necesita escribir sidecars `.wal`/`.shm`). Smoke real end-to-end: 4.745 patients, 1.692 rejected (264 patients + 1.428 admissions incl. 935 huerfanos), cuadre exacto entre Mongo y SQL. Persistencia verificada con `docker compose stop && start`; `docker compose down -v` borra los tres volumenes (`mongo-data`, `minio-data`, `pipeline-db`).
- PostgreSQL reemplazado por MongoDB (NoSQL) tras detectar texto oculto en el enunciado
- docker-compose y .env limpiados (variables sin consumidor eliminadas, redundancias eliminadas)
- `ImageIngester`: campo `capture_date` renombrado a `ingested_at` (el nombre anterior era enganoso: guardaba la fecha de ingesta, no la de captura real de la radiografia)
- `ImageIngester`: object key pasa de `{patient_id}/{timestamp}_{filename}` a `{patient_id}/{filename}` (deterministico → subidas idempotentes)
- `DataCleaner`: reemplazada la window function con `monotonically_increasing_id` por `dropDuplicates(subset=...)` — mas idiomatico y sin no-determinismo entre particiones
- `bootstrap.py`: skip selectivo (diff entre filenames locales y object_keys en MinIO) en vez de skip total si existe cualquier objeto en el bucket
- `CSVIngester`: el log de ingesta ya no fuerza `df.count()` (eliminaba un action innecesario sobre el DataFrame)
- **Deep Learning: PyTorch reemplazado por Keras/TensorFlow** tras auditar el temario del Master. La asignatura de Aprenentatge Automatic (Jordi, Bloque 6) usa exclusivamente `keras.Sequential`, `Conv2D`, `MaxPooling2D`, `Dropout`, `EarlyStopping` y normalizacion `pixels/255`. Ver ADR-003. Coste de migracion: cero (el modelo aun no estaba implementado). README, CLAUDE.md, backlog y lessons actualizados
- **Watcher integrado como servicio real en docker-compose** (antes solo existia como modulo Python con tests unitarios, pero sin proceso vivo en produccion). Cierra el lado automatico de RF-7 / CA-1: dropear `patients.csv` + `admissions.csv` en `data/incoming/` ahora dispara el ETL y mueve los ficheros a `data/incoming/processed/`. Nuevos artefactos: `src/pipeline/scripts/watcher_daemon.py` (entrypoint long-running), `data/incoming/` con volumen rw, servicio `watcher` en compose con `restart: unless-stopped`, test E2E `test_watcher_integration.py`

### Fixed

- `DataValidator`: las reglas `isin` (gender, blood_type, status) no capturaban valores `null` por la logica ternaria de PySpark. Anadido `col.isNull() |` a las tres reglas, con tests de regresion. Descubierto cuadrando los numeros del smoke test
- `MongoWriter.add_radiography_to_patient`: no era idempotente (violaba CB-4). Ahora usa `$ne` sobre `minio_object_key` para evitar anadir la misma radiografia dos veces al array del paciente. Test de regresion anadido
- `ImageIngester`: dos llamadas separadas a `datetime.now()` podian generar timestamps con microsegundos distintos. Ahora se calcula una sola vez por imagen

### Removed

- Variables `MONGO_USER` y `MONGO_PASSWORD` del `.env` (sin consumidor real, generaban impresion falsa de auth en MongoDB)
- Variable `MONGO_INITDB_DATABASE` del compose (redundante con script de init)
- Acceso a `_client.admin.command("ping")` desde fuera de `MongoWriter`. Reemplazado por el metodo publico `ping()`
