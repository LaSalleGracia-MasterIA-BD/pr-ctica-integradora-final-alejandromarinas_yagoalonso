# Tasks: Clasificacion de radiografias de torax (Sana / Neumonia / COVID-19)

> Spec: specs/clasificacion-radiografias.md
> Design: design/clasificacion-radiografias.md

## Tareas

| # | Tarea | Requisitos | Dependencias | Tamano | Estado |
|---|-------|-----------|-------------|--------|--------|
| T1 | Anadir `tensorflow-cpu` + `scikit-learn` (para sklearn.metrics) + `matplotlib` (para PNGs del reporte) a `requirements-pipeline.txt`. Rebuild de la imagen `hospital-pipeline`. Smoke test: `python -c "import tensorflow as tf; print(tf.__version__)"` dentro del contenedor | RNF-1, ADR-006 | — | S | done |
| T2 | Refactor de volumenes en `docker-compose.yml`: descomponer `./data:/app/data:ro` en submontajes especificos (`data/raw:ro` para todos; `data/models:rw` para pipeline, `:ro` para api; `pipeline-db:rw` como hoy). Actualizar `.gitignore`: (a) **excluir el dataset real descargado**: `data/raw/covid_radiography/` (1.5 GB no debe llegar al repo); (b) excepcion `!data/models/*.keras` y `!data/models/*.meta.json` para poder commitear modelos < 50 MB. Crear `data/models/.gitkeep`. **Cuidado** de no romper exclusiones existentes (`data/raw/patients.csv`, `data/raw/admissions.csv`, `data/raw/images/` siguen rastreados — el bloque actual del `.gitignore` ya los preserva) | RNF-4, design "Refactor de volumenes", spec RNF-6 | — | S | done |
| T3 | Runbook del dataset: revisar y actualizar `docs/runbooks/download-radiography-dataset.md` con la URL real, comando de descarga, **estructura real de Kaggle** (cada clase contiene subcarpetas `images/` y `masks/`; usamos SOLO `images/`): `data/raw/covid_radiography/COVID-19_Radiography_Dataset/{COVID,Normal,Viral Pneumonia,Lung_Opacity}/images/*.png`. Notas explicitas: `Lung_Opacity` se descarta, `masks/` se ignora. Documentar tamano (~1.5 GB), tiempo de descarga. Descargar el dataset una vez (manual, fuera del contenedor) y verificar la estructura en disco | CB-1, RF-3 | — | S | done (descarga pendiente del usuario) |
| T4 | `src/ml/dataset.py`: `discover_dataset()` que itera carpetas Kaggle **con la estructura real `{class}/images/*.png`** (ignora `{class}/masks/` y cualquier otra subcarpeta), mapea `COVID→COVID-19`, `Normal→Normal`, `Viral Pneumonia→Pneumonia` y **descarta `Lung_Opacity`**; `DatasetNotFoundError` con referencia al runbook si falta la raiz o si una clase esperada no tiene `images/`; `build_splits(items, seed=42, ratios=(0.8, 0.1, 0.1))` estratificado por clase. Tests unitarios con fixture de directorios temporales reproduciendo la estructura `{class}/images/*.png` (sin imagenes reales, solo paths) | RF-3, CB-1 | T2 | M | done |
| T5 | `src/ml/preprocessing.py`: constantes `IMAGE_SIZE=(224,224)` y `CLASSES`; `preprocess_for_inference(image_bytes) -> np.ndarray (224,224,1) float32 [0,1]`; `InvalidImageError` para CB-3/CB-7 (formato invalido, < 32 px); `build_training_pipeline(items, batch_size, augment=bool) -> tf.data.Dataset` con augmentation moderada (rotacion ±10°, zoom ±10%, brillo ±10%) y **sin horizontal flip**. Tests: shape/dtype/range de salida, rechazo de imagenes pequenas, rechazo de bytes no-PNG, ausencia de flip horizontal | CB-3, CB-7, RNF-3 | T1 | M | done |
| T6 | `src/ml/model.py`: `build_model(num_classes=3, input_shape=(224,224,1))` con la arquitectura del design (4 Conv2D `padding="same"` + MaxPool, Dropout(0.5), Flatten, Dense(64,relu), Dropout(0.3), Dense(3,softmax)). Compile con Adam(lr=1e-3) + `sparse_categorical_crossentropy` + accuracy. Tests smoke: build + forward con tensor dummy (1,224,224,1), conteo de parametros razonable (~1.8M ± 5%), shapes intermedios cuadran (14x14x128 antes de Flatten) | RNF-1, RNF-3, RNF-4 | T1 | S | done |
| T7 | `src/ml/evaluate.py`: `generate_report(model, test_dataset, output_dir, history)` que produce `metrics.json` (accuracy, macro_f1, per_class precision/recall/f1, confusion_matrix, hiperparametros), `confusion_matrix.png` (heatmap), `learning_curves.png` (loss+acc por epoch desde `history`), y `report.md` con estructura del design (resumen + matriz + **analisis clinico CA-3** + hiperparametros + limitaciones). Tests con modelo dummy y dataset tiny | RF-2, RNF-2, CA-2, CA-3, CA-4 | T4, T5, T6 | M | done |
| T8 | `src/ml/train.py` CLI: set seeds + `enable_op_determinism`; descubrir dataset, splits train/val/test; `compute_class_weight` sobre train; build pipelines (augment solo en train); compile + callbacks (EarlyStopping/ModelCheckpoint sobre `val_loss`, CSVLogger); `fit(train, validation_data=val, class_weight=...)`; al final llama a `generate_report(model, test_dataset, history)` — **metricas sobre test, val solo durante entrenamiento**; guarda artefacto `data/models/radiography_classifier.keras` + `radiography_classifier.meta.json`. Test funcional con dataset tiny (10 imagenes/clase, 2 epochs): produce los artefactos esperados, formatos correctos | RF-1, RF-3, CB-6, RNF-5 | T4, T5, T6, T7 | M | done |
| T9 | **Entrenamiento real sobre el dataset completo** ejecutando `docker compose run --rm pipeline python -m src.ml.train`. Validar: (a) el modelo entrenado pesa < 50 MB; (b) `metrics.json` muestra accuracy razonable y recall COVID/Pneumonia >= 0.70 (orientativo, no bloqueante); (c) `report.md` se rellena con el analisis clinico. Si el entrenamiento tarda > 3h: contingencia (input 128x128, menos filtros, menos epochs). Commitear modelo + meta + reporte si caben | RF-1, RF-2, CA-1, CA-2, CA-3, CA-4 | T3, T8 | L | done (v3, 35 epochs, 21MB, macro-F1=0.846, recall COVID=0.70) |
| T10 | `src/ml/predictor.py`: clase `Predictor(model_path, meta_path)` que valida al construir (lanza `ModelNotAvailableError` si falta artefacto), expone `predict(image_bytes) -> Prediction` y propiedad `model_version`. **Thread-safety con `threading.Lock`** alrededor de `model.predict` (FastAPI sirve en threadpool). Factory `Predictor.from_env()` que lee `MODEL_PATH` del env con default `data/models/radiography_classifier.keras`. Tests con modelo dummy entrenado al vuelo (2 epochs) + tests de ModelNotAvailableError | RF-4, RF-5, RNF-3, RNF-6 | T5, T6, T8 | M | done |
| T11 | `MongoWriter.set_radiography_classification(minio_object_key, classification) -> bool` (firma SOLO con la key, sin patient_external_id — el endpoint no recibe el paciente). Usa `update_one({"radiographies.minio_object_key": key}, {"$set": {"radiographies.$[r].classification": classification}}, array_filters=[{"r.minio_object_key": key}])` y devuelve `result.matched_count > 0` (NO `modified_count`: si se re-clasifica con resultado identico la operacion es exitosa pero `modified_count==0`). Anadir indice `radiographies.minio_object_key` en `docker/mongo-init/init-db.js`. `MongoReader.get_radiography_classification(minio_object_key)` con aggregation `$unwind` + `$match`. Tests integracion contra MongoDB real (actualizar classification, leer, verificar que otras radiografias no se tocan, idempotencia con el mismo payload no falla) | RF-6, RF-7 | — | M | done |
| T12 | (a) **Anadir `MinIOClient.download_bytes(bucket, key) -> bytes`** al cliente existente — hoy solo hay `download_file(path)`, que requiere fichero temporal en disco; el endpoint necesita los bytes en memoria. Lanza la misma excepcion de MinIO si la key no existe (la atrapa el router → 404). Tests basicos: descarga bytes de un objeto, lanza error en key inexistente. (b) Endpoints en `src/api/routers/classify.py`: `POST /api/v1/radiographies/classify` con body `ClassifyRequest{minio_object_key}` y respuesta `ClassificationResponse`; `GET /api/v1/radiographies/classification?key=...` con respuesta misma estructura. Manejo de 200/404 (MinIO o Mongo)/422 (key vacia, imagen corrupta, < 32px)/503 (modelo no cargado). Pydantic models en `src/api/models.py`: `ClassifyRequest`, `ClassificationResponse`, `RadiographyClassification` (este reutilizado en `Radiography.classification` — ver T13). Tests con TestClient y predictor mock (200, 404 Mongo, 404 MinIO, 422 imagen corrupta, 503 sin modelo) | RF-4, RF-5, RF-6, CB-2, CB-3, CB-4, CB-7 | T10, T11 | M | done |
| T13 | Wire del Predictor en la app: `src/api/main.py` carga `Predictor.from_env()` en `build_app` (try/except → `app.state.predictor=None` si falla). Anadir `app.state.mongo_writer` y `app.state.minio_client` en lifespan (cierre en shutdown). Registrar el router de classify. **Actualizar `src/api/models.py`:** `Radiography.classification` pasa de `str | None` a `RadiographyClassification | None` (objeto con `predicted_class`, `probabilities`, `predicted_at`, `model_version`). Tambien anadir `predictor_loaded: bool` a `HealthResponse` y rellenarlo en el handler `/health`. Tests del lifespan: predictor None si modelo no existe; predictor cargado si si. Tests del modelo Pydantic Radiography: serializa/deserializa el objeto classification correctamente y acepta None | RF-4, RF-7, CB-4 | T12 | S | done |
| T14 | Test E2E `tests/e2e/test_classification_e2e.py` con **fixture valido >= 32 px** (NO usar las 17 PNGs dummy 1x1 del bootstrap): si existe `/app/data/raw/covid_radiography/`, copiar una imagen real al bucket MinIO; si no, generar PNG 64x64 grayscale valido al vuelo. Flujo: subir imagen → POST /classify → verificar 200 + persistencia en Mongo → GET /classification → verificar misma estructura. Cleanup tras el test (eliminar imagen del bucket + clasificacion del Mongo). **Skip limpio** si `GET /health` devuelve `predictor_loaded=False` (campo del HealthResponse anadido en T13) | RF-5, RF-6, RF-7, CA-5, CA-6 | T13 | M | done |
| T15 | Verificacion end-to-end real con `docker compose down -v && docker compose up`: comprobar que la API levanta cargando el modelo (log "Predictor cargado"); curl a `POST /classify` con una key real (de las 17 dummy NO porque CB-7 las rechaza — usar una real del dataset previamente copiada a `data/raw/images/` y al bucket); verificar persistencia en Mongo; reiniciar API sin `-v` y volver a hacer GET para validar persistencia. Smoke contra CB-4: arrancar API sin modelo (mover artefacto temporalmente) y comprobar 503 limpio | CA-5, CA-6, CA-7, RF-3 | T13, T9 | S | done (3/3 imagenes reales clasificadas correctamente con confianzas 0.91/0.97/1.00, latencia <100ms; 404/422 cubiertos) |
| T16 | Documentacion viva: CHANGELOG entrada en `Added` con resumen del modelo + endpoints + metricas finales; README incorporar curl de los nuevos endpoints + tabla de stack actualizada (TF/Keras); `docs/diario-ia.md` sesion nueva con prompts/decisiones/aciertos/lecciones; `tasks/lessons.md` con lo aprendido (clases desbalanceadas, train-serve skew evitado por preprocesado compartido, padding="same", split usage strict, etc.); `tasks/backlog.md` feature 2 a `done` | — | T15 | S | done |

