# Tasks: Dashboard de visualizacion del sistema hospitalario

> Spec: specs/dashboard.md
> Design: design/dashboard.md

## Tareas

| # | Tarea | Requisitos | Dependencias | Tamano | Estado |
|---|-------|-----------|-------------|--------|--------|
| T1 | API: nuevo endpoint `GET /api/v1/radiographies/image?key=...` en `src/api/routers/classify.py` (mismo router, familia radiografies). Usa `MinIOClient.download_bytes` que ya existe. Devuelve `Response(media_type="image/png")`. Errores: 422 key vacia (Query validation), 404 NoSuchKey, 502 otro S3Error. NO toca Mongo ni clasifica. Tests: `tests/api/test_image_endpoint.py` con 200 (bytes correctos + Content-Type), 404 (key inexistente), 422 (sin key). MinIO mockeado o usando bucket de test | RF-8, CB-5 | — | S | done |
| T2 | API: nuevo router `src/api/routers/model.py` con `GET /api/v1/model/evaluation`. Lee `MODEL_EVALUATION_PATH` (default `/app/docs/model-evaluation/metrics.json`), devuelve el JSON. 503 si fichero no existe, 500 si JSON corrupto. Wire en `src/api/main.py` (`app.include_router(model_router.router)`). Modificar `docker-compose.yml`: anadir mount `./docs/model-evaluation:/app/docs/model-evaluation:ro` al servicio `api`. Tests `tests/api/test_model_evaluation_endpoint.py`: 200 con JSON valido, 503 si fichero ausente (monkeypatch del path), 500 si JSON corrupto | RF-9, CB-4 | — | S | done |
| T3 | Verificacion del endpoint plano `GET /api/v1/radiographies?limit=...&offset=...` ya existente. Comprobar que devuelve los campos que el dropdown del clasificador necesita: `minio_object_key`, `patient_external_id`, `original_filename`, `classification`. Si falta alguno, completar `MongoReader.list_radiographies` para que los incluya. Smoke con curl contra el stack real | RF-4 | — | S | done |
| T4 | `requirements-dashboard.txt` con `streamlit==1.36.0`, `httpx==0.27.0`, `plotly==5.22.0`, `pandas==2.2.2`. **SIN pillow** (`st.image` acepta bytes PNG directamente). Smoke local: `python -c "import streamlit, httpx, plotly, pandas; print(...)"` | RNF-1 | — | S | done |
| T5 | `Dockerfile.dashboard` base `python:3.11-slim`, copia `requirements-dashboard.txt` + `src/dashboard/` + `.streamlit/`, expone 8501, healthcheck contra `/_stcore/health`, CMD `streamlit run src/dashboard/app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true`. Crear `.streamlit/config.toml` con tema (primaryColor `#2563EB`, bg `#FFFFFF`, secondaryBg `#F5F7FA`, text `#0F172A`, font sans-serif). Anadir servicio `dashboard` a `docker-compose.yml` con depends_on `api: service_healthy`, env `API_BASE_URL=http://api:8000`, puerto 8501. Smoke: `docker compose build dashboard` < 3 min, `docker compose up -d dashboard` levanta y `curl localhost:8501/_stcore/health` responde 200 < 15s (RNF-5) | RNF-1, RNF-5, RNF-6 | T4 | M | done |
| T6 | `src/dashboard/__init__.py` + `src/dashboard/config.py`. Constantes desde env: `API_BASE_URL` (default `http://api:8000`), `API_TIMEOUT_SECONDS` (default 10), `CACHE_TTL_SECONDS` (default 10). Test trivial de defaults | RF-6 | — | S | done |
| T7 | `src/dashboard/api_client.py`: clase `ApiClient(base_url, timeout)` + dataclass `ApiError(kind, status, detail, raw)` + helper `_handle_response`. Metodos GET: health, count_{patients,admissions,radiographies}, list_patients, get_patient, list_radiographies, latest_pipeline_run, list_runs, latest_quality_summary, quality_summary_history(dimension,limit,offset), get_classification, model_evaluation, image_bytes. Metodo POST: classify. **Mapping HTTP→kind:** network (httpx.RequestError), not_found (404), validation (422), unavailable (503), server (5xx u otro 4xx). Tests `tests/dashboard/test_api_client.py` con `httpx.MockTransport`: caso happy + cada kind de error | RF-1..RF-5, RF-7a, RF-7b, CB-1, CB-2, CB-4 | T6 | M | done |
| T8 | `src/dashboard/components/__init__.py` + `error_banner.py` (`show_api_error(err, context)` con mensajes en castellano segun `kind` — tabla del design, incluido distinguir `unavailable` en `/classify` vs en `/model/evaluation`) + `system_status.py` (`render_system_status(api_client)` con 3 chips API/Modelo/Ultimo run, usando `st.cache_data(ttl=10s)` para compartir llamada a `/health` + `/pipeline/status`, renderizado con `st.markdown` minimo). **NO crear `cards.py`** (usar `st.metric` directo). Tests `tests/dashboard/test_error_banner.py` con mapping `kind`→texto. `tests/dashboard/test_system_status.py` opcional, validando el mapping de status→color | RNF-4, CB-1, CB-2, CB-4, RF-1 | T7 | S | done |
| T9 | `src/dashboard/app.py`: entrypoint con `st.set_page_config(page_title="Hospital laSalle", layout="wide")` (sin page_icon, sin emojis), inicializa `ApiClient` en `st.session_state` si no existe, registra las 5 paginas con `st.navigation([overview, quality, patients, classifier, runs]).run()`. **Tras `run()`, en bloque `with st.sidebar:`** llamar `render_system_status(client)` para que la barra persistente de estado del sistema se vea desde cualquier vista. Tema se carga automaticamente desde `.streamlit/config.toml` (T5). Las vistas se implementan vacias por ahora (un `st.title` placeholder en cada `views/*.py`) para que el entrypoint corra | Layout general | T5, T6, T7, T8 | S | done |
| T10 | `src/dashboard/views/overview.py`: 4 `st.metric` (patients, admissions, radiografias, modelo cargado) + bloque "Ultimo pipeline run" (status, trigger_type, started_at, processed, rejected, error_message expandible si failed). El bloque "cards + ultimo run" va dentro de `@st.fragment(run_every=30)` para auto-refresh. **Strip minimo de Evaluacion abajo (RF-7a):** 2 `st.metric` (accuracy + macro-F1) + `model_version`, **fuera del fragment**, cacheado `ttl=60s` (las metricas no cambian hasta reentrenar). Si `/model/evaluation` devuelve 503, muestra "Reporte no disponible" en su lugar. Boton "Recargar" manual. **NO incluye recall por clase ni matriz de confusion** (eso vive en T13) | RF-1, RF-7a, CB-3, CB-4, RNF-7 | T9 | M | done |
| T11 | `src/dashboard/views/quality.py`: tabla con dimension/total/valid/rejected/rejection_rate desde `latest_quality_summary` + grafico `plotly.express.line` del historico de rejection_rate por dimension (consume `quality_summary_history` para cada dimension). Boton "Recargar" | RF-2 | T9 | M | done |
| T12 | `src/dashboard/views/patients.py`: input "Pagina" + tabla paginada (limit=20) usando `list_patients` con `offset = (pagina-1)*20`. Click en fila / input `external_id` muestra detalle: campos basicos + acordeon admissions (con diagnosis_category) + acordeon radiografias (con classification si la tiene). Boton "Recargar" | RF-3, CB-3 | T9 | M | done |
| T13 | `src/dashboard/views/classifier.py`: dropdown poblado con `list_radiographies(limit=500, offset=0)` (NO list_patients), `st.image` con bytes de `image_bytes(key)` (consume RF-8), boton "Clasificar" que llama a `classify(key)`. Si T17 esta aplicada, ordenar `HOSP-DEMO-001/...` como primera opcion del dropdown. Manejo separado de: 422 CB-7 (mensaje + boton sigue habilitado), 503 desde `/health` CB-4 (boton deshabilitado + warning), 404 imagen CB-5, success (clase + barras horizontales de probabilidades + model_version + predicted_at). **Al final de la vista**, sub-seccion "Evaluacion del modelo — detalle" (RF-7b) via la misma `model_evaluation()` cacheada que usa Overview: tabla recall por clase (destacando recall COVID-19) + heatmap matriz confusion (`plotly.express.imshow`, `color_continuous_scale="Blues"`). NO repite accuracy + macro-F1 grandes (ya estan en Overview); puede mostrarlos pequenos como contexto si encaja. Si 503: "Reporte de evaluacion no disponible" sin bloquear el resto de la vista | RF-4, RF-7b, CB-4, CB-5, CB-7 | T9 | L | done |
| T14 | `src/dashboard/views/runs.py`: tabla paginada (limit=20) con `list_runs`, columnas started_at / trigger_type / status (badge color por status) / records_processed / records_rejected / error_message (truncado a 100 chars, expandible con `st.expander` si hay error). Boton "Recargar" | RF-5, CB-3 | T9 | S | done |
| T17 | Pre-cargar 1 radiografia de demo durante el bootstrap para que la demo del Clasificador funcione out-of-the-box sin depender de subir manualmente una imagen y sin tropezar con las dummy 1x1. **El origen y la licencia de la imagen quedan documentados en `data/raw/images-demo/README.md` + comentario inline en `bootstrap.py`** (requisito no negociable). Recomendacion: opcion (b) imagen generada sinteticamente con `numpy` + `imageio` (256x256 PNG, ruido gaussiano + simulacion tosca de torax), porque elimina cualquier duda de copyright; el modelo devolvera una clase arbitraria pero la demo ensena el flujo end-to-end (que es lo que se quiere demostrar). Si se prefiere opcion (a) imagen real del Kaggle COVID-19 Radiography Database, **commitearla solo si la licencia (CC BY 4.0 segun Kaggle) lo permite y citarla explicitamente** en `data/raw/images-demo/README.md`. El bootstrap (`src/pipeline/scripts/bootstrap.py`) sube la imagen al bucket bajo la key `HOSP-DEMO-001/HOSP-DEMO-001_xray1.png` y registra un paciente `HOSP-DEMO-001` con esa radiografia embebida. El dropdown del Clasificador la ordena al principio | Demo robusta | T1, T2 | S | done |
| T15 | Smoke E2E real con stack vivo: `docker compose down -v && docker compose up -d`. Esperar a que `dashboard` este healthy. Abrir `http://localhost:8501` en navegador y validar manualmente las 5 vistas: (1) Overview muestra counts + ultimo run + strip de evaluacion (accuracy + macro-F1); (2) Quality muestra rejection_rate; (3) Patients pagina y detalle de HOSP-000001 funciona; (4) Classifier: elegir `HOSP-DEMO-001` y verificar prediccion + probabilidades + sub-seccion de evaluacion detallada al final; luego elegir una dummy y verificar mensaje CB-7; (5) Runs muestra el run del bootstrap. Smoke contra CB-1: `docker compose stop api` y verificar que las 5 vistas muestran "API no disponible" + los 3 chips del sidebar pasan a rojo/ambar sin crashear. Volver a `docker compose start api`. Opcionalmente test `tests/e2e/test_dashboard_smoke.py` con `httpx.get("http://localhost:8501/_stcore/health")` | CA-1..CA-11 | T1, T2, T3, T10, T11, T12, T13, T14, T17 | S | done |
| T16 | Documentacion viva: `CHANGELOG.md` entrada Added (dashboard + 2 endpoints nuevos + radiografia demo); `README.md` (tabla stack con Streamlit ✓, nueva URL `http://localhost:8501`, mencion al puerto 8501 en "Requisitos previos", actualizar conteo de tests si hay nuevos); `docs/diario-ia.md` sesion nueva; `tasks/lessons.md` con lo aprendido del dashboard (st.cache_data, st.fragment, evaluacion como dos senales independientes vs predictor_loaded, RF-7 dividida en dos superficies, etc); `tasks/backlog.md` feature 4 a `done`; `tasks/dashboard.md` marcar T1-T17 como `done` | — | T15 | S | done |

