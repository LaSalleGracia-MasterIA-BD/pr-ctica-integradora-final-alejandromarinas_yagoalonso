# Study pack — Defensa del Master IA & Big Data

> Documento unico para repasar la noche antes y el dia de la defensa.
> Todo lo que necesitas saber, ordenado por importancia para el tribunal.
> Sin emojis, sin frases marketinianas. Lo que aparece aqui es lo que
> sale del repo y de la memoria tecnica, no inventos.

---

## 0. La frase con la que abro

> *"Hemos construido un sistema completo de soporte hospitalario para
> un hospital ficticio (laSalle Health Center) que ingiere datos a
> escala, ofrece asistencia diagnostica por imagen y expone una
> herramienta de turno con observabilidad accionable. Reproducible
> con un solo `docker compose up`. Entregado como asistencia, NO como
> diagnostico vinculante."*

Y luego enseguida: **"Tres almacenes, dos paradigmas de IA,
automatizacion accionable y SDD aplicada de extremo a extremo."**

---

## 1. Cifras canon que tienes que saber de memoria

### 1.1. Macro

| | |
|---|---|
| Tests verdes | **417** + 1 skip esperado |
| ADRs | **10** |
| Specs aprobadas | **6** |
| Servicios Docker | **7** |
| Almacenes heterogeneos | **3** (MongoDB + SQLite + MinIO) |
| Paradigmas de IA | **2** (CNN custom + reglas IF-THEN) |
| Vistas del dashboard | **7** |
| Tiempo de bootstrap en frio | ~50 s |
| Warm restart | ~1 s |
| `docker compose up` deja el sistema operativo en | < 1 min |

### 1.2. Modelo (recordar de memoria)

Con la regla operativa **`covid_threshold_0.35`** (ADR-010), sobre
**1.515 radiografias del split de test** (1.019 Normal + 361 COVID-19 + 135 Pneumonia):

| Metrica | Valor (operativo) | Baseline argmax descartado |
|---|---|---|
| Accuracy | **0,8766** | 0,8719 |
| Macro-F1 | **0,8594** | 0,8456 |
| Recall Normal | 0,890 | 0,926 |
| Recall Pneumonia | 0,926 | 0,933 |
| **Recall COVID-19** | **0,820** | **0,695** |
| Precision Normal | 0,932 | 0,897 |
| Precision Pneumonia | 0,845 | 0,829 |
| Precision COVID-19 | 0,751 | 0,807 |
| FN COVID-19 totales | **65 / 361** | 110 / 361 |
| FN COVID -> Normal (los mas graves) | 59 | 101 |

Detalle: la regla **sube recall COVID +12,5 pp** a cambio de **−5,6 pp
de precision COVID** y **−3,6 pp de recall Normal**. El modelo NO se
reentreno. ADR-010 lo justifica.

### 1.3. Volumen del sistema

| | |
|---|---|
| Pacientes finales en MongoDB | ~4.790 |
| Admisiones embebidas | 8.569 |
| Radiografias (HOSP-* + DEMO) | ~24 |
| Registros rechazados (rejected_records) | 1.692 (264 pacientes + 1.428 admisiones) |

### 1.4. Modelo (metadata)

| | |
|---|---|
| Tamano artefacto `.keras` | ~21 MB |
| Version del modelo | `v1.0-20260516-192647` |
| Arquitectura | Conv2D + MaxPooling2D + Dropout + Flatten + Dense + softmax |
| Split | stratified 80/10/10, seed=42 |
| Hyperparams clave | `lr=1e-4`, `batch=32`, `epochs_max=35`, `class_weight=sqrt`, `dropout=0,3` |
| Framework | TensorFlow 2.16.1 (Keras) |
| Bloque docente | Bloque 6 del Master (Jordi) |

---

## 2. Arquitectura — que hay y donde vive

```
CSV pacientes  -------+
CSV admisiones -------+--> Pipeline PySpark --> MongoDB (patients, rejected)
                      |    (validate, dedupe,  --> SQLite (pipeline_runs, quality)
PNG radiografias ----+    enrich, audit)      --> MinIO (PNG, modelo .keras)
                                                       |
                                          +------------+------------+
                                          v                         v
                                  FastAPI (17 endpoints)        CLI informe diario
                                  /patients /classify           daily_report.py
                                  /triage   /alerts             docs/reports/YYYY-MM-DD.md
                                  /reports  /model              (sha256 idempotente)
                                          |
                                          v
                                  Dashboard Streamlit
                                  (7 vistas, API-only, imagen aparte)
```

