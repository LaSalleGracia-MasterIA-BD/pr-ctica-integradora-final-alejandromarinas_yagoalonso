# ADR-010: Regla de decisión `covid_threshold_0.35` aplicada *post-hoc*

> Estado: accepted
> Fecha: 2026-05-20
> Supersede: ninguno. Refina ADR-005 sin reemplazarla (la arquitectura y los pesos del modelo no cambian).

## Contexto

El clasificador entregado (`v1.0-20260516-192647`, ADR-005) alcanza sobre el split de test (1.515 imágenes) las siguientes métricas con `argmax` puro sobre las probabilidades softmax:

- accuracy = 0,8719
- macro-F1 = 0,8456
- recall Normal = 0,9264, recall Pneumonia = 0,9333, **recall COVID-19 = 0,6953**

El *recall* de COVID-19 = 0,695 implica que el modelo deja pasar el 30 % de los positivos reales de COVID-19 del split de test (110 de 361). En contexto hospitalario el falso negativo de COVID-19 (paciente contagioso clasificado como Normal y por tanto no aislado) es el error de mayor coste clínico, así que el sistema declara explícitamente en RNF-2 de la spec de clasificación que se entrega como **asistencia, no como diagnóstico**.

Antes de la entrega final se exploró si era posible subir el *recall* de COVID-19 **sin reentrenar el modelo**, manteniendo arquitectura, pesos y dataset. El motivo de no reentrenar es triple:

1. El proyecto está en fase de cierre y un reentrenamiento abriría dependencias (refactor de `train.py`, regeneración de artefactos, nueva validación) incompatibles con el plazo de entrega.
2. La spec original aprueba *accuracy* + *recall* per clase + matriz de confusión como métricas; no exige reentrenamiento por debajo de un umbral de *recall* COVID.
3. La regla de decisión sobre probabilidades softmax es un mecanismo bien documentado en la literatura de clasificación clínica (umbrales calibrados para optimizar sensibilidad de la clase crítica).

La pregunta concreta era: **¿qué umbral sobre P(COVID-19) maximiza el balance recall/precision sin reentrenar?**

## Decisión

Se introduce una **regla de decisión `covid_threshold_0.35`** que se aplica *post-hoc* sobre las probabilidades softmax del modelo:

```
def decide(probs):
    if probs["COVID-19"] >= 0.35:
        return "COVID-19"
    # else, argmax entre Normal y Pneumonia (NO se compara con COVID-19)
    return "Normal" if probs["Normal"] >= probs["Pneumonia"] else "Pneumonia"
```

Las **probabilidades** que devuelve la API siguen siendo las salidas softmax brutas del modelo (no se renormalizan tras aplicar el umbral). El campo `predicted_class` cambia respecto al *baseline* argmax cuando `0.35 ≤ P(COVID-19) < max(P(Normal), P(Pneumonia))`.

Cada predicción persistida en MongoDB incluye `decision_rule: "covid_threshold_0.35"` para trazabilidad. Las clasificaciones persistidas antes de Feature 16 (sin ese campo) la API las lee con `decision_rule="legacy_argmax"`.

## Alternativas consideradas

| Opción | Pros | Contras |
|---|---|---|
| **`covid_threshold_0.35` aplicado post-hoc (elegida)** | Recall COVID-19 0,695 → 0,820 (+12,5 pp). Cero coste de reentrenamiento. Sin cambios en `train.py`, ni en arquitectura, ni en pesos. La regla queda trazada en cada predicción (`decision_rule` en MongoDB + en la respuesta de la API). El baseline argmax se conserva en `metrics.json` para auditoría. | Recall Normal cae 3,6 pp (0,926 → 0,890). Precision COVID-19 cae 5,6 pp (0,807 → 0,751). La calibración de las probabilidades sigue sin verificarse (la regla las usa como ranking, no como probabilidad calibrada). |
| `covid_threshold_0.30` | Maximiza recall COVID-19 (0,847) y macro-F1 sobre validación (0,8707). | Demasiado agresivo: recall Normal baja a 0,86 y precision COVID-19 a 0,71. Más falsos positivos sin ganancia clínica proporcional. |
| `covid_threshold_0.40` | Conservador: recall Normal estable (0,915), precision COVID-19 0,79. | Recall COVID-19 solo sube a 0,76. La mejora clínica se queda corta. |
| Reentrenar con `class_weight=2.5` para COVID-19 | Solución "principalmente correcta": ataca el desbalance en origen. Permitiría calibrar probabilidades de manera natural. | Coste alto: tendría que reentrenarse, regenerarse `metrics.json`, validar de nuevo, actualizar memoria, presentación y validación. Fuera del plazo de entrega y fuera del alcance acordado ("no reentrenes el modelo"). |
| Transfer learning con DenseNet/EfficientNet | Cambio de paradigma que probablemente subiría el *recall* COVID-19 más allá del 0,820 que da el umbral. | Cambio profundo de arquitectura (rompe ADR-005), tamaño del modelo subiría por encima del techo de 50 MB del RNF-4, semanas de trabajo no disponibles. Queda como **trabajo futuro prioritario** (cap 17 de la memoria). |
| Ensembling o *test-time augmentation* | Mejora plausible sin tocar pesos. | Coste de inferencia >> 1× (latencia de la API se degradaría). No compatible con el RNF-3 de tiempo de respuesta del clasificador. |