Tamanos: S (< 1h) | M (1-4h) | L (> 4h, considerar dividir)
Estados: pending | in-progress | done | blocked

## Detalle por tarea

### T1: Endpoint `GET /api/v1/radiographies/image`
- Anadir al final de `src/api/routers/classify.py`:
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
              raise HTTPException(404, f"Radiography not found in MinIO: {key}")
          raise HTTPException(502, "Upstream object storage error") from exc
      return Response(content=data, media_type="image/png")
  ```
- Tests `tests/api/test_image_endpoint.py`:
  - `test_image_returns_bytes_and_content_type` con MinIO mockeado
  - `test_image_returns_404_for_missing_key` con S3Error(NoSuchKey)
  - `test_image_returns_422_for_empty_key` (FastAPI Query validation)
- **Verificacion**: `docker compose run --rm --entrypoint "" pipeline pytest tests/api/test_image_endpoint.py -q`

### T2: Endpoint `GET /api/v1/model/evaluation`
- Crear `src/api/routers/model.py`:
  ```python
  router = APIRouter(prefix="/api/v1/model", tags=["model"])
  DEFAULT_EVAL_PATH = Path("/app/docs/model-evaluation/metrics.json")

  @router.get("/evaluation")
  def get_model_evaluation() -> dict:
      path = Path(os.environ.get("MODEL_EVALUATION_PATH", DEFAULT_EVAL_PATH))
      if not path.exists():
          raise HTTPException(503, "Model evaluation report not available")
      try:
          return json.loads(path.read_text())
      except json.JSONDecodeError as exc:
          raise HTTPException(500, f"Corrupt evaluation file: {exc}")
  ```
- Wire en `src/api/main.py`: `from src.api.routers import model as model_router; app.include_router(model_router.router)`
- `docker-compose.yml` servicio `api`: anadir `- ./docs/model-evaluation:/app/docs/model-evaluation:ro`
- Tests `tests/api/test_model_evaluation_endpoint.py`:
  - `test_returns_200_with_json` (escribir un `metrics.json` minimo en tmp_path)
  - `test_returns_503_when_file_missing` (path inexistente)
  - `test_returns_500_when_json_corrupt` (escribir bytes invalidos)

### T3: Verificacion endpoint `/radiographies`
- `curl "http://localhost:8000/api/v1/radiographies?limit=5"` y verificar que cada item trae:
  - `minio_object_key` (obligatorio)
  - `patient_external_id` (deseable, no critico)
  - `original_filename` (deseable)
  - `classification` (objeto o `null` segun RF-7 de clasificacion)
- Si algun campo falta o llega como `None` cuando deberia tener valor, abrir trabajo en `src/api/mongo_reader.py::list_radiographies` para completar la projection
- **Output esperado:** dict por item con los 4 campos

### T4: `requirements-dashboard.txt`
- Crear `requirements-dashboard.txt`:
  ```
  streamlit==1.36.0
  httpx==0.27.0
  plotly==5.22.0
  pandas==2.2.2
  ```
- **NO incluir Pillow**: `st.image` acepta bytes PNG directamente; no hacemos resize ni transform en el dashboard
- **Verificacion local (opcional):** `pip install -r requirements-dashboard.txt` en un venv limpio funciona. Validacion real en T5 (rebuild Docker)

### T5: `Dockerfile.dashboard` + servicio compose + tema
- Crear `.streamlit/config.toml`:
  ```toml
  [theme]
  base = "light"
  primaryColor = "#2563EB"
  backgroundColor = "#FFFFFF"
  secondaryBackgroundColor = "#F5F7FA"
  textColor = "#0F172A"
  font = "sans serif"

  [server]
  headless = true
  ```
- Crear `Dockerfile.dashboard`:
  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  COPY requirements-dashboard.txt .
  RUN pip install --no-cache-dir -r requirements-dashboard.txt
  COPY src/dashboard/ ./src/dashboard/
  COPY .streamlit/ ./.streamlit/
  ENV PYTHONPATH=/app
  EXPOSE 8501
  HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
      CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health').read()" || exit 1
  CMD ["streamlit", "run", "src/dashboard/app.py", \
       "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
  ```