Siete servicios Docker:
- `mongodb` + `minio` + `minio-init` (preparan el estado)
- `pipeline` + `api` + `watcher` (comparten imagen `hospital-pipeline`, ADR-006)
- `dashboard` (imagen aparte `hospital-dashboard`, ADR-007)

---

## 3. Datos

### 3.1. Persistencia poliglota (ADR-004)

| Almacen | Contiene | Por que ahi |
|---|---|---|
| **MongoDB** | `patients` (admissions + radiographies embebidas), `rejected_records` con `raw_data` heterogeneo | Jerarquia natural paciente -> admisiones -> radiografias. Payloads heterogeneos en rejected. Sin joins artificiales. ADR-002. |
| **SQLite** | `pipeline_runs` (auditoria), `data_quality_summary` (metricas por run) | Tabular, esquema fijo, queries analiticas. Alineado con Bloque 7 (SQLAlchemy). ADR-004. |
| **MinIO** | PNG de radiografias + el `.keras` del modelo | Binarios. S3-compatible. |

### 3.2. Calidad medida

Cada run del pipeline calcula `rejection_rate` por dimension y lo
persiste en `data_quality_summary`. Es la fuente del alerta
`data_quality_low` (umbral 0,10).

---

## 4. Pipeline PySpark

### 4.1. Etapas

1. **Validacion** + dedupe por `external_id`.
2. **Enriquecimiento**: categoria de diagnostico (CIE-10 → grupo), edad calculada.
3. **Image ingester**: lee PNGs, valida signature, sube a MinIO, embebe en su paciente.
4. **Auditoria por run** en SQLite (`status`, `started_at`, `finished_at`, `error_message`).
5. **Rejected records** persistidos con `raw_data` y motivo.

### 4.2. Idempotencia

- Re-bootstrap NO crea duplicados (`matched_count > 0`).
- Misma imagen mismo dia produce el mismo `sha256` (ver informe diario).

### 4.3. Bootstrap

`docker compose up` registra automaticamente los `HOSP-PRES-*` reales
del dataset Kaggle (si esta descargado en `data/raw/`) y los
`HOSP-DEMO-001` sinteticos generados al vuelo con numpy+Pillow.

---

## 5. Modelo CNN (clasificador de radiografias)

### 5.1. Que es

CNN **custom desde cero**, sin transfer learning (ADR-005), entrenada
sobre el **COVID-19 Radiography Database** de Kaggle. Tres clases:
**Normal · Pneumonia · COVID-19**.

### 5.2. Por que sin transfer learning

- **ADR-005**: alineacion literal con el patron docente del Bloque 6.
- Modelo dentro del techo de 50 MB del RNF-4.
- Sin dependencias externas en arranque (pesos descargables).

### 5.3. Anecdota docente que conviene contar si preguntan

El **primer entrenamiento fue degenerado**: el modelo predecia `Normal`
para casi todo (accuracy ~0,67 = % de Normal en el split). Diagnostico:
**`lr=1e-3` demasiado alto** + **`class_weight` lineal 3,76 demasiado
agresivo**. Fix: bajar `lr` a `1e-4` y suavizar `class_weight` con
raiz cuadrada. Documentado en `tasks/lessons.md` y `scripts/ml_diagnostics.py`.

### 5.4. Cifras (ver seccion 1.2)

### 5.5. Ciclo de vida en produccion

- Predictor cargado en `lifespan` de FastAPI.
- Si el `.keras` no esta, API arranca igualmente; endpoints de
  clasificacion devuelven **HTTP 503** con mensaje (CB-4); el resto
  sigue vivo (CA-7).
- Cada clasificacion persiste 5 campos en `patients.radiographies[].classification`:
  ```
  predicted_class · probabilities · predicted_at · model_version · decision_rule
  ```
- Idempotencia con `matched_count > 0`.

---

## 6. Regla `covid_threshold_0.35` (ADR-010) — el bloque mas delicado

### 6.1. Que es

Post-procesado sobre las probabilidades softmax del modelo. NO
reentrena, NO cambia arquitectura, NO cambia pesos.

```
si P(COVID-19) >= 0,35  ->  predicted = COVID-19
si no                    ->  argmax(Normal, Pneumonia)
```

