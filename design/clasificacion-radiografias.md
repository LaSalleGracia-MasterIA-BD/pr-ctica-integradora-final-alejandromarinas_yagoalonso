# Design: Clasificacion de radiografias de torax (Sana / Neumonia / COVID-19)

> Spec: specs/clasificacion-radiografias.md

## Decision arquitectonica

Modulo `src/ml/` autocontenido que cubre el ciclo de vida completo del
modelo (dataset → train → evaluate → predict). La API gana un router
nuevo con dos endpoints (`POST /api/v1/radiographies/classify` con la
key en el body, y `GET /api/v1/radiographies/classification?key=...`
con la key como query param) que delega en un `Predictor` instanciado
al arrancar. El modelo entrenado vive en `data/models/` como artefacto
local, con un fichero meta adjunto que la API lee para reportar la
`model_version`.

Decisiones clave (cada una con su justificacion mas abajo y, las dos
mas relevantes, con su propio ADR):

1. **CNN custom (no transfer learning)** — ADR-005. Alineacion con el
   Bloque 6 del Master (Jordi pide construir la red, no reciclar
   pre-entrenadas); modelos mas pequenos; sin dependencia de
   imagenes RGB pre-procesadas como ImageNet
2. **TensorFlow en la imagen compartida `hospital-pipeline`** — ADR-006.
   Una sola imagen para todo el stack (pipeline + api + watcher +
   training) frente a una imagen `ml` separada. Coste: imagen mas
   gorda. Beneficio: simplicidad operativa y entrenamiento dentro del
   mismo compose
3. **Pipeline de preprocesado compartida entre entrenamiento e
   inferencia** — funcion unica `preprocess_for_inference(image_bytes)`
   importada desde ambos lados. Evita "skew" train-serve clasico
4. **Modelo cargado en startup de la API (lifespan)** — `app.state.predictor`
   nulo si falta el artefacto; endpoints comprueban y devuelven 503
   (cubre CB-4)
5. **Refactor de volumenes Docker** — el bind `./data:/app/data:ro` se
   descompone en submontajes con permisos especificos para que
   `train.py` pueda escribir en `data/models/` y la API pueda leerlo
   en ro
6. **Reporte humano + maquina** — `docs/model-evaluation/report.md`
   para el evaluador + `metrics.json` para automatizacion
7. **Persistencia en MongoDB via `arrayFilters`** — actualizar el
   subdocumento de la radiografia identificado por `minio_object_key`
   sin sustituir el array entero

## Trazabilidad spec → componentes