Tamanos: S (< 1h) | M (1-4h) | L (> 4h, considerar dividir)
Estados: pending | in-progress | done | blocked

## Detalle por tarea

### T1: TensorFlow + dependencias ML en la imagen
- `requirements-pipeline.txt`: anadir
  - `tensorflow-cpu==2.16.x` (NO la variante con CUDA, ADR-006)
  - `scikit-learn==1.5.x` (para `sklearn.metrics.confusion_matrix`, `classification_report`, `compute_class_weight`)
  - `matplotlib==3.9.x` (para los PNGs del reporte)
- **Verificacion:** `docker compose build pipeline && docker compose run --rm --entrypoint "" pipeline python -c "import tensorflow as tf; import sklearn; import matplotlib; print(tf.__version__, sklearn.__version__, matplotlib.__version__)"`

### T2: Refactor de volumenes Docker
- `docker-compose.yml`:
  - `pipeline.volumes`:
    ```
    - ./data/raw:/app/data/raw:ro
    - ./data/models:/app/data/models:rw   # train escribe aqui
    - pipeline-db:/app/data/db:rw
    ```
  - `api.volumes`:
    ```
    - ./data/raw:/app/data/raw:ro
    - ./data/models:/app/data/models:ro   # API solo lee
    - pipeline-db:/app/data/db:rw
    ```
  - `watcher.volumes`: sin cambios (sigue con incoming + db)
