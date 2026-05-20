# Presentación final — Fallback en Markdown plano

> **Versión offline / sin reveal.js.** Mismo contenido que `presentation.html`,
> en Markdown plano. Pensado para usar como respaldo si no hay conexión y no
> se ha vendorizado reveal.js en `docs/presentation/vendor/`.
>
> Cada bloque empieza con el **número de slide** + **título** + **tiempo
> objetivo**. Las notas del presentador van en bloques `> ` debajo del contenido.

---

## Slide 1 — Portada · 0:00 - 0:30

# Sistema Inteligente de Soporte Hospitalario

**laSalle Health Center** — Asistencia diagnóstica con Big Data e IA.

- **Alejandro Marinas** · **Yago**
- Máster en AI & Big Data · Proyecto final del Máster
- Defensa · 2026-05-18

> **Notas (0:30):** saludo breve. Presentación del equipo y del proyecto.
> Avisar de que en 12 minutos cubriremos problema, solución, demo en vivo,
> modelo, uso de IA y SDD.

---

## Slide 2 — El problema · 0:30 - 1:30

El hospital ficticio **laSalle Health Center** tiene tres tipos de información
que hoy gestiona de forma fragmentada:

- **Datos clínicos tabulares**: pacientes, admisiones, diagnósticos. Sin
  procesamiento sistemático.
- **Radiografías de tórax**: PNG en disco. Sin clasificación automatizada.
- **Logs y trazas**: sin cuadro de mando que consolide el estado.

Falta un sistema que **procese a escala**, **asista al diagnóstico por imagen**
y **presente todo en un cuadro de mando único**.

> **Notas (1:00):** insistir en que el hospital es ficticio. Los datos son
> sintéticos (clave para la sección de ética/legal). Cerrar con la idea
> "asistencia diagnóstica, no diagnóstico final" — la repetiremos en el bloque
> del modelo.

---

## Slide 3 — Qué hemos construido · 1:30 - 2:30

Cuatro piezas interdependientes, un único `docker compose up`:

- **Pipeline ETL** — PySpark ingesta CSVs e imágenes, valida, limpia,
  enriquece.
- **Modelo de IA** — CNN Keras/TF custom. Sana / Pneumonia / COVID-19.
- **API REST** — FastAPI: 17 endpoints + Swagger automático.
- **Dashboard** — Streamlit: centro de control hospitalario, 7 vistas.

Cifras de referencia:

| Indicador | Valor |
|---|---|
| Servicios Docker | 7 |
| Almacenes (Mongo + SQLite + MinIO) | 3 |
| Tests verdes | 404 (+ 1 skip esperado) |
| ADRs documentadas | 9 |

> **Notas (1:00):** una frase por pieza. Las cifras de abajo son el "qué se
> entrega": 7 servicios, 3 almacenes (poliglota), 404 tests, 9 ADRs. Mencionar
> que arranca con un único `docker compose up` y queda listo en menos de un
> minuto.

---

## Slide 4 — Arquitectura · 2:30 - 4:00

```
   Usuario --HTTP-->  Dashboard (Streamlit, :8501)
   (navegador)              |
                            | HTTP (api_client)
                            v
                        +------------------------+
                        |     API REST           |
                        |   (FastAPI, :8000)     |
                        |   readers + classify   |
                        +------------------------+
                          |        |        |
                  lee/inf | lee    | lee    |
                          v        v        v
                       MongoDB  SQLite    MinIO
                       (docs)   (runs +   (PNGs)
                                quality)
                          ^        ^        ^
                          | write  | write  | write
                          +-----+--+--------+
                                |
                  +-------------+--------------+
                  |                            |
            Pipeline ETL                   Watcher
            (PySpark, batch)               (watchdog)
```

Polyglot persistence (**ADR-004**): cada dato vive donde su forma encaja. El
dashboard **nunca** accede directamente a los almacenes.