| Requisito | Componente(s) | Archivos |
|-----------|--------------|----------|
| RF-1 (script train reproducible) | `train.py` CLI + `dataset` + `model` + `evaluate` | `src/ml/train.py`, `src/ml/dataset.py`, `src/ml/model.py`, `src/ml/evaluate.py` |
| RF-2 (reporte con metricas + analisis) | `evaluate.generate_report` | `src/ml/evaluate.py`, `docs/model-evaluation/report.md` (output) |
| RF-3 (split oficial o 80/10/10 estratificado) | `dataset.build_splits(seed, stratified=True)` | `src/ml/dataset.py` |
| RF-4 (modelo cargado al arrancar API; 503 si falta) | `Predictor` + lifespan de FastAPI | `src/ml/predictor.py`, `src/api/main.py` |
| RF-5 (POST /radiographies/classify body) | router `classify` | `src/api/routers/classify.py` |
| RF-6 (GET /radiographies/classification?key=...) | router `classify` (mismo) + `MongoReader` | `src/api/routers/classify.py`, `src/api/mongo_reader.py` |
| RF-7 (objeto Mongo con `predicted_class`, `probabilities`, etc.) | `MongoWriter.set_radiography_classification` | `src/pipeline/storage/mongo_writer.py` |
| RF-8 (sin endpoint batch) | — | (negativo) |
| RNF-1 (Keras/TensorFlow) | `model.build_model()` con Conv2D+MaxPool+Dropout+Dense+EarlyStopping | `src/ml/model.py` |
| RNF-2 (sin umbral bloqueante; recall por clase) | `evaluate.generate_report` calcula y destaca recall COVID/Pneumonia | `src/ml/evaluate.py` |
| RNF-3 (<3s por inferencia) | input 224x224 grayscale, modelo <20MB | `src/ml/model.py`, `src/ml/predictor.py` |
| RNF-4 (<50MB modelo, commiteado si cabe) | output `.keras` + `.gitignore` ajustado | `data/models/`, `.gitignore` |
| RNF-5 (reproducibilidad) | seeds + `tf.config.experimental.enable_op_determinism` | `src/ml/train.py` |
| RNF-6 (privacidad) | API no devuelve bytes; solo metadatos | `src/api/routers/classify.py` |
| CB-1 (dataset ausente) | `dataset.discover_dataset` lanza error con instrucciones | `src/ml/dataset.py` |
| CB-2 (imagen ausente en MinIO) | `MinIOClient.download` → handler 404 | `src/api/routers/classify.py` |
| CB-3 (imagen corrupta) | `preprocessing.preprocess_for_inference` lanza `InvalidImageError` → 4xx | `src/ml/preprocessing.py`, `src/api/routers/classify.py` |
| CB-4 (modelo ausente) | `app.state.predictor = None` + 503 | `src/api/main.py`, `src/api/routers/classify.py` |
| CB-5 (concurrencia) | inferencia deterministica + Mongo upsert con arrayFilters | `src/pipeline/storage/mongo_writer.py` |
| CB-6 (clases desbalanceadas) | `class_weight` desde train split | `src/ml/train.py` |
| CB-7 (imagen muy pequena/grande) | umbral en `preprocessing` | `src/ml/preprocessing.py` |

## Componentes

### `src/ml/dataset.py` (nuevo)
- **Responsabilidad:** descubrir el dataset en disco, mapear carpetas
  Kaggle a nuestras 3 clases, generar splits estratificados con seed
  fija
- **Requisitos que cubre:** CB-1, RF-3
- **Interfaz:**
  - `DATASET_ROOT = Path("/app/data/raw/covid_radiography")` (env override)
  - `CLASS_MAP = {"COVID": "COVID-19", "Normal": "Normal", "Viral Pneumonia": "Pneumonia"}`
    — `Lung_Opacity` se descarta porque no encaja en la clasificacion
    triple del proyecto
  - `discover_dataset() -> list[tuple[Path, str]]`: itera carpetas,
    devuelve `[(image_path, class_name)]`. Lanza `DatasetNotFoundError`
    con instrucciones si la ruta no existe
  - `build_splits(items, seed=42, ratios=(0.8, 0.1, 0.1)) -> Splits`:
    estratificado por clase
- **Notas:** si en una futura version del dataset hay split oficial,
  se anade rama `if (DATASET_ROOT / "train").exists(): use_official_split()`

### `src/ml/preprocessing.py` (nuevo)
- **Responsabilidad:** convertir bytes/imagen a tensor listo para el
  modelo. **Misma funcion usada en entrenamiento e inferencia** —
  contrato unico, evita skew train-serve
- **Requisitos que cubre:** CB-3, CB-7, RNF-3
- **Interfaz:**
  - `IMAGE_SIZE = (224, 224)` (constante)
  - `preprocess_for_inference(image_bytes: bytes) -> np.ndarray` shape
    `(224, 224, 1)`, dtype float32, valores en [0, 1]
  - `build_training_pipeline(items, batch_size, augment=True) -> tf.data.Dataset`
    — usa `preprocess_for_inference` internamente + augmentation
  - `class InvalidImageError(Exception)`: se levanta para imagenes
    corruptas, formato no soportado, o dimensiones < 32 px por lado
- **Augmentation (solo en training):** rotacion ±10°, zoom ±10%,
  brillo ±10%. **No horizontal flip**: invertiria izq/dch en una
  radiografia, lo cual cambia el significado anatomico

