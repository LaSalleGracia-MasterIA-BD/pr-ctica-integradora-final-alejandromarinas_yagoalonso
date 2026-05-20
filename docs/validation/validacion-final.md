# Validación final del proyecto

> **Fecha:** 2026-05-20
> **Validación ejecutada sobre:** `8ccf250`
> **Modelo en uso:** `v1.0-20260516-192647`

Este documento recoge la validación final ejecutada sobre el sistema antes de la entrega. No reentrena el modelo ni modifica la arquitectura; comprueba que el sistema responde como dice la memoria, tanto en el clasificador como en el flujo end-to-end (triaje, alertas, informe diario). Lo que aparece aquí es lo que se puede explicar oralmente en la presentación: cifras concretas, salidas reales y los matices que conviene mencionar.

---

## 1. Validación del modelo CNN

### 1.1. Métricas finales (`docs/model-evaluation/metrics.json`)

Calculadas sobre las **1.515 radiografías** del split de test (1.019 `Normal` + 361 `COVID-19` + 135 `Viral Pneumonia`).

| Métrica | Valor |
|---|---|
| Accuracy global | **0,8719** |
| Macro-F1 | **0,8456** |
| Recall Normal | 0,926 (944 / 1.019) |
| Recall Pneumonia | 0,933 (126 / 135) |
| Recall **COVID-19** | **0,695** (251 / 361) |
| Precision Normal | 0,897 |
| Precision Pneumonia | 0,829 |
| Precision COVID-19 | 0,807 |

**Lectura:** Normal y Pneumonia se detectan bien (recall > 0,92). La principal limitación está en **COVID-19**: el modelo deja pasar como `Normal` un 28 % de los casos (101 de 361). Esto es coherente con lo que la memoria declara desde el principio: **sistema de asistencia, no de diagnóstico**.

### 1.2. Matriz de confusión

| Real \ Predicha | Normal | Pneumonia | COVID-19 |
|---|---:|---:|---:|
| **Normal** | **944** | 17 | 58 |
| **Pneumonia** | 7 | **126** | 2 |
| **COVID-19** | 101 | 9 | **251** |

La diagonal es fuerte para Normal y Pneumonia. La fila `COVID-19` muestra el principal error: 101 casos clasificados como `Normal` — son los falsos negativos clínicamente más graves (un contagioso que se trataría como sano). 58 Normal se clasifican como COVID-19 (falsos positivos: generan pruebas extra pero no riesgo). La imagen completa con escala de color está en `docs/model-evaluation/confusion_matrix.png`.

### 1.3. Curva de entrenamiento

Disponible en `docs/model-evaluation/learning_curves.png` (loss y accuracy para train + validation, 35 epochs efectivos). Lo relevante: `val_loss` baja de forma monótona y se estabiliza al final sin sobre-ajustar (no se separa de `train_loss` con un *gap* creciente), y el modelo cumple `EarlyStopping` sin recortar antes de los 35 epochs configurados. El log fila a fila está en `docs/model-evaluation/training_log.csv`.

### 1.4. Pruebas con radiografías reales (`HOSP-PRES-*`)

Las `HOSP-PRES-*` son 6 imágenes del COVID-19 Radiography Database (Kaggle) que el bootstrap copia a MinIO cuando el dataset está descargado en local (2 por clase). Las pruebas se hicieron con `POST /api/v1/radiographies/classify` contra el stack vivo.

| Key MinIO | Clase esperada (por nombre del fichero) | Predicha | Probabilidades (Normal / Pneu / COVID) | Latencia | Resultado |
|---|---|---|---|---:|---|
| `HOSP-PRES-001/COVID-1.png` | COVID-19 | **COVID-19** | 0,0918 / 0,0007 / **0,9075** | 3,13 s | ✅ correcto |
| `HOSP-PRES-003/Normal-1.png` | Normal | **Normal** | **0,9980** / 0,0000 / 0,0020 | 39 ms | ✅ correcto |
| `HOSP-PRES-005/Viral Pneumonia-1.png` | Pneumonia | **Pneumonia** | 0,0216 / **0,9716** / 0,0068 | 41 ms | ✅ correcto |

**Notas:**

- La latencia alta de la primera llamada (3,13 s) corresponde al **cold start** del predictor cuando carga el modelo en memoria por primera vez tras arrancar la API. A partir de ahí, las llamadas se sirven en ~40 ms. Para la demo conviene hacer una clasificación de "calentamiento" antes de empezar.
- La concordancia entre el nombre del fichero (`COVID-1.png` viene de la carpeta `COVID` del dataset original) y la clase predicha sirve como verificación rápida del flujo end-to-end MinIO → API → modelo → respuesta.

### 1.5. Prueba con `HOSP-DEMO-001` (imagen sintética)