> **Notas (1:30):** señalar el diagrama: dashboard arriba, API en el medio,
> tres almacenes abajo. Las únicas escrituras directas a los almacenes son del
> pipeline y del watcher. El dashboard es API-only (ADR-007) — eso permite
> imagen Docker ligera (~240 MB). Polyglot persistence (ADR-004): MongoDB para
> datos clínicos jerárquicos, SQLite para metadatos tabulares del pipeline,
> MinIO para binarios. Si preguntan por qué tres BBDD: cada dato donde su
> forma encaja, sin duplicar fuente de verdad.

---

## Slide 5 — Datos · 4:00 - 5:00

### Datos clínicos tabulares (Faker, seed 42)

| RAW | Final | Motivo del descarte |
|---|---|---|
| 5.150 pacientes | **4.745** | 264 validación + 141 dedup |
| 10.000 admisiones | **8.569** | 493 validación + 3 dedup + 935 huérfanas |

No hay PII real. **Decisión ética por diseño.**

### Radiografías de tórax

COVID-19 Radiography Database (Kaggle, ~0,9 GB local).

| Clase | Imágenes |
|---|---|
| Normal | 10.192 |
| COVID-19 | 3.616 |
| Viral Pneumonia | 1.345 |
| Lung_Opacity (descartada) | 6.012 |

Split estratificado 80 / 10 / 10, seed 42. Test = **1.515 imágenes**.

> **Notas (1:00):** decir cifras altas sin perderse en detalles. Insistir:
> datos sintéticos por ética. Lung_Opacity descartada porque "opacidad
> pulmonar" es un hallazgo radiológico, no una categoría diagnóstica.

---

## Slide 6 — Pipeline ETL · 5:00 - 6:00

```
CSVIngester -> DataValidator -> DataCleaner -> DataTransformer -> MongoWriter
                     |                                            ^
                     v                                            |
              rejected_records                              patients + admisiones
                  (Mongo)                                      embebidas

SqlWriter envuelve toda la ejecución:
  start_pipeline_run  ->  finish_pipeline_run + write_quality_summary
```

- **Validación**: reglas *first-failure-wins*. **1.692** rechazados con motivo
  trazable.
- **Idempotente**: reejecutar = mismo estado. CA-6 cubierto.
- **Auditoría completa**: cada ejecución deja huella en SQLite
  (`pipeline_runs`).

Cuatro *triggers*: bootstrap, watcher (`data/incoming/`), API
(`POST /pipeline/trigger`), tests E2E.

> **Notas (1:00):** recorrer rápido la cadena de etapas. Insistir en
> idempotencia (CA-6): re-ejecutar no duplica. Mencionar los 4 triggers. Si
> preguntan: el rechazo de las 935 admisiones huérfanas (cross-entity
> validation) fue uno de los bugs que detectamos cuadrando los números.

---

## Slide 7 — Modelo CNN · 6:00 - 7:30

### Arquitectura (ADR-005)

```
Input (224x224x1, grayscale)
  4 x Conv2D + MaxPool (32, 64, 128, 128)
  Dropout(0.3) + Flatten
  Dense(64) + Dropout(0.3)
  Dense(3, softmax)
```

- CNN custom, sin transfer learning.
- ~1,8M params · 21 MB en disco.
- 35 epochs · lr=1e-4 · class_weight=sqrt.
- Alineación literal con el Bloque 6 del Máster.

### Métricas sobre test (1.515 imágenes)

- **Accuracy:** 0,872
- **Macro-F1:** 0,846

| Clase | Recall | F1 |
|---|---|---|
| Normal | 0,926 | 0,912 |
| Pneumonia | 0,933 | 0,878 |
| COVID-19 | **0,695** | 0,747 |

> **Notas (1:30):** la arquitectura se ve pero no nos perdemos en detalles.
> Mensaje clave: CNN custom, no transfer learning, alineada con lo que enseña
> Jordi en el Bloque 6. 21 MB cabe commiteada al repo (RNF-4 < 50 MB). Las
> métricas son buenas pero NO son el indicador clave. El recall por clase sí.
> Normal y Pneumonia bien. COVID-19 0,695 → preparar el siguiente slide.

---

