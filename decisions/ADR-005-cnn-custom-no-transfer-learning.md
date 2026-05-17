# ADR-005: CNN custom desde cero para clasificacion de radiografias (sin transfer learning)

> Estado: accepted
> Fecha: 2026-05-16
> Supersede: —

## Contexto

La feature `clasificacion-radiografias` (spec aprobada el 2026-05-16)
requiere un modelo de Deep Learning que clasifique radiografias de
torax en tres clases (Normal / Pneumonia / COVID-19). El proyecto ya
fijo en **ADR-003** que el framework es **Keras/TensorFlow** alineado
con el Bloque 6 del Master (asignatura de Aprendizaje Automatico,
profesor Jordi). Lo que ese ADR NO fija es la arquitectura concreta
del modelo.

Hay dos caminos estandar para esta tarea:

- **A. CNN custom desde cero**: Conv2D + MaxPool + Dropout + Dense
  con pesos inicializados aleatoriamente, entrenada solo con el dataset
  COVID-19 Radiography Database
- **B. Transfer learning**: tomar una red pre-entrenada en ImageNet
  (MobileNetV2, ResNet50, EfficientNetB0) y ajustar las ultimas capas
  para nuestras 3 clases

Transfer learning suele dar mejor accuracy con menos datos en problemas
de vision generales. Pero para radiografias hay matices: ImageNet
contiene fotografias RGB del mundo real, no imagenes medicas
monocromaticas — la transferencia no es tan limpia como suele
asumirse.

## Decision

**Usar una CNN custom desde cero**, sin transfer learning. La
arquitectura sigue **literalmente** el patron que ensena Jordi en el
Bloque 6 del Master: **Conv2D + MaxPooling2D + Dropout + Flatten +
Dense + softmax**.

```
Input (224x224x1, grayscale)
  → Conv2D(32, 3x3, relu, padding="same")  → MaxPool(2x2)  # → 112x112x32
  → Conv2D(64, 3x3, relu, padding="same")  → MaxPool(2x2)  # →  56x56x64
  → Conv2D(128, 3x3, relu, padding="same") → MaxPool(2x2)  # →  28x28x128
  → Conv2D(128, 3x3, relu, padding="same") → MaxPool(2x2)  # →  14x14x128
  → Dropout(0.5)
  → Flatten                                                 # → 25088
  → Dense(64, relu)                                         # ~1.6M params
  → Dropout(0.3)
  → Dense(3, softmax)
```

**`padding="same"`** en las 4 Conv2D es deliberado: garantiza que la
reduccion espacial venga solo de los MaxPool (224 → 112 → 56 → 28 → 14),
dejando dimensiones enteras a cada paso. Con `padding="valid"` (default
de Keras) las conv 3x3 quitan 2 px por lado y los MaxPool generarian
tamanos impares que complican el calculo y los conteos del design.

Aproximadamente **1.8M parametros** (~1.6M en el Dense post-Flatten +
~200K en las 4 conv), peso en disco **~7-8 MB** en formato `.keras`.
Sigue holgadamente bajo el limite de 50 MB (RNF-4).

**Por que Flatten y no GlobalAveragePooling2D**: el patron docente del
Master (Jordi, Bloque 6) usa Flatten antes del Dense final. Mantener
la estructura literal del temario es importante para que la memoria
tecnica y la defensa se apoyen 1:1 en lo aprendido en clase. GAP daria
un modelo mas pequeno pero introduciria una operacion que el evaluador
no ha visto en este bloque del Master.

## Alternativas consideradas

| Opcion | Pros | Contras |
|--------|------|---------|
| **CNN custom desde cero (elegida)** | Alineacion 1:1 con el Bloque 6 del Master (lo que ensena Jordi: Conv2D + MaxPooling2D + Dropout + Flatten + Dense + softmax). Modelo dentro del limite (~7-8 MB, < 50 MB de RNF-4). Sin asunciones de imagenes RGB ImageNet. Reproducible. Tiempo de entrenamiento manejable (~1-3h en CPU) | Accuracy potencialmente menor que transfer learning. Mayor riesgo de overfitting si el dataset es pequeno tras descartar Lung_Opacity. Flatten genera un Dense con muchos params (mitigado con Dropout 0.5 previo y 0.3 posterior) |
| Transfer learning MobileNetV2 | Suele dar +3-7% de accuracy. Convergencia rapida. Menos epochs | Requiere convertir grayscale → RGB (replicar canal). Modelo mas grande (~10 MB MobileNetV2 base). Mayor latencia inferencia. Menos alineacion con lo que pide el Master |
| Transfer learning ResNet50 | Mas capacidad. Buenos resultados en literatura medica | Modelo grande (~100 MB), excede el limite de RNF-4. Latencia >3s en CPU posible (excede RNF-3) |
| Fine-tuning de DenseNet121 con CheXNet weights | Pesos pre-entrenados especificos de torax | Dependencia externa no garantizada, peso > 50 MB |

## Consecuencias

**Positivas:**
- (+) **Defendible academicamente**: la arquitectura es exactamente lo
  que ensena el Bloque 6 (Jordi). El analisis del modelo en la memoria
  tecnica se apoya directamente en lo aprendido en clase, sin
  dependencias externas que no se han visto
- (+) **Modelo dentro del limite**: ~7-8 MB cabe sobrado en el repo
  (< 50 MB de RNF-4). El evaluador clona y todo funciona sin pasos
  extra
- (+) **Inferencia rapida**: ~50-200 ms por imagen en CPU. Holgado bajo
  RNF-3 (< 3s)
- (+) **Sin dependencias adicionales**: no hay que descargar pesos
  pre-entrenados externos al arrancar
- (+) **Determinismo**: con seed fija + `enable_op_determinism`, la
  reproducibilidad es alcanzable. Transfer learning anade variabilidad
  del orden en que se carguen los pesos pre-entrenados

**Negativas:**
- (-) **Accuracy potencialmente menor**: en la practica esto es
  aceptable porque el criterio de evaluacion (RNF-2 de la spec) NO es
  accuracy bruta sino recall por clase + analisis clinico. Una CNN
  custom razonable alcanza el rango ~0.85-0.93 accuracy en este
  dataset, lo que ya permite un analisis clinico significativo
- (-) **Mayor riesgo de overfitting**: mitigado con Dropout (0.5 y
  0.3), data augmentation moderada, EarlyStopping con `patience=5`
  monitorizando `val_loss` y `class_weight` por desbalance (CB-6)
- (-) **Hay que entrenar mas epochs** que con transfer learning para
  llegar a un buen estado: ~15-25 epochs efectivas vs ~5-10 con
  transfer. Compensado porque cada epoch es mas barata (red mas
  pequena)

## Requisitos relacionados

- **Spec `clasificacion-radiografias`:** RNF-1 (Keras/TF + arquitectura
  alineada con Bloque 6), RNF-3 (<3s inferencia), RNF-4 (<50 MB),
  RNF-5 (reproducibilidad), CB-6 (clases desbalanceadas)
- **ADR-003:** fija Keras/TF como framework. Este ADR es su
  continuacion (define la arquitectura concreta)

## Notas

Si despues de entrenar y evaluar la matriz de confusion resulta que
el recall de COVID-19 o Pneumonia es **inaceptable clinicamente**
(p. ej. < 0.70), se reabre esta decision en un ADR posterior. La
alternativa mas inmediata seria probar transfer learning con
MobileNetV2 (input 224x224x3 replicando canal) como contingencia.