| Key MinIO | Predicha | Probabilidades | Latencia |
|---|---|---|---:|
| `HOSP-DEMO-001/HOSP-DEMO-001_xray1.png` | Normal | 0,9526 / 0,0026 / 0,0448 | 41 ms |

`HOSP-DEMO-001` se genera en cada `docker compose up` con `numpy + Pillow` (256 × 256, banda gradiente). **No es una radiografía real** y no tiene patrón clínico. Está pensada únicamente como *fixture* para que la vista *Clasificador* del dashboard funcione *out-of-the-box* sin pedir descarga del dataset. La UI muestra un banner amarillo "imagen sintética de demo — no es una radiografía real" siempre que esta imagen está seleccionada. El resultado de su clasificación demuestra que el flujo está vivo, no que el modelo tenga buen criterio clínico sobre ella.

### 1.6. Imagen no clasificable (control de errores)

| Key MinIO | Tamaño real | Respuesta | Latencia |
|---|---|---|---:|
| `HOSP-000000/HOSP-000000_xray1.png` | 1 × 1 px (67 B) | **HTTP 422** con `detail: "Image cannot be processed: Image too small (1x1); minimum is 32x32"` | 3 ms |

Las 17 imágenes `HOSP-NNNNNN` son PNGs dummy de 1 píxel commiteados al repo como fixture del *pipeline de ingesta* (validan la signature PNG, suben a MinIO, se embeben en su paciente). El clasificador las rechaza con HTTP 422 (umbral `MIN_IMAGE_DIM = 32` en `src/ml/preprocessing.py`). No es un crash silencioso — el dashboard recibe el `detail` y muestra un banner de error con el motivo legible. CB-7 cubierto.

### 1.7. Conclusión del modelo

**Lo que la validación demuestra:**

- El modelo entregado **no está degenerado**. En cuatro pruebas seguidas predice tres clases distintas (Normal, Pneumonia, COVID-19, Normal) y devuelve probabilidades muy variadas (0,9075 / 0,9980 / 0,9716 / 0,9526), no uniformes ni concentradas en una sola clase. Las métricas globales del split de test lo confirman: macro-F1 = 0,8456 frente a 0,267 del baseline "predecir siempre Normal".
- La clasificación de las **tres radiografías reales** del subset de presentación coincide con la clase esperada por nombre del fichero, lo que valida la cadena completa de inferencia.
- El **control de errores** funciona: una imagen no clasificable devuelve 422 con mensaje claro, no excepción ni crash.

**Lo que la validación NO demuestra:**

- **No demuestra utilidad clínica real.** Cuatro casos individuales pueden ir bien y el modelo seguir perdiendo el 30 % de los COVID-19 reales (recall = 0,695). Las cifras del split de test son la fuente de verdad, no los smokes aislados.
- **No demuestra generalización** a otros equipos, hospitales o poblaciones. El entrenamiento se hace solo sobre el *COVID-19 Radiography Database*.
- **No demuestra calibración** de las probabilidades. Un `predicted_class=COVID-19 / 0,9075` se interpreta como ranking entre clases, no como "9 de cada 10 con esta confianza son COVID reales".

**Para la presentación oral:** mostrar el smoke real con HOSP-PRES y, en cuanto se mencione "el modelo acierta", abrir el reporte y enseñar el recall = 0,695 de COVID-19 con la matriz de confusión. La franqueza sobre la limitación principal está alineada con la postura de la memoria.

---

## 2. Validación del sistema end-to-end

### 2.1. Estado base

| Verificación | Resultado |
|---|---|
| `git status --short` | ✅ vacío |
| `docker compose ps` | ✅ 5 servicios up: `api`, `dashboard`, `mongo`, `minio` (healthy), `watcher` (running) |
| `GET /api/v1/health` | ✅ `200 OK`, `predictor_loaded=true`, `version=0.1.0` |
| `GET /_stcore/health` (dashboard) | ✅ `200 OK` |

### 2.2. Pipeline operativo

El último run del pipeline registrado en SQLite tiene `status=success`, `records_processed=13.314` y `records_rejected=1.692` (264 patients + 1.428 admissions). El bootstrap deja en MongoDB **4.778 pacientes** (4.745 del ETL + altas de triaje) y **8.569 admisiones embebidas**. MinIO tiene **24 radiografías** (17 dummy + 1 demo + 6 reales). Datos confirmados leyendo `GET /api/v1/reports/daily?date=2026-05-20`.

### 2.3. Triaje grave end-to-end

`POST /api/v1/triage/patients` con un paciente de 72 años y SpO2 = 86:

```
HTTP 201
external_id: TRIAGE-20260520-0005
level: grave
reasons: ["spo2_lt_92"]
score: 1
```