El umbral 0,35 se eligió comparando las tres alternativas (0,30, 0,35, 0,40) sobre el **split de validación** (no el de test) para no contaminar la decisión con el conjunto de test. Sobre validación, 0,35 daba la mejor macro-F1 (0,8707) y el mejor balance recall/precision para COVID-19. La verificación final sobre test (que NO se usó para elegir el umbral) confirma la mejora.

Detalle cuantitativo completo de la búsqueda en `docs/model-evaluation/threshold-analysis.md`.

## Consecuencias

- (+) **Trazabilidad completa**: el campo `decision_rule` viaja con cada predicción (respuesta de la API + persistencia en MongoDB). Una auditoría posterior puede reconstruir cómo se obtuvo `predicted_class` a partir de las probabilidades.
- (+) **Modelo intacto**: los pesos del `.keras` no cambian. El reporte de evaluación (`metrics.json`) preserva el *baseline* argmax bajo `comparison_argmax` para que el evaluador vea ambos números a la vez.
- (+) **Reversibilidad**: cambiar la regla es un cambio puntual en una constante (`COVID_THRESHOLD` en `src/ml/predictor.py`) y la regeneración del reporte (`python -m src.ml.regen_evaluation`). No requiere reentrenar.
- (+) **Test cubre las dos direcciones del umbral**: P(COVID)=0,36 fuerza COVID-19; P(COVID)=0,34 cede a argmax de Normal/Pneumonia. La cobertura está en `tests/ml/test_predictor_threshold.py`.
- (-) **Precision COVID-19 baja** (0,807 → 0,751). Más falsos positivos: Normal → COVID-19 pasa de 58 a 95 (+37 casos). Son revisiones clínicas extra, no altas indebidas de contagiosos, pero el coste operativo existe.
- (-) **Recall Normal baja** (0,926 → 0,890). En un hospital donde la prevalencia real de COVID-19 fuera bajísima, esta caída se notaría más que la ganancia en COVID-19.
- (-) **La calibración de las probabilidades no está verificada**: la regla las usa como *ranking* (P(COVID-19) >= 0,35), no como probabilidad calibrada en sentido estricto. Una predicción "COVID-19 0,40" no implica que 40 de cada 100 con esa confianza sean COVID-19 reales.
- (-) **Es un parche, no una solución**: el modelo subyacente tiene *recall* COVID-19 = 0,695 con argmax. La regla compensa el sesgo del modelo hacia Normal, pero no lo elimina. El siguiente paso natural sigue siendo *transfer learning* o reentrenamiento con *class_weight* más agresivo, como documenta el cap 17 de la memoria.

## Requisitos relacionados

- Spec `clasificacion-radiografias`:
  - **RNF-2**: el sistema se entrega como asistencia, no diagnóstico. La regla `covid_threshold_0.35` no cambia esto — el sistema sigue siendo asistencia, simplemente con mejor sensibilidad para COVID-19.
  - **CA-3**: análisis clínico cualitativo de los errores. El reporte (`report.md`) actualizado mantiene la sección y comenta los nuevos números.
- ADR-005: justifica la CNN custom desde cero. ADR-010 NO la supersede; refina la regla de decisión sobre la salida del mismo modelo.

## Trazabilidad técnica

- Código del *predictor*: `src/ml/predictor.py` (constantes `COVID_CLASS`, `COVID_THRESHOLD`, `DECISION_RULE`; método `_apply_decision_rule`).
- Schema Pydantic: `src/api/models.py::RadiographyClassification` (campo `decision_rule: str`).
- Persistencia: `src/api/routers/classify.py` (incluye `decision_rule` en el dict que se pasa al `MongoWriter`).
- Reporte: `src/ml/evaluate.py` (`_apply_threshold_rule`, `comparison_argmax` en `metrics.json`).
- Regenerador *one-shot*: `src/ml/regen_evaluation.py` (carga el `.keras`, reconstruye el split, reescribe artefactos sin reentrenar).
- Tests: `tests/ml/test_predictor_threshold.py` (9 tests del rule), `tests/ml/test_predictor.py` (actualizado), `tests/api/test_classify_endpoint.py` (incluido test del fallback `legacy_argmax`), `tests/ml/test_evaluate.py` (verifica `comparison_argmax`).
- Análisis cuantitativo de la búsqueda de umbral: `docs/model-evaluation/threshold-analysis.md`.
