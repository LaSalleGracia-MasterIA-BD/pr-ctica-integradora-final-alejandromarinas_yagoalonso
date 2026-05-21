# Presentacion final — fallback en Markdown

> Mismo guion y cifras que `presentation.html`. Sirve si reveal.js o el
> navegador no van.
> Tiempos orientativos: ~12 min + Q&A.
> Sin emojis, sin frases tipo "UCI" o "notificar medico"; el sistema es
> **asistencia, no diagnostico**.

---

## Slide 1 — Portada · 00:00 - 00:30

**laSalle Health Center · Sistema Inteligente de Soporte Hospitalario**

Trabajo final del Master IA & Big Data. Alejandro Marinas + Yago Alonso. v1.0.

> **Notas (30s):** abrir con el encuadre del proyecto: hospital ficticio,
> sistema completo de soporte clinico, reproducible con un solo
> `docker compose up`. No es diagnostico vinculante, es asistencia.

---

## Slide 2 — Problema · 00:30 - 01:15

El hospital tiene datos en tres formas:

- **Historias clinicas tabulares** (pacientes + admisiones).
- **Imagen medica** (radiografias de torax sin clasificacion automatizada).
- **Observabilidad** dispersa (logs y trazas sin cuadro de mando).

**Reto:** sistema que ingiera datos a escala, ofrezca asistencia
diagnostica por imagen, exponga un cuadro de mando que un operador no
tecnico use en turno.

> **Notas (45s):** tres fuentes, tres problemas. Mensaje desde el primer
> momento: asistencia, no diagnostico.

---

## Slide 3 — Que pedia el enunciado · 01:15 - 02:00

- Big Data + framework de calculo distribuido.
- IA aplicada con al menos dos paradigmas.
- Persistencia poliglota (>= 2 tipos).
- API REST documentada.
- Dashboard con vista operativa.
- Automatizacion (alertas + informes).
- Despliegue reproducible.
- Uso de IA generativa documentado.

**Como lo cubrimos:** PySpark + CNN custom (Keras) + reglas IF-THEN + MongoDB
+ SQLite + MinIO + FastAPI + Streamlit + `/alerts` + informe diario + SDD.

> **Notas (45s):** cumplimiento literal del enunciado. Entregamos 3
> almacenamientos (no 2), 2 paradigmas (no 1).

---

## Slide 4 — Arquitectura general · 02:00 - 03:00

Siete servicios Docker: mongodb, minio, minio-init, pipeline, api, watcher,
dashboard. Una imagen compartida para pipeline/api/watcher (ADR-006) y
imagen aparte para dashboard (ADR-007).

Flujo: CSV + PNG → pipeline PySpark → MongoDB + SQLite + MinIO → API REST →
dashboard Streamlit (+ CLI informe diario).

> **Notas (1:00):** recorrer izquierda (entradas) → centro (pipeline) →
> derecha (stores + API + dashboard). ADR-001 a ADR-010 documentan las
> decisiones. No pararse mucho en cada caja.

---

## Slide 5 — Datos y almacenamiento · 03:00 - 03:45

Persistencia poliglota (ADR-004). Cada tipo de dato donde encaja.

| Almacen | Que contiene | Cifras |
|---|---|---|
| MongoDB | patients (admissions + radiografias embebidas) | 4.790 pacientes |
| SQLite | pipeline_runs + data_quality_summary | 2 tablas |
| MinIO | PNG radiografias + descartes | bucket dedicado |

Volumen procesado: 4.790 pacientes, 8.569 admisiones, 1.692 registros
rechazados con motivo persistido.

> **Notas (45s):** ADR-002 (Mongo vs Postgres) y ADR-004 (polyglot)
> razonan la decision. Calidad medida con `rejection_rate` por dimension.

---

## Slide 6 — Pipeline PySpark · 03:45 - 04:30

- Validacion + deduplicacion por external_id.
- Enriquecimiento de admisiones (categoria diagnostico, edad calculada).
- Image ingester: PNG → MinIO → embebido en su paciente.
- Idempotente (re-bootstrap NO duplica).
- Auditoria por run en SQLite.

**Performance:** bootstrap en frio ~50 s, warm restart ~1 s.
`docker compose up` deja el sistema en menos de 1 min.