- `.gitignore`:
  - **Excluir el dataset descargado (~1.5 GB) — NO debe llegar al repo:**
    ```
    # Dataset COVID-19 Radiography (Kaggle, ~1.5 GB). Se descarga manualmente
    # via docs/runbooks/download-radiography-dataset.md. No tocar a mano.
    data/raw/covid_radiography/
    ```
  - **Excepciones para modelos commiteables (< 50 MB) bajo
    `data/models/*` que hoy esta ignorado:**
    ```
    !data/models/*.keras
    !data/models/*.meta.json
    ```
  - **No romper rastreos existentes** (`data/raw/patients.csv`,
    `data/raw/admissions.csv`, `data/raw/images/*.png`,
    `data/processed/.gitkeep`, `data/models/.gitkeep`): el bloque de
    `data/raw/covid_radiography/` es especifico y no afecta a esos
    paths
- Crear `data/models/.gitkeep` si no existe
- **Verificacion del `.gitignore`** con `git check-ignore -v`:
  - `data/raw/covid_radiography/COVID/images/foo.png` → ignored
  - `data/raw/patients.csv` → NO ignored
  - `data/raw/images/HOSP-000001_xray1.png` → NO ignored
  - `data/models/radiography_classifier.keras` → NO ignored (excepcion)
  - `data/models/.gitkeep` → NO ignored
- **Verificacion:** `docker compose up -d` sin errores; `docker exec hospital-pipeline ls /app/data/models/` muestra el directorio vacio (ademas del .gitkeep)

