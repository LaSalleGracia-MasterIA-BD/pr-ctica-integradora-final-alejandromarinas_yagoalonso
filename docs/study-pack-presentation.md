# Study pack — guion slide por slide

> Alineado con las **14 slides** de `docs/presentation/presentation.html`.
> Para cada slide tienes: tiempo objetivo, que decir (en voz alta),
> cifras clave que mencionar, mensaje principal que clavar, preguntas
> tipicas que pueden caer en ese momento y como responder.
>
> Duracion objetivo: **12 min + Q&A**. Si te pasas, recorta sobre la
> marcha — no en el deck.
>
> Atajo durante la presentacion: tecla `S` abre la vista de speaker
> con cronometro + notas + preview del siguiente.

---

## Slide 1 — Portada · 00:00 - 00:30

### Que ves en pantalla
- Titulo "Sistema Inteligente de Soporte Hospitalario".
- Subtitulo "Big Data + IA aplicada".
- Pildora con autores: Alejandro Marinas + Yago Alonso.
- SVG scope con grid + linea ECG animada (decoracion sobria).

### Que digo (30 s)
> *"Buenos dias. Presentamos el sistema de soporte hospitalario
> que hemos construido para el hospital ficticio laSalle Health
> Center: ingesta de datos a escala, asistencia diagnostica por
> imagen, triaje basado en reglas y observabilidad operativa.
> Reproducible con un solo `docker compose up`. Es asistencia, no
> diagnostico vinculante."*

### Mensaje clave
- Encuadrar **desde el primer momento**: asistencia, no diagnostico.

### Cifras a mencionar
Ninguna. Solo enmarcar.

### Preguntas que pueden caer aqui
- *(Normalmente no caen en la portada. Si caen, contestar corto y
  prometer "lo cubrimos en los siguientes slides")*

---

## Slide 2 — Problema · 00:30 - 01:15

### Que ves en pantalla
- 3 cards: historias clinicas, imagen medica, observabilidad.
- Frase clave: "Reto: ingerir datos a escala, asistencia diagnostica
  por imagen, cuadro de mando para operador".

### Que digo (45 s)
> *"El hospital tiene tres tipos de informacion que hoy gestiona de
> forma fragmentada: historias clinicas tabulares, radiografias de
> torax sin clasificacion automatizada y trazas operativas sin
> cuadro de mando. El reto era construir un sistema que cubriera
> los tres huecos sin pretender reemplazar el juicio clinico humano."*

### Mensaje clave
- **Tres fuentes -> tres problemas**.
- Insistir: asistencia, no diagnostico.

### Cifras a mencionar
Ninguna obligatoria.

### Preguntas que pueden caer aqui
- *"¿Por que un hospital ficticio?"* -> sin acceso a datos reales con PII;
  sintetizamos con Faker + seed para reproducibilidad.

---

## Slide 3 — Que pedia el enunciado · 01:15 - 02:00

### Que ves en pantalla
- 8 ejes del enunciado en dos columnas.
- Card abajo: como hemos cubierto cada eje.

### Que digo (45 s)
> *"El enunciado pedia Big Data, dos paradigmas de IA, al menos dos
> almacenes, una API REST, un dashboard, automatizacion, despliegue
> reproducible y uso de IA generativa documentado. Lo hemos cubierto
> con PySpark, CNN custom + reglas IF-THEN, tres almacenes
> (MongoDB + SQLite + MinIO), FastAPI con 17 endpoints, Streamlit
> con 7 vistas, observabilidad con `/alerts` e informe diario, un
> solo `docker compose up`, y SDD aplicada de extremo a extremo."*

### Mensaje clave
- **Tres almacenes, no dos. Dos paradigmas, no uno. Entregamos mas
  de lo que pedia el enunciado, no menos.**

### Cifras a mencionar
- 3 almacenes, 2 paradigmas, 17 endpoints, 7 vistas.

### Preguntas que pueden caer aqui
- *"¿Por que tres almacenes si pedian dos?"* -> SQLite refuerza
  con capa relacional para metadatos operativos. ADR-004.

