# ADR-004: Polyglot persistence — SQLite para auditoria y metricas, MongoDB para datos clinicos, MinIO para binarios

> Estado: accepted
> Fecha: 2026-05-16
> Complementa: ADR-002 (MongoDB como BBDD principal)

## Contexto

El enunciado del proyecto exige "uso combinado de al menos dos tipos de
almacenamiento" y, en su ejemplo, presenta el patron **SQL para
estructurados + MinIO/MongoDB para no estructurados**.

Estado actual:
- MongoDB → patients, admissions, pipeline_runs, rejected_records
- MinIO → radiografias (PNG)

Esa configuracion cumple "dos tipos" pero tiene dos huecos:

1. **Lectura estricta del enunciado**: el ejemplo del PDF combina SQL
   + MinIO/MongoDB. Un evaluador estricto puede leer que falta SQL para
   datos estructurados.
2. **Mismatch con el temario**: la asignatura de Big Data (Eric, Bloque 7)
   enseña SQLAlchemy + SQLite explicitamente. PostgreSQL solo se menciona
   como "produccion real" sin ejercicios.
3. **`pipeline_runs` no esta en su almacen idoneo**: son datos tabulares
   planos con queries tipicas de agregacion. MongoDB esta ahi solo porque
   era la unica BBDD del proyecto.

## Decision

Adoptar **polyglot persistence** con tres tipos de almacenamiento, cada
uno donde mejor sirve. SQLite **complementa**, no parte ni duplica
responsabilidades existentes:

| Dato | Naturaleza | Almacen | Justificacion |
|---|---|---|---|
| `patients` con `admissions` embebidas | Jerarquico, semi-estructurado | **MongoDB** (documental) | Embeber subdocumentos evita joins; un paciente es un documento natural (ADR-002) |
| `radiographies` (metadatos en doc del paciente; PNG en objeto) | Mixto: metadatos jerarquicos + binarios | **MongoDB** (metadatos) + **MinIO** (PNG) | Estandar de la industria para blobs grandes |
| `rejected_records` con `raw_data` heterogeneo | Semi-estructurado (raw_data es JSON con shape variable) | **MongoDB** | `raw_data` es JSON heterogeneo — encaja mejor en documental que en una columna SQL |
| `pipeline_runs` | Tabular plano | **SQLite** (relacional) | Queries de agregacion, ordenacion temporal, ningun anidamiento |
| `data_quality_summary` (NUEVO) | Tabular agregado: dimension/total/valid/rejected/rate | **SQLite** (relacional) | Pre-agregado para dashboard; queries instantaneas por dimension y rango temporal |

**Motor SQL elegido: SQLite + SQLAlchemy** (ver alternativas).

**Identificadores en SQLite: UUID v4 generados con `uuid.uuid4()`**, NO
`bson.ObjectId`. SQLite no debe depender conceptualmente de BSON. Si una
referencia desde MongoDB necesita apuntar a un run en SQLite, lo hace
con un string UUID (soft reference).

## Por que NO movemos rejected_records a SQLite

Era tentador moverlo (tiene FK natural a runs, parece tabular). Razones
para dejarlo en MongoDB:

1. **`raw_data` es JSON heterogeneo**: distintos motivos de rechazo
   generan dicts con shape diferente (un nulo en `name`, una fecha
   malformada, un huerfano en admissions...). En SQL habria que
   serializarlo como TEXT y perder consultabilidad
2. **MongoDB lo gestiona nativamente**: `db.rejected_records.find({"raw_data.gender": null})` es trivial
3. **Es parte del modelo "fallos del pipeline"** y queremos ese modelo en
   un solo almacen, no partido
4. **Lo que sí necesita el dashboard** son los **agregados** (cuantos
   fallos por dimension), no las filas individuales. Eso se cubre con
   `data_quality_summary` en SQLite

## Alternativas consideradas

| Opcion | Pros | Contras |
|--------|------|---------|
| **SQLite (runs + quality_summary) + MongoDB (resto)** (elegida) | Coincide con Bloque 7 del Master. Cada dato en su almacen idoneo. UUID propios sin dependencia BSON. Memoria defendible | Aprendizaje extra (3 modelos: documental, relacional, object storage) |
| Mover TAMBIEN `rejected_records` a SQLite | Cumple lectura literal "rechazados en SQL" del draft de spec | `raw_data` JSON heterogeneo no encaja bien en columnas SQL; rompe modelo "fallos del pipeline" |
| PostgreSQL + SQLAlchemy | Mas robusto en produccion, soporta JSONB nativo | El temario solo lo menciona, no lo enseña. Anade servicio Docker y complejidad sin ganancia para nuestro volumen |
| Solo MongoDB + MinIO (status quo) | Cero coste de cambio | No cubre la lectura estricta del enunciado; no toca el Bloque 7 del temario |
| `bson.ObjectId` como PK en SQLite | Mantiene formato del `_id` del API actual | Acopla SQLite a BSON sin razon tecnica; el formato del API no es un contrato externo que tengamos que preservar |

## Consecuencias

### Positivas
- (+) Tres tipos de almacenamiento, cada uno con justificacion tecnica
  clara basada en la naturaleza del dato
- (+) Cubre la lectura estricta del enunciado
- (+) Aliña con Bloque 7 de Big Data (Eric)
- (+) `data_quality_summary` da al dashboard una fuente pre-agregada
  para queries rapidas
- (+) Identificadores limpios: UUID en SQLite, ObjectId en MongoDB,
  cada almacen con su convencion idiomatica
- (+) Memoria defendible: demuestra criterio para elegir BBDD por dato

### Negativas
- (-) Una BBDD mas que mantener (aunque embedded)
- (-) Soft reference Mongo→SQLite: un developer despistado podria
  buscar el `pipeline_run_id` de un rejected en Mongo, no encontrarlo, y
  no entender por que. Mitigado con comentario en el modelo
  `RejectedRecord` y con indice nuevo en `rejected_records.pipeline_run_id`
- (-) Cambio interno del formato `_id` en el API (ObjectId → UUID v4).
  Sin clientes externos, asumible. Se actualizan modelos Pydantic, tests
  y documentacion en consecuencia

### Neutras
- Coste de migracion: medio dia - 1 dia (sin produccion real que
  preservar; el sistema arranca limpio)

## Requisitos relacionados

- Spec `sqlite-pipeline-metadata.md` (feature 13 del backlog)
- Cumple el bloque "Pipeline a escala → Almacenamiento" del enunciado
- Cumple el bloque "Justificaciones tecnicas → Alternativas consideradas"
  de la memoria tecnica

## Notas de implementacion

- Fichero SQLite: `/app/data/db/hospital.db` dentro del contenedor
- Volumen Docker named: `pipeline-db` (compartido entre pipeline, api,
  watcher)
- `PRAGMA journal_mode=WAL` activo para concurrencia
- `check_same_thread=False` necesario por el watcher (multi-thread)
- Schema creado en `bootstrap.py` via `Base.metadata.create_all(engine)`
- IDs en SQLite: `uuid.uuid4()` como string TEXT. NO bson.ObjectId
- Indice nuevo en MongoDB: `rejected_records.pipeline_run_id` (no-unico)
  para queries de "todos los rechazos de un run"
- Metodos eliminados de `MongoWriter`: `start_pipeline_run`,
  `finish_pipeline_run` (sin periodo de compatibilidad)