> **Notas (45s):** Big Data del temario, alineado con Bloque 5. El
> watcher en filesystem complementa el bootstrap manual.

---

## Slide 7 — Modelo CNN · 04:30 - 05:30

CNN custom desde cero, sin transfer learning (ADR-005). 21 MB en disco.
Conv2D + MaxPooling2D + Dropout + Dense. Alineada con Bloque 6 del Master.

**Metricas sobre test (1.515 imagenes, regla `covid_threshold_0.35`):**

| Metrica | Valor (operativo) | Baseline argmax |
|---|---|---|
| Accuracy | **0,8766** | 0,8719 |
| Macro-F1 | **0,8594** | 0,8456 |
| Recall Normal | 0,890 | 0,926 |
| Recall Pneumonia | 0,926 | 0,933 |
| **Recall COVID-19** | **0,820** | 0,695 |

> **Notas (1:00):** accuracy y macro-F1 son utiles pero la clave es el
> recall por clase, especialmente COVID-19.

---

## Slide 8 — Threshold COVID 0,35 · 05:30 - 06:30

Regla `covid_threshold_0.35` (ADR-010): **post-hoc, NO reentrena**.

```
si P(COVID-19) >= 0,35  ->  predicted = COVID-19
si no                    ->  argmax(Normal, Pneumonia)
```

| Metrica | Argmax | Threshold 0,35 | Delta |
|---|---|---|---|
| Accuracy | 0,8719 | **0,8766** | +0,005 |
| Macro-F1 | 0,8456 | **0,8594** | +0,014 |
| Recall COVID-19 | 0,6953 | **0,8199** | **+0,125** |
| Precision COVID-19 | 0,8071 | 0,7513 | -0,056 |
| FN COVID-19 | 110 / 361 | **65 / 361** | -45 |

El campo `decision_rule` se persiste en MongoDB y la API lo devuelve.
Baseline argmax se conserva en `metrics.json` (`comparison_argmax`).

> **Notas (1:00):** insistir en que el modelo es el mismo, los pesos son
> los mismos. Lo que cambia es la regla de decision sobre las probabilidades
> softmax. Es reversible en una constante de `predictor.py`. ADR-010
> documenta alternativas descartadas.

---

## Slide 9 — Triaje basado en reglas · 06:30 - 07:15

Segundo paradigma de IA (ADR-008). No hay dataset etiquetado con gravedad
real; entrenar sobre etiquetas inventadas seria fabricar ground truth.

| Nivel | Cuando |
|---|---|
| Grave | 6 reglas criticas (SpO2 / FR / FC / PAS / T) o sintoma critico |
| Medio | 5 reglas intermedias (franjas + combinacion edad-riesgo) |
| Leve | Por defecto |

**Trazabilidad directa:** cada decision lleva la lista exacta de reglas
disparadas. No requiere SHAP ni Grad-CAM, las reglas son legibles.

