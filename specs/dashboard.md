# Spec: Dashboard de visualizacion del sistema hospitalario

> Estado: approved
> Ultima actualizacion: 2026-05-17

## Contexto y problema

El sistema hospitalario laSalle Health Center tiene:
- Un pipeline ETL (PySpark) que ingiere pacientes, ingresos y
  radiografias y los persiste en MongoDB + MinIO + SQLite
- Una API REST (FastAPI) que sirve esos datos + un modelo de
  clasificacion de radiografias en 3 clases (Normal / Pneumonia /
  COVID-19)

Todo eso, hoy, **solo se puede consultar via curl o leyendo MongoDB
con `mongosh`**. No hay forma visual de ver el estado del sistema, la
calidad de los datos, las metricas del modelo, o de clasificar una
radiografia interactivamente.

El enunciado del Master pide un dashboard de visualizacion (feature 4
del backlog) que sirva como (a) frontend visible durante la
presentacion de 10-15 min, (b) herramienta de auditoria del sistema
para personal hospitalario y (c) demo del clasificador.

## Objetivo

Entregar una aplicacion web (single-page o multi-tab) que **consume
exclusivamente la API REST existente** y permite:

- Visualizar el estado actual del sistema en un golpe de vista
- Inspeccionar la calidad de los datos del pipeline
- Navegar la lista de pacientes con sus admissions y radiografias
- Probar el modelo de clasificacion contra una radiografia ya
  almacenada en MinIO
- Consultar el historico de runs del pipeline y sus metricas
- Ver las metricas de evaluacion del modelo (accuracy, macro-F1,
  recall por clase, matriz de confusion)

No requiere autenticacion (demo academica, sin datos reales
identificativos). UI en castellano.

## Actores y alcance

**Usuarios:**
- Personal hospitalario (medico, dirigente): consulta de actividad
  agregada del sistema y casos individuales. Frecuencia ocasional
- Evaluador del proyecto durante la presentacion: ve la demo en vivo
- Developer/data-scientist: comprueba a vista de pajaro que el
  pipeline ha procesado bien los datos del ultimo run

**Dentro del alcance:**
- App web servida desde un servicio nuevo en `docker-compose`
- 5 vistas principales (Overview / Calidad de datos / Pacientes /
  Clasificador / Pipeline runs)
- Consumo exclusivo de la API REST: NO acceso directo a Mongo, SQL ni
  MinIO desde el dashboard
- URL base de la API configurable por env var (default
  `http://api:8000` dentro del compose)
- Manejo de errores explicito (API caida, modelo no cargado, datos
  vacios, imagen demasiado pequena) con mensaje claro en cada vista,
  NO crashes
- Sub-seccion "Evaluacion del modelo" con accuracy + macro-F1 +
  recall por clase + matriz de confusion 3x3
- Dos endpoints **nuevos** en la API (ver RF-8 y RF-9), porque sin
  ellos el dashboard no puede funcionar siendo API-only

**Fuera del alcance:**
- Autenticacion / autorizacion / roles
- Edicion de datos clinicos (read-only; la unica accion de escritura
  es disparar la clasificacion de una radiografia, que ya esta cubierta
  por la API)
- **Subida de imagenes nuevas al bucket MinIO desde el dashboard**:
  el clasificador solo permite elegir radiografias ya registradas en
  Mongo y subidas a MinIO. Drag&drop / upload se queda como mejora
  futura porque requeriria un endpoint mas en la API (`POST /radiographies/upload`)
- **Boton "Lanzar pipeline" en el dashboard**: la API ya tiene
  `POST /pipeline/trigger` pero NO se expone desde el dashboard,
  porque para la demo no queremos una accion que modifica datos y
  puede confundir al evaluador. El watcher en docker-compose cubre
  ya el flujo operativo (dropear CSVs → ETL automatico)
- Generacion de informes PDF/Excel descargables
- Internacionalizacion (UI en castellano, una sola lengua)
- Optimizacion para movil (escritorio first)

## Requisitos funcionales

- **RF-1 (Overview):** Existe una vista de inicio que muestra, leyendo
  de la API:
  - Total de pacientes
  - Total de admissions
  - Total de radiografias
  - Estado del ultimo run del pipeline (`status`, `trigger_type`,
    `started_at`, `records_processed`, `records_rejected`)
  - Indicador de si el modelo de clasificacion esta cargado
    (consume `predictor_loaded` de `/api/v1/health`)