---

## Slide 4 — Arquitectura general · 02:00 - 03:00

### Que ves en pantalla
- Diagrama SVG inline: entradas (CSV + PNG) -> pipeline PySpark ->
  3 almacenes -> API -> dashboard + CLI informe.

### Que digo (1 min)
> *"La arquitectura: CSV de pacientes y admisiones mas PNG de
> radiografias entran al pipeline PySpark, que valida, deduplica y
> enriquece. Los datos salen a tres almacenes — MongoDB para datos
> clinicos jerarquicos, SQLite para metadatos operativos del pipeline,
> MinIO para imagenes. La API FastAPI sirve datos y la inferencia del
> modelo. El dashboard Streamlit consume solo la API. Cierra el
> circulo el informe diario reproducible que escribe Markdown
> idempotente byte-a-byte."*

### Mensaje clave
- **Arquitectura clara**, sin sorpresas, decisiones documentadas en ADRs.

### Cifras a mencionar
- 7 servicios Docker.
- Una imagen compartida para pipeline/api/watcher (ADR-006).
- Imagen aparte para dashboard (ADR-007, ~240 MB).

### Preguntas que pueden caer aqui
- *"¿Por que una imagen compartida para 3 servicios?"* -> ADR-006.
  Evitar duplicacion de capas + desincronizacion de versiones entre
  componentes que comparten codigo. Cambio operativo minimo.
- *"¿Por que el dashboard en imagen aparte?"* -> ADR-007. Su arbol de
  dependencias no necesita TF ni PySpark; imagen ligera.

---

## Slide 5 — Datos y almacenamiento · 03:00 - 03:45

### Que ves en pantalla
- 3 cards de almacenamiento (Mongo / SQLite / MinIO).
- Cards de volumen procesado.

### Que digo (45 s)
> *"Persistencia poliglota: cada tipo de dato vive donde encaja.
> MongoDB para la jerarquia paciente -> admisiones -> radiografias,
> que no necesita joins artificiales. SQLite para metadatos operativos
> del pipeline — auditoria de runs y metricas de calidad agregadas.
> MinIO para los binarios PNG. Sobre el dataset sintetico generado
> con Faker, el pipeline procesa unos 4.790 pacientes y 8.569
> admisiones; 1.692 registros rechazados quedan persistidos con su
> raw_data y motivo, consultables desde la vista Calidad."*

### Mensaje clave
- **No es "porque puedo"**: cada base resuelve un encaje natural distinto.

### Cifras a mencionar
- 4.790 pacientes, 8.569 admisiones, 24 radiografias.
- 1.692 rechazados (264 pacientes + 1.428 admisiones).

### Preguntas que pueden caer aqui
- *"¿Por que MongoDB y no PostgreSQL?"* -> ADR-002. Jerarquia natural
  + `rejected_records.raw_data` heterogeneo entre motivos.
- *"¿Que hacen los rejected?"* -> Se persisten para auditoria. Si una
  fila falla validacion (edad fuera de rango, fecha invalida, paciente
  duplicado), se guarda en `rejected_records` con el motivo. Es lo que
  dispara la alerta `data_quality_low`.

---

## Slide 6 — Pipeline PySpark · 03:45 - 04:30

### Que ves en pantalla
- Lista de etapas (validar, deduplicar, enriquecer, ingestar imagenes,
  auditar runs).
- Card de performance (~50 s frio, ~1 s warm).
- Card de rejected records.

### Que digo (45 s)
> *"El pipeline corre sobre PySpark — Big Data del temario, alineado
> con el Bloque 5. Cinco etapas: valida, deduplica por `external_id`,
> enriquece admisiones con categoria diagnostica, sube las imagenes
> a MinIO y las embebe en su paciente, y persiste auditoria por run en
> SQLite. Es idempotente: re-bootstrap NO crea duplicados. El watcher
> sobre filesystem complementa el bootstrap manual."*

### Mensaje clave
- **Pipeline idempotente, con auditoria por run, con calidad medida**.