La regla que dispara (`spo2_lt_92`) coincide con la versión `1.0` de las reglas (consultables desde `GET /api/v1/triage/rules`). El paciente queda persistido en MongoDB y es consultable desde `GET /api/v1/patients/TRIAGE-20260520-0005` con su sub-documento `triage` completo (level, score, reasons, vital_signs, rules_version, triaged_at).

### 2.4. Cadena triaje → alerta

Inmediatamente después de crear el triaje grave, `GET /api/v1/alerts` pasa de 2 alertas a 3, incorporando la nueva:

```
[CRITICAL] triage_severe      source_id=TRIAGE-20260520-0005   <- NUEVO
[CRITICAL] triage_severe      source_id=TRIAGE-20260520-0001   (existente)
[MEDIUM  ] data_quality_low   source_id=...:admissions          (existente)
```

La alerta se calcula al consultar el endpoint, sin estado nuevo persistido (vista derivada, ADR-009). No se ha modificado ninguna tabla; la alerta aparece porque la regla `evaluate()` lee `patients.triage.level='grave'` y lo proyecta como `triage_severe / critical`.

### 2.5. Informe diario reproducible

`GET /api/v1/reports/daily?date=2026-05-20` devuelve `200 OK` con todas las secciones: `pipeline`, `quality`, `counts`, `triage` (`grave=2, medio=1, leve=2, total=5`), `alerts` (3 ítems). Coherente con lo visto en `/alerts`.

### 2.6. CLI idempotente

```
docker compose exec api python -m src.automation.daily_report --date 2026-05-20 --output /tmp/audit_report.md
```

Salida: `OK: informe escrito en /tmp/audit_report.md`. El fichero generado tiene las cinco secciones del informe en Markdown.

**Idempotencia byte por byte:** se ejecutó el CLI dos veces seguidas sobre la misma BBDD y la misma fecha, sin cambios entre ambas ejecuciones, y el hash `sha256` fue idéntico. Hash del fichero:

```
30da2949666a191d23511fb8120c5f80d5770a7912ea81e70625c394898a5ffb
```

El audit previo de cierre de la Feature 15 (commit `9898d22`) obtuvo el mismo comportamiento con la BBDD en otro estado (hash `7b58670962...`): dos ejecuciones consecutivas, dos ficheros byte por byte idénticos. La regla general: **mismo estado del sistema + misma fecha → mismo fichero**.

**Matiz importante:** la garantía fuerte de idempotencia aplica especialmente a **días cerrados**. Si se genera el informe del día en curso y entran eventos nuevos entre la primera y la segunda ejecución (por ejemplo, llega un CSV al watcher, alguien crea un triaje grave o el pipeline registra un run), el contenido del día cambia y el Markdown también — eso no es un fallo de idempotencia, es que las fuentes han cambiado.

**Sin residuo en git:** el CLI se ejecutó con `--output /tmp/...`. El directorio `docs/reports/` ni existe en el repo local, y desde el commit `8ccf250` está además ignorado en `.gitignore`. `git status` permanece vacío.

---

## 3. Interpretación

### 3.1. Qué demuestra cada prueba

| Prueba | Demuestra |
|---|---|
| Métricas del split de test (cap 1.1) | Que el modelo entrenado **no es trivial**: macro-F1 = 0,8456 muy por encima del baseline "predecir siempre Normal" (0,267). |
| Matriz de confusión (cap 1.2) | Que los errores **no se reparten al azar**: 101 COVID-19 → Normal es el patrón dominante (falsos negativos clínicamente graves). |
| Smoke real HOSP-PRES (cap 1.4) | Que la **cadena MinIO → API → predictor → respuesta** funciona end-to-end con imágenes reales. |
| HOSP-DEMO-001 (cap 1.5) | Que el flujo del dashboard funciona sin necesidad del dataset Kaggle descargado. Nada más. |
| Dummy 1 × 1 (cap 1.6) | Que el sistema **gestiona errores con código HTTP correcto** y mensaje legible (no crash, no excepción no controlada). |
| Triaje grave (cap 2.3) | Que las **reglas IF-THEN** disparan correctamente y dejan rastro auditable en `reasons` y `rules_version`. |
| Cadena triaje → alerta (cap 2.4) | Que las **alertas se calculan al vuelo** desde las fuentes existentes (vista derivada) y reflejan el estado actual. |
| Informe + CLI (caps 2.5-2.6) | Que el sistema cumple "generación automática de informes" del enunciado, con la propiedad técnica de idempotencia byte por byte para días cerrados. |

### 3.2. Qué NO demuestra esta validación