- **RF-2 (Calidad de datos):** Existe una vista que muestra el ultimo
  `quality-summary` por dimension (`patients`, `admissions`):
  - Para cada dimension: `total`, `valid`, `rejected`, `rejection_rate`
  - Al menos un grafico del historico de `rejection_rate` por
    dimension a lo largo de los runs
- **RF-3 (Pacientes):** Existe una vista que lista pacientes con
  paginacion server-side (por defecto 20 por pagina):
  - Tabla con `external_id`, nombre, edad, genero, blood_type, numero
    de admissions y numero de radiografias
  - Al seleccionar un paciente, mostrar el detalle: campos basicos +
    lista de admissions (con su `diagnosis_category`) + lista de
    radiografias (con su `classification` si la tiene)
- **RF-4 (Clasificador):** Existe una vista que permite elegir una
  radiografia ya registrada en algun paciente y ejecutar
  `POST /api/v1/radiographies/classify` contra ella:
  - Mostrar la imagen seleccionada usando el endpoint **nuevo**
    `GET /api/v1/radiographies/image?key=...` (RF-8)
  - Tras clasificar, mostrar: clase predicha + probabilidades de las
    3 clases (al menos visualmente, p. ej. barras o donut) +
    `model_version` + `predicted_at`
  - **Manejo explicito del rechazo de imagenes invalidas:** las 17
    radiografias dummy del bootstrap son PNG 1x1 y la API las
    rechaza con 422 (CB-7 de la spec de clasificacion). Si la API
    responde 422, el dashboard muestra un mensaje claro
    ("Imagen demasiado pequena o invalida; minimo 32x32") sin
    crashear ni dejar el boton bloqueado
  - Si la API responde 503 (modelo no cargado), mostrar un warning
    claro y deshabilitar el boton de clasificar
- **RF-5 (Pipeline runs):** Existe una vista con el historico de runs
  del pipeline (paginado, mas reciente primero), mostrando:
  - `id`, `trigger_type`, `status`, `started_at`, `finished_at`,
    `records_processed`, `records_rejected`, `error_message` (si lo
    hay)
- **RF-6 (Configuracion):** La URL base de la API se lee de la
  variable de entorno `API_BASE_URL` con default `http://api:8000`
  (red interna del compose). El dashboard tambien debe arrancar fuera
  del compose apuntando a `http://localhost:8000` si se ejecuta en host
- **RF-7 (Evaluacion del modelo):** En la vista Overview (o como
  sub-seccion dentro de Clasificador, decision en `/planificar`)
  existe una sub-seccion "Evaluacion del modelo" que muestra:
  - `accuracy` global
  - `macro-F1`
  - Recall por clase (Normal, Pneumonia, COVID-19) destacando
    visualmente que el recall mas critico clinicamente es el de
    COVID-19
  - Matriz de confusion 3x3 con conteos absolutos
  - `model_version` del modelo cargado
  La fuente de estos datos esta en `docs/model-evaluation/metrics.json`,
  pero el dashboard NO la lee del disco — la obtiene a traves del
  endpoint **nuevo** `GET /api/v1/model/evaluation` (RF-9)
- **RF-8 (Endpoint nuevo: imagen de radiografia):** La API expone un
  endpoint nuevo `GET /api/v1/radiographies/image?key=...` que:
  - Recibe la `minio_object_key` como query param (NO como path
    param, por la misma razon que `classify` y `classification`: la
    key contiene `/`)
  - Descarga los bytes desde MinIO y los devuelve con `Content-Type: image/png`
  - Devuelve **404** si la key no existe en MinIO
  - Devuelve **422** si `key` esta ausente o vacio
  - NO toca MongoDB ni el modelo de clasificacion. Es un proxy de
    lectura, sin side effects
- **RF-9 (Endpoint nuevo: evaluacion del modelo):** La API expone un
  endpoint nuevo `GET /api/v1/model/evaluation` que devuelve, en
  JSON, el contenido de `docs/model-evaluation/metrics.json` (o
  equivalente: accuracy, macro_f1, per_class precision/recall/f1,
  confusion_matrix, classes, model_version). Devuelve:
  - **200** con el JSON si el fichero esta presente
  - **503** si el fichero no esta presente (modelo nunca entrenado)