### Cifras a mencionar
- Bootstrap frio ~50 s, warm restart ~1 s.
- `docker compose up` deja el sistema operativo en < 1 min.

### Preguntas que pueden caer aqui
- *"¿Por que no streaming?"* -> Fuera de alcance (lo declaramos). El
  watcher sobre filesystem cubre el lado automatico.
- *"¿PySpark sobre que cluster?"* -> Single-node embebido en Docker.
  Es el patron del temario para ejercicios. Para produccion real,
  cluster de verdad.

---

## Slide 7 — Modelo CNN · 04:30 - 05:30 — BLOQUE TECNICO 1

### Que ves en pantalla
- Columna izquierda: arquitectura CNN custom, alineacion Bloque 6.
- Columna derecha: cards de metricas. **Accuracy 0,8766 · Macro-F1
  0,8594 · Recall Normal 0,890 · Recall Pneumonia 0,926 · Recall
  COVID-19 0,820 con delta +12,5 pp**.

### Que digo (1 min)
> *"El modelo es una CNN custom entrenada desde cero, sin transfer
> learning. La decision esta formalizada en ADR-005: alineacion
> literal con el patron docente del Bloque 6 del Master, modelo
> dentro del techo de 50 MB del RNF-4, sin dependencias externas en
> arranque. Sobre el split de test de 1.515 radiografias, alcanza
> accuracy de 0,8766 y macro-F1 de 0,8594. Lo importante es el
> recall por clase, porque en un hospital lo que pesa es no perder
> casos. Y ahi el recall de COVID-19 es de 0,820, frente al baseline
> argmax que daba 0,695 — una mejora de 12,5 puntos porcentuales que
> conseguimos sin reentrenar el modelo, y que explico en el siguiente
> slide."*

### Mensaje clave
- **El recall por clase importa mas que la accuracy**.
- **CNN custom es deliberado** (ADR-005), no por incapacidad.

### Cifras a mencionar (de memoria)
- 1.515 imagenes en test (1.019 Normal + 361 COVID + 135 Pneumonia).
- accuracy 0,8766, macro-F1 0,8594.
- recall COVID 0,820 (vs argmax 0,695).
- Modelo: 21 MB.

### Preguntas que pueden caer aqui
- *"¿Por que sin transfer learning?"* -> ADR-005. Bloque 6 enseña
  CNN custom. Modelo < 50 MB. Es el siguiente paso si el proyecto
  continua (cap 17).
- *"¿Que pasa con la imagen sintetica HOSP-DEMO-001?"* -> Generada
  con numpy+Pillow para que el dashboard funcione sin pedir descarga
  del dataset. La UI lo declara con banner amarillo.
- *"¿Por que el primer entrenamiento fue degenerado?"* -> `lr=1e-3`
  demasiado alto + `class_weight` lineal 3,76 agresivo. Fix: bajar lr
  a `1e-4` y suavizar class_weight con raiz cuadrada. Documentado en
  `tasks/lessons.md`.

---

## Slide 8 — Threshold COVID 0,35 · 05:30 - 06:30 — BLOQUE TECNICO 2

### Que ves en pantalla
- Frase clave: "Post-hoc sobre las probabilidades softmax. **NO
  reentrena el modelo**".
- Bloque de codigo con la regla.
- Tabla comparativa argmax vs threshold 0,35 con deltas en colores.

### Que digo (1 min)
> *"Aqui esta el aprendizaje mas honesto del proyecto. El modelo
> base, con argmax puro, daba recall COVID-19 de 0,695: dejaba pasar
> 110 de 361 positivos. Aplicamos un umbral post-hoc sobre las
> probabilidades softmax: si la probabilidad de COVID-19 supera 0,35,
> predecimos COVID-19; si no, argmax entre Normal y Pneumonia. Es la
> regla `covid_threshold_0.35`, documentada en ADR-010. El modelo es
> el mismo, los pesos son los mismos, el dataset es el mismo. Lo
> unico que cambia es la regla de decision. Subimos recall COVID de
> 0,695 a 0,820 — 45 falsos negativos menos. A cambio, perdemos 5,6
> puntos de precision COVID y 3,6 puntos de recall Normal. Cada
> prediccion persiste el campo `decision_rule` en Mongo, y el
> baseline argmax queda guardado en `metrics.json` bajo
> `comparison_argmax` para auditoria. La regla es reversible en una
> constante. ADR-010 documenta las alternativas descartadas: class
> weight mas agresivo, transfer learning, ensembling."*