Las **probabilidades** que devuelve la API siguen siendo las raw del
softmax. El campo `decision_rule` se persiste en cada clasificacion.

### 6.2. Por que 0,35 y no 0,30 o 0,40

Eleccion hecha sobre el **split de validacion** (no test, para no
contaminar la decision):

| Umbral | Que hace |
|---|---|
| 0,30 | Maximiza recall COVID-19 (0,847) pero precision baja a 0,71. Demasiado agresivo. |
| **0,35** | Mejor balance recall/precision. Macro-F1 0,8707 en validacion. |
| 0,40 | Recall COVID-19 solo sube a 0,76. Marginal. |

Sobre **test** (no usado en la busqueda), 0,35 da las cifras de la
seccion 1.2.

### 6.3. Trade-off cuantificado

- **Gana**: recall COVID-19 0,695 -> 0,820 (+12,5 pp). 45 falsos negativos menos.
- **Pierde**: recall Normal 0,926 -> 0,890. Precision COVID 0,807 -> 0,751. +37 falsos positivos COVID (revisiones extra, no altas indebidas).

### 6.4. Por que es defendible

- **Reversible** en una constante (`COVID_THRESHOLD` en `src/ml/predictor.py`).
- **Trazado** en cada prediccion (`decision_rule` en Mongo + en respuesta).
- **Baseline argmax preservado** en `metrics.json` bajo `comparison_argmax`.
- **9 tests del rule** (`tests/ml/test_predictor_threshold.py`).
- **Documentado** en ADR-010 y `docs/model-evaluation/threshold-analysis.md`.

### 6.5. Por que NO se reentreno

- Cambio post-hoc cabe en un dia; reentrenamiento abre dependencias
  (refactor `train.py`, regenerar artefactos, validar otra vez).
- La spec original no exigia reentrenamiento por debajo de un umbral
  de recall.
- ADR-010 documenta las alternativas descartadas (class_weight mas
  agresivo, transfer learning, ensembling) y por que se eligio esta.

---

## 7. Triaje por reglas (ADR-008)

### 7.1. Por que reglas y no ML

- **No existe dataset etiquetado con la gravedad real** de cada paciente.
- El CSV sintetico no tiene signos vitales ni una columna `grave/medio/leve`.
- Entrenar sobre etiquetas inventadas por el equipo seria **fabricar
  ground truth**, no aprenderlo.
- El Master presenta los **sistemas basados en reglas / reglas de
  produccion** como alternativa legitima cuando faltan etiquetas y se
  prioriza trazabilidad (Sesion 07 de Yuri, `ruleBasedSystem/`).

### 7.2. Como funciona

| Nivel | Cuando |
|---|---|
| **grave** | 6 reglas criticas (SpO2 < 92, FR > 30, FC > 130, PAS < 90, T >= 39,5, sintoma critico) |
| **medio** | 5 reglas intermedias (franjas + combinacion edad-riesgo) |
| **leve** | Caso por defecto |

### 7.3. Trazabilidad directa

Cada decision lleva la lista exacta de reglas que disparan y un
`rules_version`. No requiere SHAP ni Grad-CAM, las reglas son legibles.

### 7.4. Limitaciones declaradas

- Umbrales **academicos**, no validados clinicamente.
- Fronteras duras (SpO2=92 medio, SpO2=91 grave). Inherente a IF-THEN.
- No combina interacciones complejas entre variables.
- Sintomas declarados, no observados.
- UI con disclaimer permanente.

---

## 8. Alertas e informe diario (ADR-009)

### 8.1. Vista derivada — cero estado nuevo

ADR-009: las alertas se calculan al consultar el endpoint, NO se
persisten. Cero tabla `alerts`, cero estado leida/no leida.

### 8.2. Las 3 reglas de alerta

| Tipo | Severidad | Fuente |
|---|---|---|
| `pipeline_failed` | **HIGH** | `pipeline_runs.status='failed'` en la ventana |
| `data_quality_low` | **MEDIUM** | `rejection_rate > 0,10` |
| `triage_severe` | **CRITICAL** | `patients.triage.level='grave'` |

### 8.3. La funcion pura

`src/api/alerts.py::evaluate(failed_runs, quality_snapshots, severe_triage_patients, threshold) -> list[Alert]`.

No accede a Mongo ni a SQL directamente. Misma `evaluate()` se usa con
**dos ventanas distintas**: 24 h en `/alerts` y dia natural UTC en
`/reports/daily`. Sin duplicar logica.

