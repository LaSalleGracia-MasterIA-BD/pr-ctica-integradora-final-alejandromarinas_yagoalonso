# Design: Pipeline de datos hospitalario

> Spec: specs/pipeline-datos.md

## Decision arquitectonica
Pipeline batch con PySpark en modo standalone, orquestado por un servicio watcher (deteccion automatica de ficheros nuevos) y un endpoint API (trigger manual). Almacenamiento dual: MongoDB para datos clinicos y MinIO para imagenes. Todo containerizado con Docker Compose.

Se elige modo standalone de Spark (no cluster) porque el volumen es simulado y simplifica la infra Docker, pero el codigo PySpark es identico al que correria en un cluster real — se puede escalar sin cambiar logica.

## Trazabilidad spec → componentes

| Requisito | Componente(s) | Archivos |
|-----------|--------------|----------|
| RF-1 | CSVIngester, SparkProcessor | `src/pipeline/ingesters/csv_ingester.py`, `src/pipeline/processors/spark_processor.py` |
| RF-2 | ImageIngester, MinIOClient | `src/pipeline/ingesters/image_ingester.py`, `src/pipeline/storage/minio_client.py` |
| RF-3 | DataCleaner (PySpark) | `src/pipeline/processors/data_cleaner.py` |
| RF-4 | DataTransformer (PySpark) | `src/pipeline/processors/data_transformer.py` |
| RF-5 | MongoWriter | `src/pipeline/storage/mongo_writer.py` |
| RF-6 | API endpoints | `src/api/routers/data.py` |
| RF-7 | FileWatcher, PipelineOrchestrator | `src/pipeline/watcher.py`, `src/pipeline/orchestrator.py` |
| RNF-1 | Docker Compose config | `docker-compose.yml`, `Dockerfile.*` |
| RNF-4 | PipelineLogger | `src/pipeline/logging_config.py` |
| CB-1..5 | DataValidator | `src/pipeline/processors/data_validator.py` |

## Componentes

### PipelineOrchestrator
- **Responsabilidad:** Coordina la ejecucion completa del pipeline: ingesta → validacion → limpieza → transformacion → almacenamiento. Registra cada ejecucion en `pipeline_runs`.
- **Requisitos que cubre:** RF-7, CB-4
- **Archivos:** `src/pipeline/orchestrator.py`

### FileWatcher
- **Responsabilidad:** Monitoriza el directorio `data/incoming/` y dispara el orquestador cuando detecta ficheros nuevos. Mueve ficheros procesados a `data/incoming/processed/`.
- **Requisitos que cubre:** RF-7
- **Archivos:** `src/pipeline/watcher.py`

### CSVIngester
- **Responsabilidad:** Lee ficheros CSV de pacientes, valida que las columnas esperadas existen, y los carga como DataFrames de PySpark.
- **Requisitos que cubre:** RF-1, CB-1
- **Archivos:** `src/pipeline/ingesters/csv_ingester.py`

### ImageIngester
- **Responsabilidad:** Lee imagenes de radiografias, valida formato (PNG), extrae metadatos y las sube a MinIO.
- **Requisitos que cubre:** RF-2, CB-2
- **Archivos:** `src/pipeline/ingesters/image_ingester.py`

### DataValidator
- **Responsabilidad:** Valida registros contra reglas de negocio (campos obligatorios, rangos, formatos). Separa registros validos de rechazados con motivo.
- **Requisitos que cubre:** RF-3, CB-1, CB-3
- **Archivos:** `src/pipeline/processors/data_validator.py`

### DataCleaner (PySpark)
- **Responsabilidad:** Elimina duplicados, maneja nulos en campos opcionales, estandariza formatos (fechas, nombres, codigos).
- **Requisitos que cubre:** RF-3
- **Archivos:** `src/pipeline/processors/data_cleaner.py`

