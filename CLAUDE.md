# Sistema Inteligente de Soporte Hospitalario

## Que es
Sistema de IA para el hospital ficticio laSalle Health Center que clasifica radiografias de torax (Sana/Neumonia/COVID-19), procesa datos clinicos a escala y automatiza procesos hospitalarios.

## Equipo
- Alejandro Marinas
- Yago (companero de proyecto)

## Stack
- **Backend/API:** Python (FastAPI)
- **Pipeline de datos:** PySpark
- **ML/Deep Learning:** Keras/TensorFlow (CNN: Conv2D + MaxPooling2D + Dropout + Dense, con EarlyStopping). Ver ADR-003
- **Base de datos:** MongoDB (datos clinicos) + MinIO (imagenes/objetos)
- **Dataset:** COVID-19 Radiography Database (Kaggle)
- **Dashboard:** Streamlit
- **Infraestructura:** Docker + Docker Compose
- **Monitorización:** Logging centralizado con Python logging + rejected_records en MongoDB

## Estructura de modulos

| Modulo | Carpeta | Responsabilidad |
|--------|---------|----------------|
| API | `src/api/` | Endpoints REST para servir predicciones y datos |
| Pipeline | `src/pipeline/` | Ingesta, limpieza, transformacion de datos |
| ML | `src/ml/` | Modelo de clasificacion de radiografias |
| Dashboard | `src/dashboard/` | Visualizacion de resultados y metricas |
| Automation | `src/automation/` | Alertas, informes automaticos, procesamiento |

## Como ejecutar
```bash
docker-compose up --build
```

## Reglas especificas
- Datos sanitarios: siempre considerar privacidad y etica
- Clasificacion triple: Sana / Neumonia / COVID-19
- El modelo se evalua por criterio clinico, no solo accuracy
- Toda decision tecnica debe estar justificada en `decisions/`
- Diario de desarrollo con IA obligatorio en `docs/diario-ia.md`

## Workflow
Este proyecto sigue SDD Kit (ver rules/sdd-kit/README.md).
- Specs en `specs/`
- Designs en `design/`
- Tasks en `tasks/`
- Decisiones tecnicas en `decisions/`
- Backlog en `tasks/backlog.md`
- Changelog en `CHANGELOG.md`
- Runbooks en `docs/runbooks/`
- Antes de implementar: verificar que existen spec, design y tasks aprobados