- Anadir a `docker-compose.yml`:
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
- **Verificacion:** `docker compose build dashboard` < 3 min; tras `docker compose up -d dashboard`, `curl http://localhost:8501/_stcore/health` responde 200 antes de 15s

### T6: `src/dashboard/config.py`
- Solo 3 constantes + un test trivial:
  ```python
  API_BASE_URL = os.environ.get("API_BASE_URL", "http://api:8000")
  API_TIMEOUT_SECONDS = float(os.environ.get("API_TIMEOUT_SECONDS", "10"))
  CACHE_TTL_SECONDS = int(os.environ.get("DASHBOARD_CACHE_TTL", "10"))
  ```

### T7: `src/dashboard/api_client.py`
- `ApiError` como dataclass frozen con `kind`, `status`, `detail`, `raw`
- `ApiClient` con metodos sync. Cada metodo devuelve `(data, error)` tuple
- Helper interno `_handle_response(method, url, **kwargs) -> Result`:
  - `try: r = self._client.request(...); except httpx.RequestError: return None, ApiError(kind="network", ...)`
  - mapping de codigos a kind
  - en 200: `return r.json(), None` (excepto `image_bytes` que devuelve `r.content`)
- Tests `tests/dashboard/test_api_client.py`:
  - Usar `httpx.MockTransport` para responder a cada endpoint sin red
  - 9-10 tests: happy path por familia + cada `kind` de error
  - `test_classify_returns_validation_on_422`
  - `test_health_returns_network_on_connection_error`
  - `test_model_evaluation_returns_unavailable_on_503`
  - `test_image_bytes_returns_raw_bytes_not_dict`