### Mensaje clave
- **No hemos reentrenado. Es post-hoc, trazado, reversible, auditable**.
- **El recall COVID 0,820 sigue siendo el limite real del sistema**.

### Cifras a mencionar (de memoria)
- Threshold = 0,35.
- Recall COVID 0,695 -> 0,820 (+12,5 pp).
- FN COVID 110 -> 65 (de 361 totales).
- Precision COVID 0,807 -> 0,751 (-5,6 pp).

### Preguntas que pueden caer aqui (las mas duras del dia, leelas dos veces)

- *"¿Por que 0,35 y no 0,30?"* -> Eleccion sobre el split de
  **validacion** (no test, para no contaminar). 0,30 maximiza recall
  pero baja precision a 0,71; 0,40 marginal; 0,35 mejor balance
  recall/precision. Documentado en ADR-010 + threshold-analysis.

- *"¿Por que no reentrenais con class_weight mas agresivo?"* -> Es el
  siguiente paso (cap 17). Reentrenar abre dependencias (refactor
  train.py, regenerar artefactos, validar otra vez). El umbral
  post-hoc es la mejora barata; reentrenamiento es la mejora cara.

- *"¿No es un parche?"* -> Lo es. Y lo declaramos en ADR-010: "Es un
  parche, no una solucion". El modelo subyacente sigue teniendo
  recall 0,695 con argmax. La regla compensa el sesgo del modelo
  hacia Normal, pero no lo elimina. El siguiente paso es transfer
  learning o reentrenar.

- *"¿Como sabeis que no overfittea al test?"* -> Porque el umbral se
  elige sobre validacion, no sobre test. Test se usa una sola vez,
  para verificar la decision. ADR-010 lo documenta como practica
  metodologica.

- *"¿Estan calibradas las probabilidades?"* -> No estrictamente. Las
  usamos como ranking, no como probabilidad calibrada. Lo declaramos
  en limitaciones. Una prediccion "COVID 0,82" significa "esta clase
  tiene la mayor evidencia", no "82 de cada 100 con esta confianza son
  COVID reales".

---

## Slide 9 — Triaje por reglas · 06:30 - 07:15

### Que ves en pantalla
- 3 cards: grave / medio / leve.
- Card de trazabilidad + limitaciones declaradas.

### Que digo (45 s)
> *"El segundo paradigma de IA es un sistema basado en reglas IF-THEN
> para el triaje. La decision esta en ADR-008. La razon: no existe
> dataset etiquetado con la gravedad real de cada paciente; entrenar
> sobre etiquetas inventadas por el equipo seria fabricar ground
> truth, no aprenderlo. El sistema asigna nivel grave, medio o leve
> segun seis reglas criticas sobre signos vitales o cinco reglas
> intermedias. Cada decision lleva la lista exacta de reglas que han
> disparado: la explicabilidad es directa, no necesita SHAP ni
> Grad-CAM. Eso si: los umbrales son academicos, no validados
> clinicamente, y la UI mantiene el disclaimer en cada prediccion."*

### Mensaje clave
- **Reglas porque no hay ground truth**. Es decision metodologica.
- **Trazabilidad directa, no necesita interpretabilidad anadida**.

### Cifras a mencionar
- 6 reglas grave + 5 reglas medio.
- `rules_version` persistida en cada paciente.

### Preguntas que pueden caer aqui
- *"¿Por que no aprender las reglas con un clasificador?"* -> ADR-008.
  Sin etiquetas reales no se puede aprender. Reglas escritas formalizan
  conocimiento de dominio sin inventar ground truth.
