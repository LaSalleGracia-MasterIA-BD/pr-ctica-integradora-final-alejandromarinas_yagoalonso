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

El enunciado del Master pide **un dashboard o sistema de visualización**
(feature 4 del backlog). El enunciado NO exige literalmente las 5 vistas
que aquí se definen: las 5 vistas son una **decisión de producto del
equipo** para enseñar el sistema completo en una sola sesión de demo y
dejarlo auditable. Se entrega como un "Centro de Control Hospitalario"
de cara a la defensa ante los profesores: cada vista justifica una pieza
del stack (pipeline Big Data, calidad de datos, MongoDB documental,
API REST, modelo de IA, operación + trazabilidad).

Servirá como (a) frontend visible durante la presentación de 10-15 min,
(b) herramienta de auditoría del sistema para personal hospitalario, y
(c) demo interactiva del clasificador.

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
- 5 vistas principales, cada una con razón de producto explícita:

  | Vista | Razón de producto | Pieza del stack que vende |
  |---|---|---|
  | Overview | Estado general del sistema en 10 segundos | Salud operativa + KPI agregados |
  | Calidad de datos | Auditoría del pipeline y validación | Pipeline Big Data + `data_quality_summary` |
  | Pacientes | Demostración del modelo documental | MongoDB con `admissions` y `radiographies` embebidos |
  | Clasificador | Demo visible de IA + métricas de calidad | Keras/TF CNN + `/model/evaluation` |
  | Pipeline runs | Operación, automatización y trazabilidad | Watcher + `pipeline_runs` en SQLite |

- Consumo exclusivo de la API REST: NO acceso directo a Mongo, SQL ni
  MinIO desde el dashboard
- URL base de la API configurable por env var (default
  `http://api:8000` dentro del compose)
- Manejo de errores explicito (API caida, modelo no cargado, datos
  vacios, imagen demasiado pequena) con mensaje claro en cada vista,
  NO crashes
- Evaluacion del modelo dividida en dos superficies (RF-7a + RF-7b):
  resumen minimo en Overview, detalle completo en Clasificador
- Dos endpoints **nuevos** en la API (ver RF-8 y RF-9), porque sin
  ellos el dashboard no puede funcionar siendo API-only
- Barra persistente de estado del sistema en el footer del sidebar
  (chip API + chip Modelo + chip Ultimo run), visible desde todas las
  vistas

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
- **RF-7 (Evaluacion del modelo — dividida en 2 superficies):** La
  evaluacion del modelo se sirve en dos sitios para encajar con la
  narrativa de producto sin duplicar logica:
  - **RF-7a (resumen en Overview):** un strip pequeno de 2 metricas
    (`accuracy` y `macro-F1`) sirve como senal rapida de "el modelo
    funciona razonablemente". Sin graficos, sin tabla, sin matriz.
    Solo dos numeros + `model_version`. Si la API devuelve 503 en
    `/model/evaluation`, el strip muestra "Reporte no disponible" en
    lugar de numeros.
  - **RF-7b (detalle en Clasificador):** una sub-seccion al final de
    la vista **Clasificador**, despues del bloque de inferencia
    interactiva, con:
    - `accuracy` global (opcional, contextual)
    - `macro-F1` (opcional, contextual)
    - Recall por clase (Normal, Pneumonia, COVID-19) destacando
      visualmente que el recall mas critico clinicamente es el de
      COVID-19
    - Matriz de confusion 3x3 con conteos absolutos
    - `model_version` del modelo cargado

  La fuente de datos para ambas (Overview y Clasificador) es el
  **mismo endpoint** `GET /api/v1/model/evaluation` (RF-9), cacheado
  con `st.cache_data(ttl=60s)` para no duplicar peticiones. El
  dashboard NO lee `metrics.json` del disco directamente.

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
- **CB-4 (dos senales independientes, NO confundir):**

  | Senal | Origen | Significa | Consecuencia UI |
  |---|---|---|---|
  | `predictor_loaded=false` | `GET /api/v1/health` | El runtime de inferencia NO esta cargado (el `.keras` no se pudo cargar) | Overview: chip Modelo en rojo. Clasificador: boton "Clasificar" deshabilitado + warning. Barra persistente del sidebar: chip Modelo rojo |
  | `503` en `GET /api/v1/model/evaluation` | endpoint nuevo (RF-9) | El reporte estatico de evaluacion NO esta disponible (`metrics.json` ausente o ilegible) | Overview: strip de Evaluacion muestra "Reporte no disponible". Clasificador → sub-seccion Evaluacion detallada: muestra "Reporte de evaluacion no disponible" |

  Ambas pueden darse **independientemente**:
  - (a) modelo cargado, alguien borro `metrics.json` → `/health` OK,
    `/model/evaluation` da 503. Inferencia funciona; no hay metricas
    que ensenar.
  - (b) modelo no cargado pero hay `metrics.json` de un entrenamiento
    previo → `/health` reporta `predictor_loaded=false`,
    `/model/evaluation` devuelve 200. Metricas validas que mostrar
    aunque la inferencia este caida.
  - (c) ambas caidas → chip rojo + "Reporte no disponible". Resto del
    dashboard sigue.

  El dashboard lee las dos senales por **separado**. NO se infiere una
  de la otra.
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