### `src/ml/model.py` (nuevo)
- **Responsabilidad:** definicion de la arquitectura CNN
- **Requisitos que cubre:** RNF-1, RNF-3
- **Interfaz:**
  - `build_model(num_classes=3, input_shape=(224, 224, 1)) -> keras.Model`
  - Arquitectura (siguiendo literalmente el patron del Bloque 6 de
    Jordi: **Conv2D + MaxPooling2D + Dropout + Flatten + Dense +
    softmax**):
    ```
    Input (224x224x1)
    → Conv2D(32, 3x3, relu, padding="same")  → MaxPool(2x2)  # → 112x112x32
    → Conv2D(64, 3x3, relu, padding="same")  → MaxPool(2x2)  # →  56x56x64
    → Conv2D(128, 3x3, relu, padding="same") → MaxPool(2x2)  # →  28x28x128
    → Conv2D(128, 3x3, relu, padding="same") → MaxPool(2x2)  # →  14x14x128
    → Dropout(0.5)
    → Flatten                                                 # → 25088
    → Dense(64, relu)
    → Dropout(0.3)
    → Dense(3, softmax)
    ```
  - **`padding="same"` es obligatorio en las 4 Conv2D** para que las
    formas espaciales se reduzcan solo por los MaxPool y queden enteras
    a cada paso (224 → 112 → 56 → 28 → 14). Con el `padding="valid"`
    por defecto, una conv 3x3 quita 2 px por lado y el siguiente
    MaxPool generaria tamanos impares que rompen la cadena
  - Compile: optimizer Adam (lr=1e-3), loss
    `sparse_categorical_crossentropy`, metrics `accuracy`
- **Tamano estimado:** ~1.8M params (Flatten sobre 14x14x128 = 25.088
  features → Dense(64) aporta ~1.6M params; las 4 conv aportan ~200K
  mas). Peso en disco ~7-8 MB en formato `.keras`. Sigue holgadamente
  bajo el limite de RNF-4 (< 50 MB)

### `src/ml/train.py` (nuevo — CLI)
- **Responsabilidad:** orquestar el entrenamiento end-to-end
- **Requisitos que cubre:** RF-1, RF-3, CB-1, CB-6, RNF-5
- **Uso de los splits — regla estricta:**
  - **`train`** → se usa para `model.fit` (gradientes, actualizacion
    de pesos)
  - **`validation`** → se usa **solo durante el entrenamiento** para
    EarlyStopping (`monitor="val_loss"`), ModelCheckpoint y ajuste de
    hiperparametros. **NO entra en el reporte final de metricas**
  - **`test`** → se usa **solo al final**, una unica vez tras
    EarlyStopping, para producir las metricas del reporte (accuracy,
    macro-F1, matriz de confusion, recall por clase). El modelo nunca
    "ve" este split durante el entrenamiento, asi las metricas
    reportadas no estan contaminadas por seleccion de hiperparametros
  - Asi se elimina la ambiguedad "¿las metricas del reporte salen de
    val o de test?": **siempre test**
- **Flujo:**
  1. Set seeds (numpy, tf, python random) + `enable_op_determinism`
  2. `discover_dataset()` + `build_splits(seed=42)` → train/val/test
     estratificados
  3. `compute_class_weight(train_split)` → dict `{0: w_normal, 1: w_pneumonia, 2: w_covid}`
  4. `build_training_pipeline(train_split, augment=True)`,
     `build_training_pipeline(val_split, augment=False)` y
     `build_training_pipeline(test_split, augment=False)`
  5. `build_model()` + `model.compile(...)`
  6. Callbacks: `EarlyStopping(monitor="val_loss", patience=5,
     restore_best_weights=True)`, `ModelCheckpoint("best.keras",
     monitor="val_loss")`, `CSVLogger("training_log.csv")` — todos
     usan el **val_split**, nunca el test
  7. `model.fit(train_ds, validation_data=val_ds, class_weight=...)`
  8. `evaluate.generate_report(model, test_ds)` → metricas finales
     sobre el split de **test**, escribe a `docs/model-evaluation/`
  9. Guarda el modelo en `data/models/radiography_classifier.keras` +
     `data/models/radiography_classifier.meta.json`
- **Ejecucion (al menos una vez antes de la entrega):**
  `docker compose run --rm pipeline python -m src.ml.train`