### T3: Runbook del dataset
- Revisar `docs/runbooks/download-radiography-dataset.md`:
  - URL oficial de Kaggle: `https://www.kaggle.com/datasets/tawsifurrahman/covid19-radiography-database`
  - Comando recomendado: `kaggle datasets download -d tawsifurrahman/covid19-radiography-database` (requiere `kaggle.json` configurado) o descarga manual via web
  - **Estructura real de Kaggle tras descomprimir** (importante: cada
    clase contiene `images/` y `masks/`; usamos solo `images/`):
    ```
    data/raw/covid_radiography/
    └── COVID-19_Radiography_Dataset/
        ├── COVID/
        │   ├── images/        # ← usamos
        │   │   ├── COVID-1.png
        │   │   └── ...
        │   └── masks/         # ← ignorado
        ├── Normal/
        │   ├── images/
        │   └── masks/
        ├── Viral Pneumonia/
        │   ├── images/
        │   └── masks/
        └── Lung_Opacity/      # ← descartada (no encaja en triple)
            ├── images/
            └── masks/
    ```
  - Notas: tamano ~1.5 GB descomprimido; `Lung_Opacity` se descarta;
    `masks/` se ignora (son mascaras de segmentacion, no necesarias
    para clasificacion)
- **Variable de configuracion:**
  - `DATASET_PATH` (env) con default
    `/app/data/raw/covid_radiography/COVID-19_Radiography_Dataset`
- **Verificacion manual:** Alejandro descarga el dataset, lo descomprime
  en `data/raw/covid_radiography/`, ejecuta `find data/raw/covid_radiography -maxdepth 4 -name "images" -type d`
  y confirma 4 carpetas `images/` (COVID, Normal, Viral Pneumonia,
  Lung_Opacity)

### T4: `src/ml/dataset.py`
- `CLASS_MAP = {"COVID": "COVID-19", "Normal": "Normal", "Viral Pneumonia": "Pneumonia"}` (Lung_Opacity NO listado)
- `CLASSES = ["Normal", "Pneumonia", "COVID-19"]` (orden fijo para indices del modelo)
- `discover_dataset(root: Path | None = None) -> list[tuple[Path, str]]`:
  - Si `root is None`, usar env `DATASET_PATH` con default
    `/app/data/raw/covid_radiography/COVID-19_Radiography_Dataset`
  - Si la raiz no existe → `DatasetNotFoundError("...consulta docs/runbooks/...")`
  - Por cada subcarpeta de la raiz:
    - Si no esta en `CLASS_MAP` → ignorar con log info (cubre
      `Lung_Opacity` y cualquier otra carpeta)
    - Si esta en `CLASS_MAP` → entrar a su subcarpeta `images/` y
      enumerar `*.png`. Si falta `images/` → `DatasetNotFoundError`
      con instrucciones (probablemente el zip esta mal descomprimido)
  - Devuelve `[(image_path, class_name_mapped)]`
- `@dataclass class Splits: train, val, test  # list[tuple[Path, str]]`
- `build_splits(items, seed=42, ratios=(0.8,0.1,0.1)) -> Splits`:
  - Estratificado por clase (mismo % por clase en cada split)
  - Si el dataset trae split oficial (carpeta `train/`/`val/`/`test/`
    a la altura de la raiz) → branch `_use_official_split` (no es el
    caso de la version actual de Kaggle, pero queda preparado)
- Tests `tests/ml/test_dataset.py`:
  - `test_discover_skips_lung_opacity`
  - `test_discover_maps_class_names_correctly`
  - `test_discover_walks_into_images_subdir_and_ignores_masks`
  - `test_discover_raises_dataset_not_found_if_root_missing`
  - `test_discover_raises_dataset_not_found_if_images_subdir_missing`
  - `test_build_splits_is_stratified` (ratios por clase en cada split similares)
  - `test_build_splits_is_deterministic_with_seed`
  - Fixtures: directorios temporales reproduciendo
    `{class}/images/*.png` + `{class}/masks/*.png` con ficheros vacios
    (no hace falta PNG real para listar paths)

### T5: `src/ml/preprocessing.py`
- Constantes:
  - `IMAGE_SIZE = (224, 224)`
  - `MIN_IMAGE_DIM = 32`  # CB-7
  - `class InvalidImageError(Exception): pass`
- `preprocess_for_inference(image_bytes: bytes) -> np.ndarray`:
  1. Abrir con PIL desde BytesIO; capturar `UnidentifiedImageError` → `InvalidImageError`
  2. Validar dimensiones >= `MIN_IMAGE_DIM` por lado → `InvalidImageError`
  3. Convertir a grayscale (`'L'`)
  4. Resize a `IMAGE_SIZE` (resampling `BILINEAR`)
  5. `np.asarray(...)` a float32, normalizar `/255.0`, reshape a `(224, 224, 1)`
