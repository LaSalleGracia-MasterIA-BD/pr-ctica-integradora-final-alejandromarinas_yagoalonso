# Historial de sesiones (append-only)

> Bitacora cronologica de TODAS las sesiones cerradas. Solo se anade al final.

---

## 2026-05-16 — Feature 2: Clasificacion de radiografias (T1–T16)

- **Feature:** clasificacion-radiografias
- **Agente:** Claude Code (Opus 4.7)
- **Plan inicial:** spec → design → tasks → BUILD completo (T1–T16) + entrenamiento real del modelo CNN
- **Cambios:**
  - **Codigo nuevo:** `src/ml/{__init__,dataset,preprocessing,model,evaluate,train,predictor}.py`,
    `src/api/routers/classify.py`, `scripts/ml_diagnostics.py`
  - **Codigo modificado:** `src/api/main.py` (carga predictor en lifespan,
    /health con `predictor_loaded`), `src/api/models.py`
    (`RadiographyClassification`, `ClassifyRequest`, `ClassificationResponse`,
    `Radiography.classification` como objeto), `src/api/mongo_reader.py`
    (`get_radiography_classification`), `src/pipeline/storage/mongo_writer.py`
    (`set_radiography_classification` con `matched_count > 0`),
    `src/pipeline/storage/minio_client.py` (`download_bytes`)
  - **Tests nuevos:** `tests/ml/{test_dataset,test_preprocessing,test_model,test_evaluate,test_predictor,test_train}.py`,
    `tests/api/{test_classify_endpoint,test_mongo_reader_classification}.py`,
    `tests/e2e/test_classification_e2e.py`
  - **Tests modificados:** `tests/pipeline/test_mongo_writer.py`
    (+4 tests para `set_radiography_classification` incluyendo idempotencia con
    matched_count)
  - **Docker:** `requirements-pipeline.txt` (+tensorflow 2.16.1, scikit-learn,
    matplotlib, pillow), `docker-compose.yml` (refactor de volumenes a submontajes
    especificos en pipeline y api), `docker/mongo-init/init-db.js` (indice
    `radiographies.minio_object_key`), `.gitignore` (ignora dataset Kaggle,
    permite commitear `.keras` y `.meta.json`)
  - **Decisiones:** ADR-005 (CNN custom sin transfer learning, alineada con
    Bloque 6 del Master), ADR-006 (TF en imagen compartida `hospital-pipeline`)
  - **Artefactos producidos:** `data/models/radiography_classifier.keras` (21 MB),
    `data/models/radiography_classifier.meta.json`,
    `docs/model-evaluation/{report.md,metrics.json,confusion_matrix.png,learning_curves.png,training_log.csv,diagnostics/preprocessed_batch.png}`
  - **Docs actualizadas:** `specs/clasificacion-radiografias.md`,
    `design/clasificacion-radiografias.md`, `tasks/clasificacion-radiografias.md`,
    `tasks/backlog.md` (feature 2 → done), `tasks/lessons.md` (+7 lecciones),
    `docs/diario-ia.md` (+sesiones 25 y 26), `CHANGELOG.md`, `README.md`,
    `docs/runbooks/download-radiography-dataset.md`
- **Verificacion:**
  - Suite completa: **229 tests verdes** (208 unit + integration + 21 E2E) + 1 skip esperado
  - Smoke en vivo: API levanta con `predictor_loaded=true`, 3 imagenes reales (una de cada clase) clasificadas correctamente con confianzas 0.91/0.97/1.00, latencia <100ms
  - CB-4 verificado: API sin modelo arranca y devuelve 503 limpio en classify
  - Persistencia: GET /classification recupera el objeto persistido
- **Resultado:** done
- **Metricas finales del modelo (v3, 35 epochs, test split de 1.515 imagenes):**
  - Accuracy = 0.872
  - Macro-F1 = 0.846
  - Recall por clase: Normal=0.926, Pneumonia=0.933, COVID-19=0.695
  - Precision por clase: Normal=0.897, Pneumonia=0.829, COVID-19=0.807
  - Modelo de 21 MB (commiteado al repo bajo `data/models/`)
- **Lecciones / decisiones (movidas a `tasks/lessons.md`):**
  - Loss atascada en `ln(N)` = sintoma canonico de modelo degenerado prediciendo uniforme
  - Tiny-overfit (30 imgs, dropout reducido) es el primer sanity check obligatorio antes de cualquier reentrenamiento
  - Class weights con factor > 3-4 desestabilizan; usar `sqrt(balanced)` como compromiso
  - `min_delta=0.001` en EarlyStopping evita falsos plateaus
  - `docker compose run` NO refleja cambios en `src/` sin rebuild — siempre `docker compose build` tras editar codigo
  - `nohup caffeinate -dimsu & disown` para entrenamientos largos en Mac
- **Notas:**
  - El primer entrenamiento (v1, LR=1e-3, class_weight=balanced) dio modelo
    degenerado (macro-F1=0.27). Los sanity checks confirmaron que NO habia bug
    y el problema era de hiperparametros. v2 (LR=1e-4, class_weight=sqrt,
    20 epochs) subio a macro-F1=0.77. v3 (misma config + 35 epochs) alcanzo
    macro-F1=0.85 — modelo final
  - El recall COVID-19=0.70 es la limitacion principal del modelo, documentada
    explicitamente en el reporte clinico. El modelo se entrega como
    **asistencia diagnostica** (RNF-2), no como diagnostico final
  - Tiempo total de entrenamiento real (v1 + diagnostico + v2 + v3): ~7h
    (la mayor parte en v3 con 35 epochs)

---
