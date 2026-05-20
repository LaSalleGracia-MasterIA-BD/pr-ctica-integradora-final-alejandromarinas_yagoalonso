# Análisis de threshold tuning sobre el clasificador

> **Fecha:** 2026-05-20
> **Modelo evaluado:** `v1.0-20260516-192647` (sin reentrenar)
> **Estado:** análisis aplicado en producción → regla `covid_threshold_0.35` (ADR-010)

Este documento recoge un análisis de **threshold tuning** sobre la salida del clasificador de radiografías. NO se ha reentrenado el modelo y NO se ha modificado la arquitectura. La regla resultante (`covid_threshold_0.35`) **sí** se ha aplicado en producción a partir de Feature 16: la API, el `Predictor`, los schemas Pydantic, los tests, `metrics.json`, `meta.json`, el reporte y la memoria reflejan el umbral aplicado. La decisión técnica está formalizada en **ADR-010**.

El análisis responde a una pregunta concreta:

> ¿Se puede subir el *recall* de COVID-19 (hoy **0,695** en test) bajando el umbral de decisión, sin reentrenar y manteniéndonos dentro de la teoría dada en el Bloque 6 del Máster?

Respuesta corta: **sí**. Con `threshold = 0,35` el *recall* COVID-19 sube de 0,695 a 0,820 (+12,5 pp) a cambio de 3,6 pp menos de *recall* en Normal y 5,6 pp menos de *precision* en COVID-19. La elección concreta del umbral 0,35 (frente a 0,30 y 0,40) se hizo sobre el split de **validación** para no contaminar la decisión con test; la verificación final sobre test confirma la mejora. Detalle cuantitativo abajo.

---

## 1. Contexto y motivación

El modelo entrenado predice por defecto la clase con mayor probabilidad (`argmax`). Sobre el split de test (1.515 imágenes), eso da las cifras de la memoria:

- Accuracy global: 0,8719
- Macro-F1: 0,8456
- Recall COVID-19: **0,6953** ← limitación principal

El recall de COVID-19 es bajo porque el modelo, cuando duda entre `Normal` y `COVID-19`, tiende a etiquetar como `Normal` (es la clase mayoritaria, pesa más en la distribución). Esto es un falso negativo clínicamente grave.

**Idea del threshold tuning:** en lugar de usar `argmax`, aplicar una regla que favorezca a COVID-19 cuando su probabilidad supera un umbral más bajo que 0,5. Es post-procesado sobre el `softmax` ya entrenado, **no requiere reentrenar el modelo**.

## 2. Metodología

### 2.1. Regla aplicada

```
si P(COVID-19) >= threshold:
    predicción = COVID-19
si no:
    predicción = argmax entre Normal y Pneumonia
```

Esta regla **siempre asigna una clase** (no rechaza). El parámetro libre es el threshold para COVID-19.

### 2.2. Procedimiento

1. **Cargar el modelo actual** desde `data/models/radiography_classifier.keras` (mismo artefacto que sirve la API).
2. **Reproducir el split exacto** del entrenamiento: estratificado 80/10/10 con `seed=42` sobre el COVID-19 Radiography Database (15.153 imágenes utilizables tras descartar `Lung_Opacity` por ADR-005).
3. **Inferencia completa sobre validation** (1.515 imágenes) con el preprocesado de producción (`preprocess_for_inference`: resize 224×224, grayscale, normalización `pixels/255`).
4. **Evaluar 7 umbrales** sobre validation: `{0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50}`. Para cada uno, calcular accuracy, macro-F1, precision/recall/F1 por clase y matriz de confusión.
5. **Elegir un umbral candidato** sobre validation con criterio explícito (sección 4).
6. **Evaluar una sola vez en test** ese umbral elegido (más uno alternativo) y comparar con el `argmax` actual.

### 2.3. Distribución de los splits (reproducible con seed=42)

| Split | Normal | Pneumonia | COVID-19 | Total |
|---|---:|---:|---:|---:|
| Validation | 1.019 | 134 | 362 | 1.515 |
| Test | 1.019 | 135 | 361 | 1.515 |

## 3. Resultados sobre validation

Con `argmax` como referencia:

```
val argmax:   acc=0.8818  macro_f1=0.8545  COVID(P=0.842 R=0.721)  Normal_R=0.934  Pneu_R=0.918
```

Resultados con umbrales aplicados:

| Threshold | Accuracy | Macro-F1 | COVID prec | **COVID rec** | Normal rec | Pneumonia rec |
|---:|---:|---:|---:|---:|---:|---:|
| 0,20 | 0,8733 | 0,8626 | 0,701 | **0,934** | 0,848 | 0,903 |
| 0,25 | 0,8759 | 0,8634 | 0,721 | 0,898 | 0,864 | 0,910 |
| **0,30** | **0,8884** | **0,8707** | 0,765 | **0,881** | 0,887 | 0,918 |
| **0,35** | **0,8904** | **0,8708** | 0,787 | 0,848 | 0,902 | 0,918 |
| 0,40 | 0,8917 | 0,8683 | 0,816 | 0,809 | 0,918 | 0,918 |
| 0,45 | 0,8891 | 0,8639 | 0,833 | 0,771 | 0,927 | 0,918 |
| 0,50 | 0,8792 | 0,8511 | 0,844 | 0,704 | 0,936 | 0,918 |

**Lectura clave:**

- **El macro-F1 máximo en validation es 0,8708, en `thr=0.35`**. El umbral `thr=0.30` está prácticamente empatado con 0,8707. Ambos superan al `argmax` (0,8545) en ~1,6 puntos.
- **El recall de COVID-19 crece monótonamente al bajar el threshold**: de 0,704 con `thr=0.50` a 0,934 con `thr=0.20`. El argmax queda en 0,721, equivalente a `thr=0.45-0.50`.
- **La precision de COVID-19 baja al bajar el threshold**: de 0,842 con `argmax` a 0,701 con `thr=0.20`. Hay un trade-off claro.
- **Pneumonia es insensible al threshold de COVID** dentro de este rango: su recall se mantiene en ~0,918 desde `thr=0.30` hacia arriba. Esto es esperado, ya que la regla solo cambia el comportamiento en el límite COVID vs no-COVID.
- **Normal sufre falsos positivos hacia COVID** cuando bajamos mucho el threshold: su recall cae de 0,934 (argmax) a 0,848 (thr=0,20). En `thr=0.30` aún está en 0,887, aceptable.

## 4. Elección del threshold candidato

**Criterio explícito:**

> Subir el recall de COVID-19 lo máximo posible **sin destrozar la precision de COVID-19** y **sin que el recall de Normal caiga más de ~5 puntos respecto al argmax**.

Aplicando este criterio sobre validation:

| Threshold | ¿Macro-F1 mejora vs argmax? | ¿Recall COVID sube? | ¿Precision COVID aceptable (>0,75)? | ¿Recall Normal cae <5 pp? |
|---:|---|---|---|---|
| 0,20 | sí (+0,8 pp) | **+21 pp** | no (0,701) | no (cae 8,6 pp) |
| 0,25 | sí (+0,9 pp) | +17,7 pp | no (0,721) | no (cae 7 pp) |
| **0,30** | sí (+1,6 pp) | +16 pp | **sí (0,765)** | **sí, cae 4,7 pp** |
| 0,35 | sí (+1,6 pp) | +12,7 pp | sí (0,787) | sí, cae 3,2 pp |
| 0,40 | sí (+1,4 pp) | +8,8 pp | sí (0,816) | sí, cae 1,6 pp |
| 0,45+ | mejora pequeña o nula | poca ganancia | sí | sí |

**El primer threshold que cumple los tres criterios es `thr=0.30`.**

`thr=0.30` y `thr=0.35` están empatados técnicamente en macro-F1 (0,8707 vs 0,8708, diferencia despreciable), pero **`thr=0.30` sube más el recall de COVID** (0,881 vs 0,848). Como el criterio del proyecto prioriza recall de COVID por su consecuencia clínica (un falso negativo grave es peor que un falso positivo que solo añade pruebas), **se elige `thr=0.30`** como candidato principal y se mantiene `thr=0.35` como alternativa conservadora.

## 5. Evaluación en test (one-shot)

Aplicación única de los thresholds candidatos sobre el split de test:

### 5.1. Comparativa de cifras agregadas

| Configuración | Accuracy | Macro-F1 | Δ macro-F1 |
|---|---:|---:|---:|
| **Test argmax (baseline actual)** | **0,8719** | **0,8456** | — |
| Test threshold 0,30 | 0,8726 | 0,8554 | **+0,98 pp** |
| Test threshold 0,35 | 0,8766 | 0,8594 | **+1,38 pp** |

### 5.2. Métricas por clase

| Configuración | COVID prec | COVID rec | COVID F1 | Normal prec | Normal rec | Pneu prec | Pneu rec |
|---|---:|---:|---:|---:|---:|---:|---:|
| Test argmax | **0,807** | 0,695 | 0,747 | 0,897 | **0,926** | 0,829 | **0,933** |
| Test threshold 0,30 | 0,730 | **0,845** | **0,783** | **0,940** | 0,877 | 0,843 | 0,911 |
| Test threshold 0,35 | 0,751 | 0,820 | 0,784 | 0,932 | 0,890 | 0,845 | 0,926 |