- `build_training_pipeline(items, batch_size=32, augment=True) -> tf.data.Dataset`:
  - Mapping `class_name → int` via `CLASSES.index(...)`
  - `tf.data.Dataset.from_generator` con worker que abre el path con PIL y aplica `preprocess_for_inference`-equivalente
  - Si `augment=True`: `tf.keras.layers.RandomRotation(10/360)`, `RandomZoom(0.1)`, `RandomBrightness(0.1)`. **NO `RandomFlip("horizontal")`**
  - Batching + prefetch
- Tests `tests/ml/test_preprocessing.py`:
  - `test_preprocess_returns_correct_shape_dtype_range`
  - `test_preprocess_rejects_image_too_small`
  - `test_preprocess_rejects_non_png_garbage_bytes`
  - `test_preprocess_grayscale_conversion`  # imagen RGB de entrada → salida 1-canal
  - `test_training_pipeline_does_not_use_horizontal_flip` (inspeccion de la capa de aug)

### T6: `src/ml/model.py`
- `build_model(num_classes=3, input_shape=(224, 224, 1)) -> keras.Model`:
  - `Sequential` con la arquitectura literal del design:
    - 4x `(Conv2D(filters, 3, padding="same", activation="relu") + MaxPooling2D(2))`
      donde filters = [32, 64, 128, 128]
    - `Dropout(0.5)`
    - `Flatten()`
    - `Dense(64, activation="relu")`
    - `Dropout(0.3)`
    - `Dense(num_classes, activation="softmax")`
  - Compile: `optimizer="adam"` (lr=1e-3), `loss="sparse_categorical_crossentropy"`, `metrics=["accuracy"]`
- Tests `tests/ml/test_model.py`:
  - `test_build_model_returns_compiled_keras_model`
  - `test_forward_pass_with_dummy_input_returns_softmax_3_classes`  # shape (B, 3), suma ≈ 1 por fila
  - `test_intermediate_shapes_match_design`  # 224→112→56→28→14 verificado via model.summary()
  - `test_param_count_is_in_expected_range`  # 1.5M < params < 2.5M

### T7: `src/ml/evaluate.py`
- `generate_report(model, test_dataset, output_dir, history, hyperparams) -> Report`:
  - Inferencia sobre todo `test_dataset`, recolectar y_true / y_pred
  - Calcular:
    - accuracy global
    - macro-F1
    - per-class precision/recall/F1 (sklearn `classification_report`)
    - confusion matrix
  - Escribir:
    - `metrics.json` (estructurado, schema del design)
    - `confusion_matrix.png` (heatmap matplotlib)
    - `learning_curves.png` (loss + acc desde `history`)
    - `report.md` (markdown legible con estructura del design — resumen, matriz, **analisis clinico**, hiperparametros, limitaciones)
- **Plantilla del analisis clinico (CA-3):** el reporte incluye un parrafo redactado pre-experimento (basado en la hipotesis de la spec, anexo "Criterios clinicos"), que se ajusta segun los numeros reales tras T9. El parrafo NO depende del entrenamiento para existir como estructura
- Tests `tests/ml/test_evaluate.py`:
  - `test_generate_report_produces_all_artifacts`
  - `test_metrics_json_includes_per_class_recall_and_confusion_matrix`
  - `test_report_md_contains_clinical_analysis_section`

### T8: `src/ml/train.py` CLI
- Set seeds: `os.environ["PYTHONHASHSEED"]="42"`, `random.seed(42)`, `np.random.seed(42)`, `tf.random.set_seed(42)`, `tf.config.experimental.enable_op_determinism()` (con try/except si no esta disponible)
- Flujo seguir literalmente el "Flujo" del componente `train.py` del design (8 pasos)
- Hiperparametros por defecto (configurables por env o CLI args):
  - `EPOCHS_MAX=50`
  - `BATCH_SIZE=32`
  - `LEARNING_RATE=1e-3` (compile)
  - `SEED=42`
- Guardado:
  - Modelo: `data/models/radiography_classifier.keras`
  - Meta: `data/models/radiography_classifier.meta.json` (con los campos del design)
- **Regla estricta del uso de splits** documentada como comentario al inicio del script: `train→fit`, `val→callbacks only`, `test→generate_report only`
- Tests `tests/ml/test_train.py`:
  - `test_train_end_to_end_with_tiny_dataset` (3 clases × 10 imagenes, 2 epochs): produce los artefactos esperados y el reporte tiene la estructura correcta. **No verifica accuracy** (con 10 imagenes no tiene sentido)
  - `test_train_is_deterministic_with_same_seed` (dos runs → mismo loss final dentro de tolerancia)

### T9: Entrenamiento real
- **Pre-requisito:** dataset descargado en `data/raw/covid_radiography/...` (T3)
- Comando: `docker compose run --rm pipeline python -m src.ml.train`
- Tiempo estimado: 1-3 horas en CPU (5-10 min/epoch × ~15-25 epochs efectivos con EarlyStopping)
- **Plan de contingencia si tarda > 3h o el recall COVID/Pneumonia es inaceptable:**
  - Input shape 128x128 (mas rapido, modelo mas pequeno)
  - `epochs_max=30` (en vez de 50)
  - filters = [16, 32, 64, 64] (modelo mas pequeno)
  - Revisar `class_weight` calculado y ajustar si esta sesgado
