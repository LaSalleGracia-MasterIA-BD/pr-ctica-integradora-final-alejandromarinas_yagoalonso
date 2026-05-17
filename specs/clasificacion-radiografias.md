# Spec: Clasificacion de radiografias de torax (Sana / Neumonia / COVID-19)

> Estado: approved
> Ultima actualizacion: 2026-05-16

## Contexto y problema

El sistema hospitalario laSalle Health Center recibe radiografias de torax
de los pacientes. Hoy las imagenes se almacenan en MinIO y sus metadatos
se embeben en el documento del paciente en MongoDB con el campo
`classification` siempre a `null`: el pipeline las acepta y persiste,
pero **no las clasifica**. El enunciado del proyecto pide un modelo de
Deep Learning capaz de distinguir entre **Sana / Neumonia / COVID-19**
a partir de una radiografia, y que la prediccion alimente el sistema
(dashboard, API y flujos de alertas pueden razonar sobre la clase
clinica predicha).

Memoria del 2026-05-06: el profesor Jordi anuncio en clase que el
dataset iba a cambiar a radiografias dentales (implantes), pero a
2026-05-16 no ha publicado el enunciado formal. Con la entrega el
2026-05-20 (4 dias) se confirma seguir con el plan original — dataset
**COVID-19 Radiography Database** de Kaggle.

Lo que mas pesa en la evaluacion del modelo NO es la accuracy en bruto
sino el **analisis de la matriz de confusion bajo criterio clinico**:
¿que tipo de error es mas grave (decirle a un paciente con COVID que
esta sano vs. decirle a un sano que tiene COVID)? El recall de las
clases con consecuencia clinica grave (COVID-19, Pneumonia) pesa mas
que la accuracy global. Lo recoge la asignatura de Aprendizaje
Automatico (Bloque 6, Jordi).

## Objetivo

Entregar un modelo de clasificacion de radiografias de torax en tres
clases (Sana / Neumonia / COVID-19) entrenado sobre el COVID-19
Radiography Database, mas la integracion necesaria para que su
prediccion alimente el sistema:

- Se puede solicitar la clase para una radiografia concreta via API REST
- La prediccion se persiste en MongoDB
  (`patients.radiographies[].classification`) con su nivel de confianza
- Existen metricas de evaluacion clinica visibles: matriz de confusion,
  precision/recall por clase (con foco en COVID-19 y Pneumonia),
  macro-F1, accuracy global, y un analisis cualitativo de los errores

## Actores y alcance

**Usuarios:**
- Personal clinico (radiologo, medico): consume la prediccion como
  **asistencia diagnostica**, no como diagnostico final
- Dashboard (visualizara distribucion de clases por paciente y agregada)
- Evaluador del proyecto: consulta la API y el reporte del modelo
- Developer/data-scientist: entrena y evalua el modelo offline

**Dentro del alcance:**
- Entrenamiento offline de un modelo CNN sobre el dataset descargado
- Persistencia del modelo entrenado en `data/models/` como artefacto
  local del proyecto
- Carga del modelo en el proceso de la API al arrancar
- Endpoint REST para inferir la clase de una radiografia ya almacenada
  en MinIO
- Endpoint REST para leer la clasificacion ya persistida (cache de la
  prediccion)
- Persistencia de la prediccion en MongoDB con clase + probabilidades
  + timestamp + version del modelo
- Reporte de evaluacion clinica: matriz de confusion, precision/recall
  por clase, macro-F1, accuracy, curva de aprendizaje, hiperparametros
  y analisis cualitativo de errores
- Tests automatizados: smoke test de inferencia + invariantes
  (formato de salida, manejo de errores, idempotencia)

**Fuera del alcance:**
- Disparo automatico de la clasificacion al ingerir nuevas imagenes
  (bootstrap/watcher). **Mejora opcional documentada** — solo si sobra
  tiempo al final
- Endpoint batch `classify-all`. Con el individual basta para la entrega.
  Un batch complicaria tiempos de respuesta, gestion de errores parciales
  y estado intermedio
- Diagnostico medico vinculante (el modelo es asistencia, no decision)
- Deteccion out-of-domain (rechazar imagenes que NO son radiografias
  de torax). Se asume que solo entran radiografias en el sistema
- Interpretabilidad/explainability (Grad-CAM, mapas de saliencia)
- Re-entrenamiento automatico / online learning. Entrenamiento es
  batch, offline; un solo modelo congelado para la entrega
- Inferencia masiva en background al arrancar la API sobre todo el
  bucket

## Requisitos funcionales