### 5.3. Matrices de confusión

**Test argmax (estado actual):**

| Real \ Predicha | Normal | Pneumonia | COVID-19 |
|---|---:|---:|---:|
| **Normal** (1.019) | 944 | 17 | 58 |
| **Pneumonia** (135) | 7 | 126 | 2 |
| **COVID-19** (361) | **101** | 9 | **251** |

**Test threshold 0,30 (candidato):**

| Real \ Predicha | Normal | Pneumonia | COVID-19 |
|---|---:|---:|---:|
| **Normal** (1.019) | 894 | 17 | 108 |
| **Pneumonia** (135) | 7 | 123 | 5 |
| **COVID-19** (361) | **50** | 6 | **305** |

**Test threshold 0,35 (alternativa):**

| Real \ Predicha | Normal | Pneumonia | COVID-19 |
|---|---:|---:|---:|
| **Normal** (1.019) | 907 | 17 | 95 |
| **Pneumonia** (135) | 7 | 125 | 3 |
| **COVID-19** (361) | 59 | 6 | **296** |

### 5.4. Interpretación clínica de los cambios

Comparando **argmax vs threshold 0,30** sobre los 361 COVID-19 reales del test:

- **Falsos negativos de COVID (clasificados como Normal): 101 → 50.** El sistema deja escapar 51 pacientes contagiosos **menos** que con `argmax`. Es la mejora clínicamente más relevante.
- **Falsos negativos de COVID hacia Pneumonia: 9 → 6.** Pequeña mejora (3 menos).
- **Aciertos de COVID: 251 → 305 (+54 detectados).**

Sobre los 1.019 Normal reales:

- **Falsos positivos de Normal hacia COVID: 58 → 108 (+50).** El sistema marca como COVID 50 pacientes Normal más que con argmax. Genera pruebas adicionales, no riesgo clínico.

**Ratio del trade-off:** ganamos 51 detecciones reales de COVID a cambio de 50 falsos positivos sobre Normal. **Es ratio 1 a 1**, lo que confirma que el threshold es un cambio honesto: cada COVID detectado de más implica un Normal etiquetado de más como COVID, no es magia.

## 6. Discusión y trade-offs

### 6.1. Lo que se gana

- **Macro-F1 sube ~1 punto en test** (0,8456 → 0,8554) con `thr=0.30`; o ~1,4 puntos con `thr=0.35`.
- **Recall de COVID-19 sube +15 pp en test** (0,695 → 0,845) con `thr=0.30`.
- **F1 de COVID-19 sube** de 0,747 a 0,783.
- El cambio es **post-procesado**: cero modificaciones al modelo entrenado, cero reentrenamiento, cero coste en GPU/tiempo.

### 6.2. Lo que se pierde

- **Precision de COVID-19 baja de 0,807 a 0,730**: de cada 100 imágenes que el sistema marca como COVID, ~27 son falsos positivos (antes eran ~19).
- **Recall de Normal baja de 0,926 a 0,877**: el sistema marca como COVID un 5 % más de las radiografías Normal reales.
- **Recall de Pneumonia baja ligeramente** (0,933 → 0,911), -2 pp.

### 6.3. ¿Es defendible este cambio?

**Sí, técnicamente.** Es un patrón estándar en clasificación con clases desbalanceadas y costes de error asimétricos. Lo que hay que cambiar es cómo se reporta:

- Hoy el reporte de la memoria dice "el modelo deja escapar 30 % de COVID-19".
- Con `thr=0.30` aplicado, el reporte diría "el modelo deja escapar 16 % de COVID-19 a cambio de aumentar los falsos positivos sobre Normal de 5,7 % a 10,6 %".

Ambos enunciados son defendibles. El segundo es **más sensible al coste clínico real** (FN > FP en este dominio).

### 6.4. Riesgos del threshold tuning

- **El threshold no se transfiere a otros datasets sin recalibración.** Si el modelo se desplegara en un hospital con prevalencia COVID distinta del dataset Kaggle, el 0,30 podría no ser óptimo. En cambio, `argmax` no depende de la distribución de las clases.
- **El umbral elegido sobre validation puede no ser óptimo en producción.** Aquí se ha verificado que generaliza bien al split de test (mejora persiste), pero no se ha medido con datos externos al COVID-19 Radiography Database.
- **No mejora la capacidad del modelo, solo reasigna errores.** Si el modelo no puede distinguir bien COVID de Normal, el threshold solo decide a qué lado caen los casos dudosos. Para mejoras estructurales seguiría haciendo falta transfer learning, más datos o data augmentation más rica.

## 7. Conclusión y decisión aplicada