- **Validar tras el entrenamiento:**
  - `ls -lh data/models/radiography_classifier.keras` → tamano (objetivo < 50 MB)
  - `cat data/models/radiography_classifier.meta.json | jq .metrics`
  - `cat docs/model-evaluation/report.md` → analisis clinico tiene sentido
  - `open docs/model-evaluation/confusion_matrix.png` → revisar visualmente
- **Si el modelo cabe (<50MB):** commitear `radiography_classifier.keras`, `.meta.json` y `docs/model-evaluation/*` al repo
- **Si no cabe:** solo commitear `.meta.json` + reporte; documentar en CHANGELOG/README como regenerar

### T10: `src/ml/predictor.py`
- `@dataclass class Prediction: predicted_class: str; probabilities: dict[str, float]; model_version: str`
- `class ModelNotAvailableError(Exception): pass`
- `class Predictor`:
  - `__init__(self, model_path: Path, meta_path: Path)`:
    - Si no existen → `ModelNotAvailableError(...)`
    - `self._model = keras.models.load_model(model_path)`
    - `self._meta = json.loads(meta_path.read_text())`
    - `self._classes = self._meta["classes"]`
    - `self._lock = threading.Lock()`
  - `predict(self, image_bytes: bytes) -> Prediction`:
    - `x = preprocess_for_inference(image_bytes)`  # puede lanzar InvalidImageError → propagar
    - `with self._lock: probs = self._model.predict(x[None, ...], verbose=0)[0]`
    - Devolver `Prediction(predicted_class=classes[argmax], probabilities={c: float(p) for c,p in zip(classes, probs)}, model_version=meta["model_version"])`
  - `model_version` property
- `Predictor.from_env() -> Predictor`: lee `MODEL_PATH` con default `data/models/radiography_classifier.keras`
- Tests `tests/ml/test_predictor.py`:
  - `test_predictor_raises_model_not_available_if_missing`
  - `test_predict_returns_correct_structure` (con modelo dummy entrenado al vuelo sobre datos sinteticos)
  - `test_predict_propagates_invalid_image_error`
  - `test_predict_is_thread_safe` (concurrencia con `concurrent.futures.ThreadPoolExecutor`)

### T11: MongoDB writer + reader + indice
- `MongoWriter.set_radiography_classification(minio_object_key: str, classification: dict) -> bool`:
  - **Firma solo con la key** — el endpoint POST recibe la key en el
    body, no el paciente. Pedir `patient_external_id` obligaria al
    router a buscarlo antes con un query extra
  - `update_one({"radiographies.minio_object_key": minio_object_key}, {"$set": {"radiographies.$[r].classification": classification}}, array_filters=[{"r.minio_object_key": minio_object_key}])`
  - Devuelve **`result.matched_count > 0`**, NO `modified_count`. Si
    se re-clasifica una radiografia con el mismo `predicted_class` y
    las mismas `probabilities`, Mongo NO modifica el documento (porque
    el contenido del `$set` es identico al actual) y `modified_count`
    es 0 aunque la operacion sea exitosa. `matched_count` distingue
    "no encontre la key" (devolver False → 404) de "encontre y aplique
    aunque ya estuviera identico" (devolver True → 200)
- `MongoReader.get_radiography_classification(minio_object_key) -> dict | None`:
  - Aggregation: `$unwind` sobre `radiographies` → `$match` por
    `minio_object_key` → `$project` `classification`
  - None si no se encuentra o si `classification is None`
- Anadir a `docker/mongo-init/init-db.js`:
  ```javascript
  db.patients.createIndex({"radiographies.minio_object_key": 1});
  ```
- Tests `tests/pipeline/test_mongo_writer.py` (extendido):
  - `test_set_classification_updates_specific_radiography_without_touching_others`
  - `test_set_classification_returns_false_for_unknown_key`
  - `test_set_classification_is_idempotent_returns_true_on_identical_payload`
    (verifica que matched_count > 0 funciona; con modified_count fallaria)
  - `test_set_classification_overwrites_previous_classification`
- Tests `tests/api/test_mongo_reader.py` (nuevo o extendido):
  - `test_get_classification_returns_persisted_object`
  - `test_get_classification_returns_none_when_not_classified`
  - `test_get_classification_returns_none_for_missing_key`

### T12: API endpoints
- `src/pipeline/storage/minio_client.py` (modificado): anadir
  ```
  def download_bytes(self, bucket: str, key: str) -> bytes
  ```
  - Usa el cliente minio internamente para leer el objeto entero en
    memoria (vs `download_file` que escribe a disco)
  - Propaga `S3Error` (NoSuchKey, etc.) sin envolver, lo atrapa el
    router → 404
  - Tests `tests/pipeline/test_minio_client.py` (extendido):
    `test_download_bytes_returns_uploaded_content`, `test_download_bytes_raises_on_missing_key`
