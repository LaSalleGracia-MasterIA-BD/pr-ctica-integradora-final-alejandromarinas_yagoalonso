# Tasks: Dashboard de visualizacion del sistema hospitalario

> Spec: specs/dashboard.md
> Design: design/dashboard.md

## Tareas

| # | Tarea | Requisitos | Dependencias | Tamano | Estado |
|---|-------|-----------|-------------|--------|--------|
| T1 | API: nuevo endpoint `GET /api/v1/radiographies/image?key=...` en `src/api/routers/classify.py` (mismo router, familia radiografies). Usa `MinIOClient.download_bytes` que ya existe. Devuelve `Response(media_type="image/png")`. Errores: 422 key vacia (Query validation), 404 NoSuchKey, 502 otro S3Error. NO toca Mongo ni clasifica. Tests: `tests/api/test_image_endpoint.py` con 200 (bytes correctos + Content-Type), 404 (key inexistente), 422 (sin key). MinIO mockeado o usando bucket de test | RF-8, CB-5 | — | S | pending |
| T2 | API: nuevo router `src/api/routers/model.py` con `GET /api/v1/model/evaluation`. Lee `MODEL_EVALUATION_PATH` (default `/app/docs/model-evaluation/metrics.json`), devuelve el JSON. 503 si fichero no existe, 500 si JSON corrupto. Wire en `src/api/main.py` (`app.include_router(model_router.router)`). Modificar `docker-compose.yml`: anadir mount `./docs/model-evaluation:/app/docs/model-evaluation:ro` al servicio `api`. Tests `tests/api/test_model_evaluation_endpoint.py`: 200 con JSON valido, 503 si fichero ausente (monkeypatch del path), 500 si JSON corrupto | RF-9, CB-4 | — | S | pending |
| T3 | Verificacion del endpoint plano `GET /api/v1/radiographies?limit=...&offset=...` ya existente. Comprobar que devuelve los campos que el dropdown del clasificador necesita: `minio_object_key`, `patient_external_id`, `original_filename`, `classification`. Si falta alguno, completar `MongoReader.list_radiographies` para que los incluya. Smoke con curl contra el stack real | RF-4 | — | S | pending |
| T4 | `requirements-dashboard.txt` con `streamlit==1.36.0`, `httpx==0.27.0`, `plotly==5.22.0`, `pandas==2.2.2`, `pillow==10.3.0`. Smoke local: `python -c "import streamlit, httpx, plotly, pandas, PIL; print(...)"` | RNF-1 | — | S | pending |
| T5 | `Dockerfile.dashboard` base `python:3.11-slim`, copia `requirements-dashboard.txt` + `src/dashboard/`, expone 8501, healthcheck contra `/_stcore/health`, CMD `streamlit run src/dashboard/app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true`. Anadir servicio `dashboard` a `docker-compose.yml` con depends_on `api: service_healthy`, env `API_BASE_URL=http://api:8000`, puerto 8501. Smoke: `docker compose build dashboard` < 3 min, `docker compose up -d dashboard` levanta y `curl localhost:8501/_stcore/health` responde 200 < 15s (RNF-5) | RNF-1, RNF-5, RNF-6 | T4 | M | pending |
| T6 | `src/dashboard/__init__.py` + `src/dashboard/config.py`. Constantes desde env: `API_BASE_URL` (default `http://api:8000`), `API_TIMEOUT_SECONDS` (default 10), `CACHE_TTL_SECONDS` (default 10). Test trivial de defaults | RF-6 | — | S | pending |
| T7 | `src/dashboard/api_client.py`: clase `ApiClient(base_url, timeout)` + dataclass `ApiError(kind, status, detail, raw)` + helper `_handle_response`. Metodos GET: health, count_{patients,admissions,radiographies}, list_patients, get_patient, list_radiographies, latest_pipeline_run, list_runs, latest_quality_summary, quality_summary_history(dimension,limit,offset), get_classification, model_evaluation, image_bytes. Metodo POST: classify. **Mapping HTTP→kind:** network (httpx.RequestError), not_found (404), validation (422), unavailable (503), server (5xx u otro 4xx). Tests `tests/dashboard/test_api_client.py` con `httpx.MockTransport`: caso happy + cada kind de error | RF-1..RF-5, RF-7, CB-1, CB-2, CB-4 | T6 | M | pending |
| T8 | `src/dashboard/components/__init__.py` + `error_banner.py` (funcion `show_api_error(err: ApiError, context: str)` que pinta `st.error` o `st.warning` con mensaje en castellano segun `kind`) + `cards.py` (funcion `metric_card(label, value, color="gray")` para Overview). Mensajes mapeados a castellano segun la tabla del design. Tests minimos: `tests/dashboard/test_error_banner.py` verifica que cada `kind` produce el texto esperado (sin renderizar Streamlit; testeando la funcion de mapping) | RNF-4, CB-1, CB-2, CB-4, CB-5, CB-7 | T7 | S | pending |
| T9 | `src/dashboard/app.py`: entrypoint con `st.set_page_config(page_title="Hospital laSalle", layout="wide")` (sin page_icon, sin emojis), inicializa `ApiClient` en `st.session_state` si no existe, registra las 5 paginas con `st.navigation([overview, quality, patients, classifier, runs]).run()`. Las vistas se implementan vacias por ahora (un `st.title` placeholder en cada `views/*.py`) para que el entrypoint corra | Layout general | T5, T6, T7, T8 | S | pending |
| T10 | `src/dashboard/views/overview.py`: 4 cards (patients, admissions, radiografias, modelo cargado) + bloque "Ultimo pipeline run" + sub-seccion "Evaluacion del modelo" con accuracy, macro-F1, tabla de recall por clase y heatmap de matriz de confusion (`plotly.express.imshow`). El bloque de cards + ultimo run va dentro de `@st.fragment(run_every=30)` para auto-refresh; el bloque de evaluation queda fuera (no cambia). Manejo de CB-4 separado: indicador del modelo viene de `predictor_loaded`; bloque evaluation se renderiza si `/model/evaluation` devuelve 200, si no muestra "Reporte no disponible". Boton "Recargar" manual al final | RF-1, RF-7, CB-3, CB-4, RNF-7 | T9 | M | pending |
| T11 | `src/dashboard/views/quality.py`: tabla con dimension/total/valid/rejected/rejection_rate desde `latest_quality_summary` + grafico `plotly.express.line` del historico de rejection_rate por dimension (consume `quality_summary_history` para cada dimension). Boton "Recargar" | RF-2 | T9 | M | pending |
| T12 | `src/dashboard/views/patients.py`: input "Pagina" + tabla paginada (limit=20) usando `list_patients` con `offset = (pagina-1)*20`. Click en fila / input `external_id` muestra detalle: campos basicos + acordeon admissions (con diagnosis_category) + acordeon radiografias (con classification si la tiene). Boton "Recargar" | RF-3, CB-3 | T9 | M | pending |
| T13 | `src/dashboard/views/classifier.py`: dropdown poblado con `list_radiographies(limit=500, offset=0)` (NO list_patients), texto "Tip" sobre las dummy 1x1, `st.image` con bytes de `image_bytes(key)` (consume RF-8), boton "Clasificar" que llama a `classify(key)`. Manejo separado de: 422 (mostrar mensaje CB-7 + boton sigue habilitado para reintentar con otra), 503 desde `/health` (deshabilitar boton + warning), 404 image (mensaje CB-5), success (mostrar clase + barras horizontales de probabilidades + model_version + predicted_at). Boton "Recargar" del dropdown | RF-4, CB-4, CB-5, CB-7 | T9 | M | pending |
| T14 | `src/dashboard/views/runs.py`: tabla paginada (limit=20) con `list_runs`, columnas started_at / trigger_type / status (badge color por status) / records_processed / records_rejected / error_message (truncado a 100 chars, expandible con `st.expander` si hay error). Boton "Recargar" | RF-5, CB-3 | T9 | S | pending |
| T15 | Smoke E2E real con stack vivo: `docker compose down -v && docker compose up -d`. Esperar a que `dashboard` este healthy. Abrir `http://localhost:8501` en navegador y validar manualmente las 5 vistas: (1) Overview muestra counts + ultimo run + evaluation con metricas reales del modelo entrenado; (2) Quality muestra rejection_rate; (3) Patients pagina y detalle de HOSP-000001 funciona; (4) Classifier: subir/elegir una radiografia real (no dummy) y verificar prediccion + probabilidades, luego elegir una dummy y verificar mensaje CB-7; (5) Runs muestra el run del bootstrap. Smoke contra CB-1: `docker compose stop api` y verificar que el dashboard muestra "API no disponible" en cada vista sin crashear. Volver a `docker compose start api`. Opcionalmente test `tests/e2e/test_dashboard_smoke.py` con `httpx.get("http://localhost:8501/_stcore/health")` | CA-1..CA-11 | T1, T2, T3, T10, T11, T12, T13, T14 | S | pending |
| T16 | Documentacion viva: `CHANGELOG.md` entrada Added (dashboard + 2 endpoints nuevos); `README.md` (tabla stack con Streamlit, nueva URL `http://localhost:8501`, mencion al puerto 8501 en "Requisitos previos", actualizar conteo de tests si hay nuevos); `docs/diario-ia.md` sesion nueva; `tasks/lessons.md` con lo aprendido del dashboard (st.cache_data, st.fragment, evaluacion vs predictor_loaded, etc); `tasks/backlog.md` feature 4 a `done`; `tasks/dashboard.md` marcar T1-T16 como `done` | — | T15 | S | pending |

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
  pillow==10.3.0
  ```
- **Verificacion local (opcional):** `pip install -r requirements-dashboard.txt` en un venv limpio funciona. Validacion real en T5 (rebuild Docker)

### T5: `Dockerfile.dashboard` + servicio compose
- Crear `Dockerfile.dashboard`:
  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  COPY requirements-dashboard.txt .
  RUN pip install --no-cache-dir -r requirements-dashboard.txt
  COPY src/dashboard/ ./src/dashboard/
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
      ("unavailable", None): "El modelo de clasificacion no esta cargado en este despliegue.",
      ("validation", "/classify"): "Imagen demasiado pequena o invalida. Usa una radiografia real de >= 32x32 px.",
      ...
  }
  def format_error(err: ApiError, context: str = "") -> str: ...
  def show_api_error(err: ApiError, context: str = "") -> None:
      st.error(format_error(err, context))
  ```