### T8: Componentes
- `src/dashboard/components/error_banner.py`:
  ```python
  MESSAGES = {
      ("network", None): "API no disponible. Revisa que el contenedor `api` esta arriba.",
      ("not_found", None): "Sin datos disponibles.",
      ("unavailable", "/classify"): "El modelo de clasificacion no esta cargado en este despliegue.",
      ("unavailable", "/model/evaluation"): "Reporte de evaluacion no disponible (modelo nunca entrenado o `metrics.json` ausente).",
      ("validation", "/classify"): "Imagen demasiado pequena o invalida. Usa una radiografia real de >= 32x32 px.",
      # ... mas entradas en la tabla del design
  }
  def format_error(err: ApiError, context: str = "") -> str: ...
  def show_api_error(err: ApiError, context: str = "") -> None:
      st.error(format_error(err, context))
  ```
- `src/dashboard/components/system_status.py`:
  ```python
  @st.cache_data(ttl=10)
  def _fetch_status(_client) -> tuple[bool, bool | None, str | None]:
      health, h_err = _client.health()
      run, r_err = _client.latest_pipeline_run()
      api_up = h_err is None
      predictor_loaded = (health or {}).get("predictor_loaded") if api_up else None
      last_status = (run or {}).get("status") if r_err is None else None
      return api_up, predictor_loaded, last_status

  def render_system_status(client: ApiClient) -> None:
      api_up, predictor_loaded, last_status = _fetch_status(client)
      # 3 chips with color: api_up (green/red), predictor (green/red/amber), last_status
      # rendered with st.markdown using a minimal inline span style (max 3 lines of CSS)
  ```