- **No demuestra valor clínico real.** Cuatro radiografías acertadas en un smoke no compensan un recall COVID-19 de 0,695 sobre 361 casos reales del split de test.
- **No demuestra que las reglas de triaje sean clínicamente correctas.** Los umbrales son académicos, no han sido revisados por personal sanitario. Si en una sesión se ajustasen los umbrales, los tests del triaje irían a romperse y se sabría — pero eso solo prueba que **el sistema hace lo que sus reglas dicen**, no que las reglas estén bien clínicamente.
- **No demuestra robustez en producción.** El sistema corre en local con un solo nodo de Mongo y un solo nodo de MinIO. No hay réplicas, ni autenticación, ni *failover*, ni tests de carga.
- **No demuestra generalización del modelo.** El entrenamiento es sobre un único dataset (COVID-19 Radiography Database). Otro equipo radiológico u otra población podrían dar caídas de rendimiento no medidas.

### 3.3. Qué decir en la presentación

**Sobre el modelo:**

> El modelo alcanza accuracy global de 0,87 y macro-F1 de 0,85 sobre 1.515 radiografías de test. En clasificar Normal y Pneumonia va bien — recalls de 0,93 y 0,93. **La principal limitación es el recall de COVID-19, que es 0,695**: alrededor de un 30 % de los casos de COVID-19 se clasifican como Normal. Por eso el sistema se entrega como **asistencia, no como diagnóstico**, y por eso en la memoria proponemos *transfer learning* como mejora prioritaria si el proyecto siguiera.

**Sobre la demo:**

> Vamos a clasificar tres radiografías reales — una COVID-19, una Normal, una Pneumonia — y las tres se predicen bien con alta confianza. Eso demuestra que **la cadena end-to-end funciona** (MinIO, API, modelo, persistencia), pero **no que el modelo sea fiable clínicamente**: las cifras agregadas del split de test son la fuente de verdad. La imagen sintética `HOSP-DEMO-001` está solo para enseñar el flujo sin pedir descarga del dataset; la UI lo señala explícitamente.

**Sobre triaje y alertas:**

> El triaje es un **sistema basado en reglas IF-THEN**, no un modelo entrenado, porque no tenemos dataset etiquetado con la gravedad real de los pacientes. Las reglas son **académicas, no validadas clínicamente** — están alineadas con la teoría de sistemas basados en reglas del Máster. Cuando creamos un paciente con SpO2 baja, el sistema lo clasifica como grave y deja constancia de qué regla disparó (`spo2_lt_92`). Esa misma información se proyecta como alerta `critical` en la vista *Alertas*, sin guardar nada nuevo en BBDD — la alerta se calcula al consultar las fuentes existentes.

**Sobre la automatización:**

> El informe diario se genera con un comando y, sobre el mismo estado de la BBDD y la misma fecha, **da exactamente el mismo fichero byte a byte**. Eso permite comparar dos informes del mismo día y ver con `git diff` qué ha cambiado realmente. Es la lectura del enunciado: "automatización" entendida como **reproducibilidad**, sin meter un scheduler real que el temario no cubre.

### 3.4. Cosas a tener en cuenta el día de la presentación

- Antes de empezar, hacer una clasificación de **calentamiento** (por ejemplo `HOSP-PRES-003`) para que el cold start de 3 s no salga en la demo en vivo.
- Si la vista *Alertas* tiene pacientes residuales de pruebas anteriores (`TRIAGE-20260520-0001`, `TRIAGE-20260520-0005`...), se pueden borrar antes para empezar limpio:
  ```
  docker compose exec mongodb mongosh hospital --quiet --eval 'db.patients.deleteMany({external_id: /^TRIAGE-/})'
  ```
  Tras esto, `/alerts` solo enseñará la alerta de calidad (`data_quality_low / medium`), que es la que aparece por defecto del dataset sintético y sirve para explicar la cadena.
- La alerta `data_quality_low` por defecto **no es un fallo**, es la cadena de calidad funcionando: el `rejection_rate` de admissions es 0,1428 y el umbral configurado es 0,10. Es buena noticia, no mala.

---

## 4. Estado final del proyecto

- **Memoria técnica:** cerrada y revisada en estilo natural (commit `5e8047e`).
- **Justificación de bases de datos:** basada solo en el texto visible del enunciado (commit `044137c`).
- **Informes diarios:** ignorados localmente (commit `8ccf250`).
- **Suite de tests:** 404 verdes + 1 *skip* esperado.
- **Modelo entrenado:** `v1.0-20260516-192647`, 21 MB, commiteado al repo.
- **Documentación viva:** memoria, ADRs (9), specs (6), diario IA (30 sesiones), changelog, runbooks, fallback de presentación.

Esta validación final completa el ciclo y deja constancia de que el sistema **responde como la memoria dice que responde**, sin ningún punto pendiente que requiera tocar código antes de la entrega.
