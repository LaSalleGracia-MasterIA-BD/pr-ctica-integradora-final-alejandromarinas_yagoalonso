# Design: Dashboard de visualizacion del sistema hospitalario

> Spec: specs/dashboard.md

## Decision arquitectonica

App **Streamlit** servida como un servicio Docker independiente
(`hospital-dashboard`) que consume exclusivamente la API REST. La
imagen base es ligera (`python:3.11-slim` + streamlit + httpx +
plotly + pandas + pillow, ~250 MB) y se construye con un Dockerfile
propio (`Dockerfile.dashboard`), no reutiliza
`hospital-pipeline:latest` (que pesa ~2 GB por PySpark + TensorFlow).

La API gana dos endpoints nuevos exigidos por la spec:
- `GET /api/v1/radiographies/image?key=...` — proxy de bytes de
  MinIO con `Content-Type: image/png` (RF-8)
- `GET /api/v1/model/evaluation` — lee `docs/model-evaluation/metrics.json`
  y lo devuelve como JSON (RF-9)

Decisiones clave (cada una justificada abajo, las dos mas relevantes
con ADR propio):

1. **Streamlit + imagen Docker independiente** — ADR-007. Stack
   Python-only alineado con el resto del proyecto, comunidad amplia
   en demos academicas, levanta en < 15s (frente a 5-10s solo
   importando TF si reusaramos la imagen del pipeline). Coste:
   un Dockerfile mas y un servicio mas en compose
2. **Cliente HTTP `httpx` sync con `st.cache_data(ttl=...)`**
   alrededor de cada query a la API. Streamlit re-ejecuta el script
   en cada interaccion; sin cache se bombardearia la API en cada
   click. TTL corto (5-10s en Overview/Runs) para no servir datos
   stale en una demo
3. **Auto-refresh nativo con `st.fragment(run_every=30)`**
   (Streamlit 1.33+) en la vista Overview. Sin dependencia extra,
   no bloquea otras vistas
4. **Layout multi-pagina con `st.navigation`** (Streamlit 1.30+):
   sidebar nativa con las 5 vistas, sin hacks de session_state
5. **Cliente API encapsulado** en `src/dashboard/api_client.py`:
   una sola clase con metodos tipados que devuelve dicts. Las vistas
   NO hablan con `httpx` directamente. Beneficio: tests unitarios
   del cliente mockean `httpx`, las vistas se prueban contra un
   `FakeApiClient`
6. **Manejo de errores centralizado:** cada query devuelve
   `(data, error: ApiError | None)`. Las vistas pintan banner de
   error si `error is not None`, contenido en otro caso. NO se
   propagan excepciones a Streamlit (que las pintaria como
   stacktrace al usuario)
7. **API endpoint nuevo de imagen vive en `src/api/routers/classify.py`**
   (misma familia `/radiographies`), endpoint nuevo de evaluation
   vive en router nuevo `src/api/routers/model.py` con prefix
   `/api/v1/model`
8. **Volumen `docs/model-evaluation` montado `:ro` en la API** para
   que el endpoint `/model/evaluation` pueda leer `metrics.json`.
   Hoy ese directorio solo se monta en `pipeline` (rw, para que
   `train.py` escriba)

## Trazabilidad spec → componentes