- *"¿Los umbrales son qSOFA / NEWS2?"* -> NO. Son **academicos**, no
  validados clinicamente. Inspirados en signos vitales plausibles
  pero NO son protocolo clinico real. La UI lo declara.
- *"¿Como se combinan multiples reglas que disparan?"* -> El sistema
  guarda **todas** las reglas que disparan en `reasons`. La explicacion
  es: "se asigna grave porque dispararon estas N reglas". No hay
  ponderacion, hay enumeracion.

---

## Slide 10 — Alertas + informe diario · 07:15 - 08:00

### Que ves en pantalla
- 3 cards de alertas (pipeline_failed / data_quality_low / triage_severe).
- Card del informe diario reproducible.

### Que digo (45 s)
> *"La observabilidad del sistema vive como vista derivada: cero
> estado nuevo persistido. ADR-009. Las alertas se calculan al
> consultar el endpoint, leyendo las tres fuentes que ya existen:
> pipeline_runs para alertar fallos del ETL, data_quality_summary
> para alertar cuando el rejection_rate supera el 10 %, y patients
> .triage para alertar pacientes triajeados como grave. Tres reglas,
> tres severidades — high, medium, critical. Y un informe diario
> reproducible: el CLI `daily_report.py` escribe Markdown idempotente
> byte-a-byte para el mismo dia, sin generated_at en el cuerpo. Dos
> ejecuciones del mismo dia producen el mismo sha256. Es nuestra
> garantia de que el sistema no inventa numeros."*

### Mensaje clave
- **Cero estado nuevo persistido, vista derivada**.
- **Idempotencia byte-a-byte demuestra que el sistema no inventa**.

### Cifras a mencionar
- 3 tipos de alerta, 3 severidades.
- Umbral por defecto: `rejection_rate > 0,10`.
- Ventana por defecto: 24 h en `/alerts`, dia natural UTC en `/reports/daily`.

### Preguntas que pueden caer aqui
- *"¿Por que no persistis las alertas?"* -> ADR-009. Vista derivada.
  Reabrible si hace falta auditoria historica (tabla `alerts` en
  SQLite con `raised_at` y `resolved_at`).
- *"¿Es push o pull?"* -> Pull. El operador debe abrir el dashboard.
  Limitacion declarada. En produccion real anadiriamos notificacion
  push (email, busca).
- *"¿Que hace que el informe sea byte-a-byte identico?"* -> El cuerpo
  del Markdown no contiene `generated_at` ni timestamps de
  ejecucion. Solo contiene datos del dia consultado.

---

## Slide 11 — Dashboard / demo · 08:00 - 11:00 — DEMO EN VIVO

### Que ves en pantalla
- 7 vistas listadas.
- Flujo demo (Inicio -> Triaje -> Alertas -> Pacientes -> Clasificador).

### Que digo + hago (3 min)
> *"El dashboard esta en Streamlit, en imagen Docker aparte (ADR-007).
> Cero imports de pymongo, sqlite o minio: es API-only. Siete vistas
> divididas en Operacion — Inicio, Triaje, Alertas, Pacientes,
> Clasificador — y Sistema, las dos vistas de diagnostico tecnico:
> Calidad de datos y Pipeline runs. Vamos a hacer un recorrido."*

**Orden fijo de la demo:**

1. **Inicio (15 s)**: ensenar saludo, volumen del sistema, barra
   critica si hay, 3 chips de estado, 4 cards de actividad, 3
   accesos rapidos.
2. **Triaje (20 s)**: meter `SpO2 = 85` + nombre "Demo Tribunal".
   Click "Calcular prioridad". Mostrar panel coral "GRAVE +
   Priorizar revision inmediata por profesional sanitario". Senalar:
   recomendacion **generica**, sin "UCI" ni "notificar medico". Y la
   regla disparada: "Saturacion de oxigeno por debajo de 92 %".
3. **Alertas (15 s)**: aparece la alerta `triage_severe` /
   `critical` del paciente que acabo de crear. Tarjeta con marker
   coral, body humanizado, meta tecnica abajo.