- **RF-1:** Existe un script reproducible (`src/ml/train.py` o
  equivalente) que, dada la presencia del dataset descargado en disco,
  entrena un modelo CNN y produce como salida (a) un artefacto del
  modelo entrenado en formato Keras nativo (`.keras` o `.h5`) en
  `data/models/` y (b) un fichero de reporte de evaluacion en el mismo
  directorio (o en `docs/`, ver design)
- **RF-2:** El reporte de evaluacion incluye al menos:
  - Accuracy global sobre el split de **test**
  - **Macro-F1** sobre el split de **test**
  - Matriz de confusion 3x3 con conteos absolutos, sobre el split de **test**
  - **Precision, recall y F1 por clase, con foco explicito en el recall
    de COVID-19 y Pneumonia** (los FN clinicamente graves), sobre **test**
  - Curva de aprendizaje (loss y accuracy por epoch para train y val,
    procedente del `CSVLogger` durante el entrenamiento)
  - Listado de hiperparametros usados (lr, batch_size, epochs, seed,
    arquitectura)
  - Analisis cualitativo: parrafo razonando si las metricas obtenidas
    son **clinicamente aceptables**, especialmente desde el punto de
    vista del recall de las clases graves
  - **Regla:** el split de **validation** se usa durante el
    entrenamiento (EarlyStopping, ModelCheckpoint, ajuste de
    hiperparametros) y **no entra** en el reporte final. El split de
    **test** solo se evalua una vez, al final, y produce las metricas
    del reporte
- **RF-3:** El split del dataset es:
  - Si el dataset descargado trae un split oficial claro (train/val/test
    o train/val) → se usa ese y se documenta en el reporte
  - Si no trae split oficial → se hace **estratificado por clase
    80/10/10 con seed fija**, documentada en el reporte para
    reproducibilidad
- **RF-4:** Al arrancar la API, se intenta cargar el artefacto del
  modelo desde `data/models/`. Si esta disponible, los endpoints de
  clasificacion responden normalmente. Si no, la API arranca igualmente
  pero los endpoints de clasificacion devuelven `503 Service Unavailable`
  con mensaje claro
- **RF-5:** Existe un endpoint `POST /api/v1/radiographies/classify`
  que recibe en el body JSON la `minio_object_key`
  (p. ej. `{"minio_object_key": "HOSP-000001/HOSP-000001_xray1.png"}`)
  y:
  - Descarga la imagen de MinIO
  - La preprocesa con la misma pipeline que el entrenamiento (resize,
    normalizacion)
  - Devuelve la clase predicha + probabilidades de las 3 clases
  - Actualiza el campo `classification` en MongoDB para esa radiografia
  - **Por que body y no path param:** la `minio_object_key` contiene
    `/`. Meterla en path obliga a usar `{key:path}` y complica
    clientes, herramientas y escape de caracteres especiales
- **RF-6:** Existe un endpoint `GET /api/v1/radiographies/classification?key=...`
  que recibe la `minio_object_key` como query param y devuelve la
  clasificacion ya persistida (sin re-inferir). Si no hay clasificacion
  guardada para esa key devuelve `404 Not Found`. Si `key` esta ausente
  o vacio devuelve `422 Unprocessable Entity`
- **RF-7:** El campo `patients.radiographies[].classification` en
  MongoDB pasa de `null` a una estructura con:
  - `predicted_class`: una de `{"Normal", "Pneumonia", "COVID-19"}`
    (NO se usa `class` como nombre de campo porque colisiona con la
    palabra reservada de Python)
  - `probabilities`: dict `{clase: float}` con suma ≈ 1.0
  - `predicted_at`: timestamp ISO en UTC
  - `model_version`: string identificador del artefacto usado
- **RF-8:** No hay endpoint batch. Solo el endpoint individual de RF-5

## Requisitos no funcionales

- **RNF-1:** El stack tecnologico es **Keras / TensorFlow** (CNN:
  Conv2D + MaxPooling2D + Dropout + Dense con EarlyStopping), alineado
  con el Bloque 6 del Master (Aprendizaje Automatico, Jordi). Ver
  ADR-001 y nota en CLAUDE.md
- **RNF-2:** **No hay umbral bloqueante de accuracy.** El criterio
  clinico (recall por clase, especialmente COVID-19 y Pneumonia)
  prevalece. La accuracy global y la macro-F1 son **orientativas**: se
  reportan en el reporte de evaluacion para tener contexto, pero el
  juicio "modelo aceptable / no aceptable" se argumenta en el analisis
  cualitativo, no con un threshold numerico unico
- **RNF-3:** La inferencia individual via API responde en menos de
  3 segundos en una maquina de desarrollo media (sin GPU)