Ninguna. Todas cerradas en las revisiones del 2026-05-17:

1. 5 vistas (Overview / Calidad / Pacientes / Clasificador / Runs) — decision de producto
2. Clasificador: solo radiografias ya registradas, NO drag&drop
3. NO se expone `POST /pipeline/trigger` desde el dashboard
4. Idioma: castellano
5. Imagen de radiografia: nuevo endpoint
   `GET /api/v1/radiographies/image?key=...` (query param, no path)
6. Refresh manual + auto-opcional 30s en Overview si es facil
7. (Ajuste A) Manejo explicito de rechazo de imagenes dummy 1x1
   anadido como CB-7
8. (Ajuste B) Evaluacion del modelo anadida como RF-7, con endpoint
   nuevo `GET /api/v1/model/evaluation` (RF-9)
9. (Ajuste C, revision de producto): RF-7 dividida en RF-7a (resumen
   minimo en Overview) + RF-7b (detalle completo en Clasificador).
   CA-1 deja de exigir `bootstrap success`. Se anade barra persistente
   de estado del sistema en el sidebar. Pre-carga de radiografia de
   demo durante el bootstrap (tarea T17) con licencia documentada.

## Criterios de aceptacion

- [ ] **CA-1** (RF-1, RNF-3): Tras `docker compose up`, navegar a la
  URL del dashboard muestra Overview con los counts correctos
  (~4.745 patients, ~8.569 admissions, >=17 radiografias), el
  indicador de modelo cargado en verde, y **el ultimo run disponible**
  del pipeline correctamente renderizado con sus campos (`status`,
  `trigger_type`, `started_at`, `records_processed`,
  `records_rejected`). El ultimo run NO tiene por que ser el
  bootstrap: puede ser un run posterior del watcher o manual. La
  carga completa debe estar lista en menos de 3 segundos.
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
- [ ] **CA-8** (RF-7a, RF-7b, RF-9): Overview muestra el strip minimo
  con accuracy + macro-F1 + model_version. Clasificador muestra al
  final la sub-seccion detallada con recall por clase y matriz de
  confusion 3x3 cargados via `GET /api/v1/model/evaluation`. Si el
  endpoint responde 503, ambas superficies muestran "Reporte no
  disponible" sin crashear
- [ ] **CA-9** (RF-6, RNF-1): El dashboard arranca como un servicio
  Docker mas con `docker compose up`. La URL del dashboard responde
  200 antes de los 15 segundos tras `up`
- [ ] **CA-10** (CB-1, RNF-4): Si se para el contenedor `api`
  (`docker compose stop api`), todas las vistas del dashboard
  muestran un mensaje de error claro en vez de pantalla blanca o
  stacktrace. La barra persistente del sidebar pasa los 3 chips a
  rojo/ambar.
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
| 2026-05-17 | Revision de producto: encuadre "Centro de Control Hospitalario" + 5 vistas como decision de producto + tabla "Razon de producto por vista" + RF-7 dividida en RF-7a (resumen Overview) y RF-7b (detalle Clasificador) + CA-1 corregido (no exige bootstrap success) + CB-4 con tabla de senales independientes + barra persistente de estado del sistema | Revision con Alejandro previa a implementacion. Vender el dashboard como producto a los profesores | spec |