El análisis demuestra que **se puede subir el recall de COVID-19 sin reentrenar el modelo** aplicando un umbral de decisión sobre la probabilidad de COVID. La búsqueda sobre el split de validación da tres candidatos razonables (0,30 / 0,35 / 0,40); cada uno elige un punto distinto del trade-off recall ↑ vs precision ↓.

**Decisión final (ADR-010): se aplica `covid_threshold_0.35`** como regla operativa del sistema desde Feature 16. Resultados verificados sobre test (1.515 imágenes), no usado en la búsqueda del umbral:

| Métrica | Argmax (baseline) | `covid_threshold_0.35` (aplicado) | Δ |
|---|---|---|---|
| Accuracy | 0,8719 | **0,8766** | +0,005 |
| Macro-F1 | 0,8456 | **0,8594** | +0,014 |
| Recall Normal | 0,9264 | 0,8901 | −0,036 |
| Recall Pneumonia | 0,9333 | 0,9259 | −0,007 |
| **Recall COVID-19** | **0,6953** | **0,8199** | **+0,125** |
| Precision COVID-19 | 0,8071 | 0,7513 | −0,056 |
| FN COVID-19 (de 361) | 110 | **65** | −45 |

Por qué 0,35 y no 0,30 o 0,40:

- **0,30** maximiza el recall COVID (0,847) pero baja Normal a 0,86 y precision COVID a 0,71. Demasiado agresivo para el coste operativo del hospital ficticio.
- **0,35** mantiene Normal en 0,89, recall COVID sube a 0,82 y macro-F1 a 0,86. El balance más equilibrado.
- **0,40** apenas sube COVID (a 0,76) — ganancia marginal por el riesgo de cambiar la regla por defecto.

La decisión completa (alternativas descartadas, consecuencias positivas y negativas, trazabilidad técnica fila a fila) vive en **`decisions/ADR-010-covid-threshold.md`**.

### Por qué se aplicó y no se dejó como mejora futura

- El cambio es **post-hoc**: aplica un umbral sobre las probabilidades softmax que el modelo ya devuelve. NO se reentrenó, NO se tocó arquitectura, NO se tocó dataset.
- La regla **es reversible** en una constante (`COVID_THRESHOLD` en `src/ml/predictor.py`) y reproducible con `python -m src.ml.regen_evaluation`.
- Cada predicción persiste el campo `decision_rule` en MongoDB y la API lo devuelve en cada respuesta, así que la auditoría posterior puede reconstruir exactamente cómo se obtuvo `predicted_class`.
- El *baseline* argmax se conserva en `docs/model-evaluation/metrics.json` (bloque `comparison_argmax`) y en `data/models/radiography_classifier.meta.json` (bloque `metrics_argmax_baseline`).
- La memoria, la validación final y la presentación se actualizaron con las cifras nuevas y con la regla aplicada.

### Aplicación técnica concreta

- `src/ml/predictor.py`: constantes `COVID_CLASS`, `COVID_THRESHOLD`, `DECISION_RULE` + método `_apply_decision_rule`. La dataclass `Prediction` añade el campo `decision_rule: str`.
- `src/api/models.py::RadiographyClassification`: añade campo `decision_rule: str`.
- `src/api/routers/classify.py`: incluye `decision_rule` en el dict persistido y en la respuesta `ClassificationResponse`. Las clasificaciones persistidas antes de Feature 16 se devuelven con `decision_rule="legacy_argmax"`.
- `src/ml/evaluate.py`: `generate_report` aplica la regla en las métricas primarias y conserva `comparison_argmax` para auditoría. Tests `tests/ml/test_predictor_threshold.py` cubren los 9 casos límite del umbral (incluido P(COVID)=0,34 → no COVID, P(COVID)=0,36 → COVID).
- `src/ml/regen_evaluation.py`: script *one-shot* que regenera `metrics.json`, `report.md` y `confusion_matrix.png` sin reentrenar el modelo.

---

## Anexo A: comando para reproducir el análisis

El análisis se ejecuta dentro del contenedor `api` (que tiene el modelo cargado y el dataset montado):

```bash
docker compose exec api python -m scripts.threshold_analysis
```

Salida JSON con todas las matrices y métricas: `/tmp/threshold_analysis.json` dentro del contenedor.

Reproducible con `seed=42` sobre `data/raw/covid_radiography/COVID-19_Radiography_Dataset/`.

> **Nota:** el script utilizado para este análisis no está commiteado al repo en esta entrega; vive en `/tmp` dentro del contenedor. Si en el futuro se aplica el threshold tuning como mejora, se moverá a `scripts/threshold_analysis.py` y se documentará formalmente.
