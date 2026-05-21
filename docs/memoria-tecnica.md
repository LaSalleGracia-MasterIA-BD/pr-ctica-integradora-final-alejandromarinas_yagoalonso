# Memoria técnica — Sistema Inteligente de Soporte Hospitalario

> **Proyecto:** laSalle Health Center — Sistema de soporte clínico con clasificación de radiografías y procesamiento de datos a escala
> **Autoría:** Alejandro Marinas y Yago
> **Programa:** Máster en AI & Big Data
> **Fecha del documento:** 2026-05-20
> **Estado:** versión final
> **Repositorio:** `MarinasAlejandro/lasalle-hospital`

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Contexto y problema](#2-contexto-y-problema)
3. [Arquitectura del sistema](#3-arquitectura-del-sistema)
4. [Datos](#4-datos)
5. [Pipeline ETL](#5-pipeline-etl)
6. [Sistemas de IA](#6-sistemas-de-ia)
7. [API REST](#7-api-rest)
8. [Dashboard de visualización](#8-dashboard-de-visualización)
9. [Automatización y observabilidad](#9-automatización-y-observabilidad)
10. [Resumen de decisiones técnicas (ADRs)](#10-resumen-de-decisiones-técnicas-adrs)
11. [Operación e infraestructura](#11-operación-e-infraestructura)
12. [Testing y verificación](#12-testing-y-verificación)
13. [Resultados](#13-resultados)
14. [Limitaciones y reflexión crítica](#14-limitaciones-y-reflexión-crítica)
15. [Consideraciones éticas y legales](#15-consideraciones-éticas-y-legales)
16. [Uso de IA generativa y metodología SDD](#16-uso-de-ia-generativa-y-metodología-sdd)
17. [Conclusiones](#17-conclusiones)
18. [Anexos](#18-anexos)

---

## 1. Resumen ejecutivo

Este proyecto implementa, para el hospital ficticio **laSalle Health Center**, un sistema completo de asistencia clínica formado por cuatro piezas interdependientes:

1. Un **pipeline ETL** con PySpark que ingesta datos clínicos tabulares (pacientes e ingresos) e imágenes de radiografía, los valida, los limpia y los persiste en los almacenes apropiados.
2. Dos **sistemas de IA** complementarios: una **CNN custom en Keras/TensorFlow** que clasifica radiografías de tórax en tres clases (`Normal`, `Pneumonia`, `COVID-19`) como **asistencia al diagnóstico**, y un **sistema de triaje basado en reglas IF-THEN** que asigna prioridad `grave / medio / leve` a pacientes registrados manualmente desde el dashboard. La elección de paradigma para cada uno se justifica en el capítulo 6.
3. Una **API REST** en FastAPI que expone los datos procesados, la inferencia del modelo y la capa de observabilidad (alertas operativas e informe diario).
4. Un **dashboard** en Streamlit con **siete vistas** que actúa como centro de control hospitalario: pacientes, calidad del pipeline, runs operativos, **triaje**, **alertas**, demo del clasificador y resumen general. La generación del **informe diario** complementa la observabilidad accionable desde la línea de comandos.

La arquitectura se despliega como un único `docker compose up` que orquesta siete servicios (MongoDB, MinIO, inicializador de buckets, pipeline, API, watcher y dashboard) y deja el sistema listo en menos de un minuto. El estado actual del repositorio contiene **417 tests automáticos verdes** (más un skip controlado), diez ADRs documentadas y artefactos vivos de la metodología SDD aplicada durante todo el desarrollo.

El **modelo entrenado** sobre el split de test (1.515 radiografías del *COVID-19 Radiography Database* de Kaggle) alcanza una *accuracy* de **0,8766** y un **macro-F1 de 0,8594**, con un *recall* por clase de 0,890 (Normal), 0,926 (Pneumonia) y **0,820 (COVID-19)** aplicando la regla de decisión `covid_threshold_0.35` documentada en ADR-010 (umbral *post-hoc* sobre la probabilidad softmax de COVID-19 que NO modifica los pesos del modelo). El *recall* de COVID-19 sigue siendo la dimensión clínicamente más sensible y se discute en detalle en los capítulos de resultados, limitaciones y ética: el sistema se entrega como herramienta de **asistencia**, nunca como diagnóstico final.

El proyecto está construido con metodología **SDD (Spec-Driven Development)**: cada feature pasa por las fases `/spec -> /planificar -> /tareas -> /implementar -> /revisar`, con artefactos versionados en `specs/`, `design/`, `tasks/` y `decisions/`. El uso de IA generativa como herramienta de pareo en el desarrollo está documentado sesión a sesión en `docs/diario-ia.md` y se trata explícitamente en el capítulo 16.

### 1.1. Cifras de referencia

| Indicador | Valor |
|---|---|
| Servicios Docker orquestados | 7 (mongodb, minio, minio-init, pipeline, api, watcher, dashboard) |
| Volúmenes Docker persistentes | 3 (`mongo-data`, `minio-data`, `pipeline-db`) |
| Almacenes de datos heterogéneos | 3 (MongoDB, SQLite, MinIO) |
| Pacientes procesados desde el dataset sintético | 4.745 |
| Admisiones embebidas en MongoDB | 8.569 |
| Tests automáticos verdes | 413 (+ 1 skip esperado) |
| ADRs documentadas | 10 |
| Specs aprobadas | 6 (`pipeline-datos`, `sqlite-pipeline-metadata`, `clasificacion-radiografias`, `dashboard`, `triage-pacientes`, `automatizacion-alertas`) |
| Accuracy del modelo (test split, regla `covid_threshold_0.35`) | 0,8766 |
| Macro-F1 del modelo (test split, regla `covid_threshold_0.35`) | 0,8594 |
| Tamaño del artefacto del modelo | 21 MB (formato `.keras`) |

### 1.2. Estructura del documento

Los capítulos 2 a 8 describen **qué se ha construido**: contexto, arquitectura, datos, pipeline, sistemas de IA (clasificador CNN y triaje por reglas), API y dashboard. El capítulo 9 consolida las piezas de **automatización y observabilidad** del sistema (watcher, bootstrap idempotente, alertas, informe diario). El capítulo 10 sintetiza en una tabla las **decisiones técnicas** (ADRs) que justifican cómo se ha construido. Los capítulos 11 a 13 cubren **cómo se opera y se verifica** el sistema y los **resultados** obtenidos. Los capítulos 14 a 16 son reflexión crítica: **limitaciones**, **ética y legalidad** y un capítulo específico dedicado al **uso de IA generativa y a la metodología SDD**, por ser un eje explícito del enunciado del Máster. El capítulo 17 cierra con conclusiones y trabajo futuro. Los anexos consolidan referencias a artefactos vivos del repositorio (specs, designs, ADRs, runbooks, diario).

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
4. **Cuadro de mando** que sintetiza el estado del sistema (datos cargados, pipeline ejecutándose, modelo cargado, métricas de calidad) y permite a un operador del hospital sin perfil técnico inspeccionar pacientes, lanzar la clasificación de una radiografía y auditar el histórico de ejecuciones del ETL.

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

Cada feature relevante (pipeline, polyglot SQLite, clasificador, dashboard, triaje de pacientes, automatización-alertas) tiene su trío de artefactos `specs/<feature>.md`, `design/<feature>.md` y `tasks/<feature>.md` versionados en el repositorio. Las decisiones técnicas no triviales se documentan como ADRs en `decisions/`. La cadena de trazabilidad **requisito -> componente -> tarea -> test -> criterio de aceptación** es explícita: nada se implementa sin estar atado a un requisito de una spec aprobada.

El capítulo 16 desarrolla en detalle el uso conjunto de SDD y de asistentes de IA generativa, complementado con revisión técnica del equipo y contraste contra la spec, que ha caracterizado todo el desarrollo del proyecto.

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

Una de las decisiones de diseño más importantes del proyecto es la **persistencia poliglota** (ADR-004): cada tipo de dato vive donde su forma encaja, sin duplicar fuente de verdad.

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
| MongoDB para datos clínicos | PostgreSQL relacional | El enunciado pide "al menos dos tipos de almacenamiento" y pone PostgreSQL como ejemplo, no como obligación. La jerarquía paciente → admisiones → radiografías encaja con un modelo documental, y `rejected_records.raw_data` es heterogéneo entre motivos de rechazo. Ver ADR-002 |
| Persistencia poliglota (Mongo+SQLite+MinIO) | Solo Mongo+MinIO | MongoDB + MinIO ya cumple "≥ 2 tipos de almacenamiento". SQLite **refuerza** la arquitectura añadiendo una capa relacional/tabular para los metadatos operativos (auditoría de runs + agregados de calidad), alineada con SQLAlchemy + SQLite del Bloque 7 del Máster. ADR-004 |
| Keras / TensorFlow (en lugar de PyTorch) | PyTorch | La asignatura de Aprenentatge Automàtic del Máster usa exclusivamente Keras. ADR-003 |
| CNN custom sin *transfer learning* | EfficientNet preentrenado | Alineación literal con el Bloque 6 del Máster. ADR-005 |
| Una imagen compartida pipeline/api/watcher | Tres imágenes distintas | Evitar duplicación de capas y desincronización de versiones entre componentes que comparten código. ADR-006 |
| Dashboard *API-only* en imagen independiente | Dashboard accediendo a Mongo/SQLite/MinIO directamente | Aislamiento de capa, imagen ligera (~240 MB), reutiliza los contratos HTTP ya implementados. ADR-007 |

Estas decisiones se desarrollan formalmente en los ADR-001 a ADR-010 (capítulo 10) y se referencian a lo largo de los siguientes capítulos cuando se justifica una elección concreta.

---

## 4. Datos

### 4.1. Tipos de datos manejados

El sistema trabaja con cinco familias de datos heterogéneas, cada una persistida en el almacén que mejor encaja con su forma:

| Familia | Naturaleza | Fuente | Almacén destino |
|---|---|---|---|
| Pacientes | Tabular con campos demográficos | `data/raw/patients.csv` (sintético, *Faker*) | MongoDB (`patients`) |
| Admisiones / ingresos | Tabular con FK lógica a paciente | `data/raw/admissions.csv` (sintético) | MongoDB (embebido en `patients.admissions`) |
| Radiografías (binarios + metadatos) | Imagen PNG + metadatos | `data/raw/images/` (dummies para *smoke*) + dataset Kaggle (solo en local) | MinIO (binario) + MongoDB (metadatos en `patients.radiographies`) |
| Métricas operativas | Tabular plano (auditoría + agregados) | Generado por el orchestrator | SQLite (`pipeline_runs`, `data_quality_summary`) |
| Rechazos del pipeline | Documento heterogéneo con `raw_data` por motivo | Generado por `DataValidator` y `DataCleaner` | MongoDB (`rejected_records`) |

### 4.2. Datos sintéticos del pipeline

Los CSVs de pacientes e ingresos están **generados con Faker** (`src/pipeline/scripts/generate_data.py`) con `seed=42`, y se commitean al repositorio para que el arranque sea reproducible y offline. Es la solución natural al problema ético y legal de manejar datos clínicos identificables: no usamos datos reales (ver capítulo 15).

**`patients.csv`** contiene 5.150 filas con `external_id` (formato `HOSP-NNNNNN`), `name`, `birth_date`, `gender` (`M / F / Other`) y `blood_type`. **`admissions.csv`** contiene 10.000 filas con `patient_external_id` (FK lógica a `patients`), `admission_date`, `discharge_date`, `department` (12 valores fijos), `diagnosis_code` (ICD-10) y `status` (`admitted / discharged / transferred`). Los esquemas completos viven en `specs/pipeline-datos.md`.

El generador inyecta **~5 % de casos borde intencionados** para verificar la validación: nulos en campos obligatorios, duplicados, fechas mal formadas, valores fuera de set y admisiones huérfanas (~10 % de FKs apuntan a pacientes inexistentes). Cada uno cubre un CB de la spec (CB-3 nulos, CB-4 duplicados, etc.) y existen tests de regresión asociados. Cualquier desarrollador regenera el mismo dataset con:

```bash
docker compose run --rm --entrypoint "" pipeline \
  python -m src.pipeline.scripts.generate_data --seed 42
```

Las cifras resultantes de procesar este dataset por el pipeline se detallan en la sección 5.8.

### 4.3. Radiografías de tórax (binarios)

El sistema maneja tres familias de imágenes con propósitos distintos, identificadas por el prefijo del `external_id` del paciente al que se atan:

| Prefijo | Origen | Propósito | Estado en repo |
|---|---|---|---|
| `HOSP-NNNNNN` | `generate_dummy_images.py` | *Smoke* del pipeline de ingesta (validan PNG signature, suben a MinIO, se embeben en paciente) | 17 PNGs **dummy 1×1** commiteados |
| `HOSP-DEMO-001` | Bootstrap (numpy + Pillow, 256×256) | Fixture *out-of-the-box* para que la vista *Clasificador* funcione sin pedir descarga del dataset | No commiteada, regenerada en cada arranque |
| `HOSP-PRES-001..006` | Subset de 6 imágenes del COVID-19 Radiography Database | Demo con radiografías reales (2 por clase) | No commiteadas, el bootstrap las copia si existen en local |

**Particularidad (CB-7):** los 17 PNGs dummy son **1×1 píxel** intencionadamente mínimos. Son válidos como fixture de *ingesta* (validan signature) pero **no clasificables**: el endpoint `POST /classify` los rechaza con HTTP 422 porque `MIN_IMAGE_DIM = 32` (`src/ml/preprocessing.py`). El dashboard refuerza esto con un filtro de tamaño en bytes que oculta las dummy del dropdown del clasificador. Por eso el bootstrap genera al vuelo `HOSP-DEMO-001` (256×256), que sí pasa el umbral y permite que el flujo end-to-end del clasificador funcione sin descarga adicional. La UI declara explícitamente que `HOSP-DEMO-001` es sintética y que su predicción no aporta evidencia clínica.

### 4.4. Dataset real para entrenamiento del modelo

El modelo de clasificación se entrena sobre el **COVID-19 Radiography Database** (Kaggle), descargado localmente por el operador y **no commiteado** por tamaño (~0,9 GB) y por licencia: el dataset tiene términos de uso propios que se respetan y citan tal como el proveedor los publica (ver capítulo 15).

| Clase del dataset | Etiqueta del modelo | Imágenes |
|---|---|---:|
| `COVID` | `COVID-19` | 3.616 |
| `Normal` | `Normal` | 10.192 |
| `Viral Pneumonia` | `Pneumonia` | 1.345 |
| `Lung_Opacity` | (descartada) | 6.012 |
| **Total utilizado** | — | **15.153** |

La clase `Lung_Opacity` se **descarta** porque "opacidad pulmonar" es un hallazgo radiológico inespecífico que puede aparecer en muchas patologías, no una categoría diagnóstica que encaje con la clasificación triple del proyecto. La decisión está justificada en la spec de clasificación y en el reporte del modelo (`docs/model-evaluation/report.md`).

El dataset se reparte en **train / validation / test (80 / 10 / 10)** con partición **estratificada** y `seed=42`. La regla operativa es estricta: `train` alimenta `fit`, `validation` alimenta los callbacks (`EarlyStopping`, `ModelCheckpoint`) y guía de hiperparámetros, y `test` se reserva para el reporte final de cada versión candidata. El split de test queda fijado en **1.515 imágenes** (1.019 Normal + 361 COVID-19 + 135 Pneumonia).

### 4.5. Calidad de datos: validación, limpieza y reporte

El pipeline implementa validación **first-failure-wins**: cada fila se queda con el primer motivo de rechazo, no se acumulan. Las reglas para pacientes evalúan formato del `external_id`, presencia de `name`, parseo de `birth_date`, valores válidos de `gender` (incluyendo el rechazo de nulos tras un bug-fix documentado en `lessons.md`) y validez del `blood_type`. Para admisiones, reglas análogas sobre sus campos. Tras la validación campo a campo se ejecuta una **validación cruzada (cross-entity)**: las admisiones cuyo `patient_external_id` no apunta a ningún paciente válido se marcan como **huérfanas** y se rechazan en la dimensión `admissions` del quality summary. Las versiones iniciales del orchestrator no las contabilizaban, lo que daba la falsa impresión de que el pipeline "perdía" registros — fix documentado en `lessons.md` y cubierto por CA-3 de `sqlite-pipeline-metadata`.

`DataCleaner` aplica luego dos operaciones deliberadamente conservadoras: **trim** solo en `name` y `department` (no en campos de negocio que ya habrían fallado en validación si tuvieran whitespace), y **deduplicación** con `dropDuplicates(subset=...)` por `external_id` en pacientes y por `(patient_external_id, admission_date, department)` en admisiones. Una versión anterior basada en *window functions* con `monotonically_increasing_id` se descartó por su no-determinismo entre particiones de Spark (también en `lessons.md`).

El resultado se persiste en SQLite (`data_quality_summary`, una fila por dimensión y run) y se expone vía `GET /api/v1/pipeline/quality-summary` y su histórico paginado. El dashboard lo consume en la vista *Calidad de datos*, con un toggle que oculta por defecto snapshots con `total ≤ 100` para que los runs de test con datasets vacíos no enmascaren los runs operativos reales.

### 4.6. Trazabilidad de cada registro

Tres mecanismos garantizan que cada registro persistido pueda trazarse a su origen:

1. **`_source_file`**: columna añadida por `CSVIngester` con el nombre del CSV de origen.
2. **`pipeline_run_id` (UUID v4)**: cada documento de `rejected_records` lleva el UUID del run que lo rechazó (referencia blanda Mongo → SQLite). Permite ir del *quality summary* (SQLite) a los rechazos crudos (Mongo) para un run concreto.
3. **`ingested_at`**: timestamp en los metadatos de cada radiografía en MinIO. El campo se renombró desde `capture_date` por claridad (la fecha real de captura del paciente no la conocemos).

La conjunción de los tres permite responder a *"¿qué fichero CSV y qué run produjo este rechazo concreto?"* sin tener que consultar logs.

---

## 5. Pipeline ETL

### 5.1. Visión general del pipeline

El pipeline ETL es el componente más grande del sistema y se diseña como una **cadena de etapas** orquestadas por `PipelineOrchestrator` (`src/pipeline/orchestrator.py`):

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

Cada componente vive en una subcarpeta de `src/pipeline/` (`ingesters/`, `processors/`, `storage/`, `scripts/`) y el detalle de implementación está en la spec `pipeline-datos`. Esta sección se centra en el **porqué** de cada etapa y en los matices que conviene saber para defender el diseño.

### 5.2. Ingesta (E)

**`CSVIngester`** lee CSVs a *DataFrames* de PySpark, valida que existan las columnas requeridas (lanza `MissingColumnsError` si no) aceptando cualquier orden, y añade una columna `_source_file` para trazabilidad. Una decisión que merece comentario: no se fuerza `df.count()` tras la lectura. Era una *action* innecesaria que rompía la optimización perezosa de Spark; el bug-fix está documentado en `lessons.md`.

**`ImageIngester`** lee PNGs del filesystem, valida la *signature* PNG (primeros 8 bytes `\x89PNG\r\n\x1a\n`) y los sube a MinIO con metadatos. El *object key* es **determinista**: `{patient_id}/{filename}`, sin timestamp en el path, lo que permite que la subida sea idempotente (MinIO sobrescribe sin error). Una imagen corrupta o no-PNG se loguea y se omite sin propagar excepción (CB-2). Cada imagen genera dos efectos: el PNG sube a `MinIO/radiographies/{patient_id}/{filename}` y se añade el documento de metadatos al array `patients.radiographies` del paciente correspondiente vía `MongoWriter.add_radiography_to_patient` (idempotente con `$ne` sobre `minio_object_key`).

### 5.3. Validación y limpieza (T parte 1)

**`DataValidator`** separa filas válidas de rechazadas con una política **first-failure-wins**: cada fila se queda con el primer motivo de rechazo, no se acumulan motivos. El resultado son dos DataFrames: `valid_df` y `rejected_df`, este último con un campo `rejection_reason` (`empty_name`, `invalid_birth_date`, `invalid_gender`, etc.) y todos los campos originales conservados en `raw_data`. Las reglas concretas se describen en 4.5.

Un detalle relevante: las reglas `isin` para `gender`, `blood_type` y `status` originalmente **no capturaban valores `NULL`** por la lógica ternaria de PySpark (`null isin {a, b, c} -> null`, no `false`). El fix fue añadir `col.isNull() |` a las tres reglas, con tests de regresión propios. Es un *gotcha* clásico de PySpark y se descubrió cuadrando los números del smoke test a mano contra los datos sintéticos. Está documentado en `lessons.md`.

**`DataCleaner`** aplica dos operaciones intencionadamente conservadoras (la limpieza no debe modificar campos de negocio): **trim** solo en `name` y `department`, donde el whitespace es un artefacto típico, y **deduplicación** con `dropDuplicates(subset=['external_id'])` en pacientes y `dropDuplicates(subset=['patient_external_id', 'admission_date', 'department'])` en admisiones. Una versión anterior basada en *window functions* con `monotonically_increasing_id` se descartó por no-determinismo entre particiones de Spark — el orden en el que se elegía "qué duplicado conservar" no era estable.

### 5.4. Transformación (T parte 2)

`DataTransformer` enriquece los DataFrames con dos columnas calculadas:

- **`age`** (a partir de `birth_date`, mes a mes): `floor(months_between(reference_date, birth_date) / 12)`. Acepta `reference_date` como parámetro para tests deterministas (por defecto `current_date()` de Spark).
- **`diagnosis_category`** (a partir de `diagnosis_code` en ICD-10): `J18.x` → `Pneumonia`, `U07.1` → `COVID-19`, otros códigos válidos → `Other`, no reconocidos → `Unknown`. La distribución observada tras el smoke (**9,7 % COVID-19 / 19,5 % Pneumonia / 70,8 % Other**) cuadra con la distribución 1/10, 2/10, 7/10 que el generador inyecta intencionadamente para que las tres clases queden representadas en proporciones razonables, sin pretender que reflejen incidencia clínica real.

`DataTransformer` también expone tres métodos de agregación (`admissions_by_department`, `admissions_by_month`, `admissions_by_diagnosis_category`) **implementados y testeados unitariamente** pero todavía no consumidos por la API ni el dashboard. Quedan como bloque reutilizable para análisis futuros sin tener que rehacer el cómputo.

### 5.5. Carga (L)

**`MongoWriter`** materializa el modelo documental. Su método clave es `bulk_upsert_patients_with_admissions`, que ejecuta una operación `bulk_write` de pymongo con `UpdateOne(upsert=True)` por paciente, embebiendo las admisiones como subdocumentos en `patients.admissions` (no como colección separada con FK). La idempotencia se garantiza por construcción: re-ejecutar el pipeline con los mismos CSVs sobrescribe el array completo del paciente, sin duplicar admisiones (CA-6 del pipeline).

**`SqlWriter`** persiste los metadatos operativos en SQLite a través de SQLAlchemy. Abre el run con `start_pipeline_run(trigger_type) -> run_id` (UUID v4 string), lo cierra con `finish_pipeline_run(run_id, status, counts, error_message=None)` y escribe el resumen de calidad con `write_quality_summary(run_id, summaries)` (una fila por dimensión). El esquema completo vive en `src/pipeline/storage/sql_models.py`. Lo arquitectónicamente relevante: `pipeline_runs.id` es un **UUID v4 string** referenciado desde `rejected_records.pipeline_run_id` como referencia blanda (sin FK enforcement entre Mongo y SQLite); la tabla `pipeline_runs` incluye `images_processed` además de `records_processed` y `records_rejected` por la naturaleza dual del pipeline (tabular + binario).

SQLite se ejecuta en **modo WAL** (write-ahead logging) para soportar concurrencia entre `pipeline` (escribiendo el run), `watcher` (eventualmente escribiendo otro) y `api` (leyendo). El volumen `pipeline-db` se monta `rw` en los tres servicios porque WAL crea ficheros sidecar (`.wal`, `.shm`) en el mismo directorio.

### 5.6. Orquestación y *triggers*

`PipelineOrchestrator` coordina las etapas y gestiona el ciclo de vida del run. Su método principal, `run_from_files(patients_csv, admissions_csv, trigger_type, run_id=None)`, abre un run en SQLite si no recibe uno, ejecuta toda la cadena E→T→L dentro de un `try/except` y cierra el run con `status='success'` o `status='failed' + error_message` según el resultado.

El orchestrator se invoca desde **cuatro orígenes** (CA-6 y CA-7 del pipeline original):

| Origen | Cuándo se lanza | `trigger_type` |
|---|---|---|
| **Bootstrap** | `CMD` del servicio `pipeline` en `docker compose up`. Solo ejecuta el ETL si MongoDB está vacío. | `bootstrap` |
| **Watcher** | Proceso *long-running* que detecta `patients.csv` + `admissions.csv` en `data/incoming/`, ejecuta y mueve los ficheros a `processed/`. | `watcher` |
| **API** | `POST /api/v1/pipeline/trigger` lanza el orchestrator como `BackgroundTask`, devuelve `run_id` inmediatamente con HTTP 202. | `manual` |
| **Tests E2E** | Lanzan el orchestrator con datasets sintéticos para verificar los criterios de aceptación. | `e2e-test` (filtrado por defecto en la vista del dashboard) |

### 5.7. Gestión de fallos

Dos principios:

1. **Fallos en una fila no detienen el batch**: la validación produce un DataFrame de rechazados que se persiste en `rejected_records`; los demás siguen procesándose.
2. **Fallos en una etapa entera marcan el run como `failed` con mensaje explícito y se re-lanzan**: el `try/except` del orchestrator captura cualquier excepción, invoca `SqlWriter.finish_pipeline_run(run_id, status='failed', error_message=str(e))` para que SQLite registre el cierre y la causa, y re-lanza la excepción al llamante. El run no se "evapora": queda visible en `GET /api/v1/pipeline/runs` con su `error_message`.

La indisponibilidad de Mongo o MinIO se manifiesta como una excepción del cliente correspondiente y entra por el flujo anterior. El test `test_image_ingester_silent_failure` verifica explícitamente que `ImageIngester` con MinIO inalcanzable **no** devuelve metadatos como si todo hubiera ido bien (CA-8: "si MinIO o MongoDB no están disponibles, el pipeline loguea el error y no crashea silenciosamente"). Este caso fue uno de los cuatro bloqueantes detectados en la revisión técnica inicial y corregidos antes de cerrar T10.

### 5.8. Métricas observadas

Sobre el dataset sintético commiteado (`patients.csv` 5.150 filas + `admissions.csv` 10.000), el resultado de un bootstrap en frío es:

- **Pacientes:** 5.150 → 264 rechazados por validación + 141 deduplicados → **4.745 finales** en MongoDB.
- **Admisiones:** 10.000 → 493 rechazadas + 3 deduplicadas + 935 huérfanas cross-entity → **8.569 finales** embebidas.

| Métrica | Valor |
|---|---|
| Total en `rejected_records` | 1.692 (264 patients + 1.428 admissions, incluyendo 935 huérfanas; los deduplicados no se contabilizan ahí) |
| Imágenes en MinIO | 17 dummy + 1 demo + 6 reales (si el dataset Kaggle está presente) |
| Tiempo de bootstrap | ~50 s en una máquina de desarrollo media |
| Tiempo de *warm restart* | ~1 s (todos los skips idempotentes) |

Estos números son **reproducibles**: se obtienen idénticos en cualquier máquina con `docker compose down -v && docker compose up`.

---

## 6. Sistemas de IA

El proyecto incorpora **dos sistemas de IA complementarios**, cada uno apoyado en un paradigma distinto porque las condiciones del problema son distintas:

1. Un **clasificador de radiografías de tórax** basado en una red neuronal convolucional (CNN) entrenada desde cero sobre el *COVID-19 Radiography Database*. Cae en la familia de **modelos aprendidos a partir de datos etiquetados** que recoge el Bloque 6 del Máster (Aprendizaje Automático). Se describe en los apartados 6.1 a 6.7.
2. Un **sistema de triaje de pacientes** implementado como **reglas IF-THEN deterministas** sobre signos vitales y síntomas declarados en el registro manual. Cae en la familia de **sistemas basados en reglas / reglas de producción** que se introduce en la sesión sobre Modelos de IA del Máster (con el material de referencia `ruleBasedSystem/`). Se describe en el apartado 6.8.

El apartado 6.9 cierra el capítulo explicando por qué se ha elegido un paradigma distinto para cada sistema y por qué esa decisión no es un compromiso, sino una respuesta a los datos disponibles en cada subproblema.

### 6.1. Clasificador de radiografías — encuadre del problema (primer sistema de IA)

El **primer sistema de IA** del proyecto clasifica radiografías de tórax en tres clases (`Normal`, `Pneumonia`, `COVID-19`) como **asistencia diagnóstica** — no como diagnóstico final. La spec `clasificacion-radiografias` fija explícitamente que **no hay umbral bloqueante de *accuracy***: para evaluar el modelo se mira el *recall* por clase (cuántos positivos reales detecta) y la matriz de confusión, no solo una cifra global. Esto se alinea con lo enseñado en el Bloque 6 del Máster (Aprendizaje Automático, profesor Jordi): en problemas clínicos, dejar pasar un positivo (falso negativo) suele tener peor consecuencia que avisar de más (falso positivo), así que el *recall* manda sobre la *accuracy*.

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

Sobre las **1.515 radiografías** del split de test (1.019 `Normal` + 361 `COVID-19` + 135 `Pneumonia`), con la regla de decisión operativa `covid_threshold_0.35` (ADR-010):

- **Accuracy global:** 0,8766
- **Macro-F1:** 0,8594

Métricas por clase (con el *recall* destacado por su relevancia clínica):

| Clase | Precision | Recall | F1 | Soporte |
|---|---|---|---|---|
| Normal | 0,932 | **0,890** | 0,911 | 1.019 |
| Pneumonia | 0,845 | **0,926** | 0,883 | 135 |
| COVID-19 | 0,751 | **0,820** | 0,784 | 361 |

Matriz de confusión 3x3 con la regla operativa (filas = clase real, columnas = clase predicha):

| Real \\ Predicha | Normal | Pneumonia | COVID-19 |
|---|---|---|---|
| **Normal** | 907 | 17 | 95 |
| **Pneumonia** | 7 | 125 | 3 |
| **COVID-19** | **59** | 6 | 296 |

A modo de trazabilidad y *baseline* descartado, las mismas probabilidades evaluadas con `argmax` puro daban *accuracy* 0,8719, macro-F1 0,8456 y *recall* COVID-19 de 0,695 (110 falsos negativos COVID-19 frente a 65 con el umbral). La comparación completa argmax vs umbral se preserva en `docs/model-evaluation/metrics.json` (bloque `comparison_argmax`) y en `docs/model-evaluation/report.md`. La justificación formal de la regla, la elección concreta del umbral 0,35 frente a 0,30 y 0,40 y el alcance limitado (post-hoc, sin reentrenamiento) viven en **ADR-010** y en `docs/model-evaluation/threshold-analysis.md`.

Los artefactos visuales completos están en `docs/model-evaluation/confusion_matrix.png` (mapa de calor de la matriz con la regla operativa) y `docs/model-evaluation/learning_curves.png` (curvas de *loss* y *accuracy* por *epoch* para *train* y *val*).

### 6.6. Lectura cualitativa de los errores (CA-3)

La matriz de confusión tiene seis tipos de error y no todos pesan igual en un hospital. El más grave es el **falso negativo de COVID-19** (un paciente que sí lo es y el modelo lo clasifica como `Normal`), porque ese paciente no se aislaría. Por debajo se sitúan los **falsos negativos de Pneumonia** (neumonía no detectada) y las **confusiones COVID ↔ Pneumonia** (al menos llevan a un protocolo respiratorio aunque la etiqueta exacta esté mal). Los **falsos positivos** son los menos graves: generan pruebas adicionales pero no ponen al paciente en riesgo.

Con la regla operativa `covid_threshold_0.35`, el modelo deja **59 COVID-19 clasificados como Normal y 6 como Pneumonia (65 COVID-19 que se pierden como tal)**, lo que se traduce en un *recall* de **0,820** para esa clase — frente a los 110 falsos negativos y *recall* 0,695 del *baseline* argmax. La mejora paga un coste cuantificado: 95 falsos positivos COVID-19 sobre Normal (frente a 58 con argmax), 37 confusiones más que generan revisiones clínicas adicionales pero no implican alta de un contagioso. Aun así, el *recall* COVID-19 = 0,820 sigue lejos de la sensibilidad exigible en un entorno asistencial real, y por eso el sistema se entrega como herramienta de asistencia que prioriza casos para que los revise un profesional, no como sustituto del juicio clínico.

### 6.7. Ciclo de vida del modelo en producción

El modelo se integra con la API mediante un *predictor* cargado al arrancar (`lifespan` de FastAPI). Si el artefacto `.keras` está presente, los endpoints de clasificación responden normalmente; si no, la API arranca igualmente y los endpoints de clasificación devuelven HTTP 503 con mensaje claro (CB-4), pero el resto de endpoints siguen funcionando (CA-7).

El campo `patients.radiographies[].classification` en MongoDB pasa de `null` a un objeto con cinco campos (desde Feature 16; el quinto se rellena por defecto con `covid_threshold_0.35`):

```
predicted_class:  "Normal" | "Pneumonia" | "COVID-19"
probabilities:    {Normal: 0.62, Pneumonia: 0.02, COVID-19: 0.36}
predicted_at:     "2026-05-17T18:42:11Z"
model_version:    "v1.0-20260516-192647"
decision_rule:    "covid_threshold_0.35"
```

Las `probabilities` son las salidas softmax brutas del modelo (no se renormalizan tras aplicar el umbral). El campo `decision_rule` queda persistido para que cualquier auditoría posterior pueda reconstruir cómo se obtuvo `predicted_class` a partir de las probabilidades. Las clasificaciones persistidas antes de Feature 16 no tienen este campo: la API las devuelve con `decision_rule="legacy_argmax"` al leerlas, en lugar de fallar la validación de Pydantic.

La idempotencia se garantiza con `matched_count > 0` (no `modified_count`) en el update, de modo que clasificar dos veces la misma imagen con el mismo modelo no provoca falsos negativos al verificar que la operación ha llegado a la base.

### 6.8. Triaje de pacientes — segundo sistema de IA (reglas de producción)

El **segundo sistema de IA** del proyecto asigna un **nivel de prioridad** (`grave` / `medio` / `leve`) a cada paciente que se registra manualmente desde el dashboard, a partir de sus signos vitales y de los síntomas declarados. La spec correspondiente es `triage-pacientes` y la decisión de paradigma está formalizada en **ADR-008**.

#### Por qué no hay un modelo aprendido aquí

El proyecto **no entrena** un clasificador supervisado para esta tarea por una razón concreta: **no existe dataset etiquetado con la gravedad real de cada paciente**. El CSV sintético (`patients.csv`) no contiene signos vitales ni una columna `grave/medio/leve`; el dataset Kaggle de radiografías etiqueta imágenes con patología pulmonar, no severidad del paciente; y no se planea recolectar datos clínicos reales con permisos. Entrenar un modelo sobre etiquetas inventadas por el propio equipo sería **fabricar ground truth**, no aprenderlo, así que el problema no encaja con aprendizaje supervisado.

En cambio, el Máster presenta explícitamente los **sistemas basados en reglas / reglas de producción** como alternativa legítima cuando faltan datos etiquetados y se prioriza la **trazabilidad** sobre la capacidad predictiva fina. La sesión sobre Modelos de IA muestra ese paradigma con material de referencia (`ruleBasedSystem/`): un conjunto de condiciones IF-THEN escritas por el equipo, cada una con su semántica explícita.

#### Cómo se implementa

La lógica vive como **función pura** `evaluate(payload) -> TriageResult` en `src/api/triage.py`, sin acceder a Mongo ni a FastAPI. El esquema es deliberadamente simple:

| Nivel | Cuándo se asigna |
|---|---|
| **grave** | Si dispara al menos una regla "crítica" sobre signos vitales (saturación, frecuencia respiratoria, frecuencia cardíaca, presión sistólica) o aparece un síntoma marcado como crítico en la lista. |
| **medio** | Si NO grave y dispara alguna regla "intermedia": signos vitales en franja moderada o combinación edad-riesgo (paciente mayor con síntoma respiratorio o fiebre alta). |
| **leve** | Caso por defecto: ninguna regla anterior dispara. |

Hay **6 reglas grave** y **5 reglas medio**, cada una con un **identificador estable** del tipo `spo2_lt_92`, `fr_gt_30`, `anciano_riesgo_respiratorio`. Cuando el sistema asigna un nivel, el resultado **no es un número opaco**: viene acompañado de la lista exacta de reglas que han disparado en el campo `reasons`. El historial queda persistido en `patients.triage.reasons` con `rules_version=1.0`, lo que permite responder con precisión a la pregunta *"¿por qué este paciente se clasificó como grave?"* — propiedad mucho más directa que en un modelo entrenado, donde explicar la predicción requiere típicamente técnicas de interpretabilidad adicionales (Grad-CAM, SHAP, etc.).

Los **umbrales son valores académicos simplificados** elegidos para que las tres clases queden representadas con casos verosímiles a partir del generador sintético. No corresponden a ningún protocolo médico real, no han sido validados clínicamente y se documentan como tal en la spec, en el ADR-008 y en la propia UI del dashboard.

#### Garantías técnicas

Tres propiedades blindan que el sistema se comporte como debe:

- **Determinismo**: dada una misma entrada, `evaluate` devuelve siempre el mismo `TriageResult`. No hay aleatoriedad ni dependencia del reloj.
- **Auditabilidad**: cada decisión guarda en Mongo el `level`, el `score` (número de reglas disparadas), las `reasons`, los signos vitales evaluados y la versión de las reglas. Se puede reconstruir cualquier triaje pasado sin re-evaluar.
- **Tests**: 34 tests unitarios puros cubren las 11 reglas (incluidos los casos borde de fronteras 91/92 SpO2, 30/31 FR, 130/131 FC, 89/90 PAS, 38,9/39,0 ºC), 21 tests de endpoint cubren el contrato HTTP, 2 tests verifican que el writer no sobrescribe pacientes existentes, y 6 tests E2E ejecutan el flujo contra el stack vivo. La conjunción de unit + endpoint + E2E hace que cualquier cambio en una regla rompa al menos un test, lo que actúa como cláusula de seguridad.

#### Lo que el sistema **no** es

Conviene dejarlo escrito sin ambigüedad, porque el dominio invita a malentendidos:

- **No es un sistema clínico validado.** No ha sido evaluado contra resultados clínicos reales ni revisado por personal sanitario.
- **No sustituye el criterio médico.** Es asistencia de priorización, pensada para que un operador del hospital tenga una propuesta de nivel cuando hace un registro manual; la decisión clínica la toma siempre el profesional.
- **No implementa ningún protocolo médico estándar.** Las reglas son una elaboración propia del equipo a partir de signos vitales razonables; no se replica ningún sistema externo ni se cita como tal.

Esta posición se materializa en la UI: la vista *Triaje* muestra el nivel con su color (rojo / ámbar / gris) acompañado de un disclaimer explícito de asistencia, y un *expander* deja a la vista las reglas vigentes para que el operador pueda interpretar por qué se ha asignado ese nivel.

### 6.9. Por qué dos paradigmas de IA en el mismo proyecto

La elección de paradigma no es una preferencia estilística, es una respuesta a **los datos disponibles en cada subproblema**:

| Subproblema | Datos disponibles | Paradigma elegido |
|---|---|---|
| Clasificar una radiografía como `Normal` / `Pneumonia` / `COVID-19` | Dataset Kaggle con miles de imágenes etiquetadas por clase | **Modelo aprendido** (CNN). Aprender los patrones visuales desde los datos es la única vía razonable: no hay forma de escribir reglas IF-THEN sobre píxeles que generalicen. |
| Asignar un nivel de prioridad `grave` / `medio` / `leve` a un paciente | Sin dataset etiquetado con gravedad real; sí hay criterios operativos claros sobre signos vitales | **Sistema basado en reglas**. Sin etiquetas no se puede aprender; con criterios explícitos sí se pueden escribir reglas trazables y auditables. |

La consecuencia es que el proyecto **no usa IA por usar IA**, sino que aplica en cada subproblema la familia de técnicas que el Máster propone para ese contexto. Esa coherencia método-problema es la idea fuerza de este capítulo y la lección general que merece la pena llevarse: la **representación del problema** (qué tienes y qué te falta) determina qué técnica encaja, no al revés.

---

## 7. API REST

### 7.1. Encuadre

La API es el **único punto de entrada HTTP** del sistema. Sirve datos procesados, expone los metadatos operativos del pipeline y ofrece la inferencia del modelo. Está implementada con **FastAPI + Uvicorn**, con esquemas Pydantic V2 para validación de entrada/salida, paginación uniforme y documentación interactiva en `/docs` (Swagger UI) generada automáticamente. Todos los endpoints están bajo el prefijo `/api/v1/` para permitir versionado futuro sin romper clientes.

### 7.2. Arquitectura interna

La capa API aplica **separación lectura/escritura** como patrón interno del proyecto (`MongoReader`/`MongoWriter`, `SqlReader`/`SqlWriter`) para evitar acoplar los modelos de lectura a los del writer del pipeline:

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
| `POST /api/v1/triage/patients` | MongoDB (writer) | Alta manual de paciente con asignación de prioridad por reglas (ADR-008). Devuelve 201 con el paciente y su `triage` embebido |
| `GET /api/v1/triage/rules` | — | Devuelve la definición de las reglas de triaje vigentes (autodocumentación, RF-8 de triage) |
| `GET /api/v1/alerts` | MongoDB + SQLite | Alertas activas calculadas bajo demanda (ADR-009). 3 tipos: `pipeline_failed`/high, `data_quality_low`/medium, `triage_severe`/critical. Query params `since`, `severity`. Ventana por defecto: últimas `ALERT_WINDOW_HOURS` (24h) |
| `GET /api/v1/reports/daily?date=YYYY-MM-DD` | MongoDB + SQLite | Informe estructurado JSON del día consultado. **Ventana estricta** `[00:00, 23:59:59.999]` UTC; NO reutiliza la ventana de `/alerts`. Misma función pura `evaluate()` |

### 7.4. Decisiones de diseño relevantes

- **`minio_object_key` en *body* o *query*, nunca en *path***: la clave contiene barras (`HOSP-000001/HOSP-000001_xray1.png`). Meterla en *path* obligaría a `{key:path}` y complica clientes, escape de caracteres y herramientas. La decisión está documentada en la spec de clasificación.
- **Códigos HTTP separados para señales independientes** (CB-4 del dashboard): `predictor_loaded=false` en `/health` significa "modelo no cargado"; `503` en `/model/evaluation` significa "reporte de métricas ausente". Son dos estados distintos: puede haber modelo cargado sin reporte (alguien borró `metrics.json`) o reporte sin modelo (entrenamiento previo, artefacto perdido). El dashboard los trata por separado.
- **`/radiographies/image`** es un **proxy puro de lectura**: descarga los bytes desde MinIO con `Content-Type: image/png`, sin tocar Mongo ni el modelo. Sin este endpoint, un dashboard *API-only* no podría renderizar imágenes (no puede abrir conexión directa a MinIO por la decisión de ADR-007).
- **Idempotencia del `classify`**: `MongoWriter.set_radiography_classification` retorna `matched_count > 0` (no `modified_count`), de modo que un segundo `classify` con el mismo modelo y misma imagen — que escribe el mismo `predicted_class` y `probabilities` — sigue contando como éxito aunque `modified_count` sea 0 al no haber diferencia.
- **`POST /pipeline/trigger` devuelve 202**: la ejecución del orchestrator es asíncrona (`BackgroundTasks`). El cliente recibe el `run_id` inmediatamente; el estado se consulta luego en `/pipeline/runs`.
- **Alertas como vista derivada (ADR-009)**: `GET /api/v1/alerts` y la sección `alerts` del informe diario se calculan al vuelo combinando `pipeline_runs.status='failed'` (high), `data_quality_summary.rejection_rate > umbral` (medium) y `patients.triage.level='grave'` (critical). **Cero estado nuevo persistido**: no hay tabla `alerts`. La lógica vive como **función pura** `src/api/alerts.py::evaluate(failed_runs, quality_snapshots, severe_triage_patients, threshold) -> list[Alert]`, mismo patrón que el triaje (ADR-008) y la teoría de sistemas basados en reglas (Sesión 07 de Yuri, `ruleBasedSystem/`).
- **Doble ventana temporal sin duplicar la regla**: `/alerts` usa `[now - ALERT_WINDOW_HOURS, now]` (estado actual del sistema); `/reports/daily` usa `[YYYY-MM-DDT00:00:00Z, YYYY-MM-DDT23:59:59.999Z]` (cierre del día natural UTC). La función `evaluate` NO conoce el reloj — solo aplica las reglas sobre las listas que recibe. Los readers exponen dos familias paralelas (`_since` para `/alerts`, `_between` para `/reports/daily`).
- **Idempotencia byte-a-byte del Markdown del informe (RNF-6 / CA-11)**: el script `src/automation/daily_report.py` produce `docs/reports/YYYY-MM-DD.md` deterministicamente. Misma fecha + mismo estado del sistema → mismo fichero (`sha256` idéntico). Lo hace separando `build_daily_report` (que puede llevar `generated_at` dinámico en el dict) de `render_markdown` (que NO lee el reloj, NO incluye `generated_at` y ordena listas por claves estables). El JSON del endpoint `/reports/daily` sí lleva `generated_at` como metadato: la idempotencia byte-a-byte aplica **sólo al Markdown**.

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
| `views/{overview,quality,patients,triage,alerts,classifier,runs}.py` | Una vista por fichero (siete) |
| `components/{error_banner,system_status}.py` | Componentes reutilizables (banner de error consistente, chips de estado del sistema) |

### 8.3. Las siete vistas

Cada vista vende explícitamente una pieza del *stack* (ver tabla "Razón de producto por vista" en la spec):

| Vista | Pieza del stack que evidencia |
|---|---|
| **Overview** | Salud operativa + KPI agregados + *strip* mínimo de evaluación del modelo |
| **Calidad de datos** | Pipeline Big Data + `data_quality_summary` |
| **Pacientes** | MongoDB con `admissions` y `radiographies` embebidas |
| **Triaje** | Sistema basado en reglas (ADR-008) + registro manual de paciente con prioridad |
| **Alertas** | Observabilidad accionable (ADR-009): vista derivada calculada bajo demanda desde `pipeline_runs`, `data_quality_summary` y `patients.triage` |
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

## 9. Automatización y observabilidad

El enunciado del Máster pide tres cosas concretas en este eje: "procesamiento automático de nuevos datos", "generación automática de informes" y "alertas o notificaciones ante eventos relevantes". El proyecto cubre las tres con piezas que ya han ido apareciendo en capítulos anteriores (el watcher en 5.6, el bootstrap en 11.1, las vistas del dashboard en 8.3); este capítulo las **consolida en un mismo marco** para hacer explícito qué decisión hay detrás de cada una y por qué el sistema no incluye un *scheduler* real.

### 9.1. Dos sentidos de "automatización" — qué se entrega y qué no

La palabra "automatización" cubre realidades distintas. Este proyecto distingue dos sentidos y se posiciona explícitamente sobre cuál cubre y cuál no:

| Sentido | Definición | Lo que entrega el proyecto |
|---|---|---|
| **Automatización por evento** | Una acción del sistema se dispara sola cuando ocurre un evento externo (cambio en filesystem, mensaje en cola, hora del reloj). | **Sí**, en dos puntos: el `watcher` reacciona a nuevos CSVs en `data/incoming/` (sección 9.2) y el bootstrap reacciona al `docker compose up` ejecutando el ETL inicial si MongoDB está vacío (sección 9.3). |
| **Automatización por reproducibilidad** | Un comando produce siempre el mismo resultado dado el mismo estado del sistema. Sustituye un proceso "manual frágil" por uno "manual robusto". | **Sí**, con el script `daily_report.py` (sección 9.5) cuyo Markdown es idéntico byte-a-byte si la fecha y el estado son los mismos. |
| **Programación temporal (*scheduling*)** | Cron, Celery, APScheduler, Airflow: ejecutan acciones a intervalos. | **No.** Es una elección deliberada — ver 9.7. |
| **Notificación *push* (email/SMS/Slack)** | El sistema avisa al operador cuando algo ocurre, sin que el operador tenga que mirar. | **No.** El proyecto entrega un modelo *pull* (entrada en el dashboard) — ver 9.4. |

El enunciado deja libertad explícita en este último punto al decir "puede ser un log, un email simulado o una entrada en el dashboard". El proyecto elige la entrada en el dashboard.

### 9.2. Procesamiento automático de nuevos datos — el `watcher`

El servicio `watcher` es la pieza de automatización por evento más visible del sistema. Es un proceso *long-running* dentro de un contenedor Docker que usa la librería `watchdog` para vigilar el directorio `data/incoming/`. Cuando aparecen simultáneamente los dos ficheros esperados (`patients.csv` y `admissions.csv`), el watcher:

1. Invoca a `PipelineOrchestrator.run_from_files(...)` con `trigger_type="watcher"`.
2. Tras un cierre con éxito, mueve los ficheros a `data/incoming/processed/` para que no se re-procesen.
3. Si el orchestrator falla, los ficheros se quedan en `data/incoming/` y el run queda registrado con `status=failed` y `error_message` en SQLite, visible desde la vista *Pipeline runs*.

El watcher es uno de los **cuatro orígenes** del orchestrator descritos en la sección 5.6 (bootstrap, watcher, API y tests E2E). Aquí lo encuadramos por su rol específico: **el watcher es lo que hace que el sistema procese datos sin intervención humana**. El resto de orígenes son bajo demanda; el watcher es continuo.

Esta pieza no requiere `cron` ni planificación temporal porque el disparador es un cambio en filesystem, no un horario. Esa es la forma "fuerte" de automatización por evento que el proyecto sí entrega.

### 9.3. Arranque automático — el bootstrap idempotente

El segundo punto de automatización por evento es el **bootstrap** que se ejecuta al levantar el sistema con `docker compose up`. Su responsabilidad está descrita con detalle en 11.1; lo relevante en este capítulo es que **garantiza que no hay pasos manuales** entre clonar el repositorio y tener el sistema operativo:

- Crea el schema SQLite si no existe.
- Sincroniza imágenes locales al bucket MinIO (sólo las que faltan, comparando conjuntos).
- Ejecuta el ETL completo si MongoDB está vacío.
- Skip selectivo basado en estado: re-ejecutar no duplica nada.

La propiedad clave es la **idempotencia**: el mismo `docker compose up` aplicado dos veces produce exactamente el mismo estado. Esto convierte una operación que normalmente sería "manual + frágil" (varios comandos en orden, alguno olvidado, mensajes de error opacos) en una operación "automática + robusta" (un comando, mismo resultado siempre).

### 9.4. Alertas operativas bajo demanda — `GET /api/v1/alerts`

El tercer requisito del enunciado en este eje ("alertas o notificaciones ante eventos relevantes") se cumple con el endpoint `GET /api/v1/alerts`, expuesto por la API y consumido por la vista *Alertas* del dashboard. La decisión arquitectónica principal está formalizada en **ADR-009**: las alertas son una **vista derivada** que se calcula al consultar el endpoint, leyendo las fuentes ya existentes; **no se guardan en una tabla nueva**.

#### Qué considera "alerta" el sistema

Tres tipos, cada uno construido a partir de una fuente que ya está siendo poblada por otras partes del sistema:

| Tipo | Severity | Fuente | Cuándo se dispara |
|---|---|---|---|
| `pipeline_failed` | high | `pipeline_runs` (SQLite) | Un run con `status=failed` dentro de la ventana. |
| `data_quality_low` | medium | `data_quality_summary` (SQLite) | Un snapshot con `rejection_rate` por encima de `ALERT_REJECTION_RATE_THRESHOLD` (default 0,10). |
| `triage_severe` | critical | `patients.triage` (MongoDB) | Un paciente con `triage.level="grave"` dentro de la ventana. |

La **ventana temporal por defecto** son las últimas 24 horas (`ALERT_WINDOW_HOURS=24`), sobreescribibles con el query param `since=ISO_DATETIME`. El umbral de calidad es configurable por entorno. Ambos defaults se han elegido para que el sistema dé señal útil en una demo con el dataset sintético: ni se queda en silencio durante toda la presentación, ni se llena de alertas espurias.

#### Por qué una función pura `evaluate()`

La lógica de evaluación vive como **función pura** `evaluate(failed_runs, quality_snapshots, severe_triage_patients, threshold) -> list[Alert]` en `src/api/alerts.py`. **No accede a Mongo ni a SQLite directamente**: recibe las listas ya filtradas por el caller. Esa separación tiene un beneficio concreto: la **misma** `evaluate` se usa con dos ventanas temporales distintas (las 24 h del endpoint `/alerts` y el día natural UTC del endpoint `/reports/daily`), sin duplicar lógica. La función no conoce el reloj — solo aplica las tres reglas IF-THEN sobre las listas que recibe.

Es el mismo patrón arquitectónico que el triaje (sección 6.8): reglas explícitas, deterministas, auditables, testables sin Mongo ni FastAPI. Los 13 tests unitarios puros de `evaluate` cubren los tres tipos de alerta, los casos borde de umbral y el orden de salida por severidad.

### 9.5. Informe diario reproducible — endpoint + CLI

La "generación automática de informes" del enunciado se materializa en dos formas complementarias:

#### Endpoint HTTP — `GET /api/v1/reports/daily?date=YYYY-MM-DD`

Devuelve un JSON estructurado con el cierre del día consultado. El cuerpo tiene cinco secciones (`pipeline`, `quality`, `counts`, `triage`, `alerts`) más el metadato `generated_at` con el momento de cálculo. La ventana temporal es **estricta del día UTC**: `[YYYY-MM-DDT00:00:00Z, YYYY-MM-DDT23:59:59.999Z]`. No reutiliza la ventana móvil de `/alerts` — el informe es del día solicitado, no de las últimas 24 horas, y esa distinción es lo que hace que un informe del 15 de mayo siga siendo el informe del 15 de mayo aunque se consulte el 20.

#### Script CLI — `python -m src.automation.daily_report --date YYYY-MM-DD`

Escribe el mismo contenido en formato **Markdown** dentro de `docs/reports/YYYY-MM-DD.md`. NO arranca FastAPI: lee directamente desde `MongoReader` + `SqlReader` y llama internamente al mismo `build_daily_report(...)` que usa el endpoint. La unidad clave es DRY: una sola función arma la estructura, dos interfaces la sirven (HTTP / fichero).

#### La pieza que cierra el círculo: idempotencia byte-a-byte (RNF-6 / CA-11)

Esta es la propiedad técnica más característica del bloque. En lenguaje natural: si se ejecuta el script dos veces sobre la misma BBDD y la misma fecha (un día cerrado), el fichero `.md` resultante es **exactamente el mismo**, byte por byte. Misma BBDD + mismo `--date` aplicado dos veces → dos ficheros con `sha256` idéntico (lo que confirma que no hay ni un carácter de diferencia entre ambos).

Se consigue separando el builder del render:

- `build_daily_report(...)` puede llevar `generated_at` dinámico en el dict que produce (el endpoint HTTP lo emite tal cual).
- `render_markdown(report)` **NO lee el reloj** y **NO incluye `generated_at` en el fichero**: lee solo del dict que recibe, ordena listas por claves estables (timestamps + ids) y formatea con números fijos de dígitos.

El resultado verificable: en el smoke real, dos ejecuciones consecutivas con `--date 2026-05-20` produjeron el mismo hash `7b58670962575077f1b5166e9cdf1975c62f6596972686d04530b1368f1c0c07`. Esta propiedad es lo que hace el fichero **apto para `git diff` entre ejecuciones** y para comparaciones de regresión: si algún cambio futuro rompe la idempotencia, los tests de `tests/automation/test_daily_report.py` fallan inmediatamente.

Un caso borde explícito (CB-7b de la spec): el informe del **día en curso** NO es estrictamente idempotente — si llegan nuevos eventos entre las dos ejecuciones, los datos del día cambian y el Markdown también. La idempotencia byte-a-byte aplica a **días cerrados**.

### 9.6. La cadena se cierra en el dashboard — la vista *Alertas*

El último eslabón es la vista *Alertas* del dashboard, que consume `GET /api/v1/alerts` y materializa el modelo *pull*: el operador entra y ve el estado actual del sistema. Cuatro chips por severidad arriba (`critical / high / medium / low`), tabla central con `tipo / fuente / detectada / source_id`, detalle por alerta debajo con su texto largo. Si la API cae, el banner de error aparece sin que el resto del dashboard deje de funcionar.

La vista es API-only (ADR-007): no abre conexiones a Mongo, SQLite ni MinIO. Toda la lógica de cálculo vive en `evaluate()`; el dashboard solo renderiza. Esa separación garantiza que si en el futuro se sustituye el dashboard por otra interfaz (móvil, consola), las reglas de alerta no cambian — están en la API.

### 9.7. Lo que NO se entrega y por qué

Conviene dejar escrito explícitamente qué piezas de "observabilidad" del catálogo industrial **no** están en este proyecto, y por qué:

- **Sin *scheduler* real (cron, Celery, APScheduler, Airflow):** estos componentes están fuera del temario del Máster. Añadir uno solo por cumplir un cliché de "automatización" introduciría una dependencia que la demo no necesita y que no aporta valor académico. La automatización se entrega por dos vías ya descritas (evento + reproducibilidad).
- **Sin notificación *push* (email, SMS, Slack, webhooks):** el enunciado deja libertad y se elige el modelo *pull* (entrada en el dashboard). En un entorno clínico real esto sería insuficiente: si el operador no abre el dashboard, no se entera. Es una limitación honesta, documentada en el capítulo 14 (limitaciones) y en el 15 (ética).
- **Sin métricas tipo Prometheus + Grafana, sin tracing distribuido:** son herramientas de observabilidad de infraestructura (saber cuánta memoria usa cada servicio, cuánto tarda cada llamada). Quedan fuera del temario del Máster. Lo que sí entrega este proyecto es observabilidad **para el operador del hospital** (ver alertas y el estado del pipeline en el dashboard), no para el equipo que mantiene los servidores.
- **Sin tabla `alerts` persistida ni estado "leída / no leída":** decisión formal en ADR-009. Las alertas son vista derivada del estado actual; no hay histórico interrogable. Si en el futuro se quisiera auditar "¿cuántas alertas `critical` hubo el mes pasado?", el ADR-009 documenta cómo se reabriría (añadir tabla `alerts` en SQLite con `raised_at` y `resolved_at`).
- **Sin sistema de *acknowledgement* de alerta:** consecuencia directa de no persistirlas. Una alerta no se cierra manualmente: deja de aparecer cuando el evento que la originó sale de la ventana temporal consultada o si se corrige/modifica la fuente de datos que la generó. No existe estado leída/no leída ni cierre manual.

### 9.8. Cómo se verifica que la cadena funciona

Tres niveles de cobertura aseguran que la automatización y la observabilidad están vivas, no son solo documentación:

| Nivel | Qué verifica | Dónde vive |
|---|---|---|
| **Tests unitarios puros** | Reglas IF-THEN de `evaluate()`, render determinista del Markdown, helper `day_window_utc`. Sin Mongo ni SQLite. | `tests/api/test_alerts_rules.py`, `tests/api/test_reports_builder.py`, `tests/api/test_time_window.py` |
| **Tests de endpoint con fakes** | Contrato HTTP de `/alerts` y `/reports/daily`: estructura, query params, códigos de error, paso correcto de la ventana al reader. | `tests/api/test_alerts_endpoint.py`, `tests/api/test_reports_endpoint.py` |
| **Tests del CLI con sha256** | Idempotencia byte-a-byte del Markdown, creación del directorio, manejo de errores. | `tests/automation/test_daily_report.py` |
| **Smoke real con stack vivo** | Cadena completa: paciente grave inyectado via `POST /triage/patients` aparece como alerta `triage_severe / critical` en `/alerts`; dos ejecuciones del CLI sobre la misma fecha dan sha256 idéntico. | Verificado al cerrar la Feature 15. |

La conjunción de las cuatro capas hace que cualquier cambio que rompa una de las propiedades clave (reglas, idempotencia, ventana correcta) rompa al menos un test.

---

## 10. Resumen de decisiones técnicas (ADRs)

Las decisiones técnicas no triviales están documentadas en `decisions/` como ADRs (*Architecture Decision Records*) con contexto, alternativas consideradas y consecuencias. Esta sección las consolida en una sola tabla; el detalle completo está en los ficheros enlazados:

| ID | Decisión | Alternativa principal descartada | Motivo principal | Estado |
|---|---|---|---|---|
| **ADR-001** | Stack inicial: PySpark + PyTorch + FastAPI + MongoDB + MinIO + Docker | Dask, Apache Beam | PySpark es estándar del temario de Big Data; FastAPI + MongoDB + MinIO son stack moderno conocido | aceptada, parcialmente superada por ADR-003 |
| **ADR-002** | MongoDB para datos clínicos en lugar de PostgreSQL | PostgreSQL relacional | El enunciado pide al menos dos tipos de almacenamiento y pone PostgreSQL como ejemplo (no como obligación); la jerarquía paciente → admisiones → radiografías encaja con un modelo documental | aceptada |
| **ADR-003** | Cambio del framework de Deep Learning de PyTorch a Keras/TensorFlow | Mantener PyTorch | El Bloque 6 del Máster (Aprendizaje Automático, Jordi) usa exclusivamente Keras; trazabilidad clase -> proyecto | aceptada (supersede parcial de ADR-001) |
| **ADR-004** | Persistencia poliglota: SQLite + MongoDB + MinIO | Sólo MongoDB + MinIO | MongoDB + MinIO ya cumplía "≥ 2 tipos de almacenamiento"; SQLite **refuerza** la arquitectura con una capa relacional/tabular para metadatos operativos, alineada con SQLAlchemy + SQLite enseñados en el Bloque 7 | aceptada |
| **ADR-005** | CNN custom desde cero, sin *transfer learning* | EfficientNet/MobileNet pre-entrenado en ImageNet | Alineación literal con el patrón docente del Bloque 6; modelo dentro de los 50 MB del RNF-4; sin dependencias externas en arranque | aceptada |
| **ADR-006** | TensorFlow en la imagen Docker compartida `hospital-pipeline` | Dos imágenes (pipeline sin TF + `hospital-ml` con TF) | Cambio operativo mínimo; entrenamiento dentro del compose; tests existentes siguen funcionando | aceptada |
| **ADR-007** | Streamlit + imagen Docker independiente para el dashboard | Plotly Dash / React / reutilizar `hospital-pipeline` | A 3 días de la entrega, Streamlit corta ~70 % del tiempo de implementación vs React; imagen ligera (~240 MB) cumple holgadamente RNF-5 | aceptada |
| **ADR-008** | Triaje de pacientes implementado como **sistema basado en reglas** (no ML) | Modelo de clasificación clínica entrenado | Trazabilidad explícita clínico → predicción (cada decisión cita la regla); alineación con la Sesión 07 de Yuri (`ruleBasedSystem/`); ML no aporta valor sin etiquetas reales | aceptada |
| **ADR-009** | Alertas y vista del informe diario como **vista derivada** (cero estado nuevo) | Tabla `alerts` en SQLite con estado leída/no leída | Cero superficie de estado nuevo; las fuentes (`pipeline_runs`, `data_quality_summary`, `patients.triage`) ya tienen lo necesario; encaja con la separación lectura/escritura del proyecto (`MongoReader`/`MongoWriter`, `SqlReader`/`SqlWriter`). Si fuera producción real, se reabriría para auditoría histórica | aceptada |
| **ADR-010** | Regla de decisión `covid_threshold_0.35` aplicada *post-hoc* sobre las probabilidades softmax (sin reentrenar) | Reentrenar con `class_weight` más agresivo o con *transfer learning* | Subir el *recall* COVID-19 de 0,695 a 0,820 (+12,5 pp) sin tocar pesos del modelo ni arquitectura, manteniendo trazabilidad (`decision_rule` se persiste en cada clasificación). Coste: -3,6 pp de *recall* Normal. *Baseline* argmax se conserva en `metrics.json` para auditoría | aceptada |

Las ADRs son **vivas**: cuando una decisión cambia, se crea un ADR nuevo que *supersede* la anterior, dejando trazabilidad histórica (caso ADR-001 -> ADR-003 para la migración de PyTorch a Keras).

---

## 11. Operación e infraestructura

### 11.1. Despliegue

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

### 11.2. Puntos de acceso

| Recurso | URL | Credenciales |
|---|---|---|
| Dashboard (Streamlit) | `http://localhost:8501` | sin auth (dev) |
| API REST | `http://localhost:8000` | sin auth (dev) |
| Documentación interactiva (Swagger) | `http://localhost:8000/docs` | — |
| MongoDB | `mongodb://localhost:27017/hospital` | sin auth (dev) |
| MinIO consola web | `http://localhost:9001` | `minioadmin` / `minioadmin123` |

La ausencia de autenticación es deliberada para el entorno de demostración; ver capítulo 15 para la discusión sobre cómo evolucionaría a un entorno real.

### 11.3. Gestión de datos y volúmenes

- `mongo-data`, `minio-data` y `pipeline-db` son **volúmenes Docker named**. `docker compose stop` los conserva; sólo `docker compose down -v` los borra.
- El modelo entrenado (`data/models/*.keras` + `*.meta.json`) vive en el filesystem del repositorio y se monta en `pipeline` (`rw`, para reentrenamientos) y `api` (`ro`).
- Los CSVs sintéticos y los 17 PNG dummy están commiteados (`data/raw/`) para que el arranque sea offline y reproducible. El dataset Kaggle (~0,9 GB en la versión local utilizada) está en `.gitignore` y se descarga aparte siguiendo `docs/runbooks/download-radiography-dataset.md`.

### 11.4. Runbooks

`docs/runbooks/` contiene tres procedimientos operativos:

- `download-radiography-dataset.md`: cómo descargar el dataset COVID-19 Radiography de Kaggle.
- `use-real-radiograph-for-demo.md`: cómo dejar el dataset disponible localmente para que el bootstrap incluya las `HOSP-PRES-*`.
- `presentation-demo.md`: guion paso a paso de la demo de presentación (10-15 min) con flujo recomendado por las siete vistas y mitigaciones para problemas frecuentes.

> El contenido sobre automatización (alertas + informe diario, Feature 15) se ha promovido al capítulo 9 ("Automatización y observabilidad"), donde queda enmarcado junto con el resto de piezas automáticas del sistema (watcher, bootstrap idempotente).

---

## 12. Testing y verificación

### 12.1. Estado de la suite

El estado actual del repositorio contiene **417 tests automáticos verdes** (+ 1 skip esperado), distribuidos en las siguientes capas:

| Capa | Carpeta | Ficheros | Cobertura |
|---|---|---|---|
| Unit + integration pipeline | `tests/pipeline/` | 15 | Ingesters, processors, storage (MongoWriter + SqlWriter + MinIO), orchestrator, watcher |
| Unit + integration ML | `tests/ml/` | 6 | dataset, preprocessing, model, train, evaluate, predictor |
| Unit + integration API | `tests/api/` | 12 | data endpoints, pipeline endpoints, classify, image, model evaluation, sql_reader, mongo_reader, triage rules + endpoint, alerts rules + endpoint, reports builder + endpoint, time_window |
| Unit + integration automation | `tests/automation/` | 1 | `daily_report` CLI con verificación `sha256` byte-a-byte |
| Unit dashboard | `tests/dashboard/` | 3 | `ApiClient` con `httpx.MockTransport`, `error_banner`, `system_status` |
| E2E con stack vivo | `tests/e2e/` | 4 | `test_acceptance_criteria` (uno por CA-1..CA-8 del pipeline), watcher integration, dashboard smoke, classification E2E |

La suite cubre el **estado actual del proyecto**: pipeline ETL completo, persistencia poliglota, clasificador, API completa, triaje, alertas, informe diario y dashboard. La Feature 14 (triaje) añadió 70 tests; la Feature 15 (alertas + informe) añadió otros 60 (13 puros de `evaluate`, 11 del builder/render con sha256, 17 de los endpoints, 5 del helper de ventana, 6 del CLI y 8 del cliente HTTP). El skip controlado corresponde al test del watcher cuando se ejecuta dentro del contenedor `pipeline` (necesita permisos *rw* sobre `data/incoming/` que el contenedor no tiene). Los tests E2E de clasificación se saltan limpiamente si la API reporta `predictor_loaded=false`.

### 12.2. Tipos de prueba

- **Unit**: aislados, sin dependencias externas. Usan `httpx.MockTransport` (dashboard), schemas PySpark explícitos (processors) o dobles de los writers.
- **Integration**: tocan MongoDB o MinIO **reales** levantados por Docker; un *fixture* en `conftest.py` detecta su disponibilidad por TCP y hace *skip* limpio si no están accesibles, evitando `KeyError` por *teardown* incompleto.
- **E2E**: arrancan contra el stack vivo (compose levantado). Uno por criterio de aceptación CA-1..CA-8 del pipeline original, más tests específicos del watcher, del dashboard y del flujo de clasificación end-to-end.

### 12.3. Cómo se ejecuta

```
docker compose run --rm --entrypoint "" pipeline pytest tests -v
```

Esta orden lanza toda la suite dentro del contenedor `pipeline` que ya tiene PySpark, TensorFlow y FastAPI instalados. Los tests E2E que requieren `data/incoming/` *rw* se saltan en este modo y se cubren con el segundo comando, ejecutado contra un compose ya levantado.

### 12.4. Revisión técnica y contraste contra la spec

Los LLMs tienden a no cuestionar su propio trabajo: si una decisión la propone el mismo asistente que escribe el código, casi nunca la pondrá en duda. Para evitar ese sesgo, las *features* grandes pasaron por **revisión técnica del equipo** y **comparación punto por punto con la spec aprobada**. En esta entrega no hay un documento aparte de revisión por *feature*: las observaciones se hablaron mientras se desarrollaba, los cambios se aplicaron en el momento y lo que valía la pena conservar quedó anotado en `tasks/lessons.md`. El caso más claro fue al cerrar T10, cuando la revisión del pipeline detectó cuatro bloqueantes que se habían colado — `POST /pipeline/trigger` no estaba conectado, `/radiographies` devolvía lista vacía, el orchestrator se rompía mal si fallaba al iniciar y `ImageIngester` no avisaba si MinIO no estaba disponible. Los cuatro se corrigieron antes de cerrar la fase BUILD y quedaron reflejados en el `CHANGELOG.md`.

---

## 13. Resultados

### 13.1. Pipeline ETL — cifras de operación

Sobre el dataset sintético commiteado (`patients.csv` 5.150 filas + `admissions.csv` 10.000 filas), un *bootstrap* en frío deja **4.745 pacientes finales en MongoDB**, **8.569 admisiones embebidas** y **1.692 registros en `rejected_records`** (264 pacientes + 1.428 admisiones). El *bootstrap* completo tarda **~50 s** y un *warm restart* baja a **~1 s** (sección 5.8 desglosa los números). En conjunto, `docker compose up` deja el sistema operativo en **menos de 1 minuto** en una máquina de desarrollo media.

### 13.2. Modelo de clasificación — métricas finales

Sobre las 1.515 radiografías del *split* de test, con la regla operativa `covid_threshold_0.35` (ADR-010):

- **Accuracy global**: 0,8766
- **Macro-F1**: 0,8594
- **Recall por clase**: Normal = 0,890; Pneumonia = 0,926; **COVID-19 = 0,820**

Comparativa con dos *baselines* triviales y con el *baseline* argmax descartado:

| Sistema | Accuracy | Macro-F1 |
|---|---|---|
| Predicción aleatoria uniforme (3 clases) | ~0,333 | ~0,33 |
| Predecir siempre `Normal` (clase mayoritaria) | 0,6726 | 0,267 |
| Modelo entregado — *baseline* argmax | 0,8719 | 0,8456 |
| **Modelo entregado — regla `covid_threshold_0.35`** | **0,8766** | **0,8594** |

El modelo supera ampliamente los *baselines* triviales. La regla `covid_threshold_0.35` sube el *recall* de COVID-19 de 0,695 a 0,820 (+12,5 pp) a cambio de perder 3,6 pp de *recall* en Normal, manteniendo el modelo y sus pesos intactos. El cambio es estrictamente *post-hoc*: aplica un umbral sobre la probabilidad de COVID-19 antes de tomar la decisión y se documenta en ADR-010 con la comparación cuantitativa entre umbrales 0,30 / 0,35 / 0,40 sobre el split de validación. El proceso que llevó al modelo actual incluyó un primer entrenamiento degenerado (el modelo predecía siempre `Normal` y su *accuracy* coincidía con la del *baseline* de la clase mayoritaria), detectado por los *sanity checks* documentados en `lessons.md` y corregido bajando el *learning rate* a `1e-4` y suavizando el `class_weight` con la raíz cuadrada.

El detalle de la matriz de confusión y la interpretación clínica de los errores están en la sección 6.6.

### 13.3. Dashboard — demo operativa

El dashboard expone las siete vistas descritas en el capítulo 8. Smoke verificado en la presentación:

- Las siete vistas responden 200 OK con datos servidos desde MongoDB y SQLite a través de la API.
- `HOSP-DEMO-001` (imagen sintética generada al vuelo, no es una radiografía real) se clasifica como `Normal` con probabilidad ~0,95. Sirve para mostrar el flujo end-to-end del clasificador; no aporta valor diagnóstico y la UI lo señala explícitamente.
- Si se para la API con `docker compose stop api`, el dashboard sigue respondiendo 200 OK: el chip *API* pasa a rojo y los chips *Modelo* y *Último run* pasan a gris (estado desconocido al depender de la API). No hay pantalla blanca ni *stacktrace* visible al usuario (CA-10 del dashboard).
- Las `HOSP-PRES-*` (cuando el dataset Kaggle está descargado) permiten enseñar la clasificación sobre imágenes reales del dataset, visualmente más representativas que la sintética.

Los resultados funcionales del triaje y de las alertas se describen en 13.4 y 13.5 a continuación.

### 13.4. Triaje de pacientes — resultados funcionales

El sistema de triaje (Feature 14, ver capítulo 6.8) está implementado como **reglas IF-THEN deterministas** en la versión `1.0`, con **6 reglas para nivel `grave`** y **5 reglas para nivel `medio`**. El nivel `leve` es el caso por defecto cuando ninguna regla dispara.

Cifras de tests aportadas por la feature: **70 tests nuevos verdes** (unitarios de reglas + endpoint + escritura en MongoDB + E2E + cliente HTTP del dashboard).

Smoke real ejecutado contra el stack vivo:

- `POST /api/v1/triage/patients` con un payload de paciente con `oxygen_saturation = 85` devuelve **201** con `level = "grave"` y `reasons = ["spo2_lt_92"]`, según la regla `spo2_lt_92` de la versión actual.
- El paciente queda persistido en MongoDB con su `external_id` generado (`TRIAGE-YYYYMMDD-NNNN`) y es consultable desde `GET /api/v1/patients/{external_id}` con su sub-documento `triage` completo (level, score, reasons, signos vitales y `rules_version`).
- El expander de "reglas vigentes" en la vista *Triaje* muestra las 11 reglas y permite al operador entender por qué se ha asignado ese nivel.

Conviene declararlo explícitamente: estos son **resultados funcionales** del sistema (la feature hace lo que la spec pide y los tests lo verifican). **No son una validación clínica**: los umbrales son académicos, no han sido revisados por personal sanitario y harían falta profesionales del dominio antes de cualquier uso real. La memoria mantiene esa distinción en el capítulo 14 (limitaciones) y 15 (ética).

### 13.5. Alertas e informe diario — resultados funcionales

El sistema de alertas y observabilidad (Feature 15, ver capítulo 9) calcula **3 tipos de alerta** al consultar el endpoint:

- `pipeline_failed` (severidad `high`) — un *run* del pipeline ha terminado con `status=failed` dentro de la ventana consultada.
- `data_quality_low` (severidad `medium`) — el `rejection_rate` de algún *snapshot* de calidad supera el umbral configurado (por defecto 0,10).
- `triage_severe` (severidad `critical`) — algún paciente ha sido clasificado como `grave` por el triaje dentro de la ventana consultada.

Cifras de tests aportadas por la feature: **60 tests nuevos verdes** (unitarios puros de `evaluate()`, *builder* y *render* del informe, endpoints `/alerts` y `/reports/daily`, helper de ventana, CLI del informe y cliente HTTP del dashboard). Tras Feature 16 (umbral COVID + tests del *threshold rule* + ajustes en tests del clasificador), **la suite total del proyecto queda en 417 tests + 1 *skip* esperado** (este último corresponde al test del *watcher* que necesita permisos `rw` sobre `data/incoming/` que el contenedor `pipeline` no tiene; está documentado).

Smoke real ejecutado contra el stack vivo:

- Crear un paciente con SpO2 baja vía `POST /api/v1/triage/patients` → se genera el `triage` `grave` (resultado de 13.4). Acto seguido `GET /api/v1/alerts` devuelve una alerta `triage_severe` con `severity=critical` referenciada al `external_id` del paciente que se acaba de crear. Esto demuestra que la cadena triaje → alertas funciona end-to-end sin estado nuevo persistido: la alerta se calcula al consultar las fuentes que ya existen (decisión documentada en ADR-009).
- `GET /api/v1/reports/daily?date=YYYY-MM-DD` devuelve el informe del día consultado en JSON, con secciones `pipeline`, `quality`, `counts`, `triage` y `alerts`.
- El script `python -m src.automation.daily_report --date YYYY-MM-DD` genera el mismo informe en formato Markdown dentro de `docs/reports/`. Se ejecutó dos veces seguidas sobre la misma BBDD y la misma fecha (un día cerrado), y los dos ficheros resultantes son **byte a byte idénticos**: si se vuelve a generar con los mismos datos y la misma fecha, sale exactamente el mismo fichero. Esto se consigue ordenando las listas por claves estables y dejando fuera del Markdown cualquier campo dinámico tipo `generated_at`. La comprobación se hizo comparando los `sha256` de ambos ficheros y dieron el mismo valor.

Los detalles arquitectónicos detrás de esos resultados (función pura `evaluate()`, doble ventana temporal, separación de *builder* y *render*) están en el capítulo 9.

### 13.6. Cobertura por criterios de aceptación

Cada *feature* del backlog tiene sus criterios de aceptación atados a tests. El estado tras la entrega es:

| Feature | Criterios totales | Cubiertos por tests |
|---|---|---|
| `pipeline-datos` | 8 (CA-1..CA-8) | 8/8 (`tests/e2e/test_acceptance_criteria.py`) |
| `sqlite-pipeline-metadata` | 8 (CA-1..CA-8) | 8/8 (tests específicos + E2E) |
| `clasificacion-radiografias` | 10 (CA-1..CA-10) | 9/10 cubiertos automáticamente; CA-3 (análisis clínico cualitativo) verificado por inspección del reporte |
| `dashboard` | 11 (CA-1..CA-11) | 11/11 entre tests unit + E2E + verificación manual |
| `triage-pacientes` | 10 (CA-1..CA-10) | 10/10 entre tests unitarios de reglas (`test_triage_rules.py`), endpoint (`test_triage_endpoint.py`), MongoDB writer (`test_mongo_writer.py`), E2E (`test_triage_e2e.py`) y cliente HTTP (`test_api_client.py`) |
| `automatizacion-alertas` | 11 (CA-1..CA-11) | 11/11 entre tests de reglas (`test_alerts_rules.py`), endpoints (`test_alerts_endpoint.py`, `test_reports_endpoint.py`), *builder* del informe (`test_reports_builder.py`), helper de ventana (`test_time_window.py`), CLI (`tests/automation/test_daily_report.py`) y cliente HTTP |

---

## 14. Limitaciones y reflexión crítica

Este capítulo recorre las limitaciones reales del sistema en el orden que importa: primero los **dos sistemas de IA** (clasificador y triaje), después el **sistema de alertas/observabilidad**, después el **pipeline y el entorno**, y finalmente el **contexto de aplicación** (dónde tiene sentido este sistema y dónde no) y una **reflexión personal** corta. Cada apartado describe casos concretos donde el sistema fallaría o produciría resultados poco fiables, en lugar de listar categorías abstractas. Es un proyecto académico y conviene declarar lo que no hace tan claramente como lo que sí hace.

### 14.1. Limitaciones del clasificador de radiografías

El clasificador alcanza *accuracy* global de **0,8766** y macro-F1 de **0,8594** sobre el split de test con la regla operativa `covid_threshold_0.35` (ADR-010), pero las cifras agregadas esconden comportamientos que conviene declarar antes de que un evaluador los descubra leyendo la matriz de confusión.

- **Recall de COVID-19 = 0,820 — el límite clínico principal.** Incluso después de aplicar la regla `covid_threshold_0.35` (que sube el *recall* de COVID-19 desde 0,695 hasta 0,820, +12,5 pp), el modelo deja de detectar como tales aproximadamente el 18 % de los positivos reales de COVID-19 del split de test (59 clasificados como Normal y 6 como Pneumonia, 65 falsos negativos en total frente a los 110 del *baseline* argmax). Es el motivo central por el que el sistema **no se diseña para autonomía** (RNF-2 de la spec): aun con el umbral, sin un profesional que valide cada predicción se dejarían escapar casi 2 de cada 10 contagiosos sin alarma. Subir más el *recall* exigiría reentrenamiento (*transfer learning*, *data augmentation* dirigido) y queda como trabajo futuro.
- **Sin detección *out-of-domain*.** Si llegara una imagen que no es una radiografía de tórax — una resonancia, una foto de una mano, una captura de pantalla — el modelo devolvería igualmente una de las tres clases con la confianza que tocase. No hay un verificador previo "esto es realmente una radiografía / no lo es". Para una demo controlada esto no afecta; para un despliegue real es un agujero abierto.
- **Sin interpretabilidad.** El modelo dice qué clase predice y con qué probabilidad, pero no muestra dónde está mirando. No hay Grad-CAM, ni mapas de saliencia, ni SHAP. Un radiólogo que recibiera la predicción no tendría forma de validar si la atención del modelo cae sobre el parénquima pulmonar o sobre artefactos del marcador de la radiografía.
- **Generalización a otros equipos y poblaciones no medida.** El entrenamiento se hace exclusivamente sobre el *COVID-19 Radiography Database* (Kaggle). El comportamiento sobre radiografías capturadas con otros equipos, otras poblaciones, otras calibraciones de exposición o con artefactos clínicos distintos (drenajes, sondas, marcapasos visibles) no se ha evaluado. Lo razonable es asumir caída de rendimiento.
- **Confianzas calibradas no garantizadas.** Las probabilidades del *softmax* se pueden leer como ranking, pero no como probabilidad calibrada en sentido estricto: el modelo no se ha sometido a *temperature scaling* ni a evaluación de fiabilidad por bins. Una predicción "COVID-19 0,82" no implica que 82 de cada 100 predicciones con esa confianza sean correctas.
- **Sensibilidad a tamaños y artefactos en el preprocesado.** Imágenes muy pequeñas (`< 32 × 32 px`) se rechazan vía CB-7. Por encima de ese umbral, el preprocesado fuerza grayscale + resize a 224×224; imágenes con relaciones de aspecto extremas o con texto superpuesto pueden quedar deformadas o introducir ruido que no se ha medido en el reporte clínico.

### 14.2. Limitaciones del sistema de triaje (reglas)

El triaje es un **sistema basado en reglas IF-THEN** explícitas (capítulo 6.8). Sus limitaciones son de naturaleza distinta a las del clasificador: aquí no hay error estadístico, hay error de **modelado del dominio**.

- **Los umbrales son académicos, no clínicos.** Las fronteras (`SpO2 < 92` para grave, `SpO2 ∈ [92, 94]` para medio, `FR > 30`, `FC > 130`, `PAS < 90`, `T ≥ 39`, etc.) son una elección razonable del equipo a partir de signos vitales plausibles, no la replicación de ningún protocolo médico validado. Que un paciente caiga del lado "medio" o "grave" de la frontera depende de un número que **el equipo eligió**, no de evidencia clínica.
- **Las fronteras son duras y no graduales.** Si un paciente tiene `SpO2 = 92` se clasifica como medio; con `SpO2 = 91` como grave. Clínicamente la diferencia entre 91 y 92 es despreciable, pero el sistema responde con un salto discreto. Esto es inherente al paradigma IF-THEN y conviene declararlo: un sistema con confianza graduada (como un modelo) suavizaría esa frontera, las reglas no.
- **No combina interacciones complejas entre variables.** El sistema dispara `grave` si **alguna** regla crítica salta. Un paciente con `SpO2 = 95`, `FR = 28`, `FC = 125`, `T = 38,8` no dispararía ninguna regla `grave` y caería en `medio` aunque la combinación pueda ser clínicamente preocupante en su conjunto. Las reglas tratan cada signo vital por separado (con una excepción combinada para `anciano_riesgo_respiratorio`); no hay un score multivariable.
- **Síntomas declarados, no observados.** El triaje recibe los síntomas que el operador marca en el formulario; no hay forma de verificar que esos síntomas son los que el paciente realmente presenta. Una omisión de `alteracion_conciencia` o `dolor_toracico_fuerte` por parte del operador hace desaparecer la regla correspondiente.
- **No hay registro de incertidumbre.** El triaje devuelve `level`, `score` (número de reglas que han disparado) y `reasons`. No devuelve "no estoy seguro entre medio y grave". Si las reglas disparan al filo, no hay forma de pedirle al sistema que se abstenga: siempre da un resultado.
- **No es un sistema clínico validado.** No ha sido comparado contra triaje real ni revisado por personal sanitario; ningún resultado retrospectivo lo respalda. La UI lo señala explícitamente en cada predicción.

### 14.3. Limitaciones del sistema de alertas y de la observabilidad

El sistema de alertas (`GET /api/v1/alerts` + vista *Alertas*) es una **vista derivada** del estado actual de tres fuentes (ADR-009). Es, deliberadamente, una observabilidad **pull**, no **push**, y eso impone su techo.

- **Modelo *pull*, no *push*.** Si el operador no abre el dashboard, no se entera. Una alerta `triage_severe / critical` puede llevar horas activa sin que nadie la vea. En un entorno clínico real esto sería inadmisible — habría que añadir notificación (email, SMS, busca clínico), pero está explícitamente fuera del alcance (sección 9.7) y del temario.
- **Sin estado leída / no leída.** Consecuencia directa de no persistir las alertas (ADR-009). Dos operadores que abren la vista a la vez ven exactamente lo mismo: no hay "esta alerta ya la ha atendido alguien".
- **Ventana móvil que oculta histórico.** Por defecto la ventana es `[ahora − 24 h, ahora]`. Una alerta `pipeline_failed` de hace 25 horas ya no aparece, aunque siga sin haberse resuelto operativamente. Para investigar histórico hay que ir directamente a `pipeline_runs` en SQLite o usar el endpoint del informe diario sobre fechas pasadas; la vista *Alertas* no es la herramienta correcta para retrospectiva.
- **Umbrales fijos por configuración, no aprendidos.** El umbral de calidad (`ALERT_REJECTION_RATE_THRESHOLD = 0,10`) y la ventana (`ALERT_WINDOW_HOURS = 24`) son env vars con valores razonables para la demo. Si la distribución real del rejection rate cambia, el sistema seguiría disparando con el mismo umbral hasta que alguien modifique la configuración.
- **El informe diario del día en curso no es estrictamente idempotente.** La idempotencia byte-a-byte del Markdown aplica solo a **días cerrados** (CB-7b). Si se ejecuta el script con `--date <hoy>` antes de medianoche, el contenido puede cambiar entre dos ejecuciones porque están entrando eventos nuevos. La propiedad fuerte es para auditoría histórica, no para el cierre del día en curso.
- **No hay correlación entre alertas.** Cada alerta es un evento independiente. Si un mismo run del pipeline genera a la vez `pipeline_failed` (high) y, por su impacto en la BBDD, `data_quality_low` (medium), las dos aparecen como entradas separadas en la lista — el sistema no las agrupa ni indica causa-efecto.

### 14.4. Limitaciones del pipeline y del entorno de despliegue

- **Datos clínicos sintéticos.** Los CSVs de pacientes e ingresos se generan con `Faker` y casos borde inyectados (cap 4). Sirven para demostrar el comportamiento del pipeline (validación, deduplicación, rechazos contabilizados), pero las cifras agregadas no tienen plausibilidad clínica: una distribución diagnóstica `9,7 % COVID-19 / 19,5 % Pneumonia / 70,8 % Other` es la que el generador inyecta, no la que un hospital real produciría.
- **Procesamiento *batch*, sin streaming.** El pipeline ingiere ficheros enteros (`patients.csv` + `admissions.csv`) cuando el `watcher` los detecta. No hay procesamiento de eventos en tiempo real. Para un hospital real con HL7/FHIR continuo, el watcher quedaría corto.
- **Sin autenticación ni autorización.** El dashboard, la API REST, MongoDB, MinIO y el endpoint Swagger se sirven sin credenciales (`sin auth (dev)` en cap 11.2). Aceptable para entorno de demostración; inviable para producción. Cualquier despliegue real requeriría OAuth2/JWT, control de acceso por rol y cifrado en tránsito.
- **Sin replicación ni alta disponibilidad.** MongoDB y MinIO corren como nodos únicos. Cualquier caída implica indisponibilidad del sistema. No hay réplicas, ni *failover*, ni *backups* automáticos al cierre del compose.
- **`HOSP-DEMO-001` es una imagen sintética.** 256×256 generada con `numpy + Pillow` para que la vista *Clasificador* funcione sin pedir la descarga del dataset Kaggle. La UI lo señala con un banner amarillo explícito (*"imagen sintética de demo — no es una radiografía real"*) y la predicción se etiqueta como no evidencia clínica. La transparencia es deliberada para que nadie interprete una clasificación sobre esta imagen como dato clínico.
- **Tamaño de la imagen Docker compartida.** `hospital-pipeline` pesa ~2 GB (PySpark + TensorFlow + FastAPI + watchdog) por la decisión ADR-006 de compartir imagen entre tres servicios. Es una elección consciente que prioriza eliminar drift de dependencias entre componentes que comparten código; el coste es tamaño de imagen.

### 14.5. Contexto de aplicación — dónde tiene sentido y dónde no

Conviene cerrar el bloque de limitaciones con una posición clara sobre los escenarios donde el sistema puede usarse tal cual está, y los que requieren cambios estructurales antes de plantearlos siquiera.

**Dónde tiene sentido este sistema, tal cual:**

- **Demostración académica del flujo completo**, exactamente lo que es esta entrega. Un hospital ficticio, datos sintéticos, un comando para arrancar, métricas reportadas honestamente, *recall* COVID-19 declarado (0,820 con la regla operativa `covid_threshold_0.35`, 0,695 con argmax puro, ambas cifras conservadas en el reporte).
- **Plantilla para construir sobre ella**: pipeline ETL con calidad medida, persistencia poliglota, API con separación lectura/escritura, dashboard *API-only*, automatización por evento y por reproducibilidad. La arquitectura es generalizable; lo que habría que cambiar son los datos, los modelos y las políticas, no la estructura.
- **Ejercicio formativo sobre Spec-Driven Development con asistencia de IA**: el repositorio entero está escrito para que el siguiente programador (humano o IA) pueda recoger el testigo leyendo `specs/`, `design/`, `decisions/` y `progress/` sin tener que reconstruir el razonamiento.

**Dónde NO usaríamos este sistema sin cambios estructurales:**

- **Decisiones clínicas reales con consecuencia para un paciente.** Ni el clasificador (recall COVID-19 ≈ 0,82 incluso con la regla `covid_threshold_0.35`) ni el triaje (reglas académicas no validadas) ofrecen las garantías que exige el ámbito clínico. Un despliegue real requeriría certificación como producto sanitario (CE/FDA), auditoría con datos del centro, interpretabilidad, protocolos de incertidumbre y, sobre todo, un radiólogo o un médico de urgencias que mantenga siempre la última palabra.
- **Entornos con PII real o regulación de datos personales.** El sistema no implementa cifrado en tránsito ni en reposo, no tiene gestión de roles, no firma logs, no audita accesos. Aplicarlo sobre datos reales sería incumplimiento directo de GDPR equivalente.
- **Operación 24/7 sin observabilidad *push*.** El modelo *pull* del dashboard sirve para una demo o para un operador que mira la pantalla; no sirve para un hospital donde la alerta tiene que llegar a un busca clínico. Antes de plantearlo habría que añadir un canal de notificación y, como consecuencia, persistir las alertas con estado para no inundar.
- **Hospital con volumen real y SLA.** MongoDB y MinIO como nodos únicos no aguantan operación crítica; cualquier caída es indisponibilidad total. Antes de operación real, replicación, *failover* y *backups* automatizados son requisitos previos.
- **Generalización geográfica del clasificador.** El modelo se ha entrenado sobre un dataset concreto. Trasladarlo a otro hospital con otro equipo radiológico exige medir caída de rendimiento *antes* de exponerlo a producción, no después.

La línea divisoria no es "este proyecto es bueno o malo": es **para qué se ha construido y para qué no**. Como entrega académica con disciplina SDD aplicada, cumple su función. Para uso clínico real haría falta validarlo antes con profesionales sanitarios y reforzarlo en los puntos que esta memoria reconoce abiertos. Nada de lo que se ha escrito aquí sugiere lo contrario.

### 14.6. Decisiones que se reabrirían con más tiempo

Si el proyecto continuara, el orden natural de las siguientes mejoras sería:

1. **Transfer learning** (EfficientNet, MobileNetV2 o DenseNet121 con pesos médicos como *CheXNet*) para subir el *recall* de COVID-19 por encima del 0,820 que da la regla `covid_threshold_0.35` sin sacrificar más *recall* en Normal. ADR-005 ya lo previó como contingencia y ADR-010 lo deja como continuación natural una vez agotada la ganancia del umbral *post-hoc*.
2. **Detección *out-of-domain***: clasificador binario previo "es radiografía de tórax / no" para rechazar imágenes que no encajan en el dominio.
3. **Interpretabilidad**: Grad-CAM por defecto en cada predicción del clasificador, con el mapa de calor visible en la vista *Clasificador*.
4. **Validación clínica del triaje**: comparar las reglas vigentes contra triaje observado en datos reales (cuando estén disponibles) y refinar los umbrales con evidencia, no con elección del equipo.
5. **Persistir alertas con histórico auditable** (reabrir ADR-009): tabla `alerts` en SQLite con `raised_at`, `acknowledged_at`, `resolved_at` y estado leída/no leída, para responder "¿cuántas alertas `critical` hubo el mes pasado?" sin tener que reconstruir desde fuentes.
6. **Notificación *push*** (email, webhook, integración con buscas clínicos) sobre las alertas `critical` y `high`.
7. **Autenticación + autorización** con OAuth2/JWT y cifrado en tránsito.
8. **Tests de carga** y *performance budget* explícito en la API (hoy se mide implícitamente con el RNF-3 "inferencia < 3 s").

### 14.7. Lo que ha funcionado y lo que no en este proyecto

Las decisiones que más han contribuido a llegar a la entrega:

- **SDD aplicado con disciplina** (spec antes que código): evitó implementar sin tener claras las dudas. El ejemplo más claro es la spec del dashboard, donde 6 dudas + 3 ajustes se cerraron antes de tocar código y ahorraron retrabajos posteriores.
- **ADRs frescos**: cada decisión técnica importante quedó documentada en el momento, no a posteriori. Eso ha permitido escribir esta memoria leyendo el repositorio, no recordando.
- **Revisión técnica del equipo y contraste contra la spec** durante el desarrollo: detectó bloqueantes que una revisión superficial habría pasado por alto (el caso documentado con mayor impacto: los cuatro bloqueantes del pipeline al cerrar T10).
- **Bootstrap idempotente desde el día 1**: `docker compose up` deja siempre el mismo estado, lo que ha hecho la demo y los tests E2E mucho más predecibles.
- **Función pura `evaluate()` reutilizada en triaje y alertas**: el mismo patrón arquitectónico (lógica IF-THEN deterministas, tests sin Mongo ni FastAPI) se aplica en dos features distintas. Permitió que la Feature 15 reutilizase íntegramente la disciplina ya probada en la Feature 14.

Lo que no ha funcionado bien:

- **El primer entrenamiento degenerado** consumió un día. Faltó plantear *sanity checks* (overfit a un subconjunto diminuto, *montage* visual por clase) **antes** del primer entrenamiento "real". Quedó documentado como patrón en `lessons.md`.
- **El cambio de PyTorch a Keras** (ADR-001 → ADR-003) llegó tarde: si se hubiera auditado el temario antes de fijar el stack, no habría sido necesario. Coste real bajo (no había código PyTorch que migrar), pero llamativo.
- **El cambio anunciado de dataset a radiografías dentales** generó incertidumbre y obligó a confirmar con el equipo mantener el alcance original (registrado en la spec de `clasificacion-radiografias`).
- **Tentación inicial de reutilizar la ventana de `/alerts` en `/reports/daily`** por "DRY". Parada en la revisión de la spec de la Feature 15: dos endpoints comparten regla de cálculo pero dominio temporal distinto; se modelan dos familias de queries (`_since` vs `_between`) en lugar de duplicar la ventana. Documentado como lección en `lessons.md`.

### 14.8. Reflexión personal

Por encima de cifras concretas y de decisiones puntuales, hay una idea que ha guiado todo el proyecto y que merece quedar escrita: **la representación del problema importa tanto como la técnica que se aplique encima**. En el clasificador, esa idea se traduce en que pasar a escala de grises y normalizar a `[0, 1]` es lo que hace que una CNN modesta llegue al 87 % de *accuracy*, no la elección entre Adam y SGD. En el triaje, en que un sistema basado en reglas explícitas con `reasons` auditables es la respuesta correcta cuando no hay etiquetas de gravedad disponibles, no una limitación frente a ML. En las alertas, en que separar la **regla** (función pura `evaluate`) de la **ventana** (parámetro del caller) permite servir dos casos de uso distintos sin duplicar código. La disciplina SDD ha sido el vehículo que ha permitido aplicar esa idea de forma consistente: la spec obliga a hacer explícita la representación antes de tocar código, los ADRs obligan a defenderla con alternativas, y los tests obligan a verificar que lo construido encaja con la representación declarada. El resultado es un sistema que se puede leer, auditar y criticar honestamente — y esta memoria es la prueba.

---

## 15. Consideraciones éticas y legales

### 15.1. Datos personales y privacidad

El proyecto **no maneja datos reales de pacientes**. Tanto los datos tabulares (`patients.csv`, `admissions.csv`) como los nombres (`HOSP-NNNNNN`) están **íntegramente generados con `Faker`** sobre una *seed* fija (42). Esta decisión es la solución natural al riesgo principal de un proyecto académico que toca datos clínicos: sustituir el dato real por un dato sintético equivalente en estructura pero sin identificadores reales. En consecuencia, ningún archivo del repositorio contiene PII (información de identificación personal) sujeta a GDPR o normativa equivalente.

Las imágenes utilizadas para entrenamiento proceden del **COVID-19 Radiography Database** (Kaggle), publicado por sus autores ya anonimizado. El proyecto **no commitea** ese dataset al repositorio (`.gitignore`) y deja el procedimiento de descarga responsabilidad del operador, que debe leer y respetar los términos de uso publicados por el autor original.

### 15.2. Licencia y citación del dataset

El *COVID-19 Radiography Database* tiene términos de uso definidos por su autor original que deben respetarse y citarse **tal cual los publica el proveedor**, sin asumir licencias genéricas. Esta convención es explícita en `data/raw/images-demo/README.md`, en el runbook de presentación y en la UI del dashboard. Cualquier difusión de capturas o resultados fuera del entorno de demostración (publicaciones, presentaciones externas) requiere citar la fuente exacta tal como la indica el autor.

### 15.3. Sesgos identificados en los tres sistemas

Los sesgos no son sólo del modelo aprendido: las reglas también tienen sesgos, aunque de naturaleza distinta. Conviene declararlos en los tres sistemas.

**Sesgos del clasificador de radiografías:**

- **Desbalance de clases en el dataset**: ~10.000 `Normal` vs ~3.600 `COVID-19` vs ~1.300 `Viral Pneumonia`. Mitigado con `class_weight="sqrt"` en el entrenamiento, pero no eliminado.
- **Sesgo de equipo/centro**: las radiografías del dataset proceden de un conjunto limitado de equipos y centros, no necesariamente representativos de la variabilidad global de equipamiento radiológico.
- **Descarte de la clase `Lung_Opacity`**: 6.012 imágenes no se usan porque no encajan en la clasificación triple. Es una decisión razonada (ver cap 4.4), pero impone al modelo el supuesto cerrado "toda radiografía pertenece a una de las tres clases", lo que puede llevar a clasificar como una de ellas hallazgos que en realidad caerían en la categoría descartada.

**Sesgos del sistema de triaje (reglas):**

- **Sesgo de elección de umbrales**: las fronteras (`SpO2 < 92` para grave, `FR > 30`, `FC > 130`, etc.) las eligió el equipo. Otra elección razonable habría dado otra distribución de pacientes por nivel. El sesgo no se aprende de datos: se inscribe explícitamente al escribir la regla.
- **Sesgo de selección de variables**: el triaje sólo mira los signos vitales y síntomas que el formulario expone. Variables clínicamente relevantes que no están en el formulario (comorbilidades crónicas, medicación, tiempo de evolución de los síntomas) no influyen en la decisión, lo que puede subestimar la gravedad de pacientes complejos.
- **Sesgo de la asimetría de la regla `anciano_riesgo_respiratorio`**: el sistema combina edad con síntoma respiratorio sólo en pacientes ≥ 70 años. La cifra "70" es elegida y discreta — un paciente de 69 años con el mismo perfil no activa la regla. La frontera por edad es tan arbitraria como las de los signos vitales.

**Sesgos del sistema de alertas:**

- **Umbral fijo de calidad**: `ALERT_REJECTION_RATE_THRESHOLD = 0,10` es un valor por defecto. Si la distribución real del `rejection_rate` del pipeline cambiara, ese umbral seguiría disparando con la misma agresividad. No hay aprendizaje del umbral a partir del histórico.
- **Ventana temporal fija**: 24 h por defecto. Eventos puntuales que se concentren justo antes de cumplir las 24 h pueden parecer "una avalancha" en un instante y "no ocurrir nada" un minuto después, según cuándo se consulta.
- **Pesos de severidad jerárquicos pero no priorizados por impacto**: el orden `critical > high > medium > low` mezcla criterios distintos en la misma escala. Un `pipeline_failed` (high) y un `triage_severe` (critical) se ordenan por severidad y por tiempo, pero ese orden no refleja necesariamente el orden en el que el operador clínico debería actuar.

### 15.4. Uso clínico del clasificador — asistencia, no diagnóstico

El clasificador propone una clase y unas probabilidades; **la decisión clínica la mantiene siempre el profesional**. Esta posición se materializa como **RNF-2** de la spec de clasificación, se recuerda en el runbook de presentación, queda visible en la UI cuando una predicción se ejecuta sobre `HOSP-DEMO-001` y se discute con cifras concretas en el reporte del modelo (`docs/model-evaluation/report.md`). La métrica que la sostiene es el *recall* de COVID-19 = 0,820 con la regla operativa `covid_threshold_0.35` (ADR-010): incluso con esa regla aplicada, el modelo pierde el 18 % de los positivos reales, así que sin revisión humana de cada predicción se dejarían pasar casos contagiosos. Antes de Feature 16 ese *recall* era 0,695 (30 % de positivos perdidos); la regla *post-hoc* lo mejora sin tocar los pesos del modelo, pero no resuelve el problema clínico de fondo.

Cualquier despliegue clínico real requeriría, además: (a) certificación como producto sanitario (CE/FDA), (b) auditoría con datos representativos del centro, (c) interpretabilidad (Grad-CAM como mínimo), (d) protocolos de incertidumbre (no clasificar cuando la confianza es baja) y (e) integración con el flujo del radiólogo humano que mantenga la última palabra clínica siempre en la persona.

### 15.5. Ética del sistema de triaje (reglas)

El triaje tiene su propio perfil ético, distinto del clasificador. No hay sesgo aprendido de datos, pero hay sesgo de **autoría** (quién escribió la regla y con qué umbrales) y hay tres riesgos específicos del paradigma que conviene escribir explícitamente.

- **Apariencia médica del sistema sin validación clínica.** El triaje muestra `grave / medio / leve` con código de colores, devuelve `reasons` con identificadores tipo `spo2_lt_92` y persiste `rules_version=1.0`. Visualmente puede parecer un protocolo clínico real. **No lo es**: los umbrales los eligió el equipo, no existe validación con pacientes reales, y ningún profesional sanitario ha revisado las fronteras. La UI lo declara con un disclaimer explícito en cada predicción y la spec lo formaliza en ADR-008, pero el riesgo de que un operador no lea el disclaimer y trate la salida como protocolo está siempre presente.
- ***Automation bias* del operador.** Es el riesgo dominante en sistemas de asistencia con respuesta clara: que el operador, sobre todo si tiene prisa o poca confianza en sí mismo, **se apoye más en la propuesta del sistema que en su propio criterio**, incluso cuando el caso es ambiguo. Un triaje del sistema que dice `medio` puede frenar al operador de marcar `grave` por su cuenta, simplemente porque "la máquina dice medio". El paradigma de reglas no es inmune a esto — el sesgo no está en el modelo, está en cómo el humano lee al sistema.
- **No-objetivación del paciente.** Reducir a un paciente a tres etiquetas (`grave / medio / leve`) tiene un coste comunicativo. Cuando el dashboard muestra "Paciente X — grave" la persona puede empezar a interpretarse desde la etiqueta y no desde la historia clínica. La mitigación parcial es que el sistema siempre acompaña el nivel con `reasons` legibles y con los signos vitales originales, de modo que el operador vea **por qué** se ha clasificado así y no solo el resultado.
- **La auditabilidad como mitigación ética activa.** El triaje persiste `level`, `score`, `reasons`, `vital_signs` evaluados y `rules_version`. Esa traza completa permite responder a posteriori a "¿por qué este paciente se clasificó así?" sin reconstruir nada — lo que en términos éticos significa que **la decisión es revisable**. Un sistema que clasifica sin dejar traza es éticamente más opaco que uno que registra cada paso de su razonamiento, aunque ese razonamiento sea simple.
- **La decisión clínica final sigue en el profesional.** Es la idea que se repite en la spec, en la UI, en la presentación y en esta memoria: el triaje propone, el médico decide. Que el sistema exista no traslada al operador del dashboard la responsabilidad clínica del caso.

### 15.6. Ética del sistema de alertas y de la observabilidad

Las alertas funcionan **bajo demanda**: el operador tiene que entrar al dashboard para verlas; el sistema no envía avisos por email ni por mensajería. Eso impone tanto el alcance funcional (ya descrito en 14.3) como el alcance ético del sistema: la mejor regla de alerta no sirve si nadie la consulta a tiempo.

- **Si el operador no mira, no hay alerta.** Una alerta `triage_severe / critical` puede llevar horas activa en `/api/v1/alerts` sin que nadie la abra. En un entorno académico esto es honesto y aceptable; en uno clínico real sería inadmisible. La memoria lo declara explícitamente y el cap 14.5 ("dónde NO usaríamos este sistema") lo enumera como veto para uso 24/7. La sección 14.6 lista la notificación *push* como mejora prioritaria; mientras no exista, el sistema es lo que es.
- **Fatiga por alerta (*alert fatigue*).** El umbral por defecto (`rejection_rate > 0,10`) está calibrado para que no haya silencio absoluto durante la demo. Si en un entorno real ese umbral disparara demasiadas alertas medias sin valor accionable, el operador acabaría ignorando el panel y la observabilidad se volvería decorativa. El sistema no tiene aún forma de auto-modular el umbral; la mitigación es que es configurable por entorno, no que el sistema aprenda.
- **Sin trazabilidad de quién atiende qué.** Consecuencia directa de ADR-009 (sin persistencia, sin estado leída/no leída). Si dos operadores miran la vista *Alertas* al mismo tiempo y uno actúa sobre la alerta `pipeline_failed`, no hay forma de que el otro lo sepa. En entorno real esto genera **difusión de responsabilidad**: nadie es responsable de la alerta porque nadie está formalmente asignado.
- **Riesgo de sesgo confirmatorio cuando se cruzan triaje y alertas.** Un paciente clasificado como `grave` por el triaje aparece en `/alerts` como `triage_severe / critical`. Un operador que confíe automáticamente en el sistema podría leer la alerta como **doble confirmación** ("la regla dispara Y la alerta también dispara") cuando en realidad **es la misma señal contada dos veces**: la alerta no aporta evidencia independiente al nivel asignado por el triaje, sólo lo hace visible en otro panel. Esta correlación está documentada implícitamente en el código pero no se enseña al operador en la UI.
- **Inacción documentada como propiedad rastreable.** El lado positivo del modelo *pull*: si un operador NO atiende una alerta, el sistema no oculta ese hecho. La alerta sigue visible mientras el evento esté dentro de la ventana temporal consultada y la fuente de datos siga cumpliendo la condición. En entorno real, combinado con logs de acceso al dashboard, sería un material auditable; en entorno académico es honestidad declarada — el sistema no presume de "alertas atendidas" que no existen.

### 15.7. Riesgos del sistema y mitigaciones

| Riesgo | Mitigación implementada |
|---|---|
| Confundir `HOSP-DEMO-001` (sintética) con radiografía real | Banner amarillo + caption explícito en la UI + nota en la presentación |
| Difundir capturas con licencia genérica | Convención formal "licencia tal como la publica el proveedor"; documentado en runbook, README de imágenes y memoria |
| Interpretar el resultado del clasificador como diagnóstico | RNF-2, repetido en spec, UI, runbook y memoria; reporte clínico con análisis cualitativo |
| Fuga de datos clínicos reales | Datos sintéticos por diseño; dataset Kaggle no commiteado |
| Persistencia de predicciones erróneas del clasificador | `predicted_at` y `model_version` permiten distinguir predicciones de distintas versiones del modelo y re-clasificar si se entrena uno nuevo |
| Interpretar el triaje como protocolo médico validado | Disclaimer explícito en UI; ADR-008 declara "umbrales académicos no validados clínicamente"; cap 6.8 y 14.2 lo desarrollan |
| *Automation bias* sobre el resultado del triaje | UI muestra siempre `reasons` con identificadores legibles + signos vitales originales junto al nivel, para que el operador vea el razonamiento, no solo el veredicto |
| Pérdida de auditoría de una decisión de triaje | Persistencia completa en `patients.triage` (level, score, reasons, vital_signs, rules_version) — auditable a posteriori sin reconstrucción |
| Alerta crítica activa sin que nadie la vea | Vista Alertas dedicada con severidad critical/high visible en el dashboard; el sistema no envía avisos automáticos por email o mensajería, así que el operador tiene que entrar a mirar. Limitación reconocida (cap 14.3, 14.5) y mejora futura prioritaria (cap 14.6) |
| Fatiga por alerta por umbral demasiado bajo | Umbral configurable por env (`ALERT_REJECTION_RATE_THRESHOLD`), ventana configurable (`ALERT_WINDOW_HOURS`); ajustable sin redeploy |
| Decisión clínica vinculante basada en alerta automatizada | Las alertas son *vista derivada* (ADR-009): nunca son acción del sistema, sólo señal para el operador; el sistema no actúa por su cuenta sobre el paciente |
| Difusión de responsabilidad sobre una alerta no atendida | Limitación conocida: sin estado leída/no leída en esta entrega; en entorno real requeriría persistir alertas con `acknowledged_by` (cap 14.6) |

---

## 16. Uso de IA generativa y metodología SDD

### 16.1. Encuadre

El enunciado del Máster pide explícitamente "Desarrollo Asistido por IA" como uno de los ejes evaluables. Este capítulo documenta cómo se ha materializado ese eje en el proyecto.

El proyecto se ha desarrollado en **pareo con asistentes de IA generativa** como apoyo principal, complementados con **revisión técnica del equipo** y **contraste contra la spec** como mecanismos de control, aplicando **metodología SDD (Spec-Driven Development)** como marco para que la asistencia de la IA fuera trazable, revisable y no opaca. El criterio de partida ha sido tratar a la IA como un colaborador júnior muy rápido pero con tendencia a la complacencia: hay que darle instrucciones claras, revisar lo que produce y forzar disciplina de proceso.

### 16.2. Por qué SDD encaja con asistencia IA

SDD (descrito en cap 2.4) descompone el desarrollo en cinco fases: `/spec -> /planificar -> /tareas -> /implementar -> /revisar`. Cada fase produce un artefacto revisable antes de pasar a la siguiente. Esa disciplina aporta tres beneficios concretos cuando se trabaja con asistentes IA:

1. **La IA no inventa requisitos**: al separar `/spec` (qué construir, en castellano natural) de `/implementar` (cómo construirlo), la IA opera sobre un documento que el humano ha aprobado, en vez de proponer una solución a un problema mal definido.
2. **Las dudas están marcadas**: la convención `[NEEDS CLARIFICATION]` en las specs obliga a la IA a parar antes de asumir; el humano cierra la duda y la spec queda viva con changelog.
3. **Cada decisión técnica deja huella en un ADR**: si la IA propone elegir SQLite sobre PostgreSQL, esa elección no se queda en la conversación volátil — se escribe en `decisions/ADR-NNN.md` con alternativas y razón. Esto facilita auditoría posterior y permite revisar decisiones si cambia el contexto.

### 16.3. Cómo se ha trabajado en la práctica

El flujo de una feature típica (ejemplo: dashboard) ha sido:

1. **`/spec dashboard`**: Alejandro describe el problema; Claude redacta el primer borrador de la spec con dudas explícitas. Iteración hasta cerrar las dudas (en el caso del dashboard, 6 dudas + 3 ajustes de producto).
2. **`/planificar dashboard`**: con la spec aprobada, Claude propone una arquitectura con trazabilidad requisito -> componente. Aquí nace ADR-007 (Streamlit + imagen Docker independiente).
3. **`/tareas dashboard`**: descomposición en 17 tareas atómicas con tamaño S/M/L y dependencias.
4. **`/implementar dashboard`**: TDD desde los criterios de aceptación. Por cada tarea: test que falla -> código mínimo -> test verde -> commit.
5. **Revisión técnica del equipo y contraste contra la spec**: el flujo de revisión técnica del SDD está descrito como práctica del equipo, pero en esta entrega las revisiones se hicieron hablando durante el desarrollo, no escribiendo un documento aparte por cada *feature*. Los hallazgos que merecía la pena conservar quedaron en `tasks/lessons.md` y en los commits. El caso de mayor impacto fue la revisión del pipeline al cerrar T10, donde se detectaron y corrigieron cuatro bloqueantes (reflejado en el `CHANGELOG.md`).
6. **`/revisar dashboard`**: matriz de trazabilidad requisito -> test -> evidencia, verificación de que cada CA de la spec tiene un test que lo cubre.

### 16.4. Cifras del trabajo con IA

| Indicador | Valor |
|---|---|
| Sesiones documentadas en `docs/diario-ia.md` | 30 |
| ADRs producidos | 10 |
| Specs aprobadas | 6 (`pipeline-datos`, `sqlite-pipeline-metadata`, `clasificacion-radiografias`, `dashboard`, `triage-pacientes`, `automatizacion-alertas`) |
| Lecciones registradas en `tasks/lessons.md` | 57 entradas (patrones a evitar, decisiones, cosas que funcionan) |
| Revisión técnica del equipo y contraste contra la spec | sí, durante el desarrollo de las features grandes; sin un documento aparte de revisión por feature (los hallazgos quedan en `tasks/lessons.md` y en los commits) |

### 16.5. Lecciones aprendidas

Lo que ha funcionado especialmente bien:

- **Tratar las dudas como bloqueantes**: la IA es muy buena escribiendo specs en cuanto las dudas están cerradas. Si se le deja asumir, asume mal.
- **ADRs en el momento, no al final**: escribir el ADR mientras se toma la decisión (no a posteriori) evita reescribir la historia y permite que el ADR documente alternativas reales consideradas.
- **Validación contra criterios de aceptación en *features* grandes**: los cuatro bloqueantes detectados al cerrar T10 (en el bloque de revisión técnica del pipeline) habrían pasado desapercibidos con una revisión superficial.
- **Diario IA como reflexión, no como log**: el diario no es histórico-cronológico, es cualitativo (qué funcionó, qué hubo que corregir, qué se aprendió). Eso permite detectar patrones entre sesiones, no eventos sueltos.

Lo que ha sido necesario corregir o evitar repetir:

- **Tendencia a la verbosidad**: los primeros borradores de specs eran demasiado largos. Solución: enviar `condensa, no añadas relleno` como instrucción explícita.
- **Inventarse números**: detectada una vez ("4.745 pacientes" cuadraba, pero "1.692 rejected = 264 patients + admisiones huérfanas" omitía 3 duplicados de admisiones). Lección documentada: leer del repositorio antes de afirmar cifras.
- **Sycophancy del LLM ante su propio código**: un mismo asistente rara vez cuestiona lo que acaba de generar. Mitigado con revisión técnica del equipo y validación contra criterios de aceptación.
- **Re-implementar en lugar de leer lo ya hecho**: si un componente ya existe (ej. `MongoWriter`), la IA tiende a proponer reescribirlo. Solución: empezar cada sesión con `/retomar` que lee `progress/current.md`, `tasks/lessons.md` y los specs aprobados.

### 16.6. Estimación del impacto en productividad

Estimación cualitativa de Alejandro, registrada en el diario IA:

- **Tiempo ahorrado**: alto en redacción de specs, designs, ADRs y memoria técnica; medio-alto en código boilerplate (routers, schemas Pydantic, tests con MockTransport); medio en lógica de pipeline (donde el dominio requiere más iteración humana).
- **Calidad del código generado**: aceptable como punto de partida; requiere siempre revisión humana y, en features críticas, validación contra criterios de aceptación.
- **Trabajo humano requerido**: cierre de dudas en specs, validación de decisiones técnicas, depuración de hiperparámetros del modelo (la IA no "intuye" *learning rates*), redacción final cualitativa, pruebas manuales en la UI, decisiones de producto.

Conclusión: la IA actúa como **multiplicador de capacidad**, no como sustituto. SDD es la disciplina que hace que ese multiplicador sea seguro: sin spec, design, ADR y tests, la IA produciría código más rápido pero ese código sería más difícil de revisar, mantener y defender.

---

## 17. Conclusiones

### 17.1. Qué se entrega

Un sistema **funcional, contenedorizado y reproducible** que cubre los cuatro subproblemas del enunciado:

1. Pipeline ETL distribuido con PySpark, persistencia poliglota (MongoDB + SQLite + MinIO), validación, deduplicación y enriquecimiento.
2. Modelo CNN custom en Keras/TF para clasificación de radiografías en 3 clases, con métricas por clase reportadas (recall, precision, F1 y matriz de confusión) y artefacto commiteado al repositorio (21 MB).
3. API REST en FastAPI con 17 endpoints versionados, documentación Swagger automática y separación lectura/escritura.
4. Dashboard Streamlit con siete vistas, *API-only*, imagen Docker independiente (~240 MB), barra persistente de estado del sistema.

El despliegue se realiza con un único `docker compose up` y deja el sistema operativo en menos de un minuto. El estado actual del repositorio contiene 417 tests verdes (+ 1 skip esperado), 10 ADRs (incluida ADR-010 sobre la regla `covid_threshold_0.35`) y 6 specs aprobadas con trazabilidad spec -> design -> tareas -> tests -> criterios de aceptación.

### 17.2. Qué no se entrega y por qué

- **Diagnóstico clínico vinculante**: el modelo es asistencia, no decisión.
- **Streaming en tiempo real**: el sistema es *batch*; el watcher cubre el lado automático.
- **Autenticación y autorización**: entorno de demostración académica.
- **Subida de imágenes desde el dashboard**: fuera del alcance de la spec; las imágenes se preparan como fixtures antes del arranque.
- **Interpretabilidad del modelo**: Grad-CAM o equivalente queda como mejora futura inmediata si el sistema avanzara hacia uso clínico real.

### 17.3. Líneas de mejora prioritarias

Si el proyecto evolucionara más allá de la entrega académica, las prioridades naturales serían, por orden:

1. **Subir el *recall* de COVID-19** por encima del 0,820 que da la regla `covid_threshold_0.35` (ADR-010), mediante *transfer learning* (EfficientNet o DenseNet121 con pesos médicos) y/o *ensembling*. El umbral *post-hoc* es el primer paso barato; el segundo paso es reentrenar.
2. **Añadir interpretabilidad** (Grad-CAM por defecto en cada predicción).
3. **Detección *out-of-domain***: clasificador binario previo "es radiografía de tórax / no".
4. **Autenticación + autorización** (OAuth2/JWT) y cifrado en tránsito.
5. **Observabilidad de infraestructura**: métricas Prometheus, logs estructurados, dashboards Grafana. La observabilidad accionable para el operador (alertas y estado del pipeline en el dashboard) ya se entrega en el capítulo 9; lo que falta es la parte de plataforma.
6. **Re-entrenamiento automatizado** (DVC, MLflow) y *model registry*.
7. **Streaming**: pasar de `watchdog` sobre filesystem a Kafka/RabbitMQ.

### 17.4. Cierre

El proyecto demuestra que es posible llegar a un sistema completo, reproducible y documentado en un plazo académico ajustado combinando tres ingredientes: una **metodología disciplinada** (SDD), un **stack que el equipo conoce y que coincide con el temario** (Python + PySpark + Keras + FastAPI + Streamlit + Docker) y un **uso intensivo pero supervisado de asistentes de IA generativa**. La pieza más difícil no ha sido técnica sino metodológica: mantener la disciplina de no saltarse fases, no asumir dudas y documentar las decisiones en el momento. Esa disciplina es lo que ha permitido que esta memoria pueda escribirse leyendo el repositorio, no recordando.

---

## 18. Anexos

### 18.1. Artefactos vivos del repositorio

| Artefacto | Ruta | Contenido |
|---|---|---|
| Specs | `specs/{pipeline-datos,sqlite-pipeline-metadata,clasificacion-radiografias,dashboard,triage-pacientes,automatizacion-alertas}.md` | Qué construir + criterios de aceptación |
| Designs | `design/*.md` | Cómo construirlo + trazabilidad spec -> componente |
| Tareas | `tasks/*.md` + `tasks/backlog.md` | Trabajo descompuesto, prioridad, estado |
| ADRs | `decisions/ADR-001..ADR-010.md` | Decisiones técnicas con alternativas |
| Lecciones | `tasks/lessons.md` | 57 entradas: patrones a evitar, decisiones, cosas que funcionan |
| Diario IA | `docs/diario-ia.md` | 30 sesiones documentadas |
| Reporte del modelo | `docs/model-evaluation/{report.md,metrics.json,confusion_matrix.png,learning_curves.png}` | Métricas + lectura cualitativa de los errores + curvas + matriz de confusión |
| Runbooks | `docs/runbooks/{download-radiography-dataset,use-real-radiograph-for-demo,presentation-demo}.md` | Procedimientos operativos |
| Changelog | `CHANGELOG.md` | Historial de entregas, incluida la entrada de los 4 bloqueantes detectados y corregidos al cerrar T10 |

### 18.2. Comandos clave

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

### 18.3. URLs de acceso al sistema en marcha

| Recurso | URL |
|---|---|
| Dashboard | `http://localhost:8501` |
| API REST | `http://localhost:8000` |
| Swagger | `http://localhost:8000/docs` |
| MinIO consola | `http://localhost:9001` |
| MongoDB | `mongodb://localhost:27017/hospital` |

### 18.4. Glosario abreviado

- **CA**: Criterio de aceptación (requisito verificable de una spec).
- **CB**: Caso borde de una spec.
- **ETL**: Extract — Transform — Load.
- **FN**: Falso negativo.
- **FP**: Falso positivo.
- **PII**: Información de identificación personal.
- **RF / RNF**: Requisito funcional / no funcional.
- **SDD**: Spec-Driven Development.
- **WAL**: Write-Ahead Logging (modo de concurrencia de SQLite).

