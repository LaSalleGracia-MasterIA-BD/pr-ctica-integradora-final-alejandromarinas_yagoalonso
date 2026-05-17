# Backlog

| Prioridad | Feature | Spec | Design | Tasks | Estado | Tamano |
|-----------|---------|------|--------|-------|--------|--------|
| 1 | Pipeline de datos (ingesta, limpieza, transformacion, orquestador, API REST, tests E2E) | specs/pipeline-datos.md | design/pipeline-datos.md | tasks/pipeline-datos.md | done | L |
| 2 | Modelo clasificacion radiografias (Sana/Neumonia/COVID) con Keras/TensorFlow (CNN: Conv2D + MaxPooling2D + Dropout + Dense + EarlyStopping, segun Bloque 6 del Master) — ver ADR-003, ADR-005, ADR-006 | specs/clasificacion-radiografias.md | design/clasificacion-radiografias.md | tasks/clasificacion-radiografias.md | done | L |
| 3 | API REST (servir predicciones y datos) | specs/api-rest.md | design/api-rest.md | tasks/api-rest.md | done (cubierto en T10 del pipeline) | M |
| 4 | Dashboard de visualizacion (Streamlit) — ver ADR-007 | specs/dashboard.md | design/dashboard.md | tasks/dashboard.md | done | M |
| 5 | Automatizacion de procesos (alertas + informes + watcher como servicio) | specs/automatizacion.md | design/automatizacion.md | tasks/automatizacion.md | partial (watcher como servicio Docker + bootstrap on `up` ✓; alertas e informes pendientes) | M |
| 6 | Monitorizacion y calidad de datos (logging centralizado + validacion + alertas) | specs/monitorizacion.md | design/monitorizacion.md | tasks/monitorizacion.md | partial (logging + validacion ✓; alertas pendientes) | M |
| 7 | Evaluacion clinica del modelo (matriz confusion + analisis de errores) | specs/evaluacion-clinica.md | design/evaluacion-clinica.md | tasks/evaluacion-clinica.md | pending | S |
| 8 | Memoria tecnica (descripcion, datos, arquitectura, modelos, integraciones) | — | — | — | pending | L |
| 9 | Consideraciones eticas y legales (sesgos, privacidad, riesgos, limitaciones) | — | — | — | pending | S |
| 10 | Justificaciones tecnicas y reflexion critica (limitaciones, mejoras) | — | — | — | pending | S |
| 11 | Diario de desarrollo con IA (documento vivo — se actualiza cada sesion) | — | — | — | in-progress | M |
| 12 | Presentacion final (10-15 min) | — | — | — | pending | S |
| 13 | Almacenamiento SQL para metadatos del pipeline (SQLite + SQLAlchemy, alineado con Bloque 7 de Eric) | specs/sqlite-pipeline-metadata.md | design/sqlite-pipeline-metadata.md | tasks/sqlite-pipeline-metadata.md | done | M |

Estados: pending | spec-done | design-done | tasks-done | in-progress | done
Tamanos: S (< 1 dia) | M (1-3 dias) | L (> 3 dias)

## Notas

- **Feature 11 (Diario IA)** — Es un documento vivo que se actualiza cada sesion de trabajo. Entregable OBLIGATORIO segun el enunciado.
- **Feature 6 (Monitorizacion)** — Se construye incrementalmente con el pipeline. Incluye logging, validacion de calidad (rejected_records) y alertas.
- **Feature 7 (Evaluacion clinica)** — Separada del modelo porque el enunciado da peso especifico al "Porque" del modelo (matriz de confusion, impacto de errores desde punto de vista medico).
- **Features 8-10, 12** — Documentacion final y presentacion, se abordan en las ultimas semanas.