Umbrales **academicos**, no validados clinicamente. UI con disclaimer
permanente. Recomendaciones operativas genericas (sin "UCI", sin "notificar
medico").

> **Notas (45s):** los dos paradigmas son complementarios. CNN aprende
> donde hay datos; reglas formalizan conocimiento de dominio sin
> ground truth.

---

## Slide 10 — Alertas e informe diario · 07:15 - 08:00

**Vista derivada** (ADR-009). Cero estado nuevo: se calcula al consultar.

| Tipo | Severidad | Fuente |
|---|---|---|
| `pipeline_failed` | HIGH | `pipeline_runs.status='failed'` |
| `data_quality_low` | MEDIUM | `rejection_rate > 0,10` |
| `triage_severe` | CRITICAL | `patients.triage.level='grave'` |

**Informe diario reproducible:**
`python -m src.automation.daily_report --date YYYY-MM-DD` genera
`docs/reports/YYYY-MM-DD.md` con sha256 byte-a-byte identico entre
ejecuciones del mismo dia (sin `generated_at` en el cuerpo).

> **Notas (45s):** tres reglas, dos endpoints, un CLI. Cero estado nuevo.
> Si se quisiera historico auditable de alertas, ADR-009 documenta como
> se reabriria (tabla alerts en SQLite).

---

## Slide 11 — Dashboard · 08:00 - 11:00

Streamlit en imagen Docker aparte (ADR-007). **API-only**: cero imports
de pymongo / sqlite / sqlalchemy / minio en `src/dashboard/`.

**Navegacion:**

- Operacion: Inicio · Triaje · Alertas · Pacientes · Clasificador
- Sistema: Calidad de datos · Pipeline runs

**Demo (orden fijo):**

1. **Inicio (15s)** — barra critica + 3 chips de estado + actividad + accesos rapidos.
2. **Triaje (20s)** — formulario con SpO2 = 85 → grave. Recomendacion generica + motivos humanizados.
3. **Alertas (15s)** — la alerta `triage_severe / critical` del paciente recien creado.
4. **Pacientes (15s)** — paginar y abrir detalle.
5. **Clasificador (45s)** — `HOSP-PRES-001/COVID-1.png` → predicted COVID-19, mostrar `decision_rule = covid_threshold_0.35` en la respuesta. Bajar a "Ver detalle del modelo" → matriz de confusion.
6. **Calidad / Runs (opcional)** — solo si queda tiempo.

> **Notas (3:00):** bloque mas largo. Si la API esta caida, ensenar
> chips rojos del sidebar como ejemplo de error handling. Si la imagen
> no aparece, fallback a HOSP-DEMO-001 con disclaimer.

---

## Slide 12 — IA generativa + SDD · 11:00 - 11:45

`/spec → /planificar → /tareas → /implementar → /revisar`. Dudas
marcadas `[NEEDS CLARIFICATION]`, decisiones en ADRs.

| | |
|---|---|
| Specs aprobadas | 6 |
| ADRs | 10 |
| Sesiones IA documentadas | 31 |
| Tests verde | 417 (+ 1 skip esperado) |

Cross-provider review con Codex cuando aporta valor. Diario IA en
`docs/diario-ia.md`. Lecciones en `tasks/lessons.md`.

> **Notas (45s):** eje obligatorio del enunciado. Mensaje final: la IA es
> multiplicador, SDD es la disciplina que hace seguro ese multiplicador.

---

## Slide 13 — Etica, limitaciones · 11:45 - 12:30

**Etico:**

- Datos sinteticos (Faker + seed). Sin PII real.
- Dataset Kaggle: licencia del autor; no asumimos generica.
- Asistencia, no diagnostico. Decision clinica siempre humana.

**Limitaciones declaradas:**

- Recall COVID-19 = 0,820 con threshold (era 0,695 con argmax). Aun 65 / 361 perdidos.
- Sin deteccion out-of-domain.
- Sin interpretabilidad (Grad-CAM como mejora prioritaria).
- Sin auth, sin replicacion, sin HA.
- Triaje con umbrales academicos, no validados clinicamente.

> **Notas (45s):** honestidad total. La limitacion principal es el
> recall COVID. Por eso el sistema se entrega como asistencia.

---

## Slide 14 — Conclusion + Q&A · 12:30 - cierre

**Tres cifras finales:**

- Modelo: accuracy 0,8766 con threshold 0,35.
- Recall COVID-19: 0,820 (+12,5 pp vs argmax baseline).
- Suite: 417 verde + 1 skip esperado.

**Trabajo futuro priorizado:**

1. Subir recall COVID via transfer learning (la regla post-hoc ya agoto la ganancia barata).
2. Grad-CAM por defecto.
3. Deteccion out-of-domain.
4. Persistir alertas con historico auditable.

**Preguntas.**

> **Notas (cierre):** repositorio en `github.com/MarinasAlejandro/lasalle-hospital`.
> Si preguntan por SDD o IA: remitir al diario y al CHANGELOG.

---

## Plan B si algo falla

- Si la API no responde: ensenar chips rojos del sidebar como ejemplo de
  manejo de errores. CB-4 cubierto.
- Si `HOSP-PRES-*` no aparece: usar `HOSP-DEMO-001` y avisar explicitamente
  que es sintetica.
- Si la demo no arranca: capturas y matriz de confusion en
  `docs/model-evaluation/`, saltar al slide 12.
