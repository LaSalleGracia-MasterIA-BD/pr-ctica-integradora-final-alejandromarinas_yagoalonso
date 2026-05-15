# ADR-001: Stack tecnologico del proyecto

> Estado: accepted (parcialmente superado)
> Fecha: 2026-04-14
> Superseded by: [ADR-003](ADR-003-keras-tensorflow.md) en el punto "Deep Learning: PyTorch" → cambiado a Keras/TensorFlow tras auditar el temario del Master (la asignatura usa TensorFlow, no PyTorch)

## Contexto
El enunciado requiere un framework de procesamiento distribuido y un modelo de Deep Learning para clasificacion de radiografias. Hay que elegir tecnologias concretas.

## Decision
- **Procesamiento distribuido:** PySpark
- **Deep Learning:** PyTorch
- **Dataset:** COVID-19 Radiography Database (Kaggle, Qatar University + University of Dhaka)
- **API:** FastAPI
- **BBDD clinica:** MongoDB
- **Almacenamiento objetos:** MinIO (compatible S3)
- **Infraestructura:** Docker + Docker Compose

## Alternativas consideradas

| Opcion | Pros | Contras |
|--------|------|---------|
| PySpark (elegida) | Estandar industria, demuestra principios Big Data reales, muy valorado | Mas pesado en Docker |
| Dask | Ligero, pythonico, facil setup | Menos reconocido como "Big Data real" |
| Apache Beam | Batch + streaming unificado | Overkill para el scope del proyecto |

| Opcion | Pros | Contras |
|--------|------|---------|
| PyTorch (elegida) | Dominante en investigacion, debug intuitivo, flexible | Deploy mas manual |
| TensorFlow/Keras | TF Serving, Keras simple | Menos flexible para investigar |

## Consecuencias
- (+) PySpark impresiona a evaluadores de Big Data
- (+) PyTorch da flexibilidad para la investigacion que pide el enunciado
- (+) FastAPI + MongoDB + MinIO son stack moderno y conocido por el equipo
- (-) PySpark requiere mas RAM en Docker (JVM)
- (-) PyTorch requiere configurar inference server manualmente

## Requisitos relacionados
- Pipeline de datos a escala (ingesta, almacenamiento, procesamiento, servicio)
- Modelo de clasificacion triple de radiografias (Sana/Neumonia/COVID-19)