## Slide 8 — Análisis clínico · 7:30 - 8:30

### Matriz de confusión

| Real \ Pred. | Normal | Pneumonia | COVID-19 |
|---|---|---|---|
| **Normal** | 944 | 17 | 58 |
| **Pneumonia** | 7 | 126 | 2 |
| **COVID-19** | **101** | 9 | 251 |

110 COVID-19 mal clasificados de 361 (recall 0,695).

### Consecuencia clínica

- **FN COVID → "Normal"**: no se aísla a un contagioso. **Error más grave.**
- FN Pneumonia: paciente sin tratamiento adecuado.
- FP: pruebas adicionales innecesarias, pero sin riesgo clínico.

**Posicionamiento del sistema:** el modelo se entrega como **asistencia
diagnóstica**, NUNCA como diagnóstico final. La última palabra es del clínico
humano.

> **Notas (1:00):** insistir en que el recall COVID 0,695 es el LÍMITE del
> sistema. 110 COVID-19 mal clasificados / 361 = ~30% de FN. Mensaje clave que
> se repite en memoria, runbook y UI: ASISTENCIA, no diagnóstico. Mejoras
> posibles: transfer learning con DenseNet/EfficientNet, Grad-CAM,
> out-of-domain.

---

## Slide 9 — Demo en vivo · 8:30 - 11:00

Abrir en el navegador:

- **Dashboard:** http://localhost:8501
- API · Swagger: http://localhost:8000/docs
- MinIO · consola: http://localhost:9001

Recorrido por las 7 vistas: **Overview · Calidad · Pacientes · Triaje ·
Alertas · Clasificador · Pipeline runs**.

### Guion (sigue `docs/runbooks/presentation-demo.md`)

1. **Overview (20s)** — 4 cards arriba + último run + strip de evaluación +
   sidebar con 3 chips verdes. Mensaje: "el sistema está arriba, los datos
   cargados, el modelo listo".
2. **Calidad de datos (15s)** — snapshot por dimensión + gráfico histórico
   rejection_rate. Mensaje: "el pipeline rechaza datos malos de forma
   controlada y queda traza".
3. **Pacientes (15s)** — tabla paginada → click en una fila → detalle con
   admisiones y radiografías embebidas. Mensaje: "MongoDB embebe admisiones
   y radiografías sin joins".
4. **Triaje (20s)** — formulario con signos vitales (SpO2 = 85). POST →
   paciente nuevo con `triage.level=grave` y `reasons=["spo2_lt_92"]`.
   Mensaje: "reglas IF-THEN deterministas, cada decisión cita la regla
   (ADR-008)".
5. **Alertas (15s)** — vista nueva: la alerta `triage_severe`/`critical`
   del paciente recién creado aparece en tiempo real. Mensaje: "vista
   derivada, cero estado nuevo persistido (ADR-009)".
6. **Clasificador (45s)** — momento clave. Dropdown ordenado: `HOSP-PRES-*`
   primero. Seleccionar `HOSP-PRES-001` (COVID real). "Clasificar" → clase +
   probabilidades + `model_version`. Bajar a "Evaluación detallada" → matriz
   de confusión heatmap. PARAR y decir: "el recall de COVID-19 es 0,695. Por
   eso el sistema es asistencia, no diagnóstico."
7. **Pipeline runs (20s)** — tabla del histórico + opcional run failed con
   `error_message`. Mensaje: "cada ejecución deja traza auditable en SQLite,
   no en ficheros sueltos".

### Plan B si algo falla

- Si la API no responde: enseñar los chips rojos del sidebar como ejemplo de
  manejo de errores.
- Si `HOSP-PRES-*` no aparece: usar `HOSP-DEMO-001` y AVISAR explícitamente
  que es sintética.
- Si la demo no arranca: capturas en `docs/model-evaluation/` + ir directo al
  slide 10.

> **Pre-demo checklist (preflight):** ver `README.md` de esta carpeta.

---

## Slide 10 — Uso de IA + SDD · 11:00 - 11:45