- **RNF-4:** El modelo entrenado vive en `data/models/`. Si pesa menos
  de 50 MB se commitea al repo para que el evaluador clone y todo
  funcione sin pasos extra (requiere ajustar `.gitignore` que hoy
  ignora `data/models/*`; queda registrado para la fase de diseño /
  implementacion). Si pesa mas, se ignora y se documenta como
  regenerarlo a partir del script de entrenamiento
- **RNF-5:** El entrenamiento es reproducible: misma seed → misma
  matriz de confusion dentro de la tolerancia de no-determinismo de TF
  (operaciones de GPU/CPU no siempre deterministas al 100% incluso con
  seed)
- **RNF-6:** Los datos sanitarios procesados deben mantener la
  privacidad: el dataset publico ya viene anonimizado, y la API no
  expone bytes de imagenes en sus respuestas (solo metadatos +
  clasificacion)

## Casos borde y errores

- **CB-1:** Dataset no descargado al lanzar el entrenamiento → error
  explicito con instrucciones (referencia al runbook
  `docs/runbooks/download-radiography-dataset.md`)
- **CB-2:** Imagen referenciada no existe en MinIO al pedir
  clasificacion → 404 con mensaje claro
- **CB-3:** Imagen corrupta o de canales/dimensiones inesperados (RGBA,
  16-bit, no-PNG) → o se convierte al formato esperado, o se rechaza
  con `4xx` claro (NO 500)
- **CB-4:** Modelo no disponible al arrancar la API (artefacto ausente)
  → API arranca normal; `/health` responde 200; endpoints de
  clasificacion devuelven 503 con mensaje claro; el resto de endpoints
  (`/patients`, `/admissions`, `/radiographies`, `/pipeline/*`) siguen
  funcionando
- **CB-5:** Dos peticiones simultaneas de `/classify` sobre la misma
  radiografia → la ultima escritura gana en MongoDB. La inferencia es
  deterministica, asi que el contenido es identico; el unico campo que
  puede cambiar es `predicted_at`
- **CB-6:** Clases muy desbalanceadas en el dataset (el COVID-19
  Radiography Database tiene mas Normal que COVID-19) → el entrenamiento
  debe contemplarlo (p. ej. `class_weight` o oversampling) para que el
  recall de las clases minoritarias no se hunda
- **CB-7:** Imagen muy pequena o muy grande comparada con el input del
  modelo → se redimensiona al input esperado; si la imagen es < 32 px
  por lado se rechaza con 4xx (probablemente no es una radiografia
  valida)

## Dudas abiertas

Ninguna. Las 6 dudas iniciales se cerraron en la revision del 2026-05-16:

1. Disparo de la clasificacion → solo bajo peticion via API
2. Umbral de accuracy → eliminado como bloqueante; metricas
   orientativas + analisis clinico cualitativo (RNF-2)
3. Persistencia del modelo → `data/models/`, commiteado si < 50 MB
4. Split → 80/10/10 estratificado con seed fija, salvo que el dataset
   traiga split oficial
5. Endpoint batch → fuera del alcance
6. Campo `classification` en MongoDB → objeto completo con
   `predicted_class` (no `class`), `probabilities`, `predicted_at`,
   `model_version`

## Criterios de aceptacion

- [ ] **CA-1** (RF-1): Existe el comando reproducible para entrenar.
  Tras ejecutarlo con el dataset descargado, se genera el artefacto del
  modelo en `data/models/` + el fichero de reporte
- [ ] **CA-2** (RF-2): El reporte contiene **accuracy, macro-F1, matriz
  de confusion 3x3, precision/recall/F1 por clase, curva de aprendizaje
  e hiperparametros**. El recall de COVID-19 y Pneumonia aparece
  destacado
- [ ] **CA-3** (RF-2, RNF-2 — criterio clinico): El reporte incluye un
  parrafo de **analisis cualitativo** que razona si las metricas
  obtenidas son clinicamente aceptables, justificando explicitamente
  el comportamiento del modelo en los falsos negativos de COVID-19 y
  Pneumonia (los errores de mayor consecuencia clinica)
- [ ] **CA-4** (RF-3): El reporte documenta como se ha hecho el split
  del dataset (oficial si existe; o estratificado 80/10/10 con seed
  fija)
- [ ] **CA-5** (RF-4, RF-5): Tras `docker compose up` con el artefacto
  del modelo disponible, `POST /api/v1/radiographies/classify` con
  body `{"minio_object_key": "..."}` para una radiografia existente
  devuelve clase + probabilidades en menos de 3s y persiste el
  resultado en MongoDB con la estructura de RF-7