- Tests `tests/dashboard/test_error_banner.py` validan `format_error`
  (texto en castellano por `kind` y `context`) sin invocar Streamlit
- **NO crear `cards.py`**: las cards de Overview son `st.metric` directo

### T9: Entrypoint
- `src/dashboard/app.py`:
  ```python
  import streamlit as st
  from src.dashboard.api_client import ApiClient
  from src.dashboard.components.system_status import render_system_status
  from src.dashboard.config import API_BASE_URL, API_TIMEOUT_SECONDS

  st.set_page_config(page_title="Hospital laSalle", layout="wide")

  if "api_client" not in st.session_state:
      st.session_state["api_client"] = ApiClient(API_BASE_URL, API_TIMEOUT_SECONDS)
  client = st.session_state["api_client"]

  pages = [
      st.Page("views/overview.py", title="Overview", default=True),
      st.Page("views/quality.py", title="Calidad de datos"),
      st.Page("views/patients.py", title="Pacientes"),
      st.Page("views/classifier.py", title="Clasificador"),
      st.Page("views/runs.py", title="Pipeline runs"),
  ]
  st.navigation(pages).run()

  with st.sidebar:
      render_system_status(client)
  ```
- Las vistas se crean en T10-T14 con `st.title(...)` placeholder + contenido real