## Requisitos no funcionales

- **RNF-1:** El dashboard usa **Streamlit** (formalizado en
  ADR-007) como servicio Docker independiente
  (`hospital-dashboard:latest`, imagen ligera sin TF/PySpark)
  dentro de `docker-compose.yml`, levantado con el mismo
  `docker compose up` del resto del sistema
- **RNF-2:** El dashboard NO mantiene estado propio (no BBDD, no
  sesiones persistentes). Todo lo necesario para una vista se obtiene
  de la API en la propia peticion del usuario
- **RNF-3:** Cada vista carga en menos de 3 segundos sobre el dataset
  actual (~4.745 pacientes, ~8.569 admissions) en una maquina de
  desarrollo media. La paginacion debe servirse server-side (via los
  `limit`/`offset` de la API), NO cargar todo a memoria del dashboard
- **RNF-4:** Si la API esta caida o devuelve 5xx, el dashboard muestra
  un mensaje de error claro en la vista afectada, sin caer ni
  bloquear las demas vistas
- **RNF-5:** El dashboard se construye con la imagen Docker en menos
  de 3 minutos (build limpio) y arranca en menos de 15 segundos
- **RNF-6:** El acceso es por navegador moderno (Chrome/Firefox/Safari
  recientes). No hace falta soporte para IE/Edge legacy ni para movil
- **RNF-7:** Refresh manual mediante boton "Recargar" en cada vista.
  Opcional: auto-refresh cada 30 segundos solo en la vista Overview
  (no bloqueante; si es complejo se omite). En el resto de vistas el
  refresh es siempre manual

## Casos borde y errores

- **CB-1:** API totalmente caida → todas las vistas muestran un
  mensaje "API no disponible" en lugar del contenido. El dashboard NO
  cae
- **CB-2:** Endpoint concreto de la API devuelve 5xx puntualmente →
  la vista afectada muestra el error con el `detail` de la respuesta,
  el resto de vistas siguen funcionando
- **CB-3:** El sistema esta arrancado pero el bootstrap no ha
  terminado (sin pacientes aun) → vista Overview muestra 0/0/0,
  vistas de lista muestran "Sin datos" en vez de tabla vacia silente
- **CB-4:** Dos senales independientes aunque relacionadas (ambas
  se deben manejar por separado):
  - **`predictor_loaded=false`** (de `/api/v1/health`): la API no
    puede ejecutar inferencia (el `.keras` no carga). Consecuencia:
    Overview muestra el indicador del modelo en rojo; Classifier
    deshabilita el boton de classify con warning
  - **`/api/v1/model/evaluation` responde 503**: no hay reporte de
    evaluacion para mostrar (`metrics.json` ausente). Consecuencia:
    la sub-seccion "Evaluacion del modelo" muestra "Reporte de
    evaluacion no disponible"
  Casos posibles distintos: (a) modelo cargado pero alguien borro
  `metrics.json` → `/health` dice OK, `/model/evaluation` da 503;
  (b) modelo no cargado pero el `metrics.json` esta del entrenamiento
  previo → metricas validas que mostrar aunque no se pueda inferir
- **CB-5:** Una radiografia seleccionada para clasificar / mostrar no
  esta en MinIO (404 inesperado en `GET /radiographies/image?key=...`)
  → mensaje en la vista, no crash
- **CB-6:** El usuario navega a una vista mientras la API esta
  respondiendo lento (>3s pero <30s) → spinner visible, sin freezing
  ni timeout corto
- **CB-7 (imagen invalida en el clasificador):** El usuario elige una
  de las 17 radiografias dummy del bootstrap (PNG 1x1) o cualquier
  imagen < 32 px por lado. La API responde 422. El dashboard:
  - Muestra el mensaje "Imagen demasiado pequena o invalida; usa
    una radiografia real (>= 32 px)"
  - Mantiene el boton "Clasificar" habilitado para que el usuario
    elija otra radiografia distinta
  - **No promete** en ningun texto de la UI que cualquier radiografia
    listada sea clasificable

## Dudas abiertas

Ninguna. Todas cerradas en la revision del 2026-05-17:

1. 5 vistas (Overview / Calidad / Pacientes / Clasificador / Runs)
2. Clasificador: solo radiografias ya registradas, NO drag&drop
3. NO se expone `POST /pipeline/trigger` desde el dashboard
4. Idioma: castellano
5. Imagen de radiografia: nuevo endpoint
   `GET /api/v1/radiographies/image?key=...` (query param, no path —
   coherente con `/classify` y `/classification`)
6. Refresh manual + auto-opcional 30s en Overview si es facil
7. (Ajuste A) Manejo explicito de rechazo de imagenes dummy 1x1
   añadido como CB-7
8. (Ajuste B) Evaluacion del modelo añadida como RF-7, con endpoint
   nuevo `GET /api/v1/model/evaluation` (RF-9)

## Criterios de aceptacion

- [ ] **CA-1** (RF-1, RNF-3): Tras `docker compose up`, navegar a la
  URL del dashboard muestra Overview con los counts correctos
  (~4.745 patients, ~8.569 admissions, 17 radiografias), status del
  bootstrap = `success` y el indicador de modelo cargado en verde,
  todo en menos de 3 segundos
- [ ] **CA-2** (RF-2): La vista de calidad muestra `patients` y
  `admissions` con sus totales/valid/rejected y al menos un grafico
  del historico de rejection_rate
- [ ] **CA-3** (RF-3): La lista de pacientes pagina correctamente
  (server-side), permite seleccionar uno y muestra detalle con
  admissions y radiografias embebidas
- [ ] **CA-4** (RF-4, RF-8): Desde el clasificador, eligiendo una
  radiografia real **(>= 32 px)** del bucket y pulsando "Clasificar",
  la imagen se muestra en pantalla (via `GET /radiographies/image`),
  la API responde con clase + probabilidades y el dashboard pinta
  el resultado en menos de 3 segundos
- [ ] **CA-5** (RF-4, CB-4): Si el modelo NO esta cargado, el boton
  de clasificar esta deshabilitado y hay un warning visible. El
  resto de vistas siguen funcionando
- [ ] **CA-6** (CB-7): Si el usuario selecciona una de las 17 dummy
  1x1 y pulsa "Clasificar", el dashboard muestra el mensaje de
  rechazo y permite reintentar con otra imagen sin tener que recargar
  la pagina
- [ ] **CA-7** (RF-5): La vista Pipeline runs muestra los runs
  ordenados por fecha descendente; los fallidos muestran
  `error_message`
- [ ] **CA-8** (RF-7, RF-9): La sub-seccion "Evaluacion del modelo"
  muestra accuracy, macro-F1, recall por clase y matriz de confusion
  3x3 cargados via `GET /api/v1/model/evaluation`. Si el modelo no
  esta cargado, muestra "Modelo no cargado" sin crashear
- [ ] **CA-9** (RF-6, RNF-1): El dashboard arranca como un servicio
  Docker mas con `docker compose up`. La URL del dashboard responde
  200 antes de los 15 segundos tras `up`
- [ ] **CA-10** (CB-1, RNF-4): Si se para el contenedor `api`
  (`docker compose stop api`), todas las vistas del dashboard
  muestran un mensaje de error claro en vez de pantalla blanca o
  stacktrace
- [ ] **CA-11** (RF-8): `GET /api/v1/radiographies/image?key=<existing>`
  responde 200 con `Content-Type: image/png` y los bytes correctos.
  Sin `key` o vacio → 422. Key inexistente → 404. NO se persiste
  nada en Mongo

## Changelog

| Fecha | Cambio | Motivo | Fase |
|-------|--------|--------|------|
| 2026-05-17 | Creacion inicial (draft) | Feature 4 del backlog. Dashboard como frontend visible para la presentacion + auditoria operativa del sistema | spec |
| 2026-05-17 | 6 dudas cerradas + 2 ajustes (CB-7 dummy 1x1, RF-7 evaluacion modelo) + spec aprobada | Revision con Alejandro: 5 vistas, solo radiografias ya registradas, NO trigger pipeline, castellano, endpoint nuevo de imagen con query param, endpoint nuevo de evaluacion del modelo, manejo explicito de rechazo 422 para dummy 1x1 | spec |
| 2026-05-17 | Back-sync de RNF-1 tras /planificar | El stack queda formalizado en ADR-007 (Streamlit + imagen Docker independiente); RNF-1 ya no dice "se elige en /planificar" | design (back-sync) |