### 8.4. Informe diario reproducible

```bash
docker compose run --rm api python -m src.automation.daily_report --date 2026-05-21
```

Genera `docs/reports/YYYY-MM-DD.md` con **sha256 byte-a-byte
identico** entre dos ejecuciones del mismo dia (sin `generated_at` en
el cuerpo).

### 8.5. Reabrible si hace falta

ADR-009 documenta como se reabriria: tabla `alerts` en SQLite con
`raised_at`, `acknowledged_at`, `resolved_at`, estado leida/no leida.
No se hizo porque el alcance era cero estado nuevo.

---

## 9. Dashboard (Streamlit, ADR-007)

### 9.1. Por que Streamlit

- A 3 dias de la entrega original, Streamlit corto ~70 % del tiempo de
  implementacion vs React.
- Imagen ligera (~240 MB) cumple holgadamente RNF-5.
- Dashboard **API-only**: cero imports de pymongo/sqlite/sqlalchemy/minio
  en `src/dashboard/`. ADR-007.

### 9.2. Las 7 vistas (orden actual)

| Bloque | Vistas |
|---|---|
| **Operacion** | Inicio · Triaje · Alertas · Pacientes · Clasificador |
| **Sistema** (atenuado) | Calidad de datos · Pipeline runs |

### 9.3. Inicio — centro de turno

- Saludo + meta de turno (manana/tarde/noche segun la hora).
- Linea discreta de volumen: pacientes · admisiones · radiografias.
- Barra critica condicional (solo si hay alertas `critical`).
- 3 chips de estado: API · Modelo · Pipeline.
- 4 cards de actividad (alertas crit/high/med + runs 24h).
- 3 accesos rapidos como action cards: Nuevo triaje · Buscar paciente · Clasificar radiografia.

### 9.4. Robustez frente a fallos

- Si la API esta caida: chips rojos en sidebar, dashboard sigue
  respondiendo 200 OK, no hay pantalla blanca (CA-10).
- Si el modelo no se carga: chip "Modelo" rojo, clasificador
  responde con error claro, resto del dashboard funciona.

---

## 10. IA generativa + SDD

### 10.1. El flujo

```
/spec -> /clarificar -> /planificar -> /tareas -> /analizar
       -> /implementar -> /revisar -> /auditoria
```

### 10.2. Disciplina

- Cada feature tiene `specs/<feature>.md`, `design/<feature>.md`, `tasks/<feature>.md`.
- Dudas marcadas `[NEEDS CLARIFICATION]`, NO se asumen.
- Decisiones tecnicas en ADRs (10 en total).
- Cross-provider review con Codex cuando aporta valor (mitiga sycophancy del LLM).

### 10.3. Artefactos vivos

- `docs/diario-ia.md` con 31 sesiones documentadas.
- `tasks/lessons.md` con lecciones aprendidas.
- `progress/current.md` (sesion actual) + `progress/history.md` (historico).

### 10.4. Mensaje final

> *"La IA generativa es un multiplicador de capacidad, no un
> sustituto. SDD es la disciplina que hace seguro ese multiplicador."*

---

## 11. Etica y limitaciones (no opcional)

### 11.1. Etico y legal

- **Datos sinteticos** por diseno (Faker + seed 42). Sin PII real.
- Dataset Kaggle: licencia tal como la publica el proveedor. NO se asume licencia generica.
- **Asistencia, NO diagnostico**. La decision clinica la mantiene siempre el profesional.

### 11.2. Limitaciones del clasificador

- **Recall COVID-19 = 0,820** con la regla. Aun 65 / 361 positivos perdidos (~18 %).
- Sin deteccion **out-of-domain** (una imagen que no sea radiografia de torax devuelve igualmente una clase).
- Sin **interpretabilidad** (Grad-CAM como mejora prioritaria).
- Sin **calibracion** de probabilidades.
- Generalizacion a otros equipos/poblaciones no medida.

### 11.3. Limitaciones del triaje

- Umbrales academicos, no validados clinicamente.
- Fronteras duras, sin gradacion.
- No combina interacciones complejas entre variables.

### 11.4. Limitaciones del sistema de alertas

- Modelo **pull** (el operador debe abrir el dashboard).
- Sin estado leida/no leida.
- Umbral fijo de calidad (0,10), sin aprendizaje del historico.