### T10: `views/overview.py`
- Layout en columnas (`st.columns(4)`) para las 4 cards
- Cards:
  - "Pacientes" — value desde `count_patients`
  - "Admissions" — value desde `count_admissions`
  - "Radiografias" — value desde `count_radiografias`
  - "Modelo" — value "Cargado" (verde) o "No cargado" (rojo) desde `health.predictor_loaded`
- Bloque "Ultimo run":
  - 5 cells: status, trigger_type, started_at, processed, rejected
  - Si run failed: mostrar `error_message`
- Auto-refresh: cards + ultimo run dentro de `@st.fragment(run_every=30)`
- **Strip minimo de Evaluacion (RF-7a), FUERA del fragment:**
  ```python
  st.divider()
  st.subheader("Evaluación del modelo")
  evaluation, err = client.model_evaluation()  # cacheado ttl=60s
  if err and err.kind == "unavailable":
      st.info("Reporte de evaluación no disponible.")
  elif err:
      show_api_error(err, context="/model/evaluation")
  else:
      col1, col2, col3 = st.columns([1, 1, 2])
      col1.metric("Accuracy", f"{evaluation['accuracy']:.3f}")
      col2.metric("Macro-F1", f"{evaluation['macro_f1']:.3f}")
      col3.caption(f"model_version: `{evaluation['model_version']}` · "
                   f"detalle completo en Clasificador")
  ```
- Boton "Recargar" abajo que invalida el cache via `st.cache_data.clear()` o `st.rerun()`

### T11: `views/quality.py`
- `latest_quality_summary()` → tabla pandas
- `quality_summary_history(dimension="patients", limit=50)` y idem para `admissions`
- Concatenar dataframes y plotly line con `color="dimension"`
- Boton "Recargar"

### T12: `views/patients.py`
- `st.number_input("Pagina", min_value=1)` o `st.selectbox` paginacion
- Llamar `list_patients(limit=20, offset=(page-1)*20)`
- `st.dataframe` con seleccion (Streamlit 1.30+ soporta `on_select="rerun"`)
- Detalle del seleccionado: `get_patient(external_id)` + 2 acordeones (`st.expander`)
- Alternativa simple si la seleccion es compleja: input `st.text_input("External ID")` + boton "Buscar"

### T13: `views/classifier.py`
- `list_radiographies(limit=500, offset=0)` (cached) → lista de keys
- Si T17 aplicada, mover `HOSP-DEMO-001/...` al principio del dropdown
- `st.selectbox("Radiografia", keys)`
- `image_bytes(key)` → `st.image(bytes, use_column_width=True)`
- Si `health.predictor_loaded == False`: warning + boton deshabilitado
- Boton "Clasificar" → `classify(key)`:
  - 200: pintar barras horizontales de probabilidades (plotly), badge clase, model_version
  - 422 (CB-7): `show_api_error(err, context="/classify")` con mensaje "Imagen demasiado pequena o invalida..." + boton SIGUE habilitado
  - 503: cubrirlo aun antes con el check de health
  - 404: "Imagen no encontrada en MinIO"
- **Sub-seccion Evaluacion del modelo (RF-7b, al final de la vista):**
  ```python
  st.divider()
  st.subheader("Evaluación del modelo — detalle")
  evaluation, err = client.model_evaluation()  # MISMA llamada cacheada que Overview
  if err and err.kind == "unavailable":
      st.info("Reporte de evaluación no disponible (modelo nunca entrenado o metrics.json ausente).")
  elif err:
      show_api_error(err, context="/model/evaluation")
  else:
      # tabla recall por clase (destacar COVID-19 visualmente)
      # heatmap matriz confusion con plotly.express.imshow
      # accuracy + macro-F1 pequenos como contexto (opcional)
      ...
  ```

### T14: `views/runs.py`
- `list_runs(limit=20, offset=0)` → tabla
- Color de status (custom CSS o emoji ASCII tipo `[OK]` / `[FAIL]`)
- Para los failed, `st.expander("Ver error")` con `error_message`
- Boton "Recargar"

### T17: Pre-cargar radiografia de demo (aprobada, con licencia documentada)