4. **Pacientes (15 s)**: ensenar el buscador y la paginacion. Click
   en una fila para ver detalle.
5. **Clasificador (45 s) — momento clave**: dropdown ordenado.
   Seleccionar `HOSP-PRES-001/COVID-1.png`. Click "Clasificar
   imagen". Panel coral "PREDICCION / COVID-19". Mostrar meta:
   model_version + **`Umbral COVID-19: 0,35`** + timestamp. Bajar al
   expander "Ver detalle del modelo" — mostrar matriz de confusion +
   recall por clase con COVID destacado.
6. **(Opcional, si queda tiempo)** Calidad y Pipeline runs: 10 s
   cada una, "es donde el ingeniero de turno mira si algo se ha
   roto".

**Cierre de la demo:**
> *"Lo que acabais de ver: cinco vistas funcionando contra una API
> que esta sirviendo el modelo real, con la regla `covid_threshold_0.35`
> aplicada y trazada en la respuesta. Cero datos inventados. Y si la
> API se cayera ahora mismo, el dashboard seguiria respondiendo,
> los chips del sidebar pasarian a rojo y el operador veria
> exactamente que componente no responde."*

### Mensaje clave
- **El sistema funciona end-to-end**.
- **`decision_rule` visible** en la respuesta del clasificador.
- **Robustez frente a fallos** (chips rojos en sidebar).

### Cifras a mencionar
- 7 vistas, dashboard API-only.
- Imagen ~240 MB (ligera).

### Preguntas que pueden caer aqui
- *"¿Por que Streamlit y no React?"* -> ADR-007. 70 % menos tiempo
  a 3 dias de entrega. Imagen ligera.
- *"¿Como sabe el dashboard que la API esta caida?"* -> Healthcheck
  cada 10 s sobre `/api/v1/health`. Si falla, los 3 chips del sidebar
  pasan a rojo/gris. CA-10 cubierto.
- *"¿Funcionaria offline?"* -> No. El dashboard depende de la API.
  Si la API tiene datos cacheados (TTL=10s) el dashboard sobrevive
  10s al corte.

### Plan B si algo falla en la demo
- API caida -> mostrar chips rojos como ejemplo de error handling.
- HOSP-PRES-* no en dropdown -> usar HOSP-DEMO-001 y avisar
  explicitamente que es sintetica.
- Demo no arranca -> saltar al slide 12 directamente, las capturas
  estan en `docs/model-evaluation/`.

---

## Slide 12 — IA generativa + SDD · 11:00 - 11:45

### Que ves en pantalla
- Flujo `/spec -> /planificar -> /tareas -> /implementar -> /revisar`.
- 4 metricas: 6 specs / 10 ADRs / 31 sesiones IA / 417 tests verde.

### Que digo (45 s)
> *"El uso de IA generativa es uno de los ejes obligatorios del
> enunciado. Lo hemos cubierto con Spec-Driven Development: cada
> feature pasa por cinco fases con artefacto revisable por fase. La
> IA no inventa requisitos; trabaja sobre una spec aprobada. Las
> dudas se marcan `[NEEDS CLARIFICATION]` antes de codificar. Las
> decisiones tecnicas no triviales acaban en ADR. Hay 31 sesiones de
> IA documentadas en docs/diario-ia.md, y cuando una feature era
> delicada, hacia falta una revision cruzada con otro proveedor para
> mitigar la tendencia del modelo a no cuestionar su propio trabajo.
> La disciplina SDD es lo que ha permitido que esta memoria pueda
> escribirse leyendo el repo, no recordando."*

### Mensaje clave
- *"La IA generativa es un multiplicador de capacidad, no un
  sustituto. SDD es la disciplina que hace seguro ese multiplicador."*

### Cifras a mencionar
- 6 specs, 10 ADRs, 31 sesiones IA, 417 tests verde + 1 skip.