### `src/ml/evaluate.py` (nuevo)
- **Responsabilidad:** generar el reporte de evaluacion final sobre el
  **split de test** (nunca sobre validation, ver `train.py`)
- **Requisitos que cubre:** RF-2, RNF-2, CA-2, CA-3, CA-4
- **Interfaz:**
  - `generate_report(model, test_dataset, output_dir) -> Report`
  - Las metricas (accuracy, macro-F1, matriz de confusion, precision/
    recall/F1 por clase) se computan SOLO sobre `test_dataset`. La
    curva de aprendizaje (loss/acc por epoch) sale del `CSVLogger`
    del entrenamiento y refleja train vs val
- **Salidas:**
  - `docs/model-evaluation/metrics.json` — accuracy, macro_f1, por_clase
    {precision, recall, f1, support}, confusion_matrix (lista de listas),
    hiperparametros
  - `docs/model-evaluation/confusion_matrix.png` — heatmap con conteos
  - `docs/model-evaluation/learning_curves.png` — loss y accuracy por
    epoch (lee de `training_log.csv`)
  - `docs/model-evaluation/report.md` — analisis humano legible.
    Estructura:
    1. Resumen: accuracy, macro-F1, recall por clase
    2. Matriz de confusion + interpretacion
    3. **Analisis clinico (CA-3):** parrafo razonando los FN COVID/Pneumonia,
       si el modelo es aceptable como asistencia diagnostica, y bajo
       que condiciones (umbral de confianza minimo, revision humana)
    4. Hiperparametros y reproducibilidad
    5. Limitaciones

### `src/ml/predictor.py` (nuevo)
- **Responsabilidad:** encapsular la inferencia. Una instancia por
  proceso de API
- **Requisitos que cubre:** RF-4, RF-5, RNF-3, RNF-6
- **Interfaz:**
  ```
  class Prediction:
      predicted_class: str
      probabilities: dict[str, float]
      model_version: str

  class Predictor:
      def __init__(self, model_path: Path, meta_path: Path)
      def predict(self, image_bytes: bytes) -> Prediction
      @property
      def model_version(self) -> str
  ```
- **Comportamiento:** lazy-validates al construir; si falta el modelo
  lanza `ModelNotAvailableError` → el lifespan lo captura y deja
  `app.state.predictor = None`

### `src/api/routers/classify.py` (nuevo)
- **Responsabilidad:** endpoints HTTP de clasificacion
- **Requisitos que cubre:** RF-5, RF-6, CB-2, CB-3, CB-4
- **Endpoints:**
  - `POST /api/v1/radiographies/classify` — la key viaja en el body
    JSON (`{"minio_object_key": "..."}`)
  - `GET /api/v1/radiographies/classification?key=...` — la key viaja
    como query param
  - **Por que no path param:** la `minio_object_key` contiene `/`
    (`HOSP-000001/HOSP-000001_xray1.png`). Meterla en path obliga a
    usar `{key:path}` de FastAPI, complica clientes y herramientas
    (curl, Swagger UI no escapa bien) y abre superficie a problemas
    con caracteres especiales. Body + query es mas robusto
- **Dependencias inyectadas:** `app.state.predictor`, `mongo_reader`,
  `mongo_writer` (nuevo en la app — hoy la API solo tiene reader),
  `minio_client`
- **Detalle ver "Contratos / API"**

### `src/api/main.py` (modificado)
- **Cambios:**
  - En `build_app`, tras construir `mongo_reader` y `sql_reader`:
    intentar `predictor = Predictor.from_env()`. Si lanza
    `ModelNotAvailableError`, log warning + `predictor = None`
  - `app.state.predictor = predictor`
  - `app.state.mongo_writer = mongo_writer` (nuevo — antes solo reader)
  - `app.state.minio_client = minio_client` (nuevo)
  - Registrar el router de classify
  - `GET /api/v1/health` devuelve ahora un `HealthResponse` ampliado
    con un campo nuevo `predictor_loaded: bool` que refleja si
    `app.state.predictor is not None`. Util para que los tests E2E
    sepan si pueden ejecutarse sin tener que inspeccionar el
    filesystem
- **Lifespan:** cerrar `mongo_writer` y `minio_client` al shutdown si
  aplicables