### DataTransformer (PySpark)
- **Responsabilidad:** Enriquece datos: calcula edad desde fecha de nacimiento, categoriza diagnosticos, agrega metricas por periodo.
- **Requisitos que cubre:** RF-4
- **Archivos:** `src/pipeline/processors/data_transformer.py`

### MongoWriter
- **Responsabilidad:** Escribe datos procesados a colecciones de MongoDB. Maneja upserts por external_id para evitar duplicados en re-ejecuciones.
- **Requisitos que cubre:** RF-5, CB-4
- **Archivos:** `src/pipeline/storage/mongo_writer.py`

### MinIOClient
- **Responsabilidad:** Wrapper sobre boto3/minio-py para subir/descargar objetos de MinIO. Organiza por buckets y prefijos.
- **Requisitos que cubre:** RF-2
- **Archivos:** `src/pipeline/storage/minio_client.py`

### DataGenerator (script auxiliar)
- **Responsabilidad:** Genera CSVs simulados de pacientes con datos realistas usando Faker. Incluye casos borde intencionados (nulos, duplicados, formatos incorrectos).
- **Requisitos que cubre:** Soporte para testing y demo
- **Archivos:** `src/pipeline/scripts/generate_data.py`

## Modelo de datos

### MongoDB — Colecciones

Base de datos: `hospital`

```
patients (indice unico: external_id)
{
  _id: ObjectId,
  external_id: String,       // ID hospital
  name: String,
  birth_date: ISODate,
  age: Number,               // calculado
  gender: String,            // M/F/Other
  blood_type: String,
  admissions: [              // subdocumentos embebidos
    {
      admission_date: ISODate,
      discharge_date: ISODate | null,
      department: String,
      diagnosis_code: String,    // ICD-10
      diagnosis_description: String,
      status: String             // admitted/discharged/transferred
    }
  ],
  radiographies: [           // referencias a MinIO
    {
      minio_object_key: String,
      classification: String | null,  // normal/pneumonia/covid
      ingested_at: String,           // ISO timestamp UTC
      file_size_bytes: Number,
      original_filename: String
    }
  ],
  created_at: ISODate,
  updated_at: ISODate
}

pipeline_runs
{
  _id: ObjectId,
  trigger_type: String,      // manual/watcher
  started_at: ISODate,
  finished_at: ISODate | null,
  status: String,            // running/success/failed
  records_processed: Number,
  records_rejected: Number,
  images_processed: Number,
  error_message: String | null
}

rejected_records (indice: pipeline_run_id)
{
  _id: ObjectId,
  pipeline_run_id: ObjectId,
  source_file: String,
  row_number: Number,
  rejection_reason: String,
  raw_data: Object,
  created_at: ISODate
}
```

> Nota: Se aprovecha el modelo de documentos de MongoDB para embeber admissions y radiographies dentro del paciente. Esto evita joins y refleja la relacion natural de los datos (un paciente TIENE ingresos y radiografias).

### MinIO — Buckets

```
radiographies/
├── {patient_id}/{original_filename}        # key deterministico → subidas idempotentes

raw-backups/
├── {pipeline_run_id}/{original_filename}
```

## Contratos de datos

### Datos de entrada

| Fuente | Formato | Campos obligatorios | Validaciones | Que pasa si falta/falla |
|--------|---------|-------------------|-------------|------------------------|
| CSV pacientes | CSV UTF-8 | external_id, name, birth_date, gender | birth_date formato ISO, gender en (M/F/Other) | Documento va a coleccion rejected_records con motivo |
| CSV ingresos | CSV UTF-8 | patient_external_id, admission_date, department, diagnosis_code | admission_date ISO, patient debe existir | Registro rechazado |
| Imagenes | PNG | filename con patron `{patient_id}_*.png` | Formato PNG valido, tamano < 50MB | Se loguea error, imagen se omite |

### Datos de salida