### Preguntas que pueden caer aqui
- *"¿Como evitasteis que la IA alucinara?"* -> Dudas marcadas, tests
  TDD desde criterios de aceptacion, revisiones cruzadas, ADRs antes
  de implementar. Cuando algo iba mal, pedia clarificacion.
- *"¿Cuanto tiempo ahorrasteis?"* -> Sin cifras vinculantes. Orden
  de magnitud: features de 2-3 dias se cerraron en sesion intensiva
  con revision humana.
- *"¿Que es cross-provider review?"* -> Cuando una decision era
  delicada, pasabamos la spec + el diff a otro proveedor distinto
  (Codex) para que opinara sin contaminacion. Mitiga sycophancy del LLM.

---

## Slide 13 — Etica + limitaciones · 11:45 - 12:30 — NO OPCIONAL

### Que ves en pantalla
- Dos columnas: Etico/legal + Limitaciones declaradas.
- Card abajo: donde NO se usaria sin cambios estructurales.

### Que digo (45 s)
> *"Etica y limitaciones, sin maquillaje. Los datos son sinteticos
> por diseno; cero PII real. El dataset Kaggle se usa con la licencia
> que el autor publica. Y la posicion clave: asistencia, no
> diagnostico — la decision clinica la mantiene siempre el
> profesional. Limitaciones reconocidas: recall COVID-19 sigue siendo
> 0,820 con la regla — aun se pierden 65 de cada 361 positivos. Sin
> deteccion out-of-domain. Sin interpretabilidad. Sin auth, sin
> replicacion. Triaje con umbrales academicos, no validados
> clinicamente. Donde NO usariamos este sistema sin cambios
> estructurales: decisiones clinicas reales, entornos con PII real,
> operacion 24/7 sin push, hospitales con SLA real."*

### Mensaje clave
- **Honestidad total sobre las limitaciones**.
- **Asistencia, no diagnostico** (decirlo otra vez, sin verguenza).

### Cifras a mencionar
- Recall COVID 0,820. Aun 65 de 361 perdidos (~18 %).

### Preguntas que pueden caer aqui
- *"¿No es peligroso desplegar un clasificador con recall 0,82?"*
  -> Lo es si se usa como diagnostico. Por eso es asistencia. La UI
  lo declara, la memoria lo declara, las predicciones se persisten
  con `decision_rule`, y se exige revision humana.
- *"¿Por que no Grad-CAM?"* -> Mejora prioritaria, declarada como
  trabajo futuro (cap 17). Sale rapido (1 dia) y aumenta la confianza
  del clinico.
- *"¿Que pasa si llega una imagen que no es radiografia?"* -> El
  modelo devolveria una clase con confianza arbitraria. Es la
  limitacion mas seria del clasificador para uso real, declarada en
  cap 14.1.

---

## Slide 14 — Conclusion + Q&A · 12:30 - cierre

### Que ves en pantalla
- Tres metricas finales: accuracy 0,8766 · recall COVID 0,820 · tests 417 +1.
- Trabajo futuro priorizado.

### Que digo (30 s + Q&A)
> *"Para cerrar: el modelo alcanza 0,8766 de accuracy con la regla
> `covid_threshold_0.35`, recall COVID-19 de 0,820 — 12,5 puntos por
> encima del baseline argmax. La suite de tests son 417 verdes mas un
> skip esperado, distribuidos en pipeline, API, ML, automatizacion,
> dashboard y E2E. Trabajo futuro priorizado: transfer learning para
> subir el recall por encima de 0,820, Grad-CAM por defecto para
> interpretabilidad, deteccion out-of-domain, y persistir alertas con
> historico auditable reabriendo ADR-009. Gracias por la atencion.
> ¿Preguntas?"*

### Mensaje clave
- **Tres cifras finales claras**.
- **Trabajo futuro priorizado**, no improvisado.

### Cifras a mencionar (las ultimas que el tribunal oye)
- accuracy 0,8766, recall COVID 0,820, tests 417 +1 skip.

### Preguntas que pueden caer en el Q&A

Las **20 preguntas mas probables** estan en `docs/study-pack.md`
seccion 13. Las que mas se repiten:

1. ¿Por que CNN custom y no transfer learning?
2. ¿Por que tres almacenes si pedian dos?
3. ¿Por que umbral 0,35 y no 0,30?
4. ¿Como evitasteis que la IA alucinara?
5. ¿Esto se podria desplegar manana en un hospital?
6. ¿Que harias diferente si lo empezaras hoy?

Respuestas defendibles en `docs/study-pack.md` cap 13.

---

## Resumen — distribucion temporal

| Slide | Tema | De | A | Duracion |
|---|---|---|---|---|
| 1 | Portada | 00:00 | 00:30 | 30 s |
| 2 | Problema | 00:30 | 01:15 | 45 s |
| 3 | Enunciado | 01:15 | 02:00 | 45 s |
| 4 | Arquitectura | 02:00 | 03:00 | 1:00 |
| 5 | Datos | 03:00 | 03:45 | 45 s |
| 6 | Pipeline | 03:45 | 04:30 | 45 s |
| 7 | **Modelo CNN** | 04:30 | 05:30 | **1:00** |
| 8 | **Threshold 0,35** | 05:30 | 06:30 | **1:00** |
| 9 | Triaje | 06:30 | 07:15 | 45 s |
| 10 | Alertas / informe | 07:15 | 08:00 | 45 s |
| 11 | **Dashboard / demo** | 08:00 | 11:00 | **3:00** |
| 12 | IA + SDD | 11:00 | 11:45 | 45 s |
| 13 | Etica / limitaciones | 11:45 | 12:30 | 45 s |
| 14 | Cierre + Q&A | 12:30 | cierre | 30 s + Q&A |

**Bloques mas largos**: slide 11 (demo, 3 min), slides 7-8 (modelo +
threshold, 2 min). Si vas justo de tiempo, recorta de aqui:

- **Slide 4** (arquitectura): si no preguntan, ensenar el diagrama
  rapido y seguir.
- **Slide 6** (pipeline): si vas justo, una frase y siguiente.

**Bloques que NO recortes**:

- Slide 8 (threshold) — es la decision tecnica del proyecto.
- Slide 11 (demo) — es lo que el tribunal recordara.
- Slide 13 (etica) — es lo que valida el posicionamiento.

---

## Resumen — frases que conviene repetir

- *"Asistencia, no diagnostico. La decision clinica la mantiene
  siempre el profesional."* (slides 1, 2, 7, 8, 9, 13)
- *"Tres almacenes, dos paradigmas, observabilidad accionable, SDD
  aplicada de extremo a extremo."* (slides 3, 12)
- *"El umbral post-hoc es la mejora barata. Transfer learning es el
  siguiente paso."* (slides 8, 14)
- *"Cifras reportadas honestamente: recall COVID-19 = 0,820. Aun se
  pierden 65 de cada 361 positivos."* (slides 7, 8, 13)
- *"Reproducible con un solo `docker compose up`."* (slides 1, 4)

---

## Resumen — cifras que tienes que saber de memoria (de cara al Q&A)

- **0,8766** — accuracy operativa
- **0,8594** — macro-F1 operativa
- **0,820** — recall COVID-19 con threshold
- **0,695** — recall COVID-19 argmax baseline
- **+12,5 pp** — mejora recall COVID con la regla
- **65 / 361** — falsos negativos COVID con la regla
- **1.515** — radiografias en el split de test
- **417** — tests verdes
- **10** — ADRs
- **6** — specs aprobadas
- **7** — vistas dashboard
- **3** — almacenes (Mongo + SQLite + MinIO)
- **2** — paradigmas IA (CNN + reglas)
- **4.790** — pacientes en Mongo (~)

Si te preguntan una cifra que no sabes: *"No la tengo de memoria,
pero esta en `metrics.json` / `validacion-final.md` / cap X de la
memoria. Si me lo permitis, lo abro y os lo confirmo."* Es
defendible y mejor que inventar.

---

## Ultimo recordatorio

> **Es asistencia, no diagnostico. Lo demas son detalles.**