- `src/dashboard/components/cards.py`:
  ```python
  def metric_card(label: str, value: str, color: str = "gray") -> None:
      st.metric(label=label, value=value)  # plus optional color styling
  ```
- Tests `tests/dashboard/test_error_banner.py`: validar `format_error` (texto) sin invocar Streamlit

### T9: Entrypoint
- `src/dashboard/app.py`:
  ```python
  import streamlit as st
  from src.dashboard.api_client import ApiClient
  from src.dashboard.config import API_BASE_URL, API_TIMEOUT_SECONDS

  st.set_page_config(page_title="Hospital laSalle", layout="wide")

  if "api_client" not in st.session_state:
      st.session_state["api_client"] = ApiClient(API_BASE_URL, API_TIMEOUT_SECONDS)

  pages = [
      st.Page("views/overview.py", title="Overview", default=True),
      st.Page("views/quality.py", title="Calidad de datos"),
      st.Page("views/patients.py", title="Pacientes"),
      st.Page("views/classifier.py", title="Clasificador"),
      st.Page("views/runs.py", title="Pipeline runs"),
  ]
  st.navigation(pages).run()
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
- Sub-seccion "Evaluacion del modelo":
  - Llamar `model_evaluation()`. Si error: mostrar "Reporte no disponible"
  - Si OK: accuracy y macro-F1 grandes, tabla recall por clase, heatmap con plotly:
    ```python
    import plotly.express as px
    fig = px.imshow(
        cm_array, x=classes, y=classes, text_auto=True,
        labels={"x": "Predicha", "y": "Real"}, color_continuous_scale="Blues",
    )
    st.plotly_chart(fig, use_container_width=True)
    ```
- Auto-refresh: el bloque de cards + ultimo run dentro de `@st.fragment(run_every=30)`
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
- `st.selectbox("Radiografia", keys)`
- `st.caption("Tip: las 17 radiografias dummy del bootstrap son 1x1 y se rechazaran. Usa una real (>=32px)")`
- `image_bytes(key)` → `st.image(bytes, use_column_width=True)`
- Si `health.predictor_loaded == False`: warning + boton deshabilitado
- Boton "Clasificar" → `classify(key)`:
  - 200: pintar barras horizontales de probabilidades (plotly), badge clase, model_version
  - 422 (CB-7): `show_api_error(err, context="/classify")` con mensaje "Imagen demasiado pequena o invalida..." + boton SIGUE habilitado
  - 503: cubrirlo aun antes con el check de health
  - 404: "Imagen no encontrada en MinIO"

### T14: `views/runs.py`
- `list_runs(limit=20, offset=0)` → tabla
- Color de status (custom CSS o emoji ASCII tipo `[OK]` / `[FAIL]`)
- Para los failed, `st.expander("Ver error")` con `error_message`
- Boton "Recargar"

### T15: Smoke real end-to-end
- `docker compose down -v && docker compose up -d`
- Esperar healthchecks (max 60s)
- Validar manualmente las 5 vistas en `http://localhost:8501`
- Probar clasificador con una imagen real del dataset (subir manualmente via T9 del proyecto de clasificacion: `docker compose run pipeline python -c "..."` con upload a `HOSP-DASH-VERIF/sample.png` + insert patient en Mongo)
- Probar con una dummy 1x1 → verificar mensaje CB-7
- `docker compose stop api` → todas las vistas muestran error CB-1 limpiamente
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
- `README.md`: stack con fila Dashboard (Streamlit + Plotly + Pandas, ✓ Implementado); seccion "Acceso al sistema" anadir `http://localhost:8501` para el dashboard; "Requisitos previos" anadir puerto 8501; actualizar conteo de tests
- `docs/diario-ia.md`: sesion nueva (proxima al numero actual) con prompts/decisiones/aciertos/lecciones
- `tasks/lessons.md`: lecciones del dashboard (st.cache_data necesario en cada GET, st.fragment para auto-refresh, predictor_loaded vs metrics.json son senales distintas, etc.)
- `tasks/backlog.md`: feature 4 a `done`
- `tasks/dashboard.md`: marcar T1-T16 como `done`