### 11.5. Limitaciones del entorno

- Sin auth, sin replicacion, sin alta disponibilidad.
- MongoDB y MinIO como nodos unicos.
- Imagen Docker compartida pesa ~2 GB (ADR-006).

### 11.6. Donde NO se usaria sin cambios estructurales

- Decisiones clinicas con consecuencia para un paciente.
- Entornos con PII real o regulacion (GDPR).
- Operacion 24/7 sin observabilidad push.
- Hospital con SLA real.
- Generalizacion geografica del clasificador.

---

## 12. Las 10 ADRs en una pagina

| ID | Decision | Alternativa descartada | Motivo |
|---|---|---|---|
| **001** | Stack inicial: PySpark + PyTorch + FastAPI + MongoDB + MinIO + Docker | Dask, Apache Beam | PySpark del temario; stack moderno conocido |
| **002** | MongoDB para datos clinicos | PostgreSQL | Jerarquia paciente -> admisiones; `rejected.raw_data` heterogeneo |
| **003** | Cambio DL framework PyTorch -> Keras/TensorFlow | Mantener PyTorch | Bloque 6 del Master usa Keras; trazabilidad clase -> proyecto |
| **004** | Persistencia poliglota: SQLite + MongoDB + MinIO | Solo Mongo + MinIO | SQLite refuerza con capa relacional (Bloque 7, SQLAlchemy) |
| **005** | CNN custom desde cero, sin transfer learning | EfficientNet pre-entrenada | Alineacion literal Bloque 6; modelo dentro de RNF-4 (50 MB) |
| **006** | TensorFlow en imagen Docker compartida `hospital-pipeline` | Dos imagenes (pipeline sin TF + ml con TF) | Cambio operativo minimo; entrenamiento dentro del compose |
| **007** | Streamlit + imagen Docker independiente para dashboard | React / Plotly Dash | A 3 dias, Streamlit corta ~70 % del tiempo |
| **008** | Triaje basado en reglas IF-THEN | Clasificador supervisado | No hay etiquetas reales; entrenarlas seria fabricar ground truth |
| **009** | Alertas y vista del informe diario como **vista derivada** (cero estado nuevo) | Tabla `alerts` con estado | Las fuentes (`pipeline_runs`, quality, triage) ya tienen lo necesario |
| **010** | Regla `covid_threshold_0.35` aplicada post-hoc (sin reentrenar) | Reentrenar con class_weight mas agresivo | Sube recall COVID +12,5 pp sin tocar pesos; reversible; trazado |

---

## 13. FAQ — las 20 preguntas mas probables

### Tecnicas

1. **¿Por que CNN custom y no transfer learning?**
   ADR-005. Alineacion literal con el Bloque 6 del Master (Jordi).
   Modelo dentro de 50 MB. Sin dependencias externas en arranque.

2. **¿Por que MongoDB y no Postgres?**
   ADR-002. La jerarquia paciente -> admisiones -> radiografias encaja
   con un modelo documental. `rejected_records.raw_data` es heterogeneo
   entre motivos. PostgreSQL exigiria joins artificiales.

3. **¿Por que tres almacenes si pediais dos?**
   ADR-004. SQLite refuerza la arquitectura con capa relacional
   tabular para metadatos operativos (auditoria runs + quality summary),
   alineada con SQLAlchemy del Bloque 7. Mongo+MinIO ya cumplian, SQLite
   anade rigor.

4. **¿Por que reglas en triaje y no ML?**
   ADR-008. No hay dataset etiquetado con la gravedad real. Entrenar
   sobre etiquetas inventadas por el equipo seria fabricar ground
   truth. Las reglas dan trazabilidad directa.

5. **¿Por que umbral 0,35 y no 0,30?**
   ADR-010. Eleccion sobre el split de **validacion** (no test, para
   no contaminar). 0,30 maximiza recall pero baja precision a 0,71;
   0,40 marginal; 0,35 es el balance recall/precision optimo.

6. **¿Por que post-hoc y no reentrenais?**
   El cambio es reversible en una constante. Reentrenar abre
   dependencias y plazo. El umbral post-hoc es la **mejora barata**;
   transfer learning es el **siguiente paso** (cap 17 de la memoria).

7. **¿Y si las probabilidades no estan calibradas?**
   Lo declaramos en limitaciones (cap 14.1). Las usamos como
   **ranking**, no como probabilidad calibrada en sentido estricto.
   Una prediccion "COVID 0,82" significa "esta es la clase con mayor
   evidencia", no "82 de cada 100".