El proyecto se ha desarrollado en pareo con asistentes de IA + revisión
técnica del equipo y contraste contra la spec, bajo metodología
**Spec-Driven Development**.

```
/spec  ->  /planificar  ->  /tareas  ->  /implementar  ->  /revisar
 QUÉ         CÓMO          EN QUÉ        CÓDIGO          ¿CUMPLE?
                           ORDEN
```

| Indicador | Valor |
|---|---|
| Specs aprobadas | 4 |
| ADRs | 7 |
| Sesiones IA documentadas | 28 |
| Lecciones registradas | 57 |

**Disciplina:** dudas marcadas como `[NEEDS CLARIFICATION]`, no se asumen.
Decisiones técnicas en ADRs. Revisión cruzada con otro proveedor para mitigar
*sycophancy* del LLM.

> **Notas (45s):** eje obligatorio del enunciado. SDD descompone en 5 fases con
> artefacto revisable por fase. La IA no inventa requisitos: trabaja sobre una
> spec aprobada. Cierre: "la IA es un multiplicador de capacidad, no un
> sustituto; SDD es la disciplina que hace seguro ese multiplicador".

---

## Slide 11 — Ética + Limitaciones · 11:45 - 12:05

### Ético y legal

- **Datos sintéticos por diseño**: ninguna PII real. Faker + seed 42.
- Dataset Kaggle: licencia tal como la publica el proveedor. **No asumimos
  licencia genérica.**
- **Asistencia, no diagnóstico.** La última palabra es del clínico.

### Limitaciones reconocidas

- Recall COVID **0,695** → ~30% FN clínicamente graves.
- Sin detección *out-of-domain* (rechazar lo que no es radiografía).
- Sin interpretabilidad (Grad-CAM).
- Sin auth ni HA: entorno académico de demo.

> **Notas (20s):** datos sintéticos = riesgo de PII neutralizado. Licencia: no
> citar una licencia concreta sin comprobarla; usar "los términos que publica
> el autor del dataset". Ser honesto sobre el recall COVID como límite real.

---

## Slide 12 — Conclusiones · 12:05 - 12:30

### Qué se entrega

- Sistema completo, reproducible: 1 comando.
- 404 tests verdes + 1 skip esperado.
- Memoria técnica de 26 pp. + 9 ADRs + 6 specs.
- Diario IA: 30 sesiones documentadas.
- **Observabilidad accionable (Feature 15)**: `GET /api/v1/alerts`,
  `GET /api/v1/reports/daily`, script CLI `daily_report.py` con Markdown
  idempotente byte-a-byte y vista *Alertas* en el dashboard.

### Trabajo futuro priorizado

1. Subir recall COVID via *transfer learning*.
2. Interpretabilidad: Grad-CAM por defecto.
3. Detección *out-of-domain*.
4. Auth + cifrado en tránsito.
5. Persistir alertas como histórico auditable (reabrir ADR-009).

> **Notas (25s):** cerrar lo que se entrega. El orden del trabajo futuro
> importa, refleja lo que la memoria razona en cap 16.3.

---

## Slide 13 — Gracias + Q&A · cierre

# Gracias

**Preguntas y comentarios.**

- Repositorio: `github.com/MarinasAlejandro/lasalle-hospital`
- Memoria técnica: `docs/memoria-tecnica.md`
- Diario IA: `docs/diario-ia.md`
- Runbook demo: `docs/runbooks/presentation-demo.md`

*Alejandro Marinas · Yago · Máster en AI & Big Data · 2026-05-18*

> **Preguntas frecuentes esperables:**
> - "¿Por qué CNN custom y no transfer learning?" → ADR-005, alineación con
>   Bloque 6 + tamaño <50 MB.
> - "¿Cómo afecta el desbalance de clases?" → CB-6 mitigado con
>   `class_weight=sqrt`.
> - "¿Cómo escalaría a producción?" → cap 13 limitaciones + cap 16 trabajo
>   futuro.
> - "¿Cómo se mide el éxito del proyecto?" → 404 tests + criterio clínico
>   cualitativo, no accuracy bruta.
