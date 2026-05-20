# Backlog

| Prioridad | Feature | Spec | Design | Tasks | Estado | Tamano |
|-----------|---------|------|--------|-------|--------|--------|
| 1 | Pipeline de datos (ingesta, limpieza, transformacion, orquestador, API REST, tests E2E) | specs/pipeline-datos.md | design/pipeline-datos.md | tasks/pipeline-datos.md | done | L |
| 2 | Modelo clasificacion radiografias (Sana/Neumonia/COVID) con Keras/TensorFlow (CNN: Conv2D + MaxPooling2D + Dropout + Dense + EarlyStopping, segun Bloque 6 del Master) — ver ADR-003, ADR-005, ADR-006 | specs/clasificacion-radiografias.md | design/clasificacion-radiografias.md | tasks/clasificacion-radiografias.md | done | L |
| 3 | API REST (servir predicciones y datos) | specs/api-rest.md | design/api-rest.md | tasks/api-rest.md | done (cubierto en T10 del pipeline) | M |
| 4 | Dashboard de visualizacion (Streamlit) — ver ADR-007 | specs/dashboard.md | design/dashboard.md | tasks/dashboard.md | done | M |
| 5 | Automatizacion de procesos (alertas + informes + watcher como servicio) | specs/automatizacion.md | design/automatizacion.md | tasks/automatizacion.md | partial (watcher como servicio Docker + bootstrap on `up` ✓; alertas e informes pendientes) | M |
| 6 | Monitorizacion y calidad de datos (logging centralizado + validacion + alertas) | specs/monitorizacion.md | design/monitorizacion.md | tasks/monitorizacion.md | partial (logging + validacion ✓; alertas pendientes) | M |
| 7 | Evaluacion clinica del modelo (matriz confusion + analisis de errores) | specs/evaluacion-clinica.md | design/evaluacion-clinica.md | tasks/evaluacion-clinica.md | done (cubierta por `docs/model-evaluation/report.md` + caps 6, 12 y 14 de `docs/memoria-tecnica.md`) | S |
| 8 | Memoria tecnica (descripcion, datos, arquitectura, modelos, integraciones) | — | — | — | done (borrador integrado en `docs/memoria-tecnica.md`, 17 capitulos) | L |
| 9 | Consideraciones eticas y legales (sesgos, privacidad, riesgos, limitaciones) | — | — | — | done (integrado como cap 14 de `docs/memoria-tecnica.md`) | S |
| 10 | Justificaciones tecnicas y reflexion critica (limitaciones, mejoras) | — | — | — | done (integrado como cap 13 + tabla de ADRs en cap 9 de `docs/memoria-tecnica.md`) | S |
| 11 | Diario de desarrollo con IA (documento vivo — se actualiza cada sesion) | — | — | — | in-progress | M |
| 12 | Presentacion final (10-15 min) | — | — | — | done (12 slides de contenido + slide Q&A en `docs/presentation/presentation.html` con reveal.js + guion en notas del presentador + preflight y plan B en `docs/presentation/README.md` + fallback offline en `docs/presentation/fallback.md`) | S |
| 13 | Almacenamiento SQL para metadatos del pipeline (SQLite + SQLAlchemy, alineado con Bloque 7 de Eric) | specs/sqlite-pipeline-metadata.md | design/sqlite-pipeline-metadata.md | tasks/sqlite-pipeline-metadata.md | done | M |
| 14 | Triaje de pacientes en alta manual (sistema basado en reglas, alineado con teoria de Modelos de IA del Master) — ver ADR-008 | specs/triage-pacientes.md | design/triage-pacientes.md | tasks/triage-pacientes.md | done (70 tests verdes nuevos; suite proyecto 344+1 skip; endpoint POST /triage/patients + GET /triage/rules; vista dashboard "Triaje"; buscador por external_id en vista Pacientes) | M |

Estados: pending | spec-done | design-done | tasks-done | in-progress | done
Tamanos: S (< 1 dia) | M (1-3 dias) | L (> 3 dias)

## Notas

- **Feature 11 (Diario IA)** — Es un documento vivo que se actualiza cada sesion de trabajo. Entregable OBLIGATORIO segun el enunciado.
- **Feature 6 (Monitorizacion)** — Se construye incrementalmente con el pipeline. Incluye logging, validacion de calidad (rejected_records) y alertas.
- **Feature 7 (Evaluacion clinica)** — Separada del modelo porque el enunciado da peso especifico al "Porque" del modelo (matriz de confusion, impacto de errores desde punto de vista medico).
- **Features 8-10** — Documentacion final integrada en `docs/memoria-tecnica.md` (caps 1-17).
- **Feature 12** — Presentacion completada en `docs/presentation/` (slides reveal.js + README con preflight + fallback Markdown offline).