### `src/api/models.py` (modificado)
- **Cambios:**
  - Nueva clase `RadiographyClassification(BaseModel)` con
    `predicted_class: str`, `probabilities: dict[str, float]`,
    `predicted_at: datetime`, `model_version: str`
  - `Radiography.classification: RadiographyClassification | None`
    (antes era `str | None`)
  - `ClassifyRequest(BaseModel)` con `minio_object_key: str = Field(min_length=1)`
  - `ClassificationResponse(BaseModel)` reutiliza la misma estructura
    de `RadiographyClassification` + campo `minio_object_key`
  - `HealthResponse` gana `predictor_loaded: bool`

### `src/pipeline/storage/mongo_writer.py` (modificado)
- **Metodo nuevo:**
  ```
  set_radiography_classification(
      minio_object_key: str,
      classification: dict,
  ) -> bool
  ```
  - Firma SOLO con la key porque el endpoint POST recibe solo la key
    en el body. El router NO conoce ni necesita conocer el
    `patient_external_id`
  - Usa `update_one` con `arrayFilters` sobre
    `{"radiographies.minio_object_key": key}` para actualizar el
    subdocumento sin tocar el resto del array
  - Devuelve `matched_count > 0` (NO `modified_count`). Diferencia
    relevante: re-clasificar con resultado identico → Mongo no toca el
    doc (`modified_count=0`) pero la operacion es exitosa. Con
    `matched_count` distinguimos "no encontre la key" (False → 404)
    de "encontre y aplique" (True → 200), incluido el caso idempotente
- **Indice nuevo en Mongo (init-db.js):**
  `db.patients.createIndex({"radiographies.minio_object_key": 1})` para
  que el `arrayFilters` sea rapido

### `src/api/mongo_reader.py` (modificado)
- **Metodo nuevo:**
  ```
  get_radiography_classification(minio_object_key: str) -> dict | None
  ```
  - Pipeline con `$unwind` sobre `radiographies` + match por
    `minio_object_key`, proyecta `classification`
  - None si no se encuentra o si `classification is None`

### Refactor de volumenes Docker
- **Hoy:** `pipeline` y `api` montan `./data:/app/data:ro` global.
  `train.py` no podria escribir en `data/models/`
- **Manana:** descomponer en submontajes con permisos especificos:
  ```yaml
  pipeline:
    volumes:
      - ./data/raw:/app/data/raw:ro
      - ./data/models:/app/data/models:rw    # train escribe aqui
      - pipeline-db:/app/data/db:rw
  api:
    volumes:
      - ./data/raw:/app/data/raw:ro
      - ./data/models:/app/data/models:ro    # API solo lee
      - pipeline-db:/app/data/db:rw
  watcher:
    volumes:
      - ./data/raw:/app/data/raw:ro          # ya monta solo incoming hoy
      - ./data/incoming:/app/data/incoming:rw
      - pipeline-db:/app/data/db:rw
  ```
  Beneficio: cada servicio ve exactamente lo que necesita, con los
  permisos correctos. Cero ambiguedad sobre quien puede escribir donde

## Modelo de datos

### Artefacto del modelo en disco
```
data/models/
├── radiography_classifier.keras       # peso del modelo Keras
└── radiography_classifier.meta.json   # metadatos: version, fecha,
                                        # accuracy, classes, input_shape
```

### `radiography_classifier.meta.json`
```json
{
  "model_version": "v1.0-20260516",
  "trained_at": "2026-05-16T18:30:00Z",
  "classes": ["Normal", "Pneumonia", "COVID-19"],
  "input_shape": [224, 224, 1],
  "framework": "tensorflow",
  "framework_version": "2.16.x",
  "metrics": {
    "accuracy": 0.93,
    "macro_f1": 0.91,
    "per_class": {
      "Normal":    {"precision": 0.95, "recall": 0.94, "f1": 0.94},
      "Pneumonia": {"precision": 0.92, "recall": 0.89, "f1": 0.90},
      "COVID-19":  {"precision": 0.90, "recall": 0.88, "f1": 0.89}
    }
  },
  "training": {
    "seed": 42,
    "split": "stratified-80-10-10",
    "epochs_run": 22,
    "epochs_max": 50,
    "batch_size": 32,
    "class_weight": {"0": 0.8, "1": 1.4, "2": 1.5}
  }
}
```