- `src/api/models.py`:
  - `class RadiographyClassification(BaseModel)`: campos
    `predicted_class: str`, `probabilities: dict[str, float]`,
    `predicted_at: datetime`, `model_version: str`. **Reutilizada**
    en `Radiography.classification` (T13) y como base de
    `ClassificationResponse`
  - `class ClassifyRequest(BaseModel)`:
    `minio_object_key: str = Field(min_length=1)`
  - `class ClassificationResponse(RadiographyClassification)` con
    campo extra `minio_object_key: str` (o composicion equivalente)
- `src/api/routers/classify.py`:
  - `POST /api/v1/radiographies/classify`:
    - 503 si `app.state.predictor is None`
    - 404 si `minio_client.exists(...)` False (CB-2)
    - Descargar bytes con `minio_client.download_bytes(bucket, key)`, llamar `predictor.predict(bytes)` (puede lanzar `InvalidImageError` → 422)
    - Construir payload con `predicted_at = datetime.now(UTC)`
    - Llamar `mongo_writer.set_radiography_classification(key, classification_payload)` (firma con key, sin paciente — ver T11). Si devuelve False (la key no aparece en ningun `radiographies[]` de Mongo), tambien 404
    - Devolver 200 con `ClassificationResponse`
  - `GET /api/v1/radiographies/classification?key=...`:
    - `key: str = Query(..., min_length=1)` → 422 si vacio
    - `mongo_reader.get_radiography_classification(key)` → 404 si None
    - 200 con `ClassificationResponse`
- Tests `tests/api/test_classify_endpoint.py`:
  - `test_post_classify_returns_503_without_model`
  - `test_post_classify_returns_404_when_image_not_in_minio`
  - `test_post_classify_returns_422_for_corrupt_image`
  - `test_post_classify_returns_422_for_image_too_small`
  - `test_post_classify_returns_200_and_persists` (con predictor mock + minio mock + mongo real)
  - `test_get_classification_returns_persisted` (200) y `_returns_404` (sin classification)
  - `test_get_classification_returns_422_for_missing_key`

### T13: Wire en la app + ajustes Pydantic
- `src/api/main.py`:
  - En `build_app`, tras crear los readers:
    ```python
    try:
        predictor = Predictor.from_env()
        logger.info("Predictor cargado: %s", predictor.model_version)
    except ModelNotAvailableError as e:
        logger.warning("Predictor no disponible: %s", e)
        predictor = None
    ```
  - `app.state.predictor = predictor`
  - `app.state.mongo_writer = get_mongo_writer_from_env()`
  - `app.state.minio_client = get_minio_client_from_env()`
  - Lifespan: cerrar `mongo_writer` y `minio_client` al shutdown
  - `app.include_router(classify_router.router)`
  - Handler `/api/v1/health` actualizado para rellenar el campo nuevo:
    ```python
    return HealthResponse(
        status="ok",
        version=API_VERSION,
        predictor_loaded=request.app.state.predictor is not None,
    )
    ```
- `src/api/models.py`:
  - `HealthResponse` gana `predictor_loaded: bool` (sin default — debe
    estar siempre presente para que los clientes puedan confiar en el
    campo)
  - `Radiography.classification` pasa de `str | None` a
    `RadiographyClassification | None`. Esto es **compatible hacia
    atras** con documentos antiguos donde `classification is None`
    (Pydantic acepta None directamente)
- Tests del lifespan: con `MODEL_PATH` apuntando a un path
  inexistente → `app.state.predictor is None` y `/health` devuelve
  `predictor_loaded=False`; con path valido → predictor cargado y
  `predictor_loaded=True`
- Test del modelo Pydantic Radiography:
  `test_radiography_serializes_classification_object_correctly`
  (entrada dict con la estructura nueva → Radiography valida)
  y `test_radiography_accepts_null_classification` (compatibilidad
  hacia atras)
- **Cuidado:** al construir el `mongo_writer` en la API, tener en
  cuenta que ahora la API escribe en Mongo (antes solo leia). El test
  del CQRS-light se relaja: explicitamente justificado en el
  commit/CHANGELOG

### T14: Test E2E
- `tests/e2e/test_classification_e2e.py`:
  - Fixture `valid_radiography_in_minio`:
    - Si existe `/app/data/raw/covid_radiography/...`, copia una imagen real al bucket con key `e2e-test/HOSP-E2E-001/sample.png`
    - Si no, genera al vuelo un PNG 64x64 grayscale con `PIL.Image.new("L", (64,64))` con un patron simple (no negro puro), lo sube al bucket
    - Cleanup: elimina la key al final
  - Fixture `patient_with_radiography_in_mongo`: inserta un paciente con la radiografia referenciada (sin classification)
  - `test_classify_e2e_full_flow`:
    1. POST `/api/v1/radiographies/classify` con la key → 200
    2. Verificar Mongo: el paciente tiene `classification` con `predicted_class`, `probabilities`, `predicted_at`, `model_version`
    3. GET `/api/v1/radiographies/classification?key=...` → 200, misma estructura
  - **Skip clean** si la API responde `GET /health` con `predictor_loaded=False` (campo nuevo del HealthResponse, ver T13). Asi el test es self-contained y NO necesita inspeccionar el filesystem del host