**Paso 1 — Decidir origen y documentar licencia.** Crear
`data/raw/images-demo/README.md` con uno de estos dos bloques:

- **Opción A — Imagen real del dataset Kaggle (recomendado solo si licencia compatible):**
  ```
  # Radiografía de demo

  Fichero: HOSP-DEMO-001_xray1.png
  Origen: COVID-19 Radiography Database (Kaggle)
    https://www.kaggle.com/datasets/tawsifurrahman/covid19-radiography-database
  Licencia: CC BY 4.0 (verificar en la página del dataset antes de commitear)
  Cita: M.E.H. Chowdhury et al., "Can AI help in screening Viral and COVID-19
    pneumonia?", IEEE Access, 2020.
  Uso en este repo: pre-cargada al bucket MinIO durante el bootstrap
    para que la demo del Clasificador funcione out-of-the-box. NO se
    usa para entrenar ni evaluar; solo como input de inferencia en la demo.
  ```

- **Opción B — Imagen sintética (más segura, recomendada por defecto):**
  ```
  # Radiografía de demo

  Fichero: HOSP-DEMO-001_xray1.png
  Origen: generada sintéticamente con `src/pipeline/scripts/generate_demo_xray.py`
    (numpy + imageio: 256x256, ruido gaussiano + máscara elíptica simulando tórax).
  Licencia: propia del proyecto (no requiere atribución externa).
  Uso en este repo: input del clasificador en la demo. El modelo
    devolverá una clase arbitraria; el propósito es demostrar el
    flujo end-to-end (selección → inferencia → resultado), NO precisión clínica.
  ```

**Paso 2 — Si opción B, crear el generador.**
`src/pipeline/scripts/generate_demo_xray.py` con un `main()` que
escribe `data/raw/images-demo/HOSP-DEMO-001_xray1.png`. Determinista
con `--seed 42`. Imagen 256x256 (>=32 px → no se rechaza con 422).

**Paso 3 — Bootstrap.** Modificar `src/pipeline/scripts/bootstrap.py`:
- Comentario inline citando `data/raw/images-demo/README.md`.
- Subir la imagen al bucket bajo la key
  `HOSP-DEMO-001/HOSP-DEMO-001_xray1.png`.
- Registrar paciente `HOSP-DEMO-001` (nombre "Paciente Demo", edad
  ficticia, género N/A) con la radiografía embebida (sin
  `classification`).
- Idempotente: si ya existe, no duplicar.

**Paso 4 — Dropdown del Clasificador.** Ordenar para que
`HOSP-DEMO-001/...` aparezca como primera opción.

**Paso 5 — Verificación.** Tras `docker compose down -v && up`,
abrir el Clasificador, seleccionar la radiografía de demo, pulsar
"Clasificar" → devuelve clase + probabilidades sin error 422.

**Por qué la licencia es no negociable**: el repo es entregable de
Máster y queda público en GitHub; cualquier asset con copyright
ambiguo debe estar explícitamente justificado.

### T15: Smoke real end-to-end
- `docker compose down -v && docker compose up -d`
- Esperar healthchecks (max 60s)
- Validar manualmente las 5 vistas en `http://localhost:8501`
- **Overview**: counts + ultimo run + strip de evaluacion con accuracy + macro-F1
- **Classifier**: probar con `HOSP-DEMO-001` (T17) → resultado limpio + sub-seccion detallada de evaluacion al final. Probar con dummy 1x1 → mensaje CB-7
- **Sidebar**: 3 chips en verde
- `docker compose stop api` → 5 vistas con "API no disponible" + 3 chips rojo/ambar limpiamente
- `docker compose start api` → vuelve a funcionar
- Test opcional `tests/e2e/test_dashboard_smoke.py`:
  ```python
  def test_dashboard_health(http):
      r = http.get("http://localhost:8501/_stcore/health")
      assert r.status_code == 200
  ```

### T16: Documentacion viva
- `CHANGELOG.md`: entrada Added con:
  - Nuevo servicio `dashboard` (Streamlit, puerto 8501)
  - 2 endpoints API nuevos (`GET /radiographies/image?key=...` y `GET /model/evaluation`)
  - 5 vistas (Overview, Calidad, Pacientes, Clasificador, Runs)
  - Barra persistente de estado del sistema en sidebar
  - Radiografia de demo `HOSP-DEMO-001` pre-cargada al bootstrap