8. **¿Por que las alertas no se persisten?**
   ADR-009. Vista derivada del estado actual. Cero estado nuevo.
   Reabrible si hiciera falta auditoria historica (tabla `alerts` en
   SQLite con `raised_at`/`resolved_at`).

9. **¿Como sabes que el sistema no inventa datos en el informe diario?**
   Idempotencia byte-a-byte: dos ejecuciones del mismo dia producen
   el mismo sha256. El cuerpo del Markdown no contiene `generated_at`.
   Si las fuentes (Mongo + SQL) no han cambiado, el output no cambia.

10. **¿Como prueba el sistema que funciona end-to-end?**
    Smoke real en `docs/validation/validacion-final.md`: paciente
    con SpO2=85 -> triaje grave -> alerta `triage_severe`/`critical`
    en `/api/v1/alerts`. Mas 417 tests unitarios + integracion + E2E.

### Producto / Decisiones

11. **¿Esto se podria desplegar manana en un hospital?**
    **No**. Cap 14.5 de la memoria lo dice. Es asistencia, no
    diagnostico. Sin certificacion CE/FDA, sin PII real, sin auth,
    sin replicacion. Es entrega academica.

12. **¿Que pasa si la API se cae durante la demo?**
    CB-4. La API responde 503 con mensaje claro en endpoints
    afectados; el dashboard muestra chips rojos en sidebar y sigue
    respondiendo. No hay pantalla blanca, no hay stacktrace al
    operador.

13. **¿Que pasa si llega una imagen que no es radiografia?**
    Limitacion declarada (no hay deteccion out-of-domain). El modelo
    devolveria una clase con confianza arbitraria. Es la limitacion
    mas seria del clasificador para uso real.

14. **¿Por que Streamlit y no React?**
    ADR-007. A 3 dias de la entrega original, Streamlit corto ~70 %
    del tiempo. Dashboard API-only (no rompe la arquitectura).
    Aceptable en entrega academica; con tiempo, React + custom
    components.

### Metodologia y proceso

15. **¿Como aplicasteis IA generativa?**
    Spec-Driven Development (SDD). Cada feature: spec -> design ->
    tareas -> implementar -> revisar. 31 sesiones documentadas en
    `docs/diario-ia.md`. Cross-provider review con Codex en lo
    delicado. La IA no inventa requisitos: trabaja sobre una spec
    aprobada.

16. **¿Como evitasteis que la IA alucinara?**
    Dudas marcadas `[NEEDS CLARIFICATION]`. Decisiones tecnicas
    forzadas a ADR antes de implementar. Tests TDD desde criterios de
    aceptacion. Revisiones cruzadas. Y cuando algo iba mal, paraba y
    pedia clarificacion.

17. **¿Cuanto tiempo ahorrasteis con IA?**
    Estimable en el cap 16 de la memoria. Sin cifras vinculantes,
    pero el orden de magnitud: features que hubiera tardado 2-3 dias
    se cerraron en una sesion intensiva con revision humana.

### Limitaciones / Etica

18. **¿No es peligroso desplegar un clasificador con recall 0,82?**
    Lo es si se usa como diagnostico. **Por eso es asistencia**. La
    UI lo declara, la memoria lo declara, las predicciones se
    persisten con la regla de decision para auditoria, y la
    documentacion exige revision humana de cada prediccion.

19. **¿Los datos respetan GDPR?**
    Son sinteticos por diseno (Faker + seed). Cero PII real. El
    dataset de imagenes es publico (Kaggle) con la licencia que el
    autor publica. No se asume licencia generica.