### Mongo — campo `classification` (objeto, no string)
```javascript
patients.radiographies[i].classification = {
  predicted_class: "COVID-19",
  probabilities: {
    "Normal": 0.04,
    "Pneumonia": 0.11,
    "COVID-19": 0.85
  },
  predicted_at: ISODate("2026-05-16T18:35:12.000Z"),
  model_version: "v1.0-20260516"
}
```

`null` sigue siendo valor valido para radiografias sin clasificar (las
17 dummy al arrancar, por ejemplo).

## Contratos de datos

### Datos de entrada (a entrenamiento)

| Fuente | Formato | Campos obligatorios | Validaciones | Que pasa si falta/falla |
|--------|---------|--------------------|--------------|------------------------|
| Dataset COVID-19 Radiography Database | PNG en carpetas por clase | `COVID/`, `Normal/`, `Viral Pneumonia/` con al menos N imagenes | imagenes legibles, >= 32 px por lado | `DatasetNotFoundError` con referencia al runbook (CB-1) |

### Datos de salida (de entrenamiento)

| Destino | Formato | Campos | Ejemplo |
|---------|---------|--------|---------|
| `data/models/` | `.keras` + `.meta.json` | binario + JSON estructurado | ver arriba |
| `docs/model-evaluation/` | `report.md`, `metrics.json`, 2 PNGs | analisis legible + maquina | ver arriba |

### Glosario

| Termino | Definicion | NO significa |
|---------|-----------|--------------|
| Clase | Una de `{Normal, Pneumonia, COVID-19}` | Cualquier otra patologia (Lung_Opacity se descarta) |
| Inferencia | Una sola pasada `imagen → clase + probabilidades` | Entrenamiento |
| `predicted_class` | Salida `argmax` del softmax | Diagnostico medico |
| `model_version` | String identificador del artefacto (`v1.0-fecha`) | Hash del codigo |
| Recall COVID | Sensibilidad clinica para detectar COVID. Lo importante para no dar de alta a un contagioso | Accuracy global |

## Contratos / API

### `POST /api/v1/radiographies/classify`

**Request body (JSON):**
```json
{
  "minio_object_key": "HOSP-000001/HOSP-000001_xray1.png"
}
```

La key se valida con un modelo Pydantic (`ClassifyRequest`) que exige
el campo no vacio. No se acepta como query param para que el contrato
de escritura quede explicito (idempotency + auditable en logs).

**Respuestas:**

`200 OK` — clasificacion exitosa + persistida en MongoDB:
```json
{
  "minio_object_key": "HOSP-000001/HOSP-000001_xray1.png",
  "predicted_class": "Normal",
  "probabilities": {"Normal": 0.92, "Pneumonia": 0.05, "COVID-19": 0.03},
  "predicted_at": "2026-05-16T18:35:12Z",
  "model_version": "v1.0-20260516"
}
```

`404 Not Found` — la key no existe en MinIO (CB-2):
```json
{"detail": "Radiography not found in MinIO: HOSP-XXX/file.png"}
```

`422 Unprocessable Entity` — imagen corrupta, formato invalido, o
imagen demasiado pequena (CB-3, CB-7):
```json
{"detail": "Image cannot be processed: <reason>"}
```

`503 Service Unavailable` — modelo no cargado (CB-4):
```json
{"detail": "Classification model is not loaded in this deployment"}
```

### `GET /api/v1/radiographies/classification?key=...`

**Query params:**
- `key` (obligatorio, string no vacio): el `minio_object_key`. Con
  slashes URL-encoded por el cliente (ej. `key=HOSP-000001%2FHOSP-000001_xray1.png`),
  FastAPI los decodifica automaticamente

**Respuestas:**

