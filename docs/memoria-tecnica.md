# Memoria técnica — Sistema Inteligente de Soporte Hospitalario

> **Proyecto:** laSalle Health Center — Sistema de soporte clínico con clasificación de radiografías y procesamiento de datos a escala
> **Autoría:** Alejandro Marinas y Yago
> **Programa:** Máster en AI & Big Data
> **Fecha del documento:** 2026-05-18
> **Estado:** versión final
> **Repositorio:** `MarinasAlejandro/lasalle-hospital`

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Contexto y problema](#2-contexto-y-problema)
3. [Arquitectura del sistema](#3-arquitectura-del-sistema)
4. [Datos](#4-datos)
5. [Pipeline ETL](#5-pipeline-etl)
6. [Modelo de IA — Clasificación de radiografías](#6-modelo-de-ia--clasificación-de-radiografías)
7. [API REST](#7-api-rest)
8. [Dashboard de visualización](#8-dashboard-de-visualización)
9. [Resumen de decisiones técnicas (ADRs)](#9-resumen-de-decisiones-técnicas-adrs)
10. [Operación e infraestructura](#10-operación-e-infraestructura)
11. [Testing y verificación](#11-testing-y-verificación)
12. [Resultados](#12-resultados)
13. [Limitaciones y reflexión crítica](#13-limitaciones-y-reflexión-crítica)
14. [Consideraciones éticas y legales](#14-consideraciones-éticas-y-legales)
15. [Uso de IA generativa y metodología SDD](#15-uso-de-ia-generativa-y-metodología-sdd)
16. [Conclusiones](#16-conclusiones)
17. [Anexos](#17-anexos)

---

## 1. Resumen ejecutivo

Este proyecto implementa, para el hospital ficticio **laSalle Health Center**, un sistema completo de soporte a la decisión clínica formado por cuatro piezas interdependientes:

1. Un **pipeline ETL** con PySpark que ingesta datos clínicos tabulares (pacientes e ingresos) e imágenes de radiografía, los valida, los limpia y los persiste en los almacenes apropiados.
2. Un **modelo de Deep Learning** (CNN custom en Keras/TensorFlow) que clasifica radiografías de tórax en tres clases — `Normal`, `Pneumonia`, `COVID-19` — como **asistencia al diagnóstico**.
3. Una **API REST** en FastAPI que expone los datos procesados y la inferencia del modelo.
4. Un **dashboard** en Streamlit que actúa como centro de control hospitalario: vista de pacientes, calidad del pipeline, runs operativos, y demo del clasificador.

La arquitectura se despliega como un único `docker compose up` que orquesta siete servicios (MongoDB, MinIO, inicializador de buckets, pipeline, API, watcher y dashboard) y deja el sistema listo en menos de un minuto. El estado actual del repositorio contiene **275 tests automáticos verdes** (más un skip controlado), siete ADRs documentadas y artefactos vivos de la metodología SDD aplicada durante todo el desarrollo.

El **modelo entrenado** sobre el split de test (1.515 radiografías del *COVID-19 Radiography Database* de Kaggle) alcanza una *accuracy* de **0,8719** y un **macro-F1 de 0,8456**, con un *recall* por clase de 0,926 (Normal), 0,933 (Pneumonia) y **0,695 (COVID-19)**. Esta última cifra es el principal límite clínico del sistema y se discute en detalle en los capítulos de resultados, limitaciones y ética: el sistema se entrega como herramienta de **asistencia**, nunca como diagnóstico final.

El proyecto está construido con metodología **SDD (Spec-Driven Development)**: cada feature pasa por las fases `/spec -> /planificar -> /tareas -> /implementar -> /revisar`, con artefactos versionados en `specs/`, `design/`, `tasks/` y `decisions/`. El uso de IA generativa como herramienta de pareo en el desarrollo está documentado sesión a sesión en `docs/diario-ia.md` y se trata explícitamente en el capítulo 15.

### 1.1. Cifras de referencia

| Indicador | Valor |
|---|---|
| Servicios Docker orquestados | 7 (mongodb, minio, minio-init, pipeline, api, watcher, dashboard) |
| Volúmenes Docker persistentes | 3 (`mongo-data`, `minio-data`, `pipeline-db`) |
| Almacenes de datos heterogéneos | 3 (MongoDB, SQLite, MinIO) |
| Pacientes procesados desde el dataset sintético | 4.745 |
| Admisiones embebidas en MongoDB | 8.569 |
| Tests automáticos verdes | 275 (+ 1 skip esperado) |
| ADRs documentadas | 7 |
| Specs aprobadas | 4 (`pipeline-datos`, `sqlite-pipeline-metadata`, `clasificacion-radiografias`, `dashboard`) |
| Accuracy del modelo (test split) | 0,8719 |
| Macro-F1 del modelo (test split) | 0,8456 |
| Tamaño del artefacto del modelo | 21 MB (formato `.keras`) |

### 1.2. Estructura del documento

Los capítulos 2 a 8 describen **qué se ha construido**: contexto, arquitectura, datos, pipeline, modelo, API y dashboard. El capítulo 9 sintetiza en una tabla las **decisiones técnicas** (ADRs) que justifican cómo se ha construido. Los capítulos 10 a 12 cubren **cómo se opera y se verifica** el sistema y los **resultados** obtenidos. Los capítulos 13 a 15 son reflexión crítica: **limitaciones**, **ética y legalidad** y un capítulo específico dedicado al **uso de IA generativa y a la metodología SDD**, por ser un eje explícito del enunciado del Máster. El capítulo 16 cierra con conclusiones y trabajo futuro. Los anexos consolidan referencias a artefactos vivos del repositorio (specs, designs, ADRs, runbooks, diario).

---

## 2. Contexto y problema

### 2.1. Escenario clínico

El hospital ficticio **laSalle Health Center** dispone de tres tipos de información que hoy gestiona de forma manual o fragmentada:

- **Historias clínicas tabulares**: ficheros con datos demográficos de pacientes y registros de ingresos (admisiones), departamentos, fechas y categorías diagnósticas.
- **Radiografías de tórax** en formato PNG, asociadas a pacientes concretos, sin clasificación automatizada.
- **Logs y trazas operativas** que no se consolidan en ningún cuadro de mando.

El hospital carece de un sistema que (a) procese estos datos de forma sistemática y reproducible, (b) ofrezca asistencia automatizada al diagnóstico por imagen y (c) presente la información en un cuadro de mando único accesible desde un navegador. El proyecto se construye para cubrir esos tres huecos sin pretender reemplazar el juicio clínico humano.

### 2.2. Problema concreto que resuelve el proyecto

El problema operacional se descompone en cuatro subproblemas, que se han trabajado como features independientes siguiendo la metodología SDD:

1. **Ingesta y procesamiento a escala** de datos clínicos heterogéneos (CSVs + imágenes) sobre un *framework* de cómputo distribuido (PySpark), con validación, deduplicación y enriquecimiento, persistiendo el resultado en almacenes adecuados a cada tipo de dato.
2. **Clasificación automática** de radiografías de tórax como `Normal`, `Pneumonia` o `COVID-19`, empleando una **CNN propia** entrenada desde cero (sin *transfer learning*) sobre el *COVID-19 Radiography Database* de Kaggle. Esta decisión se justifica formalmente en la ADR-005, alineada con el Bloque 6 del Máster.
3. **Servicio HTTP** que expone tanto los datos procesados como la inferencia del modelo a través de una API REST documentada (FastAPI + Swagger), con contratos estables y separación lectura/escritura.
4. **Cuadro de mando** que sintetiza el estado del sistema (datos cargados, pipeline ejecutándose, modelo cargado, métricas de calidad) y permite a un operador clínico no técnico inspeccionar pacientes, lanzar la clasificación de una radiografía y auditar el histórico de ejecuciones del ETL.

### 2.3. Alcance, supuestos y exclusiones

- **Dentro del alcance**:
  - Procesamiento *batch* con PySpark sobre datasets sintéticos generados con *Faker* (offline, reproducibles).
  - Persistencia poliglota (MongoDB + SQLite + MinIO) — ver ADR-004.
  - Modelo CNN custom con arquitectura definida (ADR-005) y *pipeline* de evaluación con métricas clínicas (no solo *accuracy*).
  - API REST sin autenticación (entorno *dev*) con endpoints versionados (`/api/v1/...`).
  - Dashboard *API-only* (no accede directamente a las bases de datos — ADR-007).
  - Despliegue completo con `docker compose up` desde cero, sin pasos manuales adicionales.
- **Fuera del alcance**:
  - Procesamiento *streaming* en tiempo real (todo es *batch* con un *watcher* sobre `data/incoming/`).
  - Integraciones con sistemas hospitalarios reales (HIS, HL7, FHIR).
  - Datos reales de pacientes — todo el dato tabular es sintético, generado con *Faker* y *seed* fija.
  - Autenticación, autorización y cifrado en tránsito (entorno académico de demostración).
  - Despliegue en cloud o Kubernetes.

### 2.4. Metodología de trabajo

El proyecto se ha desarrollado siguiendo **Spec-Driven Development** (SDD), un flujo en cinco fases en el que la especificación funcional es el artefacto central:

```
/spec  ->  /planificar  ->  /tareas  ->  /implementar  ->  /revisar
 QUÉ         CÓMO          EN QUÉ        CÓDIGO          ¿CUMPLE?
                           ORDEN
```

Cada feature relevante (pipeline, polyglot SQLite, clasificador, dashboard) tiene su trío de artefactos `specs/<feature>.md`, `design/<feature>.md` y `tasks/<feature>.md` versionados en el repositorio. Las decisiones técnicas no triviales se documentan como ADRs en `decisions/`. La cadena de trazabilidad **requisito -> componente -> tarea -> test -> criterio de aceptación** es explícita: nada se implementa sin estar atado a un requisito de una spec aprobada.

El capítulo 15 desarrolla en detalle el uso conjunto de SDD y de asistentes de IA generativa, complementado con revisión técnica del equipo y contraste contra la spec, que ha caracterizado todo el desarrollo del proyecto.

---

## 3. Arquitectura del sistema

### 3.1. Visión general

El sistema se modela como un conjunto de servicios contenedorizados con un único punto de entrada HTTP para los consumidores externos (la **API REST**). La API es el componente que **lee directamente** de MongoDB, SQLite y MinIO (a través de sus `readers` y del cliente MinIO embebido en el endpoint de imágenes); el **dashboard**, en cambio, es un cliente HTTP más de la API y **nunca abre conexiones directas** a esos almacenes. Pipeline y watcher sí escriben directamente en los almacenes porque ese es su trabajo. El despliegue arranca **siete servicios** y crea **tres volúmenes persistentes** con un único `docker compose up`.

```
   Usuario --HTTP-->  Dashboard (Streamlit, :8501)
   (navegador)              |
                            | HTTP (api_client)
                            v
                        +------------------------+
                        |     API REST           |
                        |   (FastAPI, :8000)     |
                        |   readers (Mongo/SQL)  |
                        |   + MinIO client       |
                        |   + classify endpoint  |
                        +------------------------+
                          |        |        |
                lee/inferr|   lee  |   lee  |
                          v        v        v
                       MongoDB  SQLite    MinIO
                       (docs)   (runs +   (PNGs)
                                quality)
                          ^        ^        ^
                          | write  | write  | write
                          +-----+--+--------+
                                |
                  +-------------+--------------+
                  |                            |
            Pipeline ETL                   Watcher
            (PySpark, batch)               (watchdog,
                                            long-running)
```

El dashboard no aparece como vecino de ningún almacén: todas sus consultas pasan por la API. Las únicas escrituras directas a los almacenes provienen del **pipeline** y del **watcher** (dos puntos de entrada del mismo `PipelineOrchestrator`); todas las lecturas operativas pasan por la API.

### 3.2. Servicios desplegados

| Servicio | Imagen | Responsabilidad |
|---|---|---|
| `mongodb` | `mongo:7` | Base documental: `patients` (con `admissions` y `radiographies` embebidas), `rejected_records` con `raw_data` heterogéneo |
| `minio` | `minio/minio` (S3-compatible) | Almacenamiento de objetos: PNG de radiografías y *backups* crudos |
| `minio-init` | `minio/mc` | *Job* one-shot que crea los buckets (`radiographies`, `raw-backups`) y termina |
| `pipeline` | `hospital-pipeline` (build local) | Ejecuta el bootstrap (sincroniza imágenes, lanza ETL si Mongo está vacío), expone CLIs PySpark |
| `api` | `hospital-pipeline` (misma imagen) | FastAPI + Uvicorn en `:8000`, carga el modelo ML al arrancar (*lifespan*) |
| `watcher` | `hospital-pipeline` (misma imagen) | Proceso *long-running* que vigila `data/incoming/` y dispara el ETL cuando aparecen `patients.csv` + `admissions.csv` |
| `dashboard` | `hospital-dashboard` (build local) | Streamlit en `:8501`, imagen ligera (~240 MB) sin TensorFlow ni PySpark (ADR-007) |

Tres servicios — `pipeline`, `api` y `watcher` — comparten la **misma imagen Docker** (`hospital-pipeline`, ~2 GB con PySpark + TensorFlow + FastAPI + *watchdog*), cambiando solo el `CMD`. Sacrifica tamaño a cambio de eliminar duplicación de capas y bloqueos de versión entre componentes que comparten código (ADR-006). El dashboard (`hospital-dashboard`) sí va en imagen independiente (~240 MB) porque su árbol de dependencias no necesita TF ni PySpark (ADR-007).

### 3.3. Persistencia poliglota

Una de las decisiones de diseño nucleares del proyecto es la **persistencia poliglota** (ADR-004): cada tipo de dato vive donde su forma encaja, sin duplicar fuente de verdad.

| Almacén | Datos | Justificación |
|---|---|---|
| **MongoDB** | `patients` (con `admissions` y `radiographies` embebidas), `rejected_records` con `raw_data` heterogéneo | Datos con jerarquía natural (paciente ↔ admisiones ↔ radiografías) y payloads heterogéneos (cada motivo de rechazo lleva campos distintos). Encajan en documental sin necesidad de *joins* artificiales. ADR-002 |
| **SQLite** | `pipeline_runs` (auditoría de cada ejecución), `data_quality_summary` (métricas agregadas por dimensión) | Datos tabulares de esquema fijo, con FK natural entre las dos tablas y queries analíticas (agregaciones, históricos). Bloque 7 del Máster usa SQLAlchemy + SQLite, por lo que la elección está alineada con la formación. ADR-004 |
| **MinIO** | PNG de radiografías + backups crudos | Binarios. No tiene sentido meterlos en una base de datos. S3-compatible para facilitar migración a cloud si fuera necesario. |

La **referencia cruzada Mongo -> SQLite** (campo `rejected_records.pipeline_run_id` en MongoDB apuntando al `id` UUID de SQLite) es una *soft reference* sin enforcement de FK, asumida explícitamente y documentada en la spec correspondiente.

### 3.4. Estructura del repositorio

El árbol del repositorio refleja la separación por capas y la metodología SDD: los artefactos SDD (`specs/`, `design/`, `tasks/`, `decisions/`) en la raíz, el código de cada feature en `src/{pipeline,ml,api,dashboard}/`, los tests reflejando esa misma estructura en `tests/`, y los datos en `data/{raw,incoming,db,models}/`. El árbol completo está en `README.md`.

### 3.5. Flujo de datos end-to-end

Un cambio de datos atraviesa el sistema en el siguiente orden, descrito desde la perspectiva del operador:

1. El operador coloca dos ficheros (`patients.csv`, `admissions.csv`) en `data/incoming/`.
2. El servicio `watcher` detecta el evento de filesystem, lanza el `PipelineOrchestrator`, registra el inicio del run en SQLite (`status=running`, `trigger_type=watcher`).
3. El orchestrator ingesta con `CSVIngester` (PySpark) -> valida con `DataValidator` -> limpia con `DataCleaner` -> enriquece con `DataTransformer` (calcula edad y categoría diagnóstica) -> persiste con `MongoWriter` (upsert idempotente con admisiones embebidas).
4. Los registros rechazados se escriben en `rejected_records` (MongoDB) con el motivo de rechazo y `pipeline_run_id`.
5. Al cerrar el run, el orchestrator actualiza SQLite (`status=success/failed`, contadores, timestamps) y escribe el `data_quality_summary` (una fila por dimensión: `patients`, `admissions`).
6. El watcher mueve los ficheros procesados a `data/incoming/processed/`.
7. La API expone el estado actualizado a través de `GET /api/v1/pipeline/status`, `GET /api/v1/pipeline/runs` y `GET /api/v1/pipeline/quality-summary` (los `readers` consultan SQLite y MongoDB; el dashboard no toca esos almacenes directamente).
8. El dashboard refresca su vista *Overview* mediante `st.fragment(run_every=30)`, llama a la API por HTTP y muestra el nuevo run en *Pipeline runs*.

Para las radiografías, el sistema **no expone hoy un endpoint de subida operativa**. La forma soportada de incorporar imágenes al bucket es como *fixture* preparado antes del arranque: los PNG que estén en `data/raw/images/` (los 17 dummies) y, si el dataset Kaggle está descargado en local, las seis `HOSP-PRES-*`, son sincronizados a MinIO por el **bootstrap** al ejecutar `docker compose up` mediante `ImageIngester`, que también embebe sus metadatos en el documento `patients` correspondiente vía `MongoWriter.add_radiography_to_patient` (idempotente). Para añadir imágenes adicionales se reejecuta el bootstrap (`docker compose run --rm pipeline`), que sigue siendo idempotente. Una vez en MinIO + Mongo, el endpoint `POST /api/v1/radiographies/classify` puede ejecutar inferencia sobre cualquiera de ellas y persistir la clasificación en el subdocumento embebido.

### 3.6. Trade-offs arquitectónicos relevantes

A modo de resumen, las decisiones arquitectónicas con mayor impacto son:

| Decisión | Alternativa descartada | Motivo principal |
|---|---|---|
| MongoDB para datos clínicos | PostgreSQL relacional | Lectura cuidadosa del enunciado (que orienta hacia un almacén NoSQL para los datos clínicos) sumada a la jerarquía natural paciente -> admisiones -> radiografías, que encaja con un modelo documental. ADR-002 |
| Persistencia poliglota (Mongo+SQLite+MinIO) | Solo Mongo+MinIO | MongoDB + MinIO ya cumple "≥ 2 tipos de almacenamiento". SQLite **refuerza** la arquitectura añadiendo una capa relacional/tabular para los metadatos operativos (auditoría de runs + agregados de calidad), alineada con SQLAlchemy + SQLite del Bloque 7 del Máster. ADR-004 |
| Keras / TensorFlow (en lugar de PyTorch) | PyTorch | La asignatura de Aprenentatge Automàtic del Máster usa exclusivamente Keras. ADR-003 |
| CNN custom sin *transfer learning* | EfficientNet preentrenado | Alineación literal con el Bloque 6 del Máster. ADR-005 |
| Una imagen compartida pipeline/api/watcher | Tres imágenes distintas | Evitar duplicación de capas y desincronización de versiones entre componentes que comparten código. ADR-006 |
| Dashboard *API-only* en imagen independiente | Dashboard accediendo a Mongo/SQLite/MinIO directamente | Aislamiento de capa, imagen ligera (~240 MB), reutiliza los contratos HTTP ya implementados. ADR-007 |

Estas decisiones se desarrollan formalmente en los ADR-001 a ADR-007 (capítulo 9) y se referencian a lo largo de los siguientes capítulos cuando se justifica una elección concreta.

---

## 4. Datos

### 4.1. Tipos de datos manejados

El sistema trabaja con tres familias de datos heterogéneas, cada una persistida en el almacén que mejor encaja con su forma:

| Familia | Naturaleza | Fuente | Almacén destino |
|---|---|---|---|
| Pacientes | Tabular relacional con campos demográficos | `data/raw/patients.csv` (sintético, *Faker*) | MongoDB (`patients`) |
| Admisiones / ingresos | Tabular relacional con FK a paciente | `data/raw/admissions.csv` (sintético) | MongoDB (embebido en `patients.admissions`) |
| Radiografías (binarios + metadatos) | Imagen PNG + metadatos | `data/raw/images/` (dummies para *smoke*) + `data/raw/covid_radiography/` (dataset Kaggle, solo en local) | MinIO (binario) + MongoDB (metadatos embebidos en `patients.radiographies`) |
| Métricas operativas | Tabular plano (auditoría + agregados) | Generado por el orchestrator | SQLite (`pipeline_runs`, `data_quality_summary`) |
| Rechazos del pipeline | Documento heterogéneo con `raw_data` específico de cada motivo | Generado por `DataValidator` y `DataCleaner` | MongoDB (`rejected_records`) |

### 4.2. Datos sintéticos del pipeline (CSVs)

Los CSVs de pacientes e ingresos están **generados con Faker** (`src/pipeline/scripts/generate_data.py`) y commiteados al repositorio para que el arranque sea reproducible y offline. Esta decisión deliberada — *no usar* datos reales — es la solución natural al problema ético y legal de manejar datos clínicos identificables (ver capítulo 14).

**`data/raw/patients.csv`** (5.150 filas, ~5.000 pacientes + ~5% de casos borde intencionados):

| Campo | Tipo | Ejemplo | Notas |
|---|---|---|---|
| `external_id` | string | `HOSP-000042` | Formato fijo `HOSP-NNNNNN`, validado |
| `name` | string | `María García López` | Puede venir vacío en casos borde |
| `birth_date` | string ISO | `1972-08-14` | Puede venir mal formada en casos borde |
| `gender` | string | `F` | Set válido: `M`, `F`, `Other`; otros valores se rechazan |
| `blood_type` | string | `A+` | Set válido: 8 grupos sanguíneos estándar |

**`data/raw/admissions.csv`** (10.000 filas):

| Campo | Tipo | Ejemplo | Notas |
|---|---|---|---|
| `patient_external_id` | string | `HOSP-000042` | FK lógica a `patients.external_id` — puede ser huérfana (intencionado) |
| `admission_date` | string ISO | `2024-03-15` | |
| `discharge_date` | string ISO | `2024-03-22` | Opcional |
| `department` | string | `Urgencias` | 12 valores fijos (Cardiología, Oncología, Urgencias, etc.) |
| `diagnosis_code` | string | `J18.9` | Código ICD-10; distribución intencionada 10% COVID-19, 20% Pneumonia, 70% Other |
| `status` | string | `discharged` | Set válido: `admitted`, `discharged`, `transferred` |

**Casos borde intencionados** introducidos por el generador (parámetro `--seed 42` por defecto):

- **Nulos** en campos obligatorios (~5%): nombres vacíos, fechas faltantes, *gender* nulo. Permiten verificar CB-3 ("registros con valores nulos en campos obligatorios se rechazan con motivo").
- **Duplicados** (~3%): mismo `external_id` repetido. Permiten verificar CB-4 ("registros duplicados se deduplican antes de persistir").
- **Fechas malformadas**: `1972-13-44` o cadenas no-ISO. Permiten verificar la robustez del parser.
- **Valores fuera de set**: `gender=X`, `status=unknown`, `blood_type=ZZ`. Permiten verificar que las reglas `isin` capturan correctamente lo fuera de dominio (con el bug fix de `null` documentado en `lessons.md`).
- **Admisiones huérfanas**: ~10% de `patient_external_id` apuntan a pacientes inexistentes. Permiten verificar la validación cruzada (cross-entity) entre `admissions` y `patients`.

El script de generación es **determinista por *seed***, lo que permite que cualquier desarrollador regenere exactamente el mismo dataset:

```bash
docker compose run --rm --entrypoint "" pipeline \
  python -m src.pipeline.scripts.generate_data --seed 42
```

El resultado de procesar este dataset por el pipeline se detalla con todas sus cifras en la sección 5.8 (métricas observadas). Estos números se persisten en `data_quality_summary` (una fila por dimensión) y son consultables vía `GET /api/v1/pipeline/quality-summary` o desde la vista *Calidad de datos* del dashboard.

### 4.3. Radiografías de tórax (binarios)

El sistema maneja tres familias de imágenes con propósitos distintos. Cada una se identifica por el prefijo del `external_id` del paciente al que se ata:

| Prefijo | Origen | Propósito | Estado en repo |
|---|---|---|---|
| `HOSP-NNNNNN` | Generador `generate_dummy_images.py` | Smoke test del pipeline de ingesta (validan PNG signature, suben a MinIO, se embeben en paciente) | 17 PNGs **dummy 1x1** commiteados en `data/raw/images/` |
| `HOSP-DEMO-001` | Bootstrap genera al vuelo (numpy + Pillow + ImageDraw, 256x256, banda gradiente sintética) | Fixture *out-of-the-box* para que la vista *Clasificador* del dashboard tenga al menos una imagen clasificable sin pedir descarga del dataset real | No commiteada — generada en cada bootstrap |
| `HOSP-PRES-001..006` | Subset de 6 imágenes del *COVID-19 Radiography Database* de Kaggle | Demo con radiografías reales del dataset (2 por clase: COVID, Normal, Viral Pneumonia), más representativa visualmente que la sintética y suficiente para ilustrar el comportamiento del modelo; **sin valor diagnóstico real** sobre ningún paciente | No commiteadas — el bootstrap las copia a MinIO **solo si existen localmente** en `data/raw/covid_radiography/` |

**Particularidad técnica relevante (CB-7)**: los 17 PNGs dummy son archivos **1x1 píxel** intencionadamente mínimos, lo justo para validar la *signature* PNG. Esto los hace válidos como fixture del pipeline de *ingesta*, pero **no clasificables**: la API rechaza con HTTP 422 cualquier imagen con dimensiones inferiores a **32x32 píxeles** (constante `MIN_IMAGE_DIM = 32` en `src/ml/preprocessing.py`), por debajo de las cuales una entrada no puede corresponder a una radiografía real. Adicionalmente, el **dashboard** aplica una heurística más laxa basada en tamaño en bytes (`MIN_CLASSIFIABLE_BYTES = 1024` en `src/dashboard/views/classifier.py`) para **ocultar del dropdown** las imágenes 1x1 antes incluso de mostrarlas, evitando que el operador llegue a intentar clasificarlas. Para que el flujo end-to-end del clasificador funcione *out-of-the-box* sin necesidad de descargar el dataset de Kaggle, el bootstrap genera al vuelo la imagen sintética `HOSP-DEMO-001` (256x256).

La transparencia sobre la naturaleza de `HOSP-DEMO-001` es explícita en la UI: la vista *Clasificador* muestra un banner amarillo con la nota *"imagen sintética de demo — no es una radiografía real"* siempre que esa imagen está seleccionada, y la predicción se etiqueta como **no evidencia clínica**.

### 4.4. Dataset real para entrenamiento del modelo

El modelo de clasificación se entrena sobre el **COVID-19 Radiography Database** (Kaggle), descargado localmente por el operador y **no commiteado al repositorio** por:

1. **Tamaño**: ~0,9 GB en la versión local utilizada (descomprimido).
2. **Licencia**: el dataset tiene términos de uso propios definidos por su autor original que deben respetarse y citarse tal cual el proveedor los publica (ver capítulo 14 y `data/raw/images-demo/README.md`).

El subconjunto utilizado para el entrenamiento incluye tres de las cuatro clases originales:

| Clase del dataset | Etiqueta interna del modelo | Imágenes utilizadas |
|---|---|---|
| `COVID` | `COVID-19` | 3.616 |
| `Normal` | `Normal` | 10.192 |
| `Viral Pneumonia` | `Pneumonia` | 1.345 |
| `Lung_Opacity` | (descartada) | 6.012 |
| **Total utilizado** | — | **15.153** |

La clase `Lung_Opacity` se **descarta explícitamente** porque no encaja en la clasificación triple del proyecto (`Normal` / `Pneumonia` / `COVID-19`): "opacidad pulmonar" es un hallazgo radiológico que puede aparecer en múltiples patologías, no una categoría diagnóstica clasificatoria. Esta decisión está documentada en la spec de clasificación de radiografías y en el reporte clínico (`docs/model-evaluation/report.md`).

El dataset se reparte en **train / validation / test (80 / 10 / 10)** con **partición estratificada** (manteniendo la proporción de clases en cada split) y **seed = 42**. La regla operativa estricta es:

- `train` -> entrenamiento (`fit`)
- `validation` -> callbacks (EarlyStopping, ModelCheckpoint) y guía de hiperparámetros
- `test` -> reporte final al cierre de cada versión candidata del modelo

El split de test queda fijado en **1.515 imágenes** (1.019 Normal + 361 COVID-19 + 135 Pneumonia, manteniendo la proporción del dataset original).

### 4.5. Calidad de datos: validación, limpieza y reporte

El pipeline implementa un esquema de validación **first-failure-wins**: cada fila se evalúa contra una secuencia de reglas y se queda con el primer motivo de rechazo. Las reglas para pacientes son:

1. `external_id` debe coincidir con el patrón `HOSP-\d{6}`.
2. `name` no puede ser vacío ni nulo.
3. `birth_date` debe ser ISO parseable.
4. `gender` debe estar en `{M, F, Other}` (o ser nulo, que también se rechaza).
5. `blood_type` debe estar en el set de 8 grupos sanguíneos válidos.

Para admisiones, análogamente: `patient_external_id` no vacío, `admission_date` ISO, `department` no vacío y `status` en `{admitted, discharged, transferred}`.

Adicionalmente, tras la validación campo a campo, se ejecuta una **validación cruzada (cross-entity)**: las admisiones cuyo `patient_external_id` no apunta a ningún paciente válido se marcan como **huérfanas** y se rechazan en la dimensión `admissions` del *quality summary*. Este detalle fue el origen de un bug-fix relevante documentado en `lessons.md`: las primeras versiones del orchestrator no contabilizaban los huérfanos en el summary, lo que daba la falsa impresión de que el pipeline "perdía" registros. La spec `sqlite-pipeline-metadata.md` recoge explícitamente este caso en su CA-3.

Tras la validación, `DataCleaner` aplica:

- **Trim** conservador de whitespace: solo en `name` (pacientes) y `department` (admisiones), no en todos los campos. La política deliberada es **no tocar los campos de negocio** y normalizar únicamente artefactos obvios de tabulación.
- **Deduplicación**: `dropDuplicates(subset=...)` por `external_id` en pacientes y por la tupla `(patient_external_id, admission_date, department)` en admisiones. Esta elección reemplaza una versión anterior basada en *window functions* con `monotonically_increasing_id`, que sufría de no-determinismo entre particiones (también documentado en `lessons.md`).

El reporte de calidad por ejecución se persiste en SQLite en la tabla `data_quality_summary` (esquema completo en `src/pipeline/storage/sql_models.py`): una fila por dimensión (`patients`, `admissions`) por run, con `total`, `valid`, `rejected`, `rejection_rate` y `pipeline_run_id` como FK lógica a `pipeline_runs`. Y se expone via `GET /api/v1/pipeline/quality-summary` (snapshot del último run) y `GET /api/v1/pipeline/quality-summary/history?dimension=...` (histórico paginado). El dashboard consume estos dos endpoints en la vista *Calidad de datos*, donde un toggle permite mostrar todos los snapshots o esconder por defecto los **snapshots pequeños o de prueba** mediante un umbral por `total` (filtro `total > 100`): un run con dataset vacío o casi vacío enmascararía el comportamiento real del pipeline si se mostrase junto a los runs operativos sin distinción.

### 4.6. Trazabilidad de cada registro

Tres mecanismos juntos garantizan que cada registro persistido pueda trazarse a su origen:

1. **`_source_file`**: columna añadida por `CSVIngester` con el nombre del CSV de origen.
2. **`pipeline_run_id` (UUID v4)**: cada documento de `rejected_records` lleva el UUID del run que lo rechazó (`soft reference` Mongo -> SQLite). Esto permite ir del *quality summary* (SQLite) a los rechazos crudos (Mongo) para un run concreto.
3. **`ingested_at`**: timestamp en los metadatos de cada radiografía en MinIO (renombrado desde `capture_date` por claridad — la fecha real de captura del paciente no la conocemos).

La conjunción de estos tres campos permite responder preguntas como *"¿qué fichero CSV y qué run del pipeline produjo este rechazo concreto?"* sin necesidad de consultar logs.

---

## 5. Pipeline ETL

### 5.1. Visión general del pipeline

El pipeline ETL es el componente con más superficie del sistema y se diseña como una **cadena de etapas** orquestadas por `PipelineOrchestrator` (`src/pipeline/orchestrator.py`):

```
CSVIngester -> DataValidator -> DataCleaner -> DataTransformer -> MongoWriter
                     |                                                  ^
                     v                                                  |
              rejected_records                                   patients +
                  (Mongo)                                       admissions
                                                                 embebidas
ImageIngester -> MinIO (radiographies bucket)
                     |
                     +--> MongoWriter.add_radiography_to_patient

SqlWriter envuelve toda la ejecución: start_pipeline_run al inicio,
finish_pipeline_run + write_quality_summary al final.
```

Cada componente vive en una subcarpeta de `src/pipeline/`: `ingesters/` (csv + image), `processors/` (validator, cleaner, transformer, quality_summary_builder), `storage/` (mongo_writer, minio_client, sql_writer/engine + modelos SQLAlchemy) y `scripts/` (bootstrap, watcher_daemon, generadores).

### 5.2. Ingesta (E)

#### 5.2.1. CSVIngester

`CSVIngester` lee CSVs a *DataFrames* de PySpark. Valida que existan las columnas requeridas (lanza `MissingColumnsError` si no) pero acepta cualquier orden, y añade una columna `_source_file` para trazabilidad. Por decisión documentada en `lessons.md`, no fuerza `df.count()` tras la lectura (era una *action* innecesaria que rompía la optimización perezosa de Spark).

#### 5.2.2. ImageIngester

`ImageIngester` lee PNGs del filesystem, valida la *signature* PNG (primeros 8 bytes coinciden con `\x89PNG\r\n\x1a\n`) y los sube a MinIO con metadatos. El object key es **determinista**: `{patient_id}/{filename}` (sin timestamp en el path, lo que permite que la subida sea idempotente — MinIO sobreescribe sin error).

CB-2 está cubierto: una imagen corrupta o no-PNG se loguea y se omite sin propagar excepción.

Cada imagen genera dos efectos:

1. PNG subido a `MinIO/radiographies/{patient_id}/{filename}`.
2. Documento embebido en `patients.radiographies` (vía `MongoWriter.add_radiography_to_patient`, idempotente con `$ne` sobre `minio_object_key`).

### 5.3. Validación y limpieza (T parte 1)

#### 5.3.1. DataValidator

`DataValidator` separa filas válidas de rechazadas, con una regla *first-failure-wins*: cada fila se queda con el primer motivo de rechazo (no se acumulan motivos). El resultado son dos DataFrames: `valid_df` y `rejected_df`. El `rejected_df` tiene un campo `rejection_reason` con el motivo (`empty_name`, `invalid_birth_date`, `invalid_gender`, `invalid_status`, etc.) y conserva todos los campos originales en `raw_data`.

**Detalle de implementación relevante** (documentado en `lessons.md` como bug-fix): las reglas `isin` para `gender`, `blood_type` y `status` originalmente no capturaban valores `NULL` por la lógica ternaria de PySpark (`null isin {a, b, c} -> null`, no `false`). La fix fue añadir `col.isNull() |` a las tres reglas, con sus tests de regresión correspondientes. Este *gotcha* es uno de los más típicos al trabajar con PySpark y se descubrió cuadrando manualmente los números del smoke test contra los datos sintéticos generados.

#### 5.3.2. DataCleaner

`DataCleaner` aplica dos operaciones después de la validación, intencionadamente conservadoras (la limpieza no debe modificar campos de negocio):

- **Trim** solo en los campos donde el whitespace es un artefacto típico: `name` para pacientes y `department` para admisiones. No se aplica a `external_id`, fechas, género, código diagnóstico, etc., porque cualquier whitespace en esos campos debería haber hecho fallar antes la validación.
- **Deduplicación**: `dropDuplicates(subset=['external_id'])` para pacientes y `dropDuplicates(subset=['patient_external_id', 'admission_date', 'department'])` para admisiones.

Se descartó una versión inicial basada en *window functions* con `monotonically_increasing_id` por su no-determinismo entre particiones — el orden en el que se elegía "qué duplicado conservar" no era estable. `dropDuplicates` es más idiomático en Spark y suficiente para las garantías que se necesitan.

### 5.4. Transformación (T parte 2)

`DataTransformer` enriquece los DataFrames con dos columnas calculadas que son fundamentales para los casos de uso clínicos:

#### 5.4.1. `enrich_patients` — cálculo de edad

Calcula la columna `age` a partir de `birth_date` con precisión mes-a-mes:

```python
age = floor(months_between(reference_date, birth_date) / 12)
```

Acepta un parámetro `reference_date` para tests deterministas (por defecto `current_date()` de Spark). El resultado se cuadra con la pirámide de edad esperada del dataset sintético.

#### 5.4.2. `enrich_admissions` — categoría diagnóstica

Mapea cada `diagnosis_code` (ICD-10) a uno de cuatro valores en `diagnosis_category`:

- `J18.x` y similares -> `Pneumonia`
- `U07.1` y similares -> `COVID-19`
- Otros códigos válidos -> `Other`
- Códigos no reconocidos -> `Unknown`

La distribución observada tras el smoke test contra los datos sintéticos generados es **9,7 % COVID-19 / 19,5 % Pneumonia / 70,8 % Other**, que cuadra con la distribución 1/10, 2/10, 7/10 que el generador (`generate_data.py`) inyecta intencionadamente para que las tres clases estén representadas con peso clínicamente verosímil.

#### 5.4.3. Agregaciones

`DataTransformer` también expone tres métodos de agregación, hoy **implementados y testeados unitariamente** pero todavía no consumidos por la API ni el dashboard. Quedan disponibles como bloque reutilizable para análisis o endpoints futuros sin necesidad de rehacer el cómputo en cada caso de uso:

- `admissions_by_department(df)` -> conteo por departamento.
- `admissions_by_month(df)` -> conteo por mes (formato `yyyy-MM`).
- `admissions_by_diagnosis_category(df)` -> conteo por categoría diagnóstica.

### 5.5. Carga (L)

#### 5.5.1. MongoWriter

`MongoWriter` es el componente que materializa el modelo documental. Su método clave es `bulk_upsert_patients_with_admissions`, que toma listas de diccionarios (pacientes + admisiones por paciente) y ejecuta una operación `bulk_write` de pymongo con `UpdateOne(upsert=True)` por paciente. Las admisiones se **embeben como subdocumentos** en el array `patients.admissions` (no como colección separada con FK).

La idempotencia se garantiza por construcción: re-ejecutar el pipeline con los mismos CSVs sobreescribe el array completo del paciente, sin duplicar admisiones. Esto cubre CA-6 ("ejecutar el pipeline dos veces con los mismos datos no genera duplicados").

#### 5.5.2. SqlWriter

`SqlWriter` (introducido como parte de la feature `sqlite-pipeline-metadata`) es el componente que persiste los metadatos operativos en SQLite. Sus métodos principales son:

- `start_pipeline_run(trigger_type) -> run_id` (UUID v4 string): abre un registro con `status=running` y devuelve el UUID.
- `finish_pipeline_run(run_id, status, counts, error_message=None)`: cierra el registro, guarda `finished_at`, `records_processed`, `records_rejected`, `images_processed` y opcionalmente `error_message`.
- `write_quality_summary(run_id, summaries)`: recibe una **lista** de objetos summary y los persiste en bloque (una fila por dimensión).

El esquema completo vive en `src/pipeline/storage/sql_models.py`. Lo más relevante para entender la arquitectura es que `pipeline_runs.id` es un **UUID v4 string** (independiente del concepto de BSON de Mongo, y referenciado desde `rejected_records.pipeline_run_id` como *soft reference*), mientras que `data_quality_summary.id` es un `Integer autoincrement` interno (la identidad útil aquí es la combinación `pipeline_run_id + dimension`). La tabla `pipeline_runs` incluye un contador específico `images_processed` además de `records_processed` y `records_rejected`, por la naturaleza dual del pipeline (tabular + binario).

SQLite se ejecuta en **modo WAL** (write-ahead logging) para soportar concurrencia entre `pipeline` (escribiendo el run inicial), `watcher` (eventualmente escribiendo otro run) y `api` (leyendo). El volumen Docker named `pipeline-db` se monta `rw` en los tres servicios porque WAL crea ficheros sidecar (`.wal`, `.shm`) en el mismo directorio.

### 5.6. Orquestación y *trigger*s

`PipelineOrchestrator` coordina las etapas y gestiona el ciclo de vida del run. Su método principal, `run_from_files(patients_csv, admissions_csv, trigger_type, run_id=None)`, abre un run en SQLite si no recibe uno, ejecuta toda la cadena E->T->L dentro de un `try/except`, y cierra el run con `status='success'` o `status='failed' + error_message` según el resultado (gestión de fallos detallada en 5.7).

El orchestrator se invoca desde **cuatro orígenes** distintos (CA-6 y CA-7 del pipeline original):

1. **Bootstrap**: `src/pipeline/scripts/bootstrap.py`, lanzado por `CMD` del servicio `pipeline` en `docker compose up`. Solo ejecuta el ETL si MongoDB está vacío (idempotente). Lanza el run con `trigger_type=bootstrap`.
2. **Watcher**: `src/pipeline/scripts/watcher_daemon.py`, servicio long-running que usa la librería `watchdog` para detectar la llegada de `patients.csv` + `admissions.csv` a `data/incoming/`. Lanza el run con `trigger_type=watcher` y mueve los ficheros a `data/incoming/processed/` tras procesarlos.
3. **API**: `POST /api/v1/pipeline/trigger` lanza el orchestrator como `BackgroundTask` de FastAPI. Lanza el run con `trigger_type=manual` y devuelve `run_id` inmediatamente (HTTP 202).
4. **Tests E2E**: `tests/e2e/` lanzan el orchestrator directamente con datasets vacíos o sintéticos para verificar el cumplimiento de los criterios de aceptación. Lanza el run con `trigger_type=e2e-test` (filtrado por defecto en el dashboard para no contaminar la vista operativa).

### 5.7. Gestión de fallos

La gestión de fallos del pipeline se rige por dos principios:

1. **Fallos en una fila no detienen el batch**: la validación produce un DataFrame de rechazados que se persiste en `rejected_records`. Los demás se procesan.
2. **Fallos en una etapa entera marcan el run como `failed` con mensaje explícito y se re-lanzan**: el `try/except` del orchestrator captura cualquier excepción de las etapas (ingesta, validación, transformación, carga), invoca `SqlWriter.finish_pipeline_run(run_id, status='failed', error_message=str(e))` para que SQLite registre el cierre y la causa, y re-lanza la excepción al llamante. El run no se "evapora": queda visible en `GET /api/v1/pipeline/runs` con su `error_message`.

La indisponibilidad de Mongo o MinIO se manifiesta como una excepción del cliente correspondiente en la etapa donde se intenta acceder, lo que entra por el flujo anterior. El test de regresión `test_image_ingester_silent_failure` verifica explícitamente que `ImageIngester` con MinIO inalcanzable **no** devuelve metadatos como si todo hubiera ido bien (CA-8: "si MinIO o MongoDB no están disponibles, el pipeline loguea el error y no crashea silenciosamente"). Este caso fue uno de los cuatro bloqueantes detectados en la auditoría interna inicial y corregidos antes de cerrar T10.

### 5.8. Métricas observadas

Sobre el dataset sintético commiteado (`patients.csv` con 5.150 filas + `admissions.csv` con 10.000 filas), el resultado de un bootstrap en frío es:

**Pacientes** — 5.150 RAW -> 264 rechazados por validación + 141 deduplicados -> **4.745 finales** en MongoDB.

**Admisiones** — 10.000 RAW -> 493 rechazadas por validación + 3 deduplicadas + 935 huérfanas cross-entity -> **8.569 finales** embebidas en sus pacientes.

| Métrica | Valor |
|---|---|
| Total registros en `rejected_records` | 1.692 (264 patients + 1.428 admissions incl. 935 huérfanas; los deduplicados no se contabilizan ahí) |
| Imágenes en MinIO (bucket `radiographies`) | 17 dummy + 1 demo + 6 reales si el dataset Kaggle está presente |
| Tiempo de bootstrap completo | ~50 s en una máquina de desarrollo media |
| Tiempo de *warm restart* | ~1 s (todos los skips idempotentes) |

Estos números son **reproducibles**: se obtienen exactamente igual en cualquier máquina con `docker compose down -v && docker compose up`.

---

## 6. Modelo de IA — Clasificación de radiografías

### 6.1. Encuadre del problema

El sistema clasifica radiografías de tórax en tres clases (`Normal`, `Pneumonia`, `COVID-19`) como **asistencia diagnóstica** — no como diagnóstico final. La spec `clasificacion-radiografias` fija explícitamente que **no hay umbral bloqueante de *accuracy***: el criterio de evaluación es **clínico**, basado en *recall* por clase y análisis cualitativo de la matriz de confusión, no en una cifra global de *accuracy*. Esta orientación está alineada con lo enseñado en el Bloque 6 del Máster (Aprendizaje Automático, profesor Jordi), donde se subraya que en problemas clínicos el coste de un falso negativo es mayor que el de un falso positivo.

### 6.2. Arquitectura del modelo

La arquitectura es una **CNN custom entrenada desde cero**, sin *transfer learning* (ADR-005). Se reproduce literalmente el patrón docente del Bloque 6 (`keras.Sequential` con `Conv2D + MaxPooling2D + Dropout + Flatten + Dense + softmax`):

```
Input (224 x 224 x 1, grayscale)
  -> Conv2D(32,  3x3, relu, padding="same") -> MaxPool(2x2)   # 112x112x32
  -> Conv2D(64,  3x3, relu, padding="same") -> MaxPool(2x2)   # 56x56x64
  -> Conv2D(128, 3x3, relu, padding="same") -> MaxPool(2x2)   # 28x28x128
  -> Conv2D(128, 3x3, relu, padding="same") -> MaxPool(2x2)   # 14x14x128
  -> Dropout(0.3)
  -> Flatten                                                   # 25088
  -> Dense(64, relu)
  -> Dropout(0.3)
  -> Dense(3, softmax)
```

Tres decisiones de diseño merecen comentario:

1. **`padding="same"`** en las cuatro `Conv2D`: garantiza que la reducción espacial venga sólo de los `MaxPool` (224 -> 112 -> 56 -> 28 -> 14), evitando dimensiones impares y manteniendo trazables los conteos del *design*.
2. **`Flatten`** en lugar de `GlobalAveragePooling2D`: aunque GAP daría un modelo más pequeño, el patrón docente del Máster usa `Flatten` y conservar esa estructura es deliberado por trazabilidad con el temario.
3. **Sin *horizontal flip*** en *data augmentation*: una radiografía tiene lateralidad anatómica (corazón a la izquierda) y *flippearla* altera la semántica clínica; rotaciones pequeñas y *zoom* moderado sí se permiten.

El modelo entrenado tiene **~1,8 M parámetros** y pesa **21 MB** en el formato `.keras` final (suficientemente por debajo de los 50 MB del RNF-4, lo que permite commitearlo al repositorio para que el evaluador clone y arranque sin pasos adicionales).

### 6.3. Pipeline de entrenamiento

El código del modelo se organiza en `src/ml/` siguiendo una división por responsabilidades:

| Módulo | Responsabilidad |
|---|---|
| `dataset.py` | Discovery del dataset descargado + split estratificado 80/10/10 con `seed=42` |
| `preprocessing.py` | Pipeline de imagen único (resize 224x224, grayscale, normalización `pixels/255`). Usado **tanto en entrenamiento como en serving** para evitar *train-serve skew* |
| `model.py` | Definición de la arquitectura `keras.Sequential` |
| `train.py` | CLI de entrenamiento con `EarlyStopping`, `ModelCheckpoint`, `CSVLogger`, `class_weight` |
| `evaluate.py` | Genera `metrics.json` + `confusion_matrix.png` + `learning_curves.png` + `report.md` sobre el split de **test** |
| `predictor.py` | Wrapper *thread-safe* (con `Lock`) que la API carga al arrancar |

La regla operativa para los splits, materializada en el código de `src/ml/dataset.py`, es:

- `train` -> alimenta `fit`.
- `validation` -> alimenta los *callbacks* (`EarlyStopping`, `ModelCheckpoint`) y guía los ajustes de hiperparámetros.
- `test` -> queda separado en código y solo se utiliza al cierre de cada versión candidata del modelo para generar el reporte final.

Honestidad sobre el proceso: durante el desarrollo hubo más de una versión candidata (v2 y v3 quedan reflejadas en el diario IA), y cada una se evaluó sobre el split de test al cierre del entrenamiento. La decisión de **ampliar los epochs hasta 35** entre versiones se justificó observando la **curva de validación** (val_loss aún descendente, sin signo de overfitting en val), no optimizando directamente sobre las métricas del test. Es un compromiso típico: el test no es completamente "virgen" frente al proceso global de toma de decisiones, pero los ajustes de hiperparámetros se hicieron mirando *validation*, no *test*.

### 6.4. Hiperparámetros y proceso iterativo

Los hiperparámetros finales, registrados en `data/models/radiography_classifier.meta.json` y replicados en `docs/model-evaluation/report.md` para reproducibilidad:

| Hiperparámetro | Valor |
|---|---|
| `seed` | 42 |
| `batch_size` | 32 |
| `epochs_max` | 35 (efectivos: 35, `EarlyStopping` no recortó) |
| `learning_rate` | 1e-4 |
| `class_weight_mode` | `sqrt` (compensación moderada del desbalance) |
| `dropout_conv` / `dropout_dense` | 0,3 / 0,3 |
| `early_stop_patience` / `min_delta` | 5 / 0,001 |
| `split` | `stratified-80-10-10` |
| `input_shape` | `[224, 224, 1]` |

El primer intento de entrenamiento (con `learning_rate=1e-3` y `class_weight` lineal `3,76` para COVID) produjo un **modelo degenerado** que predecía `Normal` para casi todas las imágenes (*accuracy* ~0,67 — el porcentaje de `Normal` en el split). El proceso de diagnóstico, documentado en `tasks/lessons.md` y soportado por `scripts/ml_diagnostics.py` (overfit a un subconjunto diminuto, montaje visual de imágenes por clase, *mapping* explícito de clases, validación del artefacto), descartó cualquier bug en el preprocesado, las etiquetas o la arquitectura. La causa fue de **hiperparámetros**: `lr=1e-3` era demasiado alto para el tamaño del dataset y `class_weight=3,76` empujaba al modelo a sobre-corregir. Bajar el *learning rate* a `1e-4` y suavizar el `class_weight` con la raíz cuadrada (`sqrt`) llevó al modelo a aprender de forma estable.

### 6.5. Resultados sobre el split de test

Sobre las **1.515 radiografías** del split de test (1.019 `Normal` + 361 `COVID-19` + 135 `Pneumonia`):

- **Accuracy global:** 0,8719
- **Macro-F1:** 0,8456

Métricas por clase (con el *recall* destacado por su relevancia clínica):

| Clase | Precision | Recall | F1 | Soporte |
|---|---|---|---|---|
| Normal | 0,897 | **0,926** | 0,912 | 1.019 |
| Pneumonia | 0,829 | **0,933** | 0,878 | 135 |
| COVID-19 | 0,807 | **0,695** | 0,747 | 361 |

Matriz de confusión 3x3 (filas = clase real, columnas = clase predicha):

| Real \\ Predicha | Normal | Pneumonia | COVID-19 |
|---|---|---|---|
| **Normal** | 944 | 17 | 58 |
| **Pneumonia** | 7 | 126 | 2 |
| **COVID-19** | **101** | 9 | 251 |

Los artefactos visuales completos están en `docs/model-evaluation/confusion_matrix.png` (mapa de calor de la matriz) y `docs/model-evaluation/learning_curves.png` (curvas de *loss* y *accuracy* por *epoch* para *train* y *val*).

### 6.6. Análisis clínico (CA-3)

La matriz de confusión tiene seis tipos de error con consecuencias clínicas distintas. El error de mayor gravedad en contexto hospitalario es el **falso negativo de COVID-19** (un paciente realmente positivo clasificado como `Normal`), porque implica no aislar a un contagioso. Por debajo se sitúan los **falsos negativos de Pneumonia** (paciente con neumonía no detectada) y las **confusiones COVID/Pneumonia** (al menos disparan protocolo respiratorio aunque etiqueten mal). Los **falsos positivos** son los menos graves: generan pruebas adicionales pero no ponen en riesgo al paciente.

Con la matriz obtenida, el modelo presenta **101 COVID-19 clasificados como Normal y 9 como Pneumonia (total 110 COVID-19 no detectados como tal)**, lo que se traduce en un *recall* de **0,695** para esa clase. Esta cifra es **el principal límite clínico del sistema** y se discute con franqueza en las secciones 13 (limitaciones) y 14 (ética). La conclusión clínica es que el modelo, en su estado actual, **no es apto para uso autónomo**: se entrega como herramienta de asistencia que prioriza casos para revisión humana, no como sustituto del juicio clínico.

### 6.7. Ciclo de vida del modelo en producción

El modelo se integra con la API mediante un *predictor* cargado al arrancar (`lifespan` de FastAPI). Si el artefacto `.keras` está presente, los endpoints de clasificación responden normalmente; si no, la API arranca igualmente y los endpoints de clasificación devuelven HTTP 503 con mensaje claro (CB-4), pero el resto de endpoints siguen funcionando (CA-7).

El campo `patients.radiographies[].classification` en MongoDB pasa de `null` a un objeto con cuatro campos:

```
predicted_class:  "Normal" | "Pneumonia" | "COVID-19"
probabilities:    {Normal: 0.94, Pneumonia: 0.02, COVID-19: 0.04}
predicted_at:     "2026-05-17T18:42:11Z"
model_version:    "v1.0-20260516-192647"
```

La idempotencia se garantiza con `matched_count > 0` (no `modified_count`) en el update, de modo que clasificar dos veces la misma imagen con el mismo modelo no provoca falsos negativos al verificar que la operación ha llegado a la base.

---

## 7. API REST

### 7.1. Encuadre

La API es el **único punto de entrada HTTP** del sistema. Sirve datos procesados, expone los metadatos operativos del pipeline y ofrece la inferencia del modelo. Está implementada con **FastAPI + Uvicorn**, con esquemas Pydantic V2 para validación de entrada/salida, paginación uniforme y documentación interactiva en `/docs` (Swagger UI) generada automáticamente. Todos los endpoints están bajo el prefijo `/api/v1/` para permitir versionado futuro sin romper clientes.

### 7.2. Arquitectura interna

La capa API aplica **CQRS-light** (separación lectura/escritura) para evitar acoplar los modelos de lectura a los del writer del pipeline:

| Capa | Módulo | Responsabilidad |
|---|---|---|
| Entry point | `src/api/main.py` | `build_app()` factory testable + `lifespan` (carga predictor) |
| Modelos | `src/api/models.py` | Schemas Pydantic V2 (`Patient`, `Admission`, `Radiography`, `PipelineRun`, páginas paginadas) |
| Readers | `src/api/mongo_reader.py`, `src/api/sql_reader.py` | Sólo lectura sobre Mongo y SQLite, con *unwind* para flatten de admisiones/radiografías |
| Pipeline launcher | `src/api/pipeline_launcher.py` | Encapsula la ejecución asíncrona del orchestrator vía `BackgroundTasks` |
| Routers | `src/api/routers/{data,pipeline,classify,model,health}.py` | Endpoints agrupados por dominio funcional |

La fábrica `build_app()` recibe sus colaboradores (readers, writers, launcher, predictor) por inyección de dependencias, lo que permite a los tests construir una `app` con dobles sin tocar Mongo, SQLite, MinIO ni TensorFlow.

### 7.3. Catálogo de endpoints

| Endpoint | Origen del dato | Propósito |
|---|---|---|
| `GET /api/v1/health` | — | Healthcheck. Incluye `predictor_loaded: bool` para que el dashboard sepa si el modelo está disponible |
| `GET /api/v1/patients` | MongoDB | Lista paginada de pacientes con sus contadores |
| `GET /api/v1/patients/{external_id}` | MongoDB | Detalle de un paciente con admisiones y radiografías embebidas |
| `GET /api/v1/admissions` | MongoDB (*unwind*) | Lista plana paginada de admisiones |
| `GET /api/v1/radiographies` | MongoDB (*unwind*) | Lista plana paginada de metadatos de radiografías |
| `GET /api/v1/pipeline/runs` | SQLite (`pipeline_runs`) | Histórico paginado de ejecuciones del ETL, orden descendente |
| `GET /api/v1/pipeline/status` | SQLite | Último run con todos sus campos |
| `GET /api/v1/pipeline/quality-summary` | SQLite (`data_quality_summary`) | Snapshot del último run (una fila por dimensión) |
| `GET /api/v1/pipeline/quality-summary/history?dimension=...` | SQLite | Histórico paginado para una dimensión |
| `POST /api/v1/pipeline/trigger` | — | Dispara una ejecución del orchestrator como `BackgroundTask`, devuelve `run_id` con `202 Accepted` |
| `POST /api/v1/radiographies/classify` | MinIO + modelo | Recibe `{minio_object_key}` en body, descarga, preprocesa, infiere y persiste en Mongo |
| `GET /api/v1/radiographies/classification?key=...` | MongoDB | Devuelve la clasificación ya persistida, sin re-inferir |
| `GET /api/v1/radiographies/image?key=...` | MinIO | Proxy de bytes PNG (necesario para que el dashboard *API-only* pueda renderizar imágenes) |
| `GET /api/v1/model/evaluation` | Filesystem (`docs/model-evaluation/metrics.json`) | Devuelve las métricas del reporte como JSON |

### 7.4. Decisiones de diseño relevantes

- **`minio_object_key` en *body* o *query*, nunca en *path***: la clave contiene barras (`HOSP-000001/HOSP-000001_xray1.png`). Meterla en *path* obligaría a `{key:path}` y complica clientes, escape de caracteres y herramientas. La decisión está documentada en la spec de clasificación.
- **Códigos HTTP separados para señales independientes** (CB-4 del dashboard): `predictor_loaded=false` en `/health` significa "modelo no cargado"; `503` en `/model/evaluation` significa "reporte de métricas ausente". Son dos estados distintos: puede haber modelo cargado sin reporte (alguien borró `metrics.json`) o reporte sin modelo (entrenamiento previo, artefacto perdido). El dashboard los trata por separado.
- **`/radiographies/image`** es un **proxy puro de lectura**: descarga los bytes desde MinIO con `Content-Type: image/png`, sin tocar Mongo ni el modelo. Sin este endpoint, un dashboard *API-only* no podría renderizar imágenes (no puede abrir conexión directa a MinIO por la decisión de ADR-007).
- **Idempotencia del `classify`**: `MongoWriter.set_radiography_classification` retorna `matched_count > 0` (no `modified_count`), de modo que un segundo `classify` con el mismo modelo y misma imagen — que escribe el mismo `predicted_class` y `probabilities` — sigue contando como éxito aunque `modified_count` sea 0 al no haber diferencia.
- **`POST /pipeline/trigger` devuelve 202**: la ejecución del orchestrator es asíncrona (`BackgroundTasks`). El cliente recibe el `run_id` inmediatamente; el estado se consulta luego en `/pipeline/runs`.

### 7.5. Manejo de errores

La API distingue cuatro familias de error con códigos HTTP coherentes:

- **422 Unprocessable Entity**: input mal formado (clave vacía, body inválido, imagen menor de 32x32 px).
- **404 Not Found**: recurso pedido inexistente (paciente, clave de MinIO sin objeto, clasificación no persistida).
- **503 Service Unavailable**: dependencia caída o ausente (predictor no cargado, `metrics.json` ausente).
- **500 Internal Server Error**: error inesperado (en la práctica, intencionadamente raro: el código atrapa fallos esperados y los reclasifica como 4xx/503).

Cada respuesta de error lleva un `detail` legible. El dashboard explota esta convención en `error_banner.py` mapeando `kind + status` a un mensaje en castellano apto para personal no técnico.

---

## 8. Dashboard de visualización

### 8.1. Encuadre

El dashboard es la cara visible del sistema durante la presentación y, fuera de ella, un **centro de control hospitalario** para auditar el estado del ETL, navegar pacientes y probar el clasificador. Está implementado en **Streamlit 1.39** y desplegado como **imagen Docker independiente** (`hospital-dashboard:latest`, ~240 MB sin TensorFlow ni PySpark — ADR-007). Consume exclusivamente la API REST por HTTP; no abre conexiones directas a MongoDB, SQLite ni MinIO.

### 8.2. Estructura de la aplicación

La app se organiza en `src/dashboard/`:

| Subcarpeta / módulo | Responsabilidad |
|---|---|
| `app.py` | Entry point: configura tema, sidebar con la barra persistente de estado del sistema, navegación |
| `api_client.py` | `ApiClient` con todos los métodos HTTP envueltos, manejo uniforme de errores (`ApiError(kind, status, detail)`) |
| `config.py` | Lee `API_BASE_URL` y `CACHE_TTL_SECONDS` del entorno |
| `views/{overview,quality,patients,classifier,runs}.py` | Una vista por fichero (cinco) |
| `components/{error_banner,system_status}.py` | Componentes reutilizables (banner de error consistente, chips de estado del sistema) |

### 8.3. Las cinco vistas

Cada vista vende explícitamente una pieza del *stack* (ver tabla "Razón de producto por vista" en la spec):

| Vista | Pieza del stack que evidencia |
|---|---|
| **Overview** | Salud operativa + KPI agregados + *strip* mínimo de evaluación del modelo |
| **Calidad de datos** | Pipeline Big Data + `data_quality_summary` |
| **Pacientes** | MongoDB con `admissions` y `radiographies` embebidas |
| **Clasificador** | Keras/TF CNN + sub-sección de evaluación detallada (matriz de confusión) |
| **Pipeline runs** | Watcher + `pipeline_runs` en SQLite |

La vista **Overview** usa `st.fragment(run_every=30)` para auto-refresco sin recargar la página completa, lo único interactivo "vivo" del dashboard. El resto de vistas tienen botón "Recargar" manual.

### 8.4. Patrones técnicos relevantes

- **Caché unificada**: `st.cache_data(ttl=10s)` en todas las consultas GET y `ttl=60s` en `/model/evaluation` (las métricas no cambian hasta reentrenar). El `POST /classify` no se cachea.
- **Selección de fila en `st.dataframe`**: la vista *Pacientes* usa `on_select="rerun"` + `selection_mode="single-row"` (Streamlit 1.30+) para mostrar el detalle del paciente sin un *input* de texto. Click en una fila -> detalle abajo. Ese patrón motivó el upgrade de Streamlit de 1.36 a 1.39, porque la 1.36 carecía de `st.fragment` estable (solo `experimental_fragment`).
- **Manejo de imágenes invalidas (CB-7)**: la vista *Clasificador* mantiene el botón habilitado tras un 422 para que el usuario pueda elegir otra radiografía sin recargar la página, y aplica una **heurística adicional** (`MIN_CLASSIFIABLE_BYTES = 1024`) para ocultar del *dropdown* los archivos manifiestamente pequeños (las 17 dummy 1x1) antes incluso de intentar clasificarlas.
- **Transparencia con `HOSP-DEMO-001`**: cuando esta imagen sintética está seleccionada, la UI muestra un *banner* amarillo con la nota *"imagen sintética de demo — no es una radiografía real"* y la predicción se etiqueta explícitamente como *no evidencia clínica*. Cubre el riesgo ético de presentar como diagnóstico real una predicción sobre datos sintéticos.
- **Filtros de claridad** en vistas operativas: *Calidad* oculta por defecto *snapshots* con `total <= 100` (umbral `RELEVANT_TOTAL_THRESHOLD`) para que los runs de test con *datasets* mínimos no enmascaren los runs reales. *Pipeline runs* oculta por defecto los runs con `trigger_type=e2e-test`. Ambos comportamientos son **toggleables** desde la UI para que la transparencia sea explícita: el operador puede ver "todo" con un click.

### 8.5. Barra persistente de estado del sistema

El sidebar del dashboard incluye tres *chips* visibles desde cualquier vista (`src/dashboard/components/system_status.py`):

- **API**: verde (`ok`) si `/health` responde 200; rojo (`caida`) si no responde.
- **Modelo**: verde (`cargado`) si `/health` reporta `predictor_loaded=true`; rojo (`no cargado`) si reporta `false`; **gris** (`?`, estado desconocido) si la API no responde — la señal del modelo depende de la API, así que su valor no puede afirmarse cuando la API está caída.
- **Último run**: verde (`success`), ámbar (`running`), rojo (`failed`), o **gris** (`sin runs`, `?`) si no hay runs o no se puede consultar.

Este componente materializa el encuadre "centro de control hospitalario" del que habla la spec: con un golpe de vista, antes de entrar en ninguna vista concreta, se ve si la plataforma está sana, y los estados *gris* dejan claros qué hechos no se pueden afirmar en cada momento sin propagar falsos rojos.

### 8.6. Tema y experiencia visual

El tema se define en `.streamlit/config.toml` con paleta sobria (`primaryColor = "#2563EB"`, fondo blanco, texto `#0F172A`). El `toolbarMode = "minimal"` esconde el menú "Deploy" y otros controles irrelevantes para una demo académica. La UI evita explícitamente emojis y CSS *custom*: prioriza claridad y densidad informativa sobre estética.

---

## 9. Resumen de decisiones técnicas (ADRs)

Las decisiones técnicas no triviales están documentadas en `decisions/` como ADRs (*Architecture Decision Records*) con contexto, alternativas consideradas y consecuencias. Esta sección las consolida en una sola tabla; el detalle completo está en los ficheros enlazados:

| ID | Decisión | Alternativa principal descartada | Razón nuclear | Estado |
|---|---|---|---|---|
| **ADR-001** | Stack inicial: PySpark + PyTorch + FastAPI + MongoDB + MinIO + Docker | Dask, Apache Beam | PySpark es estándar del temario de Big Data; FastAPI + MongoDB + MinIO son stack moderno conocido | aceptada, parcialmente superada por ADR-003 |
| **ADR-002** | MongoDB para datos clínicos en lugar de PostgreSQL | PostgreSQL relacional | El enunciado del Máster orienta hacia NoSQL para datos clínicos; la jerarquía paciente -> admisiones -> radiografías encaja en documental | aceptada |
| **ADR-003** | Cambio del framework de Deep Learning de PyTorch a Keras/TensorFlow | Mantener PyTorch | El Bloque 6 del Máster (Aprendizaje Automático, Jordi) usa exclusivamente Keras; trazabilidad clase -> proyecto | aceptada (supersede parcial de ADR-001) |
| **ADR-004** | Persistencia poliglota: SQLite + MongoDB + MinIO | Sólo MongoDB + MinIO | MongoDB + MinIO ya cumplía "≥ 2 tipos de almacenamiento"; SQLite **refuerza** la arquitectura con una capa relacional/tabular para metadatos operativos, alineada con SQLAlchemy + SQLite enseñados en el Bloque 7 | aceptada |
| **ADR-005** | CNN custom desde cero, sin *transfer learning* | EfficientNet/MobileNet pre-entrenado en ImageNet | Alineación literal con el patrón docente del Bloque 6; modelo dentro de los 50 MB del RNF-4; sin dependencias externas en arranque | aceptada |
| **ADR-006** | TensorFlow en la imagen Docker compartida `hospital-pipeline` | Dos imágenes (pipeline sin TF + `hospital-ml` con TF) | Cambio operativo mínimo; entrenamiento dentro del compose; tests existentes siguen funcionando | aceptada |
| **ADR-007** | Streamlit + imagen Docker independiente para el dashboard | Plotly Dash / React / reutilizar `hospital-pipeline` | A 3 días de la entrega, Streamlit corta ~70 % del tiempo de implementación vs React; imagen ligera (~240 MB) cumple holgadamente RNF-5 | aceptada |

Las ADRs son **vivas**: cuando una decisión cambia, se crea un ADR nuevo que *supersede* la anterior, dejando trazabilidad histórica (caso ADR-001 -> ADR-003 para la migración de PyTorch a Keras).

---

## 10. Operación e infraestructura

### 10.1. Despliegue

El sistema se despliega con un único comando desde la raíz del repositorio:

```
docker compose up
```

Si el repositorio se clona limpio (sin volúmenes previos), el orden de arranque y bootstrap automático es:

1. `mongodb` y `minio` arrancan con sus volúmenes vacíos.
2. `minio-init` crea los buckets `radiographies` y `raw-backups` y termina.
3. `pipeline` ejecuta `bootstrap.py`:
   - Crea el schema SQLite en el volumen `pipeline-db` mediante `Base.metadata.create_all(engine)`.
   - Sincroniza los 17 PNG dummy (`data/raw/images/`) al bucket MinIO.
   - Si el dataset Kaggle existe en local (`data/raw/covid_radiography/`), copia las 6 `HOSP-PRES-*` al bucket.
   - Genera al vuelo `HOSP-DEMO-001` (256x256) y la sube a MinIO.
   - Si MongoDB está vacío, ejecuta el ETL completo sobre los CSVs sintéticos commiteados y deja **4.745 pacientes** + **8.569 admisiones** procesados; persiste un `pipeline_run` con `trigger_type=bootstrap`.
4. `api` arranca, carga el modelo `.keras` desde `data/models/` (CB-4 si falta) y queda listo en `:8000`.
5. `watcher` queda en espera sobre `data/incoming/`.
6. `dashboard` arranca en `:8501`.

El bootstrap es **idempotente**: re-ejecutar `docker compose up` no vuelve a procesar lo que ya está hecho (skip selectivo basado en estado de cada almacén). Un *warm restart* tarda ~1 s.

### 10.2. Puntos de acceso

| Recurso | URL | Credenciales |
|---|---|---|
| Dashboard (Streamlit) | `http://localhost:8501` | sin auth (dev) |
| API REST | `http://localhost:8000` | sin auth (dev) |
| Documentación interactiva (Swagger) | `http://localhost:8000/docs` | — |
| MongoDB | `mongodb://localhost:27017/hospital` | sin auth (dev) |
| MinIO consola web | `http://localhost:9001` | `minioadmin` / `minioadmin123` |

La ausencia de autenticación es deliberada para el entorno de demostración; ver capítulo 14 para la discusión sobre cómo evolucionaría a un entorno real.

### 10.3. Gestión de datos y volúmenes

- `mongo-data`, `minio-data` y `pipeline-db` son **volúmenes Docker named**. `docker compose stop` los conserva; sólo `docker compose down -v` los borra.
- El modelo entrenado (`data/models/*.keras` + `*.meta.json`) vive en el filesystem del repositorio y se monta en `pipeline` (`rw`, para reentrenamientos) y `api` (`ro`).
- Los CSVs sintéticos y los 17 PNG dummy están commiteados (`data/raw/`) para que el arranque sea offline y reproducible. El dataset Kaggle (~0,9 GB en la versión local utilizada) está en `.gitignore` y se descarga aparte siguiendo `docs/runbooks/download-radiography-dataset.md`.

### 10.4. Runbooks

`docs/runbooks/` contiene tres procedimientos operativos:

- `download-radiography-dataset.md`: cómo descargar el dataset COVID-19 Radiography de Kaggle.
- `use-real-radiograph-for-demo.md`: cómo dejar el dataset disponible localmente para que el bootstrap incluya las `HOSP-PRES-*`.
- `presentation-demo.md`: guion paso a paso de la demo de presentación (10-15 min) con flujo recomendado por las cinco vistas y mitigaciones para problemas frecuentes.

---

## 11. Testing y verificación

### 11.1. Estado de la suite

El estado actual del repositorio contiene **275 tests automáticos verdes** (+ 1 skip esperado), distribuidos en cuatro grandes capas:

| Capa | Carpeta | Ficheros | Cobertura |
|---|---|---|---|
| Unit + integration pipeline | `tests/pipeline/` | 15 | Ingesters, processors, storage (MongoWriter + SqlWriter + MinIO), orchestrator, watcher |
| Unit + integration ML | `tests/ml/` | 6 | dataset, preprocessing, model, train, evaluate, predictor |
| Unit + integration API | `tests/api/` | 7 | data endpoints, pipeline endpoints, classify, image, model evaluation, sql_reader, mongo_reader |
| Unit dashboard | `tests/dashboard/` | 3 | `ApiClient` con `httpx.MockTransport`, `error_banner`, `system_status` |
| E2E con stack vivo | `tests/e2e/` | 4 | `test_acceptance_criteria` (uno por CA-1..CA-8 del pipeline), watcher integration, dashboard smoke, classification E2E |

Los 275 tests cubren el **estado actual del proyecto**: pipeline ETL completo, persistencia poliglota, clasificador, API completa y dashboard. El skip controlado corresponde al test del watcher cuando se ejecuta dentro del contenedor `pipeline` (necesita permisos *rw* sobre `data/incoming/` que el contenedor no tiene). Los tests E2E de clasificación se saltan limpiamente si la API reporta `predictor_loaded=false`.

### 11.2. Tipos de prueba

- **Unit**: aislados, sin dependencias externas. Usan `httpx.MockTransport` (dashboard), schemas PySpark explícitos (processors) o dobles de los writers.
- **Integration**: tocan MongoDB o MinIO **reales** levantados por Docker; un *fixture* en `conftest.py` detecta su disponibilidad por TCP y hace *skip* limpio si no están accesibles, evitando `KeyError` por *teardown* incompleto.
- **E2E**: arrancan contra el stack vivo (compose levantado). Uno por criterio de aceptación CA-1..CA-8 del pipeline original, más tests específicos del watcher, del dashboard y del flujo de clasificación end-to-end.

### 11.3. Cómo se ejecuta

```
docker compose run --rm --entrypoint "" pipeline pytest tests -v
```

Esta orden lanza toda la suite dentro del contenedor `pipeline` que ya tiene PySpark, TensorFlow y FastAPI instalados. Los tests E2E que requieren `data/incoming/` *rw* se saltan en este modo y se cubren con el segundo comando, ejecutado contra un compose ya levantado.

### 11.4. Revisiones cruzadas

Para mitigar la tendencia de los LLMs a no cuestionar su propio trabajo, las features grandes se sometieron a **revisión técnica del equipo** y **contraste contra la spec**, siguiendo el espíritu del flujo `/auditoria` del SDD Kit. Esta entrega **no preserva ficheros de revisión versionados**: las revisiones se hicieron de forma conversacional durante el desarrollo y sus conclusiones se incorporaron como cambios de código en el momento; los hallazgos que sobrevivieron al cambio quedaron también recogidos en `tasks/lessons.md` como patrones a evitar. El caso documentado con mayor impacto fue la **auditoría interna del pipeline al cerrar T10**, que detectó cuatro bloqueantes — `POST /pipeline/trigger` desconectado, `/radiographies` devolviendo lista vacía, orchestrator frágil ante fallos al iniciar, *silent failure* del `ImageIngester` con MinIO inalcanzable — todos corregidos antes de cerrar la fase BUILD y reflejados en el `CHANGELOG.md`.

---

## 12. Resultados

### 12.1. Pipeline ETL — cifras de operación

Sobre el dataset sintético commiteado (`patients.csv` 5.150 filas + `admissions.csv` 10.000 filas), el resultado de un bootstrap en frío es: **4.745 pacientes finales en MongoDB**, **8.569 admisiones embebidas**, **1.692 registros en `rejected_records`** (264 pacientes + 1.428 admisiones), tiempo de bootstrap completo **~50 s** y *warm restart* **~1 s** (sección 5.8 con el desglose completo). El sistema arranca con `docker compose up` desde cero en **menos de 1 minuto** sobre una máquina de desarrollo media.

### 12.2. Modelo — métricas finales

Sobre las 1.515 radiografías del split de test:

- **Accuracy global**: 0,8719
- **Macro-F1**: 0,8456
- **Recall**: Normal = 0,926; Pneumonia = 0,933; **COVID-19 = 0,695**

Comparativa con dos *baselines* triviales:

| Sistema | Accuracy | Macro-F1 |
|---|---|---|
| Predicción aleatoria uniforme (3 clases) | ~0,333 | ~0,33 |
| Predecir siempre `Normal` (clase mayoritaria) | 0,6726 | 0,267 |
| **Modelo entregado** | **0,8719** | **0,8456** |

El modelo supera ampliamente los *baselines* triviales. La metodología que llevó al estado actual incluyó un primer modelo degenerado (rama detectada por *sanity checks* documentados, no por *accuracy* — la *accuracy* baseline coincidía con la del "predecir todo Normal") y un ajuste de hiperparámetros (`lr=1e-4`, `class_weight=sqrt`) que devolvió un modelo no trivial.

### 12.3. Dashboard — demo operativa

El dashboard expone las cinco vistas funcionales descritas en el capítulo 8. Smoke test verificado en presentación:

- Las cinco vistas responden 200 OK con datos cargados de MongoDB/SQLite via API.
- `HOSP-DEMO-001` se clasifica como `Normal` con probabilidad ~0,95 (la imagen sintética no tiene patrón clínico real; el resultado demuestra el flujo end-to-end, no valor diagnóstico).
- Con `docker compose stop api`, el dashboard sigue respondiendo `200 OK`: el chip *API* pasa a rojo y los chips *Modelo* y *Último run* pasan a gris (estado desconocido al depender de la API), sin pantalla blanca ni *stacktrace* (CA-10).
- Las HOSP-PRES-* (cuando el dataset está descargado) permiten una demo con imágenes reales del dataset, más representativa visualmente que la sintética.

### 12.4. Cobertura por criterios de aceptación

Cada feature del backlog tiene sus criterios de aceptación atados a tests E2E. El estado tras la entrega es:

| Feature | Criterios totales | Cubiertos por tests |
|---|---|---|
| `pipeline-datos` | 8 (CA-1..CA-8) | 8/8 (`tests/e2e/test_acceptance_criteria.py`) |
| `sqlite-pipeline-metadata` | 8 (CA-1..CA-8) | 8/8 (mezcla de tests específicos + E2E) |
| `clasificacion-radiografias` | 10 (CA-1..CA-10) | 9/10 cubiertos automáticamente; CA-3 (análisis clínico cualitativo) verificado por inspección del reporte |
| `dashboard` | 11 (CA-1..CA-11) | 11/11 entre tests unit + E2E + verificación manual |

---

## 13. Limitaciones y reflexión crítica

### 13.1. Limitaciones del modelo

- **Recall de COVID-19 = 0,695**: el modelo pierde aproximadamente el 30 % de los positivos reales de COVID-19. Es el límite clínico principal del sistema y motiva la totalidad del encuadre "asistencia diagnóstica, no diagnóstico final" (RNF-2 de la spec).
- **Sin detección *out-of-domain***: una imagen que no sea una radiografía de tórax (un retrato, una resonancia, una mano) devolverá una clase con confianza arbitraria. No hay verificador de "es esto realmente una radiografía".
- **Sin interpretabilidad** (Grad-CAM, mapas de saliencia, SHAP): el modelo dice **qué** predice pero no **por qué**. Para un sistema de asistencia clínica real este sería un requisito imprescindible.
- **Generalización no garantizada**: el modelo se entrena exclusivamente sobre el COVID-19 Radiography Database. Su comportamiento sobre radiografías de otros equipos, otros centros, otras poblaciones o con artefactos distintos (calibración, exposición) no está medido.

### 13.2. Limitaciones del pipeline y del sistema

- **Datos sintéticos**: el dataset clínico tabular es generado con *Faker* y casos borde inyectados. Útil para demostrar el comportamiento del pipeline, no para evaluar plausibilidad clínica de las cifras agregadas.
- **Batch, no streaming**: el sistema ingiere ficheros enteros (CSV + PNG). No hay procesamiento de eventos en tiempo real.
- **Sin autenticación ni autorización**: aceptable para una demo académica, inviable en entorno real.
- **Sin replicación ni alta disponibilidad**: MongoDB y MinIO corren como nodos únicos. Cualquier caída implica indisponibilidad.
- **`HOSP-DEMO-001` es sintética**: 256x256 generada con `numpy + Pillow`, no procede de ningún dataset clínico. La UI lo señala explícitamente para evitar interpretarla como evidencia real.

### 13.3. Decisiones que se reabrirían con más tiempo

- **Transfer learning** (EfficientNet, MobileNetV2 o DenseNet121 con pesos médicos como CheXNet) probablemente subiría el *recall* de COVID-19 entre 5 y 10 puntos. La ADR-005 ya prevé esto como contingencia si el *recall* hubiera resultado inaceptable.
- **Detección *out-of-domain*** con un clasificador binario previo "es radiografía de tórax / no".
- **Grad-CAM** para que cada predicción incluyera un mapa de calor de la región que ha pesado más.
- **Autenticación** con OAuth2/JWT.
- **Tests de carga** y *performance budget* explícito en la API (hoy se mide implícitamente con el RNF-3 de "inferencia < 3 s").

### 13.4. Lo que ha funcionado y lo que no

Las decisiones que más han contribuido a llegar a la entrega:

- **SDD aplicado con disciplina** (spec antes que código): evitó implementar sin tener claras las dudas; el ejemplo más claro es la spec del dashboard, donde 6 dudas + 3 ajustes se cerraron antes de tocar código y ahorraron retrabajos posteriores.
- **ADRs frescos**: cada decisión técnica importante quedó documentada en el momento, no a posteriori; esto ha permitido escribir esta memoria sin reconstruir el razonamiento.
- **Revisión cruzada con otro proveedor** durante el desarrollo: detectó bloqueantes que un solo proveedor probablemente habría firmado como "OK" (el caso documentado con mayor impacto: los cuatro bloqueantes del pipeline al cerrar T10).
- **Bootstrap idempotente desde el día 1**: `docker compose up` deja siempre el mismo estado, lo que ha hecho la demo y los tests E2E mucho más predecibles.

Lo que no ha funcionado bien:

- **El primer entrenamiento degenerado** consumió un día. Faltó plantear *sanity checks* (overfit a un subconjunto diminuto, *montage* visual por clase) **antes** del primer entrenamiento "real". Quedó documentado como patrón en `lessons.md`.
- **El cambio de PyTorch a Keras** (ADR-001 -> ADR-003) llegó tarde: si se hubiera auditado el temario antes de fijar el stack, no habría sido necesario. Coste real: bajo (no había código PyTorch que migrar), pero llamativo.
- **El cambio anunciado de dataset a radiografías dentales** generó incertidumbre y obligó a confirmar explícitamente con Alejandro seguir con el plan original (registrado en la spec de `clasificacion-radiografias`).

---

## 14. Consideraciones éticas y legales

### 14.1. Datos personales y privacidad

El proyecto **no maneja datos reales de pacientes**. Tanto los datos tabulares (`patients.csv`, `admissions.csv`) como los nombres (`HOSP-NNNNNN`) están **íntegramente generados con `Faker`** sobre una *seed* fija (42). Esta decisión es la solución natural al riesgo principal de un proyecto académico que toca datos clínicos: sustituir el dato real por un dato sintético equivalente en estructura pero sin identificadores reales. En consecuencia, ningún archivo del repositorio contiene PII (información de identificación personal) sujeta a GDPR o normativa equivalente.

Las imágenes utilizadas para entrenamiento proceden del **COVID-19 Radiography Database** (Kaggle), publicado por sus autores ya anonimizado. El proyecto **no commitea** ese dataset al repositorio (`.gitignore`) y deja el procedimiento de descarga responsabilidad del operador, que debe leer y respetar los términos de uso publicados por el autor original.

### 14.2. Licencia y citación del dataset

El *COVID-19 Radiography Database* tiene términos de uso definidos por su autor original que deben respetarse y citarse **tal cual los publica el proveedor**, sin asumir licencias genéricas. Esta convención es explícita en `data/raw/images-demo/README.md`, en el runbook de presentación y en la UI del dashboard. Cualquier difusión de capturas o resultados fuera del entorno de demostración (publicaciones, presentaciones externas) requiere citar la fuente exacta tal como la indica el autor.

### 14.3. Sesgo del modelo

Tres fuentes de sesgo identificadas:

- **Desbalance de clases en el dataset**: ~10.000 `Normal` vs ~3.600 `COVID-19` vs ~1.300 `Viral Pneumonia`. Mitigado con `class_weight="sqrt"` en el entrenamiento, pero no eliminado.
- **Sesgo de equipo/centro**: las radiografías del dataset proceden de un conjunto limitado de equipos y centros, no necesariamente representativos de la variabilidad global de equipamiento radiológico.
- **Descarte de la clase `Lung_Opacity`**: 6.012 imágenes no se usan porque no encajan en la clasificación triple. Es una decisión razonada (ver cap 4.4), pero impone al modelo el supuesto cerrado "toda radiografía pertenece a una de las tres clases", lo que puede llevar a clasificar como una de ellas hallazgos que en realidad caerían en la categoría descartada.

### 14.4. Uso clínico — el sistema NO es un diagnóstico

El sistema se entrega explícitamente como **asistencia diagnóstica**, NUNCA como diagnóstico final. Esta posición está consagrada como **RNF-2** de la spec de clasificación, repetida en el runbook de presentación, visible en la UI cuando una predicción se ejecuta sobre `HOSP-DEMO-001` y discutida con datos concretos en el reporte clínico (`docs/model-evaluation/report.md`). La métrica que sostiene esta posición es el *recall* de COVID-19 = 0,695: el modelo pierde el 30 % de los positivos reales y por tanto no puede sustituir al criterio humano.

Cualquier despliegue clínico real requeriría, además: (a) certificación como producto sanitario (CE/FDA), (b) auditoría con datos representativos del centro, (c) interpretabilidad (Grad-CAM como mínimo), (d) protocolos de incertidumbre (no clasificar cuando la confianza es baja) y (e) integración con el flujo del radiólogo humano que mantenga la última palabra clínica siempre en la persona.

### 14.5. Riesgo del sistema y mitigaciones

| Riesgo | Mitigación implementada |
|---|---|
| Confundir `HOSP-DEMO-001` (sintética) con radiografía real | Banner amarillo + caption explícito en la UI + nota en la presentación |
| Difundir capturas con licencia genérica | Convención formal "licencia tal como la publica el proveedor"; documentado en runbook, README de imágenes y memoria |
| Interpretar el resultado del modelo como diagnóstico | RNF-2, repetido en spec, UI, runbook y memoria; reporte clínico con análisis cualitativo |
| Fuga de datos clínicos reales | Datos sintéticos por diseño; dataset Kaggle no commiteado |
| Persistencia de predicciones erróneas | `predicted_at` y `model_version` permiten distinguir predicciones de distintas versiones del modelo y re-clasificar si se entrena uno nuevo |

---

## 15. Uso de IA generativa y metodología SDD

### 15.1. Encuadre

El enunciado del Máster pide explícitamente "Desarrollo Asistido por IA" como uno de los ejes evaluables. Este capítulo documenta cómo se ha materializado ese eje en el proyecto.

El proyecto se ha desarrollado en **pareo con asistentes de IA generativa** como apoyo principal, complementados con **revisión técnica del equipo** y **contraste contra la spec** como mecanismos de control, aplicando **metodología SDD (Spec-Driven Development)** como marco para que la asistencia de la IA fuera trazable, revisable y no opaca. El criterio de partida ha sido tratar a la IA como un colaborador júnior muy rápido pero con tendencia a la complacencia: hay que darle instrucciones claras, revisar lo que produce y forzar disciplina de proceso.

### 15.2. Por qué SDD encaja con asistencia IA

SDD (descrito en cap 2.4) descompone el desarrollo en cinco fases: `/spec -> /planificar -> /tareas -> /implementar -> /revisar`. Cada fase produce un artefacto revisable antes de pasar a la siguiente. Esa disciplina aporta tres beneficios concretos cuando se trabaja con asistentes IA:

1. **La IA no inventa requisitos**: al separar `/spec` (qué construir, en castellano natural) de `/implementar` (cómo construirlo), la IA opera sobre un documento que el humano ha aprobado, en vez de proponer una solución a un problema mal definido.
2. **Las dudas están marcadas**: la convención `[NEEDS CLARIFICATION]` en las specs obliga a la IA a parar antes de asumir; el humano cierra la duda y la spec queda viva con changelog.
3. **Cada decisión técnica deja huella en un ADR**: si la IA propone elegir SQLite sobre PostgreSQL, esa elección no se queda en la conversación volátil — se escribe en `decisions/ADR-NNN.md` con alternativas y razón. Esto facilita auditoría posterior y permite revisar decisiones si cambia el contexto.

### 15.3. Cómo se ha trabajado en la práctica

El flujo de una feature típica (ejemplo: dashboard) ha sido:

1. **`/spec dashboard`**: Alejandro describe el problema; Claude redacta el primer borrador de la spec con dudas explícitas. Iteración hasta cerrar las dudas (en el caso del dashboard, 6 dudas + 3 ajustes de producto).
2. **`/planificar dashboard`**: con la spec aprobada, Claude propone una arquitectura con trazabilidad requisito -> componente. Aquí nace ADR-007 (Streamlit + imagen Docker independiente).
3. **`/tareas dashboard`**: descomposición en 17 tareas atómicas con tamaño S/M/L y dependencias.
4. **`/implementar dashboard`**: TDD desde los criterios de aceptación. Por cada tarea: test que falla -> código mínimo -> test verde -> commit.
5. **Revisión técnica del equipo y contraste contra la spec**: el flujo formal `/auditoria` del SDD Kit está descrito como práctica del equipo, pero en esta entrega las revisiones se realizaron de forma conversacional y sus conclusiones se incorporaron al código directamente, sin preservar ficheros de revisión versionados. La auditoría interna del pipeline al cerrar T10 (cuatro bloqueantes detectados y corregidos) es el caso con mayor impacto reflejado en el `CHANGELOG.md`.
6. **`/revisar dashboard`**: matriz de trazabilidad requisito -> test -> evidencia, verificación de que cada CA de la spec tiene un test que lo cubre.

### 15.4. Cifras del trabajo con IA

| Indicador | Valor |
|---|---|
| Sesiones documentadas en `docs/diario-ia.md` | 28 |
| ADRs producidos | 7 |
| Specs aprobadas | 4 (`pipeline-datos`, `sqlite-pipeline-metadata`, `clasificacion-radiografias`, `dashboard`) |
| Lecciones registradas en `tasks/lessons.md` | 57 entradas (patrones a evitar, decisiones, cosas que funcionan) |
| Revisiones cruzadas (otro proveedor, conversacional, no versionada) | sí, durante el desarrollo de las features grandes; sin ficheros de auditoría preservados en esta entrega |

### 15.5. Lecciones aprendidas

Lo que ha funcionado especialmente bien:

- **Tratar las dudas como bloqueantes**: la IA es muy buena escribiendo specs en cuanto las dudas están cerradas. Si se le deja asumir, asume mal.
- **ADRs en el momento, no al final**: escribir el ADR mientras se toma la decisión (no a posteriori) evita reescribir la historia y permite que el ADR documente alternativas reales consideradas.
- **Revisión cruzada con otro proveedor en *features* grandes**: los cuatro bloqueantes detectados al cerrar T10 (en el bloque de auditoría interna del pipeline) habrían pasado desapercibidos con revisión del mismo proveedor.
- **Diario IA como reflexión, no como log**: el diario no es histórico-cronológico, es cualitativo (qué funcionó, qué hubo que corregir, qué se aprendió). Eso permite detectar patrones entre sesiones, no eventos sueltos.

Lo que ha sido necesario corregir o evitar repetir:

- **Tendencia a la verbosidad**: los primeros borradores de specs eran demasiado largos. Solución: enviar `condensa, no añadas relleno` como instrucción explícita.
- **Inventarse números**: detectada una vez ("4.745 pacientes" cuadraba, pero "1.692 rejected = 264 patients + admisiones huérfanas" omitía 3 duplicados de admisiones). Lección documentada: leer del repositorio antes de afirmar cifras.
- **Sycophancy del LLM ante su propio código**: un mismo asistente rara vez cuestiona lo que acaba de generar. Mitigado con revisión técnica del equipo y validación contra criterios de aceptación.
- **Re-implementar en lugar de leer lo ya hecho**: si un componente ya existe (ej. `MongoWriter`), la IA tiende a proponer reescribirlo. Solución: empezar cada sesión con `/retomar` que lee `progress/current.md`, `tasks/lessons.md` y los specs aprobados.

### 15.6. Estimación del impacto en productividad

Estimación cualitativa de Alejandro, registrada en el diario IA:

- **Tiempo ahorrado**: alto en redacción de specs, designs, ADRs y memoria técnica; medio-alto en código boilerplate (routers, schemas Pydantic, tests con MockTransport); medio en lógica de pipeline (donde el dominio requiere más iteración humana).
- **Calidad del código generado**: aceptable como punto de partida; requiere siempre revisión humana y, en features críticas, auditoría cruzada con otro proveedor.
- **Trabajo humano requerido**: cierre de dudas en specs, validación de decisiones técnicas, depuración de hiperparámetros del modelo (la IA no "intuye" *learning rates*), redacción final cualitativa, pruebas manuales en la UI, decisiones de producto.

Conclusión: la IA actúa como **multiplicador de capacidad**, no como sustituto. SDD es la disciplina que hace que ese multiplicador sea seguro: sin spec, design, ADR y tests, la IA produciría código más rápido pero ese código sería más difícil de revisar, mantener y defender.

---

## 16. Conclusiones

### 16.1. Qué se entrega

Un sistema **funcional, contenedorizado y reproducible** que cubre los cuatro subproblemas del enunciado:

1. Pipeline ETL distribuido con PySpark, persistencia poliglota (MongoDB + SQLite + MinIO), validación, deduplicación y enriquecimiento.
2. Modelo CNN custom en Keras/TF para clasificación de radiografías en 3 clases, con métricas clínicas reportadas y artefacto commiteado al repositorio (21 MB).
3. API REST en FastAPI con 14 endpoints versionados, documentación Swagger automática y separación lectura/escritura.
4. Dashboard Streamlit con cinco vistas, *API-only*, imagen Docker independiente (~240 MB), barra persistente de estado del sistema.

El despliegue se realiza con un único `docker compose up` y deja el sistema operativo en menos de un minuto. El estado actual del repositorio contiene 275 tests verdes, 7 ADRs y 4 specs aprobadas con trazabilidad spec -> design -> tareas -> tests -> criterios de aceptación.

### 16.2. Qué no se entrega y por qué

- **Diagnóstico clínico vinculante**: el modelo es asistencia, no decisión.
- **Streaming en tiempo real**: el sistema es *batch*; el watcher cubre el lado automático.
- **Autenticación y autorización**: entorno de demostración académica.
- **Subida de imágenes desde el dashboard**: fuera del alcance de la spec; las imágenes se preparan como fixtures antes del arranque.
- **Interpretabilidad del modelo**: Grad-CAM o equivalente queda como mejora futura inmediata si el sistema avanzara hacia uso clínico real.

### 16.3. Líneas de mejora prioritarias

Si el proyecto evolucionara más allá de la entrega académica, las prioridades naturales serían, por orden:

1. **Subir el *recall* de COVID-19** mediante *transfer learning* (EfficientNet o DenseNet121 con pesos médicos) y/o *ensembling*.
2. **Añadir interpretabilidad** (Grad-CAM por defecto en cada predicción).
3. **Detección *out-of-domain***: clasificador binario previo "es radiografía de tórax / no".
4. **Autenticación + autorización** (OAuth2/JWT) y cifrado en tránsito.
5. **Observabilidad**: métricas Prometheus, logs estructurados, dashboards Grafana.
6. **Re-entrenamiento automatizado** (DVC, MLflow) y *model registry*.
7. **Streaming**: pasar de `watchdog` sobre filesystem a Kafka/RabbitMQ.

### 16.4. Cierre

El proyecto demuestra que es posible llegar a un sistema completo, reproducible y documentado en un plazo académico ajustado combinando tres ingredientes: una **metodología disciplinada** (SDD), un **stack que el equipo conoce y que coincide con el temario** (Python + PySpark + Keras + FastAPI + Streamlit + Docker) y un **uso intensivo pero supervisado de asistentes de IA generativa**. La pieza más difícil no ha sido técnica sino metodológica: mantener la disciplina de no saltarse fases, no asumir dudas y documentar las decisiones en el momento. Esa disciplina es lo que ha permitido que esta memoria pueda escribirse leyendo el repositorio, no recordando.

---

## 17. Anexos

### 17.1. Artefactos vivos del repositorio

| Artefacto | Ruta | Contenido |
|---|---|---|
| Specs | `specs/{pipeline-datos,sqlite-pipeline-metadata,clasificacion-radiografias,dashboard}.md` | Qué construir + criterios de aceptación |
| Designs | `design/*.md` | Cómo construirlo + trazabilidad spec -> componente |
| Tareas | `tasks/*.md` + `tasks/backlog.md` | Trabajo descompuesto, prioridad, estado |
| ADRs | `decisions/ADR-001..ADR-007.md` | Decisiones técnicas con alternativas |
| Lecciones | `tasks/lessons.md` | 57 entradas: patrones a evitar, decisiones, cosas que funcionan |
| Diario IA | `docs/diario-ia.md` | 28 sesiones documentadas |
| Reporte del modelo | `docs/model-evaluation/{report.md,metrics.json,confusion_matrix.png,learning_curves.png}` | Métricas + análisis clínico + curvas + matriz |
| Runbooks | `docs/runbooks/{download-radiography-dataset,use-real-radiograph-for-demo,presentation-demo}.md` | Procedimientos operativos |
| Changelog | `CHANGELOG.md` | Historial de entregas (incluye el bloque "Auditoria interna del codigo — 4 bloqueantes arreglados" tras cerrar T10) |

### 17.2. Comandos clave

```
# Arranque del sistema completo
docker compose up

# Tests
docker compose run --rm --entrypoint "" pipeline pytest tests -v

# Reentrenamiento del modelo (requiere dataset Kaggle descargado)
docker compose run --rm pipeline python -m src.ml.train

# Regenerar datos sintéticos
docker compose run --rm --entrypoint "" pipeline \
    python -m src.pipeline.scripts.generate_data --seed 42

# Apagado
docker compose down            # conserva volúmenes
docker compose down -v         # borra TODOS los volúmenes (mongo, minio, sqlite)
```

### 17.3. URLs de acceso al sistema en marcha

| Recurso | URL |
|---|---|
| Dashboard | `http://localhost:8501` |
| API REST | `http://localhost:8000` |
| Swagger | `http://localhost:8000/docs` |
| MinIO consola | `http://localhost:9001` |
| MongoDB | `mongodb://localhost:27017/hospital` |

### 17.4. Glosario abreviado

- **CA**: Criterio de aceptación (requisito verificable de una spec).
- **CB**: Caso borde de una spec.
- **CQRS**: Separación de modelos de lectura y escritura.
- **ETL**: Extract — Transform — Load.
- **FN**: Falso negativo.
- **FP**: Falso positivo.
- **PII**: Información de identificación personal.
- **RF / RNF**: Requisito funcional / no funcional.
- **SDD**: Spec-Driven Development.
- **WAL**: Write-Ahead Logging (modo de concurrencia de SQLite).