## Grafo de dependencias

```
T1 (image endpoint) ──────────────┐
T2 (model/evaluation endpoint) ───┤
T3 (verificar /radiographies) ────┤
                                  │
T4 (requirements) ──→ T5 (Docker + compose) ──┐
                                              │
T6 (config) ──┐                               │
              ├──→ T7 (api_client) ──→ T8 (components) ──┐
              │                                          │
              └──────────────────────────────────────────┴──→ T9 (app entrypoint) ──┬──→ T10 (Overview) ──┐
                                                                                    ├──→ T11 (Quality) ───┤
                                                                                    ├──→ T12 (Patients) ──┤
                                                                                    ├──→ T13 (Classifier) ┤
                                                                                    └──→ T14 (Runs) ──────┤
                                                                                                          │
T1, T2, T3 ───────────────────────────────────────────────────────────────────────────────────────────────┤
                                                                                                          ▼
                                                                                                  T15 (smoke real)
                                                                                                          │
                                                                                                          ▼
                                                                                                  T16 (docs)
```

## Ruta critica

**T4 → T5 → T7 → T9 → T13 → T15 → T16**

T13 (Clasificador) es la vista mas compleja porque integra dropdown +
imagen + clasificar + 3 casos de error (CB-4, CB-5, CB-7). Si va mal,
arrastra el smoke (T15).