| Destino | Formato | Campos | Ejemplo |
|---------|---------|--------|---------|
| API /patients | JSON | id, external_id, name, age, gender, blood_type | `{"id": "uuid", "name": "Juan", "age": 45}` |
| API /admissions | JSON | id, patient_id, admission_date, department, diagnosis | `{"department": "UCI", "diagnosis": "J18.9"}` |
| API /pipeline/status | JSON | run_id, status, records_processed, records_rejected | `{"status": "success", "records_processed": 4500}` |

### Glosario de terminos

| Termino | Definicion | NO significa |
|---------|-----------|-------------|
| Ingesta | Incorporar ficheros nuevos al sistema y parsearlos | No es procesamiento ni transformacion |
| Registro rechazado | Fila que no pasa validacion — se guarda en rejected_records para auditoria | No es un error del pipeline, es calidad de datos |
| Pipeline run | Una ejecucion completa del pipeline de inicio a fin | No es un paso individual |

## Contratos / API

```
POST /api/v1/pipeline/trigger    → Dispara ejecucion manual del pipeline
GET  /api/v1/pipeline/status     → Estado de la ultima ejecucion
GET  /api/v1/pipeline/runs       → Historico de ejecuciones
GET  /api/v1/patients            → Lista paginada de pacientes procesados
GET  /api/v1/patients/{id}       → Detalle de un paciente
GET  /api/v1/admissions          → Lista paginada de ingresos
GET  /api/v1/radiographies       → Metadatos de radiografias
```

## Flujo del pipeline

```
1. TRIGGER (watcher detecta fichero / API recibe POST)
       │
2. ORCHESTRATOR crea pipeline_run (status: running)
       │
3. INGESTA
   ├── CSVIngester: lee CSVs → DataFrames PySpark
   └── ImageIngester: lee PNGs → sube a MinIO
       │
4. VALIDACION
   └── DataValidator: separa validos / rechazados
       │
5. LIMPIEZA
   └── DataCleaner: duplicados, nulos opcionales, formatos
       │
6. TRANSFORMACION
   └── DataTransformer: edad, categorias, agregaciones
       │
7. CARGA
   ├── MongoWriter: upsert a colecciones
   └── rejected → rejected_records
       │
8. CIERRE
   └── Orchestrator actualiza pipeline_run (status: success/failed)
```

## Servicios Docker

| Servicio | Imagen base | Puerto | Responsabilidad |
|----------|-------------|--------|----------------|
| mongodb | mongo:7 | 27017 | BBDD NoSQL datos clinicos |
| minio | minio/minio | 9000, 9001 | Almacenamiento de imagenes |
| spark | bitnami/spark o custom | — | Procesamiento PySpark |
| pipeline-worker | python:3.11 + pyspark | — | Watcher + orchestrator |
| api | python:3.11 | 8000 | FastAPI |

## Trade-offs

| Decision | Alternativa descartada | Razon |
|----------|----------------------|-------|
| Spark standalone (no cluster) | Spark cluster (master + workers) | Volumen simulado no justifica cluster. El codigo PySpark es el mismo — escala sin cambiar logica |
| Upsert por external_id | insert con find previo | Operacion atomica nativa en MongoDB, robusto ante re-ejecuciones |
| Watcher por polling (watchdog) | inotify / evento S3 | Mas portable entre OS, mas simple en Docker |
| MinIO en vez de S3 real | AWS S3 | Gratis, local, compatible S3 — perfecto para proyecto academico |
| Rejected records en MongoDB | Log file con rechazados | Mas consultable, permite dashboard de calidad de datos |
| MongoDB (documental) | PostgreSQL (relacional) | El enunciado pide al menos dos tipos de almacenamiento y pone PostgreSQL como ejemplo, no como obligacion. Los documentos JSON encajan con la jerarquia paciente -> admisiones -> radiografias y con los `raw_data` heterogeneos de `rejected_records`. Ver ADR-002 |
| Admissions embebidas en patient | Colecciones separadas con referencias | Evita lookups, refleja relacion natural paciente-ingresos |