- [ ] **CA-6** (RF-6, RF-7): `GET /api/v1/radiographies/classification?key=...`
  devuelve el objeto persistido tal cual (con `predicted_class`,
  `probabilities`, `predicted_at`, `model_version`); sin clasificacion
  previa devuelve 404; sin `key` o vacio devuelve 422
- [ ] **CA-7** (CB-4): Si el artefacto del modelo NO esta disponible,
  la API arranca y `/health` responde 200; los endpoints de
  clasificacion devuelven 503 con mensaje claro; el resto de endpoints
  (`/patients`, `/admissions`, `/radiographies`, `/pipeline/*`) siguen
  funcionando
- [ ] **CA-8** (CB-2): Pedir clasificacion para una `minio_object_key`
  inexistente devuelve 404 con mensaje claro
- [ ] **CA-9** (CB-3): Pedir clasificacion para una imagen corrupta
  devuelve 4xx con mensaje claro (no 500)
- [ ] **CA-10** (RNF-5): Re-ejecutar el entrenamiento con la misma seed
  produce la misma matriz de confusion (dentro de tolerancia de
  no-determinismo de TF)

## Criterios clinicos (anexo)

Para el bloque de "criterio clinico" que pesa en la nota, la matriz de
confusion 3x3 tiene 6 tipos de error. El analisis cualitativo del
reporte (CA-3) debe razonar cual de estos es mas grave y argumentar,
con la matriz real obtenida en validacion, si el modelo entregado es
aceptable bajo ese criterio.

| Real \ Predicha | Sana | Neumonia | COVID-19 |
|---|---|---|---|
| **Sana** | OK | FP Neumonia (falsa alarma menor) | FP COVID (alarma mayor) |
| **Neumonia** | FN Neumonia (grave: no se detecta una neumonia) | OK | Confusion COVID/Neumonia (riesgo epidemiologico) |
| **COVID-19** | FN COVID (muy grave: alta sin aislar) | Confusion Neumonia/COVID (riesgo epidemiologico) | OK |

Hipotesis a defender (pendiente de validar con la matriz real): los
**FN COVID** (paciente COVID clasificado como Sano) son el error mas
grave en el contexto hospitalario, porque implican no aislar a un
contagioso. Por debajo, los **FN Pneumonia** y las **confusiones
COVID/Pneumonia** tambien tienen impacto. Los FP (sano clasificado
como enfermo) son menos graves: generan pruebas adicionales pero no
ponen en riesgo al paciente ni al hospital. Esto justifica que el
recall de las clases minoritarias prevalezca sobre la accuracy global,
y que el reporte ponga el foco en esas metricas (RF-2).

## Notas tecnicas para fases siguientes (no son requisitos)

- `.gitignore` hoy contiene `data/models/*` con excepcion solo de
  `.gitkeep`. Si se decide commitear el modelo (RNF-4, < 50 MB), hay
  que anadir excepcion para `data/models/*.keras` o el formato
  elegido. Lo aborda `/planificar` o `/implementar`
- Hay un runbook ya existente: `docs/runbooks/download-radiography-dataset.md`.
  Conviene revisarlo y actualizarlo si la URL/instrucciones cambian
- El campo `classification` en MongoDB hoy se persiste como `None` al
  insertar metadatos en `bootstrap.py`. El cambio a objeto no rompe
  nada: el cambio se aplica al persistir la prediccion, los `None`
  existentes siguen siendo validos

## Changelog

| Fecha | Cambio | Motivo | Fase |
|-------|--------|--------|------|
| 2026-05-16 | Creacion inicial (draft) | Feature 2 del backlog. Dataset confirmado: COVID-19 Radiography Database (el dataset dental anunciado por Jordi el 06-may no ha llegado a tiempo) | spec |
| 2026-05-16 | 6 dudas cerradas + spec aprobada | Revision con Alejandro: API-only, sin umbral bloqueante de accuracy, modelo en `data/models/`, split 80/10/10 con seed o split oficial, sin endpoint batch, campo Mongo con `predicted_class` | spec |
| 2026-05-16 | Endpoints corregidos y reporte sobre test | (a) RF-5 pasa de `POST /radiographies/{key:path}/classify` a `POST /radiographies/classify` con la key en el body. RF-6 pasa de `GET /radiographies/{key:path}/classification` a `GET /radiographies/classification?key=...`. Motivo: la key contiene `/`. (b) RF-2 deja claro que las metricas del reporte se computan sobre el split de **test**; el split de **validation** solo se usa durante el entrenamiento (EarlyStopping, ModelCheckpoint). CA-5 y CA-6 actualizados | design (back-sync) |