`200 OK` — objeto persistido en Mongo (estructura RF-7):
```json
{
  "minio_object_key": "HOSP-000001/HOSP-000001_xray1.png",
  "predicted_class": "Normal",
  "probabilities": {"Normal": 0.92, "Pneumonia": 0.05, "COVID-19": 0.03},
  "predicted_at": "2026-05-16T18:35:12Z",
  "model_version": "v1.0-20260516"
}
```

`404 Not Found` — no hay clasificacion persistida para esa key. (NO
distingue entre "key no existe en Mongo" y "key existe pero
`classification = null`": ambos casos son "no hay clasificacion que
devolver")

`422 Unprocessable Entity` — `key` ausente o vacio en el query string

## Trade-offs

| Decision | Alternativa descartada | Razon |
|----------|----------------------|-------|
| CNN custom desde cero (~1.8M params, ~7-8 MB) | Transfer learning (MobileNetV2, ResNet50) | ADR-005: alineacion con Bloque 6 del Master (Conv2D + MaxPooling2D + Dropout + Flatten + Dense + softmax) + sin asunciones de pre-entreno ImageNet RGB |
| Input 224x224 **grayscale** (1 canal) | 224x224x3 (replicar canal) | Las radiografias son monocromaticas. 1 canal ahorra ~3x parametros en la primera conv sin perder informacion |
| Sin horizontal flip en augmentation | Flip activado (default Keras) | El flip izq/dch cambia la semantica anatomica (lado de la lesion). Daria datos invalidos |
| Modelo en `data/models/` commiteado | Modelo en MinIO bucket | Mas simple para evaluador. MinIO complicaria el lifespan de la API (descargar al arrancar). Si pesa >50 MB se ignora y se documenta como regenerar |
| Predictor cargado en startup (lifespan) | Cargar bajo demanda en cada peticion | Carga = 1-3s. Demasiado lento por request. Bajo demanda solo seria valido si el modelo cambiara en caliente, no es el caso |
| TF en imagen compartida `hospital-pipeline` | Imagen `hospital-ml` separada | ADR-006: una sola imagen, todo el stack en mismo compose. Coste: build mas pesado |
| Endpoint individual, sin batch | Batch `POST /classify-all` | Spec lo excluye explicitamente (RF-8) |
| Misma funcion `preprocess_for_inference` en train y serve | Implementar dos veces | Evita el bug clasico "train-serve skew". Coste cero |
| Reporte humano (md) + maquina (json) + figuras (png) | Solo notebook | Notebook es ruidoso para evaluador. Markdown + figuras es legible sin Jupyter |
| Update Mongo con `arrayFilters` por `minio_object_key` | Reemplazar todo el array `radiographies` | Concurrencia segura, no sobrescribe radiografias paralelas que se anaden al array |
| `predicted_class` (no `class`) | `class` | `class` es palabra reservada de Python; obligaria a aliasing en cada acceso |

## Riesgos identificados

1. **Tiempo de entrenamiento en CPU.** El dataset tiene ~21K imagenes
   (sin contar Lung_Opacity). Con la CNN propuesta, ~5-10 min/epoch en
   una maquina sin GPU. Con EarlyStopping (~15-25 epochs reales), el
   entrenamiento completo puede tardar 1-3 horas. **Mitigacion:**
   reducir input size a 128x128 si va muy lento; reducir nº de filtros;
   reducir epochs maximos a 30. Plan de contingencia documentado.

2. **TensorFlow infla la imagen Docker (~600 MB → ~1.2 GB total).**
   Build mas lento. **Mitigacion:** usar `tensorflow-cpu` (no la
   variante full con CUDA), capa de cache en multi-stage build si hace
   falta. Documentado en ADR-006.

3. **Determinismo TF limitado.** `enable_op_determinism` reduce pero
   no elimina la varianza. RNF-5 acepta "dentro de tolerancia". Se
   documenta en el reporte y en lessons.

4. **Modelo > 50 MB:** la estimacion actual es ~7-8 MB (~1.8M params).
   Si por crecimiento de la red o cambios de input shape acaba pesando
   mas de 50 MB, se gitignorea. **Mitigacion:** el runbook explica
   como regenerarlo con `docker compose run pipeline python -m src.ml.train`.

5. **Distribucion real del dataset desbalanceada.** El COVID-19
   Radiography Database tiene ~10K Normal, ~6K Lung_Opacity (que
   descartamos), ~3.6K Viral Pneumonia, ~3.6K COVID. Sin Lung_Opacity:
   ~10K Normal vs ~3.6K Pneumonia vs ~3.6K COVID. **Mitigacion:**
   `class_weight` en `model.fit` (CB-6).

6. **Latencia de inferencia con TF en CPU.** Una pasada por una CNN
   pequena toma ~50-200 ms en CPU. Bajo el limite de 3s (RNF-3) con
   margen. Si el preprocesado anade overhead, vigilar.

7. **Concurrencia de predictor.** TF/Keras `model.predict` no es
   thread-safe historicamente. FastAPI con uvicorn single-worker
   sirve requests en threadpool. **Mitigacion:** wrappear con un
   `threading.Lock` dentro del Predictor o serializar con asyncio.

## Plan de tests (resumen — detalle en /tareas)

| Nivel | Archivo (nuevo o modificado) | Que valida |
|-------|------------------------------|------------|
| Unit | `tests/ml/test_dataset.py` | discover_dataset, build_splits estratificado, mapeo de clases, skip de Lung_Opacity, CB-1 |
| Unit | `tests/ml/test_preprocessing.py` | shape de salida, dtype, valor range [0,1], InvalidImageError en CB-3/CB-7, sin horizontal flip |
| Unit | `tests/ml/test_model.py` | smoke: build + forward con tensor dummy; conteo de parametros razonable |
| Unit | `tests/ml/test_predictor.py` | Predictor con modelo dummy entrenado al vuelo (2 epochs sobre datos tiny): predict devuelve estructura correcta, version del modelo legible, ModelNotAvailableError si falta artefacto |
| Unit | `tests/ml/test_evaluate.py` | generate_report produce metrics.json valido, includes recall por clase |
| Unit | `tests/api/test_classify_endpoint.py` | 200 / 404 / 422 / 503 con predictor mock |
| Integ | `tests/api/test_classify_endpoint.py` (mismo) | Persistencia en Mongo: tras POST /classify, GET /classification devuelve lo mismo |
| Integ | `tests/pipeline/test_mongo_writer.py` (extended) | `set_radiography_classification` actualiza el subdocumento correcto sin tocar el resto del array |
| E2E | `tests/e2e/test_classification_e2e.py` (nuevo) | Con el modelo real cargado, clasificar una radiografia **valida (>= 32 px)** via la API y verificar persistencia en Mongo + lectura por `GET /classification`. **NO se usan las 17 PNGs dummy del bootstrap** porque son 1x1 y el propio diseno las rechazaria con 422 (CB-7). Estrategia de fixture: (a) si existe el dataset descargado en `/app/data/raw/covid_radiography/`, copiar una imagen real al bucket MinIO solo para este test; (b) si no, generar al vuelo un PNG 64x64 grayscale valido y subirlo al bucket. Cleanup tras el test elimina la imagen y la clasificacion persistida. Skip limpio si no hay modelo en `data/models/` |

## Inicializacion y arranque

1. Si el modelo `data/models/radiography_classifier.keras` esta
   presente, la API lo carga al arrancar. Si no, arranca igualmente
   y los endpoints de classify devuelven 503
2. El entrenamiento se ejecuta UNA vez antes de la entrega (no en
   `docker compose up`):
   `docker compose run --rm pipeline python -m src.ml.train`
3. Cualquier servicio puede leer el modelo (API en `:ro`, pipeline en
   `:rw` para poder reentrenar)

## Decisiones registradas como ADR

- **ADR-005:** [Arquitectura del modelo CNN — custom desde cero, sin
  transfer learning, siguiendo el patron del Bloque 6 de Jordi
  (Conv2D + MaxPooling2D + Dropout + Flatten + Dense + softmax)](../decisions/ADR-005-cnn-custom-no-transfer-learning.md)
- **ADR-006:** [TensorFlow en la imagen `hospital-pipeline` compartida,
  frente a imagen `hospital-ml` separada](../decisions/ADR-006-tensorflow-en-imagen-compartida.md)