## Paralelizable

- **T1, T2, T3** (endpoints/verificaciones API) entre si. Todos sin
  dependencias previas. Se pueden lanzar a la vez al inicio
- **T4, T6** entre si (independientes)
- **T10-T14** (las 5 vistas) entre si una vez T9 hecho. Si fuera
  trabajo a varias manos, una vista por persona. En esta sesion las
  hago serie por enfoque, T13 al final (la mas compleja)

## Notas de gestion del riesgo

- **T13 (Clasificador) es el riesgo mayor**: integra mas tipos de
  error que el resto. Si CB-7 falla en demo, queda feo. Mitigacion:
  test manual exhaustivo con una imagen real Y una dummy 1x1 antes
  del commit
- **T5 puede fallar por puerto ocupado** (8501 lo usa Streamlit por
  defecto en otros proyectos). Mitigacion: env var `DASHBOARD_PORT`
  documentada en `.env.example`
- **T15 depende de un modelo entrenado real** (`data/models/`
  presente). Ya esta en el repo desde la sesion anterior. Verificar
  antes de empezar el smoke que el container `api` muestra
  `predictor_loaded:true` en `/health`
- **Tiempo total estimado:** 16 tareas, mezcla S+M. En modo enfocado
  ~6-8h. Cabe en 1 dia si T13 no se complica
