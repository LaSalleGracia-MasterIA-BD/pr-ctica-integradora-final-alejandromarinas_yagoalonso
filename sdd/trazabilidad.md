# Matriz de trazabilidad SDD

Esta matriz sirve para demostrar que el SDD no se quedo en documentacion: cada feature relevante tiene una cadena desde requisitos hasta codigo y pruebas.

## Resumen

```text
Spec -> Design -> Tasks -> ADRs -> Codigo -> Tests -> Evidencia documental
```

## 1. Pipeline de datos

| Capa | Artefacto |
|---|---|
| Spec | `specs/pipeline-datos.md` |
| Design | `design/pipeline-datos.md` |
| Tasks | `tasks/pipeline-datos.md` |
| ADRs | `decisions/ADR-001-stack-tecnologico.md`, `decisions/ADR-002-mongodb-nosql.md` |
| Codigo | `src/pipeline/` |
| Tests | `tests/pipeline/`, `tests/e2e/test_acceptance_criteria.py`, `tests/e2e/test_watcher_integration.py` |
| Evidencia | `README.md`, `docs/memoria-tecnica.md` caps. 3, 4, 5, 11 y 12 |

Puntos que demuestra:

- ingesta CSV con PySpark;
- validacion y limpieza;
- rejected records;
- escritura en MongoDB y MinIO;
- orquestacion;
- watcher;
- idempotencia;
- tests E2E.

## 2. Metadatos SQL del pipeline

| Capa | Artefacto |
|---|---|
| Spec | `specs/sqlite-pipeline-metadata.md` |
| Design | `design/sqlite-pipeline-metadata.md` |
| Tasks | `tasks/sqlite-pipeline-metadata.md` |
| ADR | `decisions/ADR-004-polyglot-persistence.md` |
| Codigo | `src/pipeline/storage/sql_engine.py`, `src/pipeline/storage/sql_models.py`, `src/pipeline/storage/sql_writer.py`, `src/api/sql_reader.py` |
| Tests | `tests/pipeline/test_sql_engine.py`, `tests/pipeline/test_sql_writer.py`, `tests/api/test_sql_reader.py`, `tests/api/test_pipeline_endpoints.py` |
| Evidencia | Dashboard: vista `Pipeline runs` y vista `Calidad de datos` |

Puntos que demuestra:

- SQLite + SQLAlchemy para metadatos tabulares;
- `pipeline_runs`;
- `data_quality_summary`;
- historico de calidad;
- auditoria de ejecuciones.

## 3. Clasificacion de radiografias

| Capa | Artefacto |
|---|---|
| Spec | `specs/clasificacion-radiografias.md` |
| Design | `design/clasificacion-radiografias.md` |
| Tasks | `tasks/clasificacion-radiografias.md` |
| ADRs | `decisions/ADR-003-keras-tensorflow.md`, `decisions/ADR-005-cnn-custom-no-transfer-learning.md`, `decisions/ADR-006-tensorflow-en-imagen-compartida.md` |
| Codigo | `src/ml/`, `src/api/routers/classify.py` |
| Tests | `tests/ml/`, `tests/api/test_classify_endpoint.py`, `tests/e2e/test_classification_e2e.py` |
| Evidencia | `docs/model-evaluation/metrics.json`, `docs/model-evaluation/report.md`, `docs/model-evaluation/confusion_matrix.png` |

Puntos que demuestra:

- CNN custom Keras/TensorFlow;
- preprocessing compartido entre entrenamiento y serving;
- inferencia via API;
- persistencia de `classification` en MongoDB;
- evaluacion con matriz de confusion y recall por clase;
- analisis clinico honesto.

## 4. Dashboard

| Capa | Artefacto |
|---|---|
| Spec | `specs/dashboard.md` |
| Design | `design/dashboard.md` |
| Tasks | `tasks/dashboard.md` |
| ADR | `decisions/ADR-007-dashboard-streamlit-imagen-independiente.md` |
| Codigo | `src/dashboard/`, `Dockerfile.dashboard`, `.streamlit/config.toml` |
| Tests | `tests/dashboard/`, `tests/e2e/test_dashboard_smoke.py` |
| Evidencia | `docs/presentation/`, `docs/runbooks/presentation-demo.md` |

Puntos que demuestra:

- dashboard API-only;
- cinco vistas;
- barra persistente de estado;
- clasificador integrado;
- visualizacion de metricas de modelo;
- manejo de errores;
- demo reproducible.

## 5. Documentacion final

| Capa | Artefacto |
|---|---|
| Backlog | `tasks/backlog.md` |
| Memoria | `docs/memoria-tecnica.md` |
| Diario IA | `docs/diario-ia.md` |
| Lecciones | `tasks/lessons.md` |
| Presentacion | `docs/presentation/presentation.html`, `docs/presentation/fallback.md` |

Puntos que demuestra:

- trazabilidad de decisiones;
- reflexion critica;
- etica y legal;
- limitaciones;
- cierre del proyecto;
- preparacion de defensa.