20. **¿Que harias diferente si lo empezaras hoy?**
    1. Transfer learning desde el principio (DenseNet/EfficientNet
       con pesos medicos como CheXNet) -> recall COVID > 0,90.
    2. Grad-CAM por defecto para interpretabilidad.
    3. Deteccion out-of-domain (clasificador binario "es radiografia
       de torax / no").
    4. Auth + cifrado en transito.
    5. Persistir alertas con historico auditable (reabrir ADR-009).

---

## 14. Frases que conviene repetir

- *"Asistencia, no diagnostico. La decision clinica la mantiene siempre el profesional."*
- *"Cifras reportadas honestamente: recall COVID-19 = 0,820 con la regla; aun asi se pierden 65 de cada 361 positivos."*
- *"El umbral post-hoc es la mejora barata. Transfer learning es el siguiente paso."*
- *"Tres almacenes, dos paradigmas, observabilidad accionable, SDD aplicada de extremo a extremo."*
- *"Decisiones tecnicas no triviales documentadas en ADRs (10). Cero magic numbers, todo razonado."*

---

## 15. Cosas que NO digas

- "El modelo funciona muy bien" -> di "alcanza 0,8766 de accuracy con la regla operativa".
- "Detecta COVID-19" -> di "asiste en la clasificacion de radiografias en 3 clases".
- "El sistema decide" -> di "el sistema propone, el profesional decide".
- "Recall 0,82 es bueno" -> di "recall 0,82 sigue siendo el limite real del sistema".
- "El modelo esta calibrado" -> di "las probabilidades se usan como ranking, no como probabilidad calibrada".
- "Es production-ready" -> di "es una entrega academica reproducible".
- "Hicimos transfer learning" -> NO, fue CNN custom (ADR-005).
- "Mejoramos el recall reentrenando" -> NO, post-hoc con `covid_threshold_0.35` (ADR-010).

---

## 16. Plan B durante la demo (si algo falla)

| Sintoma | Causa probable | Accion inmediata |
|---|---|---|
| Dashboard pinta "API no disponible" en todas las vistas | `hospital-api` parado | `docker compose start api`. Mientras tanto: ensenar chips rojos del sidebar como ejemplo de manejo de errores. |
| Chip "Modelo" en rojo | `.keras` no se cargo al arranque | `docker compose restart api`. Si no hay tiempo, ir directo al slide 12. |
| Clasificador devuelve 422 con una imagen | CB-7: imagen demasiado pequena | Elegir otra `HOSP-PRES-*` del dropdown. |
| No hay `HOSP-PRES-*` en el dropdown | Dataset Kaggle no descargado | Usar `HOSP-DEMO-001` y **avisar explicitamente** que es sintetica. |
| Reveal.js no carga (sin internet) | CDN bloqueado | Abrir `docs/presentation/fallback.md` y leer directamente. |
| Streamlit muestra una stacktrace en pantalla | Bug residual no detectado | Recargar la pagina del dashboard (F5). Si vuelve, saltar a la siguiente vista. |

Detalle completo en `docs/presentation/README.md` (preflight checklist + plan B).

---

## 17. Mapa rapido de artefactos del repo

| Pregunta del tribunal | Donde mirar |
|---|---|
| "¿Donde esta la spec de X?" | `specs/<feature>.md` |
| "¿Como decidisteis X?" | `decisions/ADR-XXX-<topic>.md` |
| "¿Cuanto tarda el pipeline?" | `docs/memoria-tecnica.md` cap 5.8 |
| "¿Que cifras tiene el modelo?" | `docs/model-evaluation/metrics.json` + cap 6.5 de la memoria |
| "¿Hay validacion final?" | `docs/validation/validacion-final.md` |
| "¿Como funciona el threshold?" | `decisions/ADR-010-covid-threshold.md` + `docs/model-evaluation/threshold-analysis.md` |
| "¿Como se uso IA generativa?" | `docs/diario-ia.md` (31 sesiones) |
| "¿Cuantos tests hay?" | 417 verde + 1 skip esperado. Carpeta `tests/` |
| "¿Que ha cambiado y cuando?" | `CHANGELOG.md` |
| "¿Como se despliega?" | `README.md` raiz + `docs/presentation/README.md` |

---

## 18. Comandos que conviene tener a mano

```bash
# Levantar el stack limpio
docker compose down -v && docker compose up -d --build

# Healthchecks
docker compose ps
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
curl -sI http://localhost:8501/_stcore/health | head -1

# Smoke real (lo del slide 11)
curl -s -X POST http://localhost:8000/api/v1/radiographies/classify \
  -H "Content-Type: application/json" \
  -d '{"minio_object_key":"HOSP-PRES-001/COVID-1.png"}' | python3 -m json.tool

# Informe diario (demuestra idempotencia)
docker compose run --rm api python -m src.automation.daily_report --date 2026-05-21
sha256sum docs/reports/2026-05-21.md

# Suite completa
docker compose run --rm api pytest tests/ -q
```

---

## 19. Lo ultimo

> **Es asistencia, no diagnostico. Lo demas son detalles.**