### T15: Verificacion end-to-end real
- `docker compose down -v && docker compose up -d`
- Esperar a que el bootstrap termine y la API esté healthy
- Verificacion del log de la API: `docker compose logs api | grep "Predictor"` → muestra "Predictor cargado: vX.Y-..."
- Curl manual:
  ```
  # 1. Subir una radiografia real al bucket via mc o via re-bootstrap
  # 2. POST /classify
  curl -X POST http://localhost:8000/api/v1/radiographies/classify \
       -H "Content-Type: application/json" \
       -d '{"minio_object_key": "HOSP-000001/HOSP-000001_xray1.png"}'
  # 3. GET /classification
  curl 'http://localhost:8000/api/v1/radiographies/classification?key=HOSP-000001/HOSP-000001_xray1.png'
  ```
- Reiniciar API sin `-v` y re-hacer GET → debe persistir
- Smoke contra CB-4: detener API, mover artefacto temporalmente (`mv data/models/radiography_classifier.keras data/models/_bak.keras`), `docker compose up api` de nuevo, llamar al endpoint → 503 limpio. Restaurar artefacto
- **Nota:** las 17 dummy del bootstrap NO se prueban porque son 1x1. Para una prueba "fresh start" o se usa una imagen real previamente subida o se sustituye el contenido de `data/raw/images/` por una imagen valida (fuera del alcance de esta tarea, documentado para una futura iteracion)

### T16: Documentacion viva
- `CHANGELOG.md` entrada en `### Added` con:
  - Modelo CNN (Conv2D + MaxPooling2D + Dropout + Flatten + Dense + softmax, padding="same", ~1.8M params, ~7-8 MB)
  - Dataset: COVID-19 Radiography Database (Lung_Opacity descartado)
  - Endpoints: `POST /classify` (body) y `GET /classification?key=...`
  - Reporte: `docs/model-evaluation/report.md` con analisis clinico
  - Metricas alcanzadas (rellenar con numeros reales de T9)
- `README.md`:
  - Stack: añadir fila "Deep Learning: Keras 3 / TensorFlow 2.16" como ✅ Implementado
  - Ejemplos de curl con los nuevos endpoints
  - Tests: actualizar el conteo (168 + N nuevos)
- `docs/diario-ia.md`: sesion nueva (proxima al numero actual) con objetivo, prompts, decisiones, aciertos, lecciones
- `tasks/lessons.md`: anadir entradas sobre:
  - Preprocesado compartido train/serve (evita skew clasico)
  - `padding="same"` para mantener formas predecibles
  - Regla estricta: val solo durante training, test solo en reporte
  - Sin horizontal flip en radiografias
  - Thread-safety de `model.predict` en FastAPI threadpool
- `tasks/backlog.md`: feature 2 a `done`
- `tasks/clasificacion-radiografias.md`: marcar T1-T16 como `done`

## Grafo de dependencias

```
T1 (TF en imagen) ─────┬──→ T5 (preprocessing) ──┬──→ T7 (evaluate) ──┐
                       ├──→ T6 (model)           ├─→                  │
                       │                          │                    │
T2 (volumenes) ────────┴──→ T4 (dataset) ────────┴──→                  ├──→ T8 (train CLI) ──→ T9 (TRAIN REAL) ──┐
                                                                       │                                          │
T3 (descarga dataset) ─────────────────────────────────────────────────┤                                          │
                                                                                                                  ▼
                                                                       ┌──→ T10 (Predictor) ────→ T12 (API endpoints) ──→ T13 (wire) ──→ T14 (E2E) ──┐
                                                                       │                                                                              │
T11 (Mongo writer + reader + indice) ──────────────────────────────────┘                                                                              │
                                                                                                                                                      ▼
                                                                                                                                                 T15 (smoke real)
                                                                                                                                                      │
                                                                                                                                                      ▼
                                                                                                                                                 T16 (docs)
```

## Ruta critica

**T1 → T2 → T6 → T8 → T9 → T10 → T12 → T13 → T14 → T15 → T16**

T9 (entrenamiento real) es la tarea de mayor tamano (L, 1-3h de wallclock).

## Paralelizable

- **T3** (descargar dataset) se puede ejecutar en paralelo con T1, T2, T4, T5, T6, T7, T8. Solo bloquea a T9
- **T11** (MongoWriter + MongoReader + indice) NO depende de nada y se puede hacer en paralelo con todo el bloque ML (T4-T10)
- **T4, T5, T6** son independientes entre si una vez T1+T2 hechos
- **T7** y **T10** dependen ambos de T4+T5+T6, pero son independientes entre si

## Notas de gestion del riesgo

- **T9 es el cuello de botella temporal**. Si se queda corto de tiempo (faltan < 24h para la entrega), recortar epochs/input size segun el plan de contingencia documentado en su detalle
- **T15 depende de T9** (modelo real). Si T9 se retrasa, T14 sigue siendo posible con un modelo dummy entrenado en T8; T15 se reduce a "comprobar 503 cuando no hay modelo" hasta que T9 termine
- **Auditoria opcional con `/auditoria`** tras T13 (antes de T14/T15) si queda tiempo; recomendable para feature critica como esta