| Requisito | Componente(s) | Archivos |
|-----------|--------------|----------|
| RF-1 (Overview) | `views/overview.py` + `ApiClient.health()`, `count_patients()`, `count_admissions()`, `count_radiographies()`, `latest_pipeline_run()` | `src/dashboard/views/overview.py`, `src/dashboard/api_client.py` |
| RF-2 (Calidad) | `views/quality.py` + `ApiClient.latest_quality_summary()`, `quality_summary_history(dimension)` | `src/dashboard/views/quality.py` |
| RF-3 (Pacientes) | `views/patients.py` + `ApiClient.list_patients(limit, offset)`, `get_patient(external_id)` | `src/dashboard/views/patients.py` |
| RF-4 (Clasificador) | `views/classifier.py` + `ApiClient.list_radiographies(limit,offset)` (poblar dropdown), `image_bytes(key)` (consume RF-8), `classify(key)` | `src/dashboard/views/classifier.py` |
| RF-5 (Runs) | `views/runs.py` + `ApiClient.list_runs(limit, offset)` | `src/dashboard/views/runs.py` |
| RF-6 (config) | `config.py` lee `API_BASE_URL` (default `http://api:8000`) | `src/dashboard/config.py` |
| RF-7 (Evaluacion modelo) | sub-seccion en `views/overview.py` + `ApiClient.model_evaluation()` (consume RF-9) | `src/dashboard/views/overview.py` |
| RF-8 (endpoint imagen) | `routers/classify.py` gana `GET /radiographies/image` | `src/api/routers/classify.py`, `src/pipeline/storage/minio_client.py` (reusa `download_bytes`) |
| RF-9 (endpoint evaluation) | nuevo router `routers/model.py` | `src/api/routers/model.py`, `src/api/main.py` (wire), `docker-compose.yml` (mount nuevo) |
| RNF-1 (Docker service) | `Dockerfile.dashboard` + servicio `dashboard` en compose | `Dockerfile.dashboard`, `docker-compose.yml` |
| RNF-2 (sin estado) | Sin BBDD ni session_state persistente; cache via `st.cache_data` con TTL corto | toda la app |
| RNF-3 (<3s por vista) | paginacion server-side + cache local con TTL | `api_client.py` |
| RNF-4 (errores claros) | `components/error_banner.py` + handler centralizado en `api_client` | `src/dashboard/components/`, `api_client.py` |
| RNF-5 (build <3min, arranque <15s) | imagen ligera sin TF (ADR-007) | `Dockerfile.dashboard`, `requirements-dashboard.txt` |
| RNF-6 (navegador moderno) | Streamlit funciona en Chrome/Firefox/Safari recientes | (cumplido por el framework) |
| RNF-7 (refresh manual + auto opcional) | boton `st.button("Recargar")` en cada vista + `st.fragment(run_every=30)` solo en Overview | views/* |
| CB-1 (API caida) | `ApiClient` captura `httpx.RequestError` → `ApiError(kind="network")` | `api_client.py` |
| CB-2 (5xx puntual) | `ApiError(kind="server", status=5xx, detail=...)` | `api_client.py` |
| CB-3 (sin datos) | vistas pintan "Sin datos" si lista vacia, no tabla vacia silente | views/* |
| CB-4 (modelo no cargado / evaluation no disponible) | Dos señales distintas: `predictor_loaded=false` de `/health` → Overview indicador rojo + Classifier deshabilita boton; `/model/evaluation` 503 → sub-seccion Evaluation muestra "Reporte de evaluacion no disponible". Pueden estar desacopladas | views/overview.py, views/classifier.py, api_client.py |
| CB-5 (radiografia 404 en image) | `views/classifier.py` muestra "Imagen no disponible en MinIO" | views/classifier.py |
| CB-6 (API lenta) | `st.spinner("Cargando…")` envolviendo cada query | views/* |
| CB-7 (dummy 1x1 rechazada con 422) | `views/classifier.py` muestra mensaje claro + permite reintentar sin recargar | views/classifier.py |

## Componentes

### `src/dashboard/app.py` (nuevo) — entrypoint
- **Responsabilidad:** registrar las 5 paginas con `st.navigation`,
  configurar layout (`st.set_page_config`), inicializar el cliente
  API en `st.session_state`
- **Requisitos que cubre:** Layout general
- **Detalle:**
  - `st.set_page_config(page_title="Hospital laSalle", layout="wide")` (sin `page_icon` — el repo mantiene la convencion ASCII y evita ruido)
  - `st.navigation([overview_page, quality_page, patients_page, classifier_page, runs_page]).run()`

### `src/dashboard/config.py` (nuevo)
- **Responsabilidad:** leer env vars y exponer constantes
- **Requisitos que cubre:** RF-6
- **Interfaz:**
  - `API_BASE_URL = os.environ.get("API_BASE_URL", "http://api:8000")`
  - `API_TIMEOUT_SECONDS = float(os.environ.get("API_TIMEOUT_SECONDS", "10"))`
  - `CACHE_TTL_SECONDS = int(os.environ.get("DASHBOARD_CACHE_TTL", "10"))`

### `src/dashboard/api_client.py` (nuevo)
- **Responsabilidad:** facade sobre httpx contra la API.
  Centraliza manejo de errores, timeouts, y conversion a estructuras
  tipadas (dicts simples por simplicidad — no Pydantic, la API ya
  valida en su lado)
- **Requisitos que cubre:** RF-1..RF-5, RF-7, CB-1..CB-6
- **Interfaz:**
  ```
  @dataclass(frozen=True)
  class ApiError:
      kind: Literal["network", "server", "not_found", "validation", "unavailable"]
      status: int | None
      detail: str
      raw: dict | None

  Result = tuple[Any | None, ApiError | None]

  class ApiClient:
      def __init__(self, base_url: str, timeout: float): ...
      def health(self) -> Result   # /api/v1/health
      def count_patients(self) -> Result   # GET /patients?limit=1 -> total
      def count_admissions(self) -> Result
      def count_radiographies(self) -> Result
      def list_patients(self, limit: int, offset: int) -> Result
      def get_patient(self, external_id: str) -> Result
      def list_radiographies(self, limit: int, offset: int) -> Result   # GET /radiographies (plano)
      def latest_pipeline_run(self) -> Result   # GET /pipeline/status
      def list_runs(self, limit: int, offset: int) -> Result
      def latest_quality_summary(self) -> Result
      def quality_summary_history(self, dimension: str, limit: int, offset: int) -> Result
      def classify(self, minio_object_key: str) -> Result
      def get_classification(self, minio_object_key: str) -> Result
      def image_bytes(self, minio_object_key: str) -> tuple[bytes | None, ApiError | None]
      def model_evaluation(self) -> Result
  ```
- **Mapping de status HTTP → ApiError.kind:**
  | Status | kind | Cuando |
  |--------|------|--------|
  | (Connection/Timeout error) | `network` | API caida o lenta |
  | 200/201/202 | (no error, devuelve datos) | OK |
  | 404 | `not_found` | recurso no encontrado |
  | 422 | `validation` | input invalido (incluye imagen <32px) |
  | 503 | `unavailable` | modelo no cargado (CB-4) |
  | 4xx (otros) | `server` con status | malo del cliente |
  | 5xx | `server` con status | malo del servidor |
- **Caching:** los metodos GET se decoran fuera (en las vistas) con
  `st.cache_data(ttl=CACHE_TTL_SECONDS)`. POST `classify` no se
  cachea
- **Sin estado interno:** se construye una vez por sesion de
  Streamlit, almacenada en `st.session_state["api_client"]`

### `src/dashboard/components/error_banner.py` (nuevo)
- **Responsabilidad:** widget reutilizable que pinta un `st.error`
  o `st.warning` segun `ApiError.kind`, con mensaje en castellano
- **Mensajes (CB-1..CB-6, CB-7):**
  | kind / detalle | Mensaje al usuario |
  |---|---|
  | `network` | "API no disponible. Revisa que el contenedor `api` esta arriba." |
  | `server` 5xx | "Error del servidor (HTTP {status}): {detail}" |
  | `server` 4xx | "Peticion invalida (HTTP {status}): {detail}" |
  | `not_found` | "Sin datos disponibles." |
  | `validation` (en /classify) | "Imagen demasiado pequena o invalida. Usa una radiografia real de >= 32x32 px." |
  | `validation` (otros) | "Parametros invalidos: {detail}" |
  | `unavailable` | "El modelo de clasificacion no esta cargado en este despliegue." |

### `src/dashboard/components/cards.py` (nuevo)
- **Responsabilidad:** card de metrica (numero grande + label) y card
  de estado (verde/rojo/amarillo)
- **Uso:** vista Overview principalmente

### `src/dashboard/views/overview.py` (nuevo)
- **Responsabilidad:** vista de inicio
- **Requisitos:** RF-1, RF-7, RNF-7 (auto-refresh)
- **Estructura visual:**
  ```
  Hospital laSalle — Resumen general
  ─────────────────────────────────────────────────────────
  [card Patients]  [card Admissions]  [card Radiografias]  [card Modelo]
  ─────────────────────────────────────────────────────────
  Ultimo pipeline run:
    status: success | trigger: bootstrap | started: 2026-05-16 ...
    records_processed: 13314 | records_rejected: 1692
  ─────────────────────────────────────────────────────────
  Evaluacion del modelo (test split, modelo v1.0-...):
    accuracy: 0.872 | macro-F1: 0.846
    [tabla recall por clase]
    [matriz de confusion 3x3 como heatmap plotly (px.imshow)]
  ─────────────────────────────────────────────────────────
  [Boton "Recargar"]    (auto-refresh cada 30s activo)
  ```
- **Logica:** `@st.fragment(run_every=30)` envolviendo el bloque de
  cards + ultimo run; el bloque de evaluation se renderiza fuera del
  fragment (no cambia)

### `src/dashboard/views/quality.py` (nuevo)
- **Responsabilidad:** vista de calidad de datos
- **Requisitos:** RF-2
- **Estructura visual:**
  ```
  Calidad de datos — ultimo snapshot
  [tabla con dimension/total/valid/rejected/rejection_rate]
  Historico (rejection_rate por run):
  [grafico plotly line por dimension (px.line)]
  [Boton "Recargar"]
  ```

### `src/dashboard/views/patients.py` (nuevo)
- **Responsabilidad:** lista + detalle de pacientes
- **Requisitos:** RF-3
- **Estructura visual:**
  - Tabla paginada (`limit=20`, controles "<<", ">>" en sidebar)
  - Sidebar / input: `external_id` para ir directo a un paciente
  - Click en fila de tabla = abre detalle abajo (o pestaña expandible)
  - Detalle: campos basicos + acordeon "Admissions" + acordeon "Radiografias"
- **Paginacion server-side:** `ApiClient.list_patients(limit=20, offset=current_page*20)`,
  el `total` viene del response y se usa para mostrar "Pagina X de Y"

### `src/dashboard/views/classifier.py` (nuevo)
- **Responsabilidad:** clasificador interactivo
- **Requisitos:** RF-4, CB-4, CB-5, CB-7
- **Estructura visual:**
  ```
  Clasificador de radiografias
  ─────────────────────────────────────────────────────────
  Selecciona una radiografia:
    [dropdown con keys disponibles]    (poblado desde la lista de patients)
  ─────────────────────────────────────────────────────────
  [imagen mostrada en grande]    ← GET /radiographies/image?key=...

  [Boton "Clasificar"]
  ─────────────────────────────────────────────────────────
  Resultado (si hay):
    Clase predicha: COVID-19    (con badge de color por clase)
    Probabilidades: [grafico horizontal bars]
    Model version: v1.0-...    Predicted at: ...
  ```
- **Poblado del dropdown:** primera carga llama
  `ApiClient.list_radiographies(limit=500, offset=0)` contra el
  endpoint plano ya existente `GET /api/v1/radiographies` (cada
  fila trae ya `patient_external_id`, `minio_object_key`,
  `classification`). Es mas ligero y mas correcto que iterar
  `list_patients` extrayendo radiografias embebidas: cubre cualquier
  radiografia del bucket sin importar a que paciente pertenece, sin
  depender de la paginacion de pacientes. (Si el dataset crece por
  encima de 500 imagenes, anadir filtro de busqueda por substring
  o paginacion en el propio dropdown)
- **Si `predictor_loaded=false`** (verificado al cargar la vista):
  - Boton "Clasificar" deshabilitado
  - Banner `unavailable` arriba
  - La imagen y el dropdown siguen funcionando
- **Si API responde 422 al clasificar:**
  - Banner `validation` debajo del boton
  - Boton se queda habilitado para que el usuario cambie de imagen
  - El estado del dropdown NO se resetea

### `src/dashboard/views/runs.py` (nuevo)
- **Responsabilidad:** vista de pipeline runs
- **Requisitos:** RF-5
- **Estructura visual:**
  - Tabla paginada con columnas: `started_at`, `trigger_type`,
    `status` (con badge), `records_processed`, `records_rejected`,
    `error_message` (truncado a 100 chars, expandible)
  - Boton "Recargar"

### API: nuevo endpoint en `src/api/routers/classify.py`
- **Anadir:** `GET /api/v1/radiographies/image`
- **Comportamiento:**
  ```python
  @router.get("/image")
  def get_radiography_image(
      request: Request,
      key: str = Query(..., min_length=1),
  ) -> Response:
      minio_client = request.app.state.minio_client
      bucket = request.app.state.radiographies_bucket
      try:
          data = minio_client.download_bytes(bucket, key)
      except S3Error as exc:
          if exc.code in {"NoSuchKey", "NoSuchObject"}:
              raise HTTPException(404, f"Radiography not found: {key}")
          raise HTTPException(502, "Upstream object storage error")
      return Response(content=data, media_type="image/png")
  ```
- **Errores:** 404 (key inexistente), 422 (key vacia, lo da Pydantic),
  503 nunca aplica (no depende del predictor), 502 si MinIO falla con
  algo distinto a NoSuchKey
- **Notas:** NO toca Mongo, NO clasifica. Es proxy de lectura puro

### API: router nuevo `src/api/routers/model.py`
- **Anadir:** `GET /api/v1/model/evaluation`
- **Comportamiento:**
  ```python
  router = APIRouter(prefix="/api/v1/model", tags=["model"])

  DEFAULT_EVAL_PATH = Path("/app/docs/model-evaluation/metrics.json")

  @router.get("/evaluation")
  def get_model_evaluation(request: Request) -> dict:
      path = Path(os.environ.get("MODEL_EVALUATION_PATH", DEFAULT_EVAL_PATH))
      if not path.exists():
          raise HTTPException(
              503,
              "Model evaluation report not available (metrics.json missing)",
          )
      try:
          return json.loads(path.read_text())
      except json.JSONDecodeError as exc:
          raise HTTPException(500, f"Corrupt evaluation file: {exc}")
  ```
- **Errores:**
  - 503 si **el fichero `metrics.json` no existe**. Ojo: esto NO es
    lo mismo que `predictor_loaded=false`. Son senales distintas
    aunque relacionadas:
    - `predictor_loaded=false` (de `/health`) → la API no puede
      ejecutar inferencia (falta el `.keras` o falla al cargar)
    - `/model/evaluation` 503 → no hay reporte de evaluacion para
      mostrar (falta `metrics.json`)
    - **Casos posibles:** modelo cargado pero alguien borro
      `metrics.json` (raro pero posible: `/health` dice cargado,
      `/model/evaluation` da 503). O modelo no cargado pero hay
      `metrics.json` de un entrenamiento previo (las metricas son
      validas, simplemente no se puede inferir).
    - El dashboard debe leer ambas senales por separado: el
      indicador rojo/verde del modelo en Overview viene de
      `predictor_loaded`; el bloque "Evaluacion del modelo" se
      muestra/oculta segun el response de `/model/evaluation`
  - 500 si el JSON esta corrupto (no deberia pasar en operacion normal)
- **Wire en `main.py`:** `app.include_router(model_router.router)`

### `Dockerfile.dashboard` (nuevo)
- **Base:** `python:3.11-slim`
- **Layers:**
  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  COPY requirements-dashboard.txt .
  RUN pip install --no-cache-dir -r requirements-dashboard.txt
  COPY src/dashboard/ ./src/dashboard/
  ENV PYTHONPATH=/app
  EXPOSE 8501
  HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
      CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health').read()"
  CMD ["streamlit", "run", "src/dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
  ```

### `requirements-dashboard.txt` (nuevo)
- `streamlit==1.36.0` (incluye `st.navigation`, `st.fragment(run_every=...)`)
- `httpx==0.27.0` (mismo que la API)
- `plotly==5.22.0` (graficos interactivos, ya en temario del Master)
- `pandas==2.2.2` (tablas + alimentacion de plotly)
- `pillow==10.3.0` (decodificar imagen para `st.image`)

**Por que Plotly (no Altair):** el temario del Master cubre pandas,
matplotlib y plotly. Altair no se ha justificado en clase. Plotly da
interactividad (zoom, hover, leyenda) que en Streamlit se integra
con `st.plotly_chart`. Matplotlib se reserva para reportes offline
del modelo (ya en uso por `src/ml/evaluate.py`).

### `docker-compose.yml` — modificaciones
- **Servicio nuevo `dashboard`:**
  ```yaml
  dashboard:
    build:
      context: .
      dockerfile: Dockerfile.dashboard
    image: hospital-dashboard:latest
    container_name: hospital-dashboard
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "${DASHBOARD_PORT:-8501}:8501"
    environment:
      API_BASE_URL: http://api:8000
      API_TIMEOUT_SECONDS: "10"
      DASHBOARD_CACHE_TTL: "10"
    restart: unless-stopped
  ```
- **Servicio `api` — mount nuevo de `docs/model-evaluation`:**
  ```yaml
  api:
    volumes:
      - ./data/raw:/app/data/raw:ro
      - ./data/models:/app/data/models:ro
      - ./docs/model-evaluation:/app/docs/model-evaluation:ro    # NUEVO
      - pipeline-db:/app/data/db:rw
  ```

## Modelo de datos

El dashboard NO tiene modelo de datos propio (no BBDD). Todas las
estructuras son dicts deserializados de la API. Para reducir
acoplamiento futuro, las vistas acceden a campos via `.get()` con
fallback, no por atributo directo.

Schemas relevantes (ya definidos por la API):
- `Patient` (con `admissions` y `radiographies` embebidos)
- `PipelineRun`
- `QualitySummaryItem`
- `ClassificationResponse`
- `HealthResponse` (incluye `predictor_loaded: bool`)
- `metrics.json` schema (definido en `src/ml/evaluate.py`)

## Contratos de datos

### Datos de entrada (al dashboard, del usuario)

| Accion | Origen | Validacion en el dashboard |
|--------|--------|---------------------------|
| Cambio de pagina | sidebar Streamlit | (nativa) |
| Seleccion de paciente | dropdown / external_id en input | trim, no vacio |
| Seleccion de radiografia para clasificar | dropdown poblado desde API | no vacio |
| Click "Clasificar" | boton | (sin extra) |
| Click "Recargar" | boton | invalida cache de la vista |

### Datos de salida (de la API, ya existentes — sin cambios)

Todos los endpoints actuales (`/patients`, `/admissions`,
`/radiographies`, `/pipeline/*`, `/health`) se consumen sin cambios.

### Datos de salida (nuevos endpoints de la API)

| Endpoint | Response 200 | Errores |
|----------|--------------|---------|
| `GET /api/v1/radiographies/image?key=...` | `Content-Type: image/png`, body = bytes del PNG | 422 (key vacia), 404 (no existe), 502 (MinIO mal) |
| `GET /api/v1/model/evaluation` | `application/json` = contenido literal de `metrics.json` (accuracy, macro_f1, per_class, confusion_matrix, classes, model_version, hyperparameters) | 503 (modelo no entrenado), 500 (fichero corrupto) |

### Glosario

| Termino | Definicion | NO significa |
|---------|-----------|--------------|
| Vista | Una de las 5 paginas del dashboard (Overview, Calidad, Pacientes, Clasificador, Runs) | Endpoint REST |
| Card | Widget de metrica grande (numero + label) en Overview | Tarjeta de paciente |
| Auto-refresh | Re-ejecucion automatica de un fragment cada N segundos | Recarga completa del navegador |
| Banner de error | Componente visual rojo/amarillo arriba de la vista cuando hay `ApiError` | Modal o dialog |

## Trade-offs

| Decision | Alternativa descartada | Razon |
|----------|----------------------|-------|
| **Streamlit** | Plotly Dash, Reflex, React/Next.js, HTML+JS | ADR-007: Python-only, comunidad amplia en demos academicas, sintaxis declarativa breve, levanta en <15s |
| **Imagen Docker independiente** (`hospital-dashboard`) | Reutilizar `hospital-pipeline:latest` (con TF) | ADR-007: imagen base 250 MB vs 2 GB. Arranque <15s vs >20s (TF tarda en importar). Sin acoplar el dashboard al ciclo de rebuild del pipeline cada vez que cambia ML |
| **Cliente HTTP `httpx` sync** | `requests` o `httpx` async | httpx ya esta en el ecosistema (la API lo usa), sync es lo natural para Streamlit (que es sync), evita complicarse con `asyncio` en cada vista |
| **`st.cache_data(ttl=10s)`** en queries GET | Sin cache | Streamlit re-ejecuta el script en cada interaccion del usuario (click, scroll, cambio de pagina). Sin cache se bombardearia la API con la misma query 5 veces en 2 segundos |
| **TTL corto (10s) vs largo (60s+)** | TTL >60s | Demo en vivo: el evaluador no debe ver datos stale al cambiar de vista. 10s mantiene la vista "viva" sin sobrecargar |
| **Cliente API encapsulado en clase** | Funciones sueltas | Tests unitarios mockean `httpx` una sola vez; las vistas se testean con `FakeApiClient` |
| **Endpoint `/radiographies/image` con query param** | `{key:path}` | Coherente con `/classify` y `/classification` (key contiene `/`). Documentado en lessons.md el 16-may |
| **Endpoint `/model/evaluation` que lee `metrics.json`** | Calcular metricas on-the-fly en cada peticion | Las metricas son del modelo entrenado, no cambian hasta que se reentrena. Calcular cada vez requiere todo el test split en memoria — caro y absurdo |
| **`metrics.json` montado `:ro` en API** | Endpoint que delega a `pipeline` por red interna | Mas simple: API lee el fichero local. El mount es trivial; la "delegacion" inventaria un patron innecesario |
| **5 vistas separadas con `st.navigation`** | Una sola vista con tabs (`st.tabs`) | navigation es nativo Streamlit 1.30+, sidebar moderno, URLs distintas (futura mejora: deeplink). tabs todo en una pagina seria un solo script gigante |
| **Dropdown para elegir radiografia (no upload)** | Drag&drop / upload | Fuera del alcance segun spec (requiere endpoint nuevo en API que no haremos) |
| **Idioma castellano** | Bilingüe | Spec lo fija. Demo en castellano |
| **Manual + auto-refresh 30s solo en Overview** | Auto en todas las vistas | Auto en Pacientes/Classifier seria mareante (cambia la tabla mientras navegas). En Overview tiene sentido para una pantalla de "control" |

## Plan de tests (resumen — detalle en /tareas)

| Nivel | Archivo | Que valida |
|-------|---------|------------|
| Unit | `tests/dashboard/test_api_client.py` (nuevo) | Mock de httpx: cada metodo devuelve `(data, None)` en 200, `(None, ApiError(kind=...))` en cada cogido de status. Sin red |
| Unit | `tests/dashboard/test_error_banner.py` (nuevo) | Snapshot de los textos por kind |
| Unit | `tests/api/test_image_endpoint.py` (nuevo) | 200 con bytes, 404 sin key, 422 sin parametro, content-type image/png |
| Unit | `tests/api/test_model_evaluation_endpoint.py` (nuevo) | 200 con JSON, 503 si fichero no existe, 500 si JSON corrupto |
| Integ | (no aplica unit) | Las vistas Streamlit son dificiles de testear unitariamente; se prueban manualmente en T15-equivalente del implementador |
| E2E | `tests/e2e/test_dashboard_smoke.py` (nuevo, opcional) | Con `httpx`, comprobar que el endpoint `/_stcore/health` responde 200 cuando `docker compose up` esta levantado |

## Inicializacion y arranque

1. `docker compose up` levanta servicios en este orden:
   - `mongodb`, `minio` (healthchecks)
   - `pipeline` (bootstrap ETL one-shot, escribe en `data/models/` si
     se reentrena, escribe en `docs/model-evaluation/` si se reentrena)
   - `api` (espera a que `pipeline` complete; carga el predictor;
     monta `docs/model-evaluation:ro`)
   - `watcher` (long-running)
   - `dashboard` (espera a que `api` este healthy)
2. El dashboard arranca:
   - lee `API_BASE_URL` del env (default `http://api:8000`)
   - inicializa `ApiClient` en `st.session_state`
   - servidor disponible en `http://localhost:${DASHBOARD_PORT:-8501}`
3. El healthcheck del compose mira `/_stcore/health` cada 10s

## Riesgos identificados

1. **`metrics.json` puede no existir** en deploys nuevos (modelo nunca
   entrenado). Mitigacion: endpoint `/model/evaluation` devuelve 503;
   dashboard pinta "Modelo no cargado" en la sub-seccion (CB-4)
2. **Streamlit re-ejecuta el script en cada interaccion** — si una
   vista tarda en cargar, el usuario percibe lentitud. Mitigacion:
   `st.cache_data(ttl=10s)` en todos los GET; `st.spinner` para los
   POST (que no se cachean)
3. **Imagen del PNG puede ser grande** si el dataset crece — hoy las
   reales son ~30 KB, las dummy son ~70 bytes. Sin riesgo de OOM
4. **`st.fragment(run_every=...)` requiere Streamlit >= 1.33.**
   Pin `streamlit==1.36.0` (estable). Si la version cambia y se pierde
   el feature, refresh se queda manual (no bloqueante)
5. **Manejo de threading en Streamlit:** httpx sync llamado desde el
   thread principal de Streamlit es seguro. No hay race conditions
6. **El dropdown del clasificador llama a `list_radiographies(limit=500)`**
   en cada render — son ~500 filas planas (un dict pequeño por
   radiografia, no documentos enteros de pacientes). El response es
   ligero (~50-100 KB para las 17 + futuras). Mitigacion: cache
   `ttl=60s` en esa query concreta. Si crece >500 imagenes anadir
   filtro de busqueda + paginacion en el dropdown
7. **CB-7 (dummy 1x1):** las 17 dummy son las que aparecen primero
   en el dropdown (HOSP-000001..HOSP-000009). Un evaluador podria
   elegir una y ver el error. Mitigacion: orden alfabetico inverso
   o filtro por tamano si el endpoint lo permite (no lo hace);
   mejor: anadir un texto "Tip: las 17 radiografias dummy son 1x1
   y se rechazan. Para una demo real, sube una imagen al bucket
   antes" en la vista del clasificador

## Decisiones registradas como ADR

- **ADR-007:** [Streamlit + imagen Docker independiente para el dashboard](../decisions/ADR-007-dashboard-streamlit-imagen-independiente.md)
