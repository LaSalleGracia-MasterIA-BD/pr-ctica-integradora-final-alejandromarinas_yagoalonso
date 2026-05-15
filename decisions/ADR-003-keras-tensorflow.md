# ADR-003: Keras/TensorFlow como framework de Deep Learning (en lugar de PyTorch)

> Estado: accepted
> Fecha: 2026-05-16
> Supersede (parcialmente): ADR-001 — solo en el punto "Deep Learning: PyTorch"

## Contexto

El ADR-001 escogio PyTorch como framework de Deep Learning por motivos
genericos del ecosistema (debug intuitivo, flexibilidad para investigacion).

Auditando el temario real del Master (carpeta `TEMARIO MASTER IA Y BIG DATA`)
contra nuestras decisiones tecnicas, se detecta que:

- El `requirements.txt` de la asignatura de Aprenentatge Automatic (Jordi)
  lista explicitamente `tensorflow` como dependencia
- El Bloque 6 (Xarxes Neuronals) esta integramente construido con
  `keras.Sequential`, `keras.layers.Conv2D`, `keras.layers.MaxPooling2D`,
  `keras.layers.Dense`, `keras.layers.Dropout`, `keras.callbacks.EarlyStopping`
- La sesion 3 de ese bloque (Overfitting i CNN) entrena una CNN sobre
  Fashion MNIST con esta API exacta
- No hay material de PyTorch en ninguna sesion del Master

El enunciado del proyecto exige "Desarrollo Asistido por IA" y SDD, pero
tambien remarca que el proyecto se aborda "como un desarrollo real en un
entorno profesional" donde "se valora justificar decisiones tecnicas" y donde
cada bloque tiene un profesor responsable de su evaluacion.

Adicionalmente, el dataset del modelo cambio del COVID-19 Radiography
Database (radiografias toracicas) a un dataset de **radiografias de
implantes dentales** (~9.000 imagenes, ~1.800 de implantes) anunciado por
el profesor Jordi en clase. El enunciado formal de ese dataset esta
pendiente.

## Decision

Cambiar el framework de Deep Learning del proyecto de **PyTorch** a
**Keras/TensorFlow**:

- Modelo: `keras.Sequential` con CNN basica (`Conv2D + MaxPooling2D +
  Dropout + Dense`), patron identico al visto en Bloque 6 · Sesion 3
- Regularizacion: `Dropout` + `EarlyStopping` (callback)
- Evaluacion: matriz de confusion + analisis clinico del error (lo que el
  profesor Jordi ha indicado que pesara mas en la nota que el accuracy)
- Preprocesado de imagenes: normalizacion `pixels / 255.0` + redimensionado,
  igual que la sesion de Fashion MNIST
- Loss: `sparse_categorical_crossentropy` para clases con etiqueta entera

El resto del stack (PySpark, MongoDB, MinIO, FastAPI, Docker Compose) se
mantiene tal como esta en ADR-001 — encaja con lo enseñado en la asignatura
de Big Data (Eric).

## Alternativas consideradas

| Opcion | Pros | Contras |
|--------|------|---------|
| Keras/TensorFlow (elegida) | Coincide 1:1 con el material de clase. El profesor reconocera patrones e identificara la trazabilidad con sus sesiones. Documentacion del bloque 6 directamente reutilizable como justificacion en la memoria tecnica | Algo menos flexible que PyTorch para investigacion experimental |
| PyTorch (descartada) | Estandar de la investigacion academica moderna, mas pythonico | NO hay material de clase. El profesor no podra ligarlo a su temario. Curva de aprendizaje adicional con 4 dias para deadline. Sin material propio se pierde la trazabilidad clase → proyecto |
| Mantener ambos | Aprendizaje extra | Sobreingeniera evidente para un proyecto de master. Doble mantenimiento sin valor añadido |

## Consecuencias

- (+) Trazabilidad directa: cada capa del modelo se puede citar con la
  sesion del Master donde se vio
- (+) Memoria tecnica mas defendible: "siguiendo el patron Conv2D + MaxPooling
  + Dense + Dropout enseñado en Bloque 6 · Sesion 3"
- (+) Permite usar `EarlyStopping` y el analisis de "tijera" train/val loss
  exactamente como se enseño en clase
- (+) Cero coste de cambio: el modelo aun no esta implementado, no hay codigo
  PyTorch que migrar
- (-) Si en el futuro queremos transfer learning con modelos pre-entrenados de
  PyTorch Hub, habria que reconsiderar (no aplica al scope actual)

## Notas de implementacion

Cuando se arranque la feature 2 del backlog (modelo de clasificacion):

1. Anadir `tensorflow` (o `tensorflow-cpu` si la imagen Docker se hace muy
   grande) a `requirements-pipeline.txt`
2. Crear `src/ml/` con la estructura: `dataset.py` (carga + preprocesado),
   `model.py` (definicion CNN), `train.py` (entrenamiento), `evaluate.py`
   (matriz confusion + analisis clinico), `inference.py` (servir
   predicciones desde la API)
3. El modelo entrenado se guarda en `data/models/<version>.keras` (no
   committeado al repo por tamaño — ver runbook a crear)
4. La API gana un endpoint `POST /api/v1/predict` que recibe el
   `minio_object_key` de una radiografia ya en MinIO, descarga la imagen,
   la pasa por el modelo y devuelve la clasificacion

## Requisitos relacionados

- Modelo de clasificacion de radiografias (feature 2 del backlog)
- Evaluacion clinica del modelo (feature 7 del backlog)
- Justificaciones tecnicas en memoria tecnica (entregable obligatorio)