- `README.md`: stack con fila Dashboard (Streamlit + Plotly + Pandas, ✓ Implementado); seccion "Acceso al sistema" anadir `http://localhost:8501` para el dashboard; "Requisitos previos" anadir puerto 8501; actualizar conteo de tests
- `docs/diario-ia.md`: sesion nueva (proxima al numero actual) con prompts/decisiones/aciertos/lecciones
- `tasks/lessons.md`: lecciones del dashboard (st.cache_data necesario en cada GET, st.fragment para auto-refresh, predictor_loaded vs metrics.json son senales distintas, RF-7 dividida en dos superficies con la misma llamada cacheada, etc.)
- `tasks/backlog.md`: feature 4 a `done`
- `tasks/dashboard.md`: marcar T1-T17 como `done`

## Grafo de dependencias

```
FASE 1 (API, paralelizable)
  T1 (image endpoint) ──────────────┐
  T2 (model/evaluation endpoint) ───┤
  T3 (verificar /radiographies) ────┤
  T17 (radiografia demo + licencia) ┤
                                    │
FASE 2 (andamio)                    │
  T4 (requirements sin pillow) ──→ T5 (Docker + compose + tema)
  T6 (config) ──┐
                ├──→ T7 (api_client) ──→ T8 (error_banner + system_status, NO cards.py)
                │                              │
                └──────────────────────────────┴──→ T9 (app + SystemStatus en sidebar)
                                                          │
FASE 3 (vistas, paralelizables tras T9)
                                                          ├──→ T10 (Overview con strip RF-7a)
                                                          ├──→ T11 (Quality)
                                                          ├──→ T12 (Patients)
                                                          ├──→ T13 (Classifier + detalle RF-7b)
                                                          └──→ T14 (Runs)
                                                                       │
T1, T2, T3, T17 ─────────────────────────────────────────────────────┐ │
                                                                     │ │
                                                                     ▼ ▼
                                                          T15 (smoke real con CB-1)
                                                                       │
                                                                       ▼
                                                          T16 (docs vivas)
```

## Ruta critica

**T4 → T5 → T7 → T9 → T13 → T15 → T16**

T13 (Clasificador) ahora es **L** porque integra dropdown + imagen +
clasificar + 3 casos de error (CB-4, CB-5, CB-7) + sub-seccion
detallada de evaluacion del modelo (RF-7b). Si va mal, arrastra el
smoke (T15). Reservar ~2-3h enfocadas.

## Paralelizable

- **T1, T2, T3, T17** (endpoints/verificaciones API + radiografia demo)
  entre si. Todos sin dependencias previas. Se pueden lanzar a la vez
  al inicio
- **T4, T6** entre si (independientes)
- **T10-T14** (las 5 vistas) entre si una vez T9 hecho. Si fuera
  trabajo a varias manos, una vista por persona. En esta sesion las
  hago serie por enfoque, T13 al final (la mas compleja)

## Notas de gestion del riesgo

- **T13 (Clasificador) es el riesgo mayor**: integra mas tipos de
  error que el resto + la sub-seccion detallada de RF-7b. Si CB-7
  falla en demo, queda feo. Mitigacion: test manual exhaustivo con
  `HOSP-DEMO-001` (T17) Y una dummy 1x1 antes del commit
- **T17 con licencia no negociable**: el repo es publico, no puede
  llevar imagenes con copyright ambiguo. Opcion B (imagen sintetica)
  es la opcion segura por defecto
- **T5 puede fallar por puerto ocupado** (8501 lo usa Streamlit por
  defecto en otros proyectos). Mitigacion: env var `DASHBOARD_PORT`
  documentada en `.env.example`
- **T15 depende de un modelo entrenado real** (`data/models/`
  presente). Ya esta en el repo desde la sesion anterior. Verificar
  antes de empezar el smoke que el container `api` muestra
  `predictor_loaded:true` en `/health`
- **Tiempo total estimado:** 17 tareas, mezcla S+M+L. En modo enfocado
  ~7-9h. Cabe en 1 dia si T13 no se complica
