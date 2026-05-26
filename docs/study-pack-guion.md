# Guion literal — Defensa Master IA & Big Data

> Sistema Inteligente de Soporte Hospitalario · laSalle Health Center
> Duracion objetivo: **13 min** + Q&A
> Esto es lo que dices, palabra a palabra, en castellano natural. No lo
> memorices literal: leelo en voz alta 3 veces hasta que el ritmo sea
> tuyo. Las **negritas** son las palabras que clavar; las cifras en
> `monospace` son las que el tribunal va a oir.

> **📂 Bloque "Archivos a la mano":** en cada slide encontraras una
> lista de archivos del repo a tener abiertos en VSCode (o el navegador
> del repo en GitHub) por si el tribunal pregunta. Abre estos archivos
> en pestanas antes de empezar, en este orden: arquitectura → modelo →
> dashboard. Si te preguntan algo concreto, sabes exactamente a que
> archivo saltar.

**Setup antes de empezar la defensa** — abre estas pestanas en VSCode:

1. `docker-compose.yml` — los 7 servicios
2. `src/api/main.py` — entrada API
3. `src/pipeline/orchestrator.py` — entrada pipeline
4. `src/ml/model.py` — arquitectura CNN
5. `src/ml/predictor.py` — donde se aplica la regla COVID
6. `src/api/triage.py` — reglas IF-THEN
7. `src/automation/daily_report.py` — informe diario
8. `src/dashboard/app.py` — dashboard
9. `decisions/` (carpeta abierta) — los 10 ADRs
10. `docs/memoria-tecnica.md` — para citas de capitulo

---

## Slide 1 — Apertura · 00:00 - 00:45 (45 s)

**Pausa de 2 segundos antes de empezar. Mira al tribunal.**

> *"Imaginad el siguiente escenario. Un hospital de tamano medio:
> casi `5.000 pacientes`, mas de `8.000 admisiones`, y un flujo
> creciente de pruebas de imagen. Cada mañana, el operador de turno
> arranca con dos preguntas que hoy no responde nadie:
> **'¿que requiere mi atencion ahora?'** y
> **'¿cuanto puedo confiar en los datos que tengo?'**."*

**Pausa de 2 segundos. Deja que esas dos preguntas se queden en el aire.**

> *"Vamos a contar como se las hemos respondido al hospital laSalle
> Health Center."*

**Pausa breve.**

> *"Soy Alejandro Marinas, junto con Yago Alonso. Hemos actuado como
> **consultora tecnologica especializada en Inteligencia Artificial
> y Big Data** durante los ultimos meses para este encargo."*

**Pausa.**

> *"En los proximos minutos: el problema que recibimos del
> hospital, la arquitectura con la que lo resolvimos, una demostracion
> en vivo del sistema, y los resultados que entregamos."*

**Lo que el tribunal tiene que sentir al oirte:** que has entendido
el negocio del cliente antes que el codigo. Esto no es "presentamos
un trabajo academico"; es "entregamos un encargo a un cliente". El
tono te coloca como **consultora, no como estudiante**.

**Mensaje clave:** Empieza por el dolor del cliente. Te presentas
DESPUES, ya como rol profesional.

**📂 Archivos a la mano si te preguntan:**

- *Sin codigo en este slide* — es la apertura.
- Si te preguntan "¿de donde sacasteis las cifras 5.000 / 8.000?" →
  `src/pipeline/orchestrator.py` (cuenta registros tras dedupe) o
  `docs/memoria-tecnica.md` capitulo 2 (Datos).

---

## Slide 2 — El encargo · 00:45 - 01:45 (1 min)

> *"Lo que recibimos de laSalle fue concreto. Una organizacion
> sanitaria de tamano medio que tenia **tres problemas operativos
> claros**: tenia volumen creciente de datos — historias, pruebas
> de imagen, logs — pero no podia extraer conocimiento de ellos;
> no automatizaba procesos repetitivos; y no tenia herramientas para
> apoyar la toma de decisiones del personal de turno."*

**Pausa.**

> *"Nos pidieron una solucion que simulara un sistema **real** de
> soporte hospitalario. No un prototipo academico — el enunciado lo
> dice literalmente: 'que tenga sentido en un contexto real
> sanitario'. Y la entrega tenia que ser reproducible, levantarse
> con un solo comando, y demostrar que el equipo entendia que un
> sistema en salud no se vende por su accuracy."*

**Pausa.**

> *"Y desde el primer momento fijamos una linea que no hemos
> cruzado: **ayudamos al medico, no le sustituimos**. La decision
> clinica la mantiene siempre el profesional sanitario — nuestro
> sistema le da informacion y sugerencias, pero el profesional
> decide. No es un disclaimer pegado al final — es la posicion
> etica desde el dia uno, y va a aparecer en cada decision tecnica
> que veais en los proximos slides."*

**Mensaje clave:** Encuadre profesional + frase de posicionamiento.

**Lo que evitas decir:** "Es un proyecto academico de practica". El
enunciado pide que se aborde **como un desarrollo real**. Tu tono es
el de una consultora entregando a un cliente.

**📂 Archivos a la mano si te preguntan:**

- `CLAUDE.md` — define la posicion etica del proyecto desde el dia uno
  (linea "Asistencia, no diagnostico"). Si te preguntan "¿donde esta
  escrita esa linea?" → CLAUDE.md.
- `tasks/backlog.md` — los tres problemas operativos estan listados
  como features priorizadas.
- `specs/` (carpeta) — las 6 specs son la concrecion formal del
  encargo.

---

## Slide 3 — Que pedia el enunciado vs que entregamos · 01:30 - 02:30 (1 min)

> *"El enunciado define cuatro ejes tecnologicos: un modelo de IA, un
> pipeline de Big Data, automatizacion de procesos, y visualizacion
> de resultados. Mas tres pilares transversales: containerizacion con
> un solo comando, desarrollo asistido por IA, y consideraciones
> eticas obligatorias."*

**Pausa.**

> *"Lo hemos cubierto con margen en varios puntos. El enunciado pedia
> **al menos dos tipos de almacenamiento**: entregamos **tres** —
> MongoDB, SQLite y MinIO. Pedia un framework distribuido: usamos
> **PySpark**, el estandar de la industria para Big Data. Pedia un modelo de IA con
> justificacion: entregamos **dos paradigmas complementarios** — una
> CNN custom para clasificacion de radiografias y un sistema de
> triaje basado en reglas IF-THEN. Pedia automatizacion: tenemos
> **cuatro mecanismos** — generacion automatica de informes, alertas
> ante eventos, procesamiento automatico de nuevos datos y ingesta
> de ficheros. Y pedia Spec-Driven Development con diario de IA: lo
> hemos seguido a rajatabla con **seis specs aprobadas, diez ADRs y
> treinta y una sesiones de IA documentadas**."*

**Mensaje clave:** Hemos entregado **mas de lo que pedia el
enunciado, no menos**. Y citamos los puntos del enunciado por su
nombre (matriz de confusion, framework distribuido, etc.).

**📂 Archivos a la mano si te preguntan:**

- `docker-compose.yml` — demuestra los 7 servicios + el "un solo
  comando".
- `decisions/` (carpeta) — los 10 ADRs justifican cada decision.
  Abre especialmente `ADR-001-stack-tecnologico.md` y
  `ADR-004-polyglot-persistence.md`.
- `specs/` (carpeta) — las 6 specs aprobadas. Si te preguntan "¿que
  significa que una spec este aprobada?" → abre cualquier `.md` y
  ensena la cabecera con `Estado: approved`.
- `docs/diario-ia.md` — las 31 sesiones documentadas.
- `tasks/backlog.md` — features cubiertas.

---

## Slide 4 — Arquitectura general · 02:30 - 03:30 (1 min)

**Senala el diagrama con el cursor mientras hablas.**

> *"Esta es la arquitectura. La leemos de izquierda a derecha:
> entradas, procesamiento, almacenamiento, servicio."*

> *"A la izquierda, **tres fuentes heterogeneas**: CSVs de pacientes
> y admisiones, mas radiografias en PNG — que son los **datos no
> estructurados** que el enunciado pide explicitamente. En el centro,
> el **pipeline PySpark**, que valida, deduplica, enriquece e ingesta
> imagenes. A la derecha, **tres almacenes especializados**: MongoDB
> para los datos clinicos jerarquicos, SQLite para los metadatos
> operativos del pipeline, y MinIO para los binarios. Y por encima,
> la API REST con FastAPI que sirve todo, y el dashboard Streamlit
> que consume solo la API."*

**Pausa.**

> *"Son **siete servicios Docker** orquestados por docker-compose. El
> objetivo es el que pide el enunciado: que cualquiera levante el
> sistema completo con un **unico comando**. Y lo hace en menos de
> un minuto."*

**Pausa breve.**

> *"Esto es lo que el hospital tiene **corriendo cada manana**:
> siete contenedores, un solo comando, sin pasos manuales. Si maniana
> el equipo de sistemas del hospital quiere replicar el entorno en
> otra maquina, lo hace en un minuto y sabe exactamente que esta
> ejecutando."*

**Mensaje clave:** Arquitectura clara, decisiones razonadas, despliegue
trivial — y operable por un equipo de sistemas real.

**Si te preguntan en este momento por que tres almacenes:** *"El
enunciado pide al menos dos. Entregamos tres porque cada tipo de
dato vive donde encaja: la jerarquia paciente-admisiones-radiografias
es natural en documental (Mongo), los metadatos operativos del
pipeline son tabulares y se consultan con queries analiticas (SQLite),
y los binarios viven en almacenamiento S3-compatible (MinIO). Esta
decision esta formalizada en ADR-002 y ADR-004."*

**📂 Archivos a la mano si te preguntan:**

- `docker-compose.yml` — los 7 servicios y como se enlazan
  (`pipeline`, `api`, `dashboard`, `mongo`, `sqlite-init`, `minio`,
  `watcher`).
- `src/api/main.py` — punto de entrada de FastAPI, registra los
  routers.
- `src/pipeline/orchestrator.py` — punto de entrada del pipeline
  PySpark.
- `src/dashboard/app.py` — entrada del dashboard Streamlit.
- `decisions/ADR-001-stack-tecnologico.md` — por que este stack.
- `decisions/ADR-002-mongodb-nosql.md` — por que Mongo para
  jerarquia clinica.
- `decisions/ADR-004-polyglot-persistence.md` — por que 3 almacenes.
- `decisions/ADR-006-tensorflow-en-imagen-compartida.md` — por que
  pipeline + API + watcher comparten imagen.
- `decisions/ADR-007-dashboard-streamlit-imagen-independiente.md` —
  por que el dashboard va aparte.

---

## Slide 5 — Datos y pipeline Big Data · 03:30 - 04:30 (1 min)

> *"El pipeline cubre las cuatro fases que pide el enunciado: ingesta,
> limpieza, transformacion y analisis. Esta implementado en **PySpark**,
> el estandar de la industria para procesamiento distribuido a escala."*

**Pausa.**

> *"Sobre el dataset sintetico generado con Faker — y digo sintetico
> deliberadamente, sin PII real, parte del compromiso etico — el
> pipeline procesa unos `4.790 pacientes`, `8.569 admisiones`
> embebidas, y unas `24 radiografias` registradas. Y lo importante:
> persiste `1.692 registros rechazados` con su `raw_data` y motivo.
> No los descarta en silencio; los guarda para auditoria. Es lo que
> dispara la alerta de **calidad de datos baja** cuando el ratio de
> rechazo supera el umbral."*

**Pausa.**

> *"El pipeline es **idempotente**: si lo ejecuto dos veces no crea
> duplicados. Bootstrap en frio tarda **cincuenta segundos**, un
> reinicio caliente **un segundo**. Y la auditoria de cada ejecucion
> queda registrada en `pipeline_runs` con su estado y tiempos."*

**Pausa breve.**

> *"Lo que esto le da al hospital: ningun dato se pierde en silencio.
> Lo que entra mal queda registrado con su motivo y se puede consultar
> desde el dashboard. Y el responsable del pipeline sabe en cualquier
> momento que ha pasado en cada ejecucion."*

**Mensaje clave:** Pipeline real, calidad medida, auditoria por run —
y el cliente sabe siempre que esta pasando con sus datos.

**📂 Archivos a la mano si te preguntan:**

- `src/pipeline/orchestrator.py` — orquestador del pipeline, lee
  CSVs y dispara las fases.
- `src/pipeline/spark_session.py` — configuracion de la SparkSession.
- `src/pipeline/ingesters/` (carpeta) — readers de CSV pacientes,
  admisiones, radiografias.
- `src/pipeline/processors/` (carpeta) — limpieza, dedupe,
  enriquecimiento, transformaciones.
- `src/pipeline/storage/` (carpeta) — escritores hacia Mongo, SQLite,
  MinIO.
- `src/pipeline/watcher.py` — watcher de `data/incoming/` que dispara
  el pipeline al detectar CSV nuevo.
- `specs/pipeline-datos.md` — la spec aprobada de este modulo.
- `specs/sqlite-pipeline-metadata.md` — spec de los metadatos
  operativos (`pipeline_runs`, `rejected_records`).

**Si te preguntan "¿donde se guardan los rechazados?"** → abre
`src/pipeline/processors/` y muestra el processor que escribe en la
tabla `rejected_records` con `raw_data` y motivo.

---

## Slide 6 — Modelo CNN · 04:30 - 06:00 (1 min 30 s)

> *"Pasamos al modelo. El enunciado pide una clasificacion triple de
> radiografias de torax: Sana, Neumonia, COVID-19. Y nos da libertad
> para elegir la arquitectura, pero exige justificarla."*

**Pausa.**

> *"Decidimos una **CNN custom entrenada desde cero**, sin transfer
> learning. La decision esta en ADR-005 y tiene tres razones:
> alineacion literal con el Bloque 6 del Master, modelo dentro de
> los 50 MB del requisito no funcional, y sin dependencias externas
> al arrancar. La arquitectura es Conv2D, MaxPooling, Dropout, Dense
> y softmax. Veintiun megabytes en disco, commiteado al repositorio."*

**Pausa.**

> *"El entrenamiento no salio a la primera. La primera version
> predicia 'Normal' para casi todas las imagenes — accuracy del
> sesenta y siete por ciento, que coincide con la frecuencia de
> Normal en el split. El diagnostico fue **learning rate demasiado
> alto y class_weight lineal demasiado agresivo**. Lo corregimos
> bajando el learning rate a `1e-4` y suavizando los class_weight
> con raiz cuadrada. Esa correccion esta documentada en
> `tasks/lessons.md` y los sanity-checks que la detectaron viven
> en `scripts/ml_diagnostics.py`."*

**Pausa larga (2 segundos), antes de las cifras.**

> *"Sobre el split de test de `1.515 radiografias`, el modelo
> alcanza accuracy de `0,8766` y macro-F1 de `0,8594`. Pero como
> dice el enunciado, **la nota no depende del accuracy**. Lo que
> importa es como se comporta el modelo, y en clinica eso significa
> el **recall por clase**. Y ahi el recall de COVID-19 es de
> `0,820`, frente al `0,695` que daba el modelo con argmax puro.
> Esa mejora — doce coma cinco puntos porcentuales — viene de una
> decision que explico en el siguiente slide."*

**Pausa breve.**

> *"Lo que esto le da al clinico: una asistencia que responde en
> menos de cincuenta milisegundos, con la **probabilidad por clase**
> visible — no un veredicto opaco. Si el clinico no esta de acuerdo
> con la prediccion, ve exactamente cuanta evidencia tenia el modelo
> para cada opcion. Esa transparencia es lo que diferencia una
> asistencia util de una caja negra."*

**Mensaje clave:** Modelo justificado, entrenamiento iterativo
honesto, recall como metrica clinica — y el clinico recibe
informacion accionable, no un dictamen.

**Lo que NO dices:** "El modelo va muy bien". El enunciado avisa
explicitamente: la nota no depende del accuracy.

**📂 Archivos a la mano si te preguntan:**

- `src/ml/model.py` — **la arquitectura CNN**: Conv2D + MaxPooling
  + Dropout + Dense + softmax. Si te piden "ensename el modelo" →
    este es el archivo.
- `src/ml/train.py` — script de entrenamiento con EarlyStopping y
  class_weight.
- `src/ml/dataset.py` — carga del dataset COVID-19 Radiography.
- `src/ml/preprocessing.py` — normalizacion y resize de imagenes.
- `src/ml/evaluate.py` — calculo de matriz de confusion y metricas
  por clase.
- `src/ml/predictor.py` — inferencia + aplicacion de la regla
  threshold (lo veras en detalle en slide 7).
- `decisions/ADR-005-cnn-custom-no-transfer-learning.md` — **las 3
  razones de no usar transfer learning**.
- `decisions/ADR-003-keras-tensorflow.md` — por que Keras/TF.
- `tasks/lessons.md` — busca la entrada del LR demasiado alto y
  class_weight lineal. Si te preguntan "¿como detectasteis que
  fallaba?" → este archivo.
- `scripts/ml_diagnostics.py` — los sanity-checks que detectaron el
  fallo (distribucion de predicciones por clase).

---

## Slide 7 — La regla `covid_threshold_0.35` · 06:00 - 07:15 (1 min 15 s)

**Este es el slide tecnico mas delicado. Ritmo lento.**

> *"El enunciado pide reflexionar sobre el impacto clinico de los
> errores y justificar las decisiones tomadas. Esta es la decision
> tecnica mas reciente del proyecto."*

**Pausa.**

> *"El modelo con argmax puro perdia el treinta por ciento de los
> positivos reales de COVID-19. En contexto hospitalario, un **falso
> negativo de enfermedad contagiosa** es el error mas grave: implica
> dar de alta a un paciente contagioso sin aislarlo. El enunciado lo
> dice literalmente."*

**Pausa.**

> *"Aplicamos una **regla de decision post-hoc** sobre las
> probabilidades del softmax: si la probabilidad de COVID-19 supera
> `0,35`, se predice COVID-19; si no, se hace argmax entre Normal y
> Pneumonia. Es la regla `covid_threshold_0.35`, documentada en
> ADR-010. **El modelo es el mismo, los pesos son los mismos, el
> dataset es el mismo**. Lo unico que cambia es la regla de decision."*

**Pausa.**

> *"El resultado: el recall de COVID-19 sube de `0,695` a `0,820`.
> Cuarenta y cinco falsos negativos menos. A cambio, perdemos cinco
> coma seis puntos de precision en COVID-19 y tres coma seis de
> recall en Normal. Es un trade-off explicito, no magia."*

**Pausa.**

> *"Y lo importante: el campo `decision_rule` se persiste en cada
> prediccion en MongoDB y se devuelve en cada respuesta de la API.
> El baseline argmax queda preservado en `metrics.json` bajo
> `comparison_argmax` para auditoria. La regla es **trazada,
> reversible y auditable**. ADR-010 documenta las alternativas
> descartadas: reentrenar con class_weight mas agresivo, transfer
> learning, ensembling — y por que elegimos esta."*

**Pausa breve.**

> *"Lo que esto le da al hospital: poder **ajustar la sensibilidad
> del modelo sin reentrenar**. Si maniana el cliente decide que
> prefiere mas falsos positivos a cambio de no perder ningun caso de
> COVID-19, cambiamos una constante y regeneramos el reporte en
> minutos. Esa flexibilidad — ajustes auditables y reversibles — es
> lo que un sistema en produccion necesita."*

**Mensaje clave:** Decision justificada, trazada, reversible. Es
**asistencia**, no parche oculto. Y la flexibilidad operativa es
argumento de venta directo.

**📂 Archivos a la mano si te preguntan:**

- `src/ml/predictor.py` — **donde se aplica la regla**. Busca
  `covid_threshold` o `decision_rule`. Si te piden "ensename el
  codigo de la regla" → este archivo.
- `src/api/models.py` — schema de la respuesta de prediccion con el
  campo `decision_rule`.
- `src/api/routers/classify.py` — endpoint que persiste la
  prediccion en MongoDB con `decision_rule`.
- `src/ml/regen_evaluation.py` — script que regenera `metrics.json`
  comparando argmax vs threshold (`comparison_argmax`).
- `decisions/ADR-010-covid-threshold.md` — **el ADR clave de este
  slide**. Tiene las alternativas descartadas (reentrenar,
  class_weight, transfer, ensembling) y por que se eligio esta.
- `docs/model-evaluation/` (carpeta) — aqui esta `metrics.json` con
  el baseline argmax bajo `comparison_argmax`.

**Si te preguntan "¿como se cambia el umbral?"** → abre
`src/ml/predictor.py` y senala la constante. *"Es esta linea. Si
cambio 0.35 a 0.30 y reinicio la API, todas las predicciones nuevas
quedan trazadas con `decision_rule: covid_threshold_0.30`. Reversible
en una constante."*

---

## Slide 8 — Triaje por reglas + Matriz de confusion · 07:15 - 08:30 (1 min 15 s)

> *"El segundo paradigma de IA es el sistema de triaje. Aqui
> tomamos una decision deliberada: **no usar machine learning**.
> Y la razon es metodologica, no tecnica."*

**Pausa.**

> *"No existe dataset etiquetado con la gravedad real de cada
> paciente. El CSV sintetico no tiene una columna grave-medio-leve.
> Y entrenar un clasificador sobre etiquetas que **inventamos
> nosotros** seria fabricar ground truth, no aprenderlo. ADR-008
> formaliza esta decision."*

**Pausa.**

> *"En su lugar, implementamos un sistema **basado en reglas
> IF-THEN** sobre signos vitales. Seis reglas para nivel grave —
> saturacion de oxigeno baja, frecuencia respiratoria o cardiaca
> alta, tension sistolica baja, fiebre alta, sintoma critico. Cinco
> reglas para nivel medio. Y leve como caso por defecto. Cada
> decision lleva la lista exacta de reglas que han disparado, y la
> version de las reglas. La explicabilidad es **directa**: no
> necesita SHAP ni Grad-CAM, las reglas son legibles."*

**Pausa.**

> *"Y como pide el enunciado, hicimos la **matriz de confusion** del
> clasificador y la **reflexion critica**. Los errores mas graves
> son los falsos negativos de COVID-19 a Normal — los que pierden
> un contagioso. Con la regla del umbral, esos casos bajan de
> ciento uno a cincuenta y nueve. Es la mejora cuantificada del
> sistema, pero seguimos perdiendo el dieciocho por ciento de los
> positivos. Y por eso seguimos diciendo: **asistencia, no
> diagnostico**."*

**Mensaje clave:** Dos paradigmas justificados. Matriz de confusion
y reflexion critica explicitas.

**📂 Archivos a la mano si te preguntan:**

- `src/api/triage.py` — **las reglas IF-THEN**. Busca
  `spo2_lt_92`, `fr_high`, `fc_high`, `pas_low`, etc. Si te piden
  "ensename las 6 reglas" → este archivo.
- `src/api/routers/triage.py` — endpoint `/api/v1/triage` que
  recibe signos vitales y devuelve nivel + reglas disparadas.
- `src/dashboard/views/triage.py` — vista del triaje en el dashboard
  (la que clicaras en la demo).
- `specs/triage-pacientes.md` — spec aprobada del triaje.
- `decisions/ADR-008-triaje-basado-en-reglas.md` — **el ADR clave**:
  por que no ML.
- `docs/model-evaluation/confusion_matrix.png` (o ruta equivalente)
  — la matriz de confusion que pide el enunciado.

**Si te preguntan "¿como se que reglas dispararon?"** → abre
`src/api/triage.py` y muestra como cada regla cuando se cumple se
anade a una lista que se devuelve en el JSON de respuesta junto al
nivel.

---

## Slide 9 — Automatizacion: alertas + informe diario · 08:30 - 09:30 (1 min)

> *"El enunciado pide cuatro mecanismos de automatizacion. Los
> tenemos los cuatro."*

**Pausa.**

> *"Uno: **generacion automatica de informes**. El comando
> `daily_report.py` produce un Markdown reproducible del dia,
> guardado en `docs/reports/YYYY-MM-DD.md`. Y es **idempotente
> byte-a-byte**: dos ejecuciones del mismo dia producen exactamente
> el mismo fichero, con el mismo sha256. No metemos `generated_at`
> en el cuerpo. Es nuestra forma de demostrar que el sistema **no
> inventa numeros** — si las fuentes no cambian, la salida no cambia."*

**Pausa.**

> *"Dos: **envio de alertas ante eventos relevantes**. El endpoint
> `/api/v1/alerts` calcula tres tipos de alerta — pipeline fallido
> con severidad alta, calidad de datos baja con severidad media, y
> triaje grave con severidad critica. Pero importante: ADR-009
> formaliza que las alertas son **vista derivada**. Cero estado
> nuevo persistido, cero tabla `alerts`. Se calculan al consultar,
> leyendo las fuentes que ya existen."*

**Pausa.**

> *"Tres: **procesamiento automatico de nuevos datos**. Un watcher
> sobre `data/incoming/` detecta CSVs nuevos y dispara el pipeline.
> Y cuatro: **organizacion de ficheros** — el image-ingester sube
> los PNG a MinIO y los embebe en su paciente."*

**Pausa breve.**

> *"Lo que esto le da al hospital: el operador de turno **deja de
> mirar logs**. El sistema le dice que requiere atencion en lugar
> de hacerle buscarlo. Y el responsable operativo recibe un informe
> diario reproducible que puede archivar, comparar y auditar — la
> misma fecha produce el mismo fichero, garantizado."*

**Mensaje clave:** Los cuatro mecanismos del enunciado, no tres — y
todos resuelven una pregunta operativa concreta del cliente.

**📂 Archivos a la mano si te preguntan:**

- `src/automation/daily_report.py` — **el generador del informe
  diario**. Si te piden "ensename el daily report" → este archivo.
- `src/api/alerts.py` — calculo de las 3 alertas como **vista
  derivada** (sin tabla nueva).
- `src/api/routers/alerts.py` — endpoint `/api/v1/alerts`.
- `src/pipeline/watcher.py` — watcher de `data/incoming/` para
  procesamiento automatico.
- `src/pipeline/ingesters/` — image-ingester que sube PNG a MinIO
  y los embebe en su paciente.
- `decisions/ADR-009-alertas-como-vista-derivada.md` — **el ADR
  clave**: por que cero estado nuevo, cero tabla `alerts`.
- `specs/automatizacion-alertas.md` — spec aprobada.
- `docs/reports/` (carpeta) — donde se guardan los informes
  generados. Si te preguntan por idempotencia, abre dos del mismo
  dia y muestra el mismo sha256.

**Si te preguntan "¿como demostrais idempotencia byte-a-byte?"** →
abre `src/automation/daily_report.py` y muestra que el cuerpo del
Markdown NO contiene `generated_at`. Ese es el truco: mismas
fuentes → mismo fichero → mismo sha256.

---

## Slide 10 — Demo en vivo · 09:30 - 12:00 (2 min 30 s)

**ESTE ES EL MOMENTO CLAVE. Calma. Narra mientras clicas.**

> *"Y ahora lo que importa: vamos a ver el sistema en vivo. **Esto es
> exactamente lo que vera el operador del hospital cada turno**."*

**Pausa breve. Mueve el portatil para que el tribunal vea bien la pantalla.**

> *"Es el dashboard Streamlit, en imagen Docker aparte para que no
> arrastre las dependencias del pipeline — ADR-007. Es **API-only**:
> cero imports de pymongo, sqlite o minio en el codigo del dashboard.
> Siete vistas, dos bloques: Operacion en la sidebar arriba, Sistema
> atenuado abajo."*

**Click en Inicio.**

> *"Esto es el Inicio. Saludo, volumen del sistema, una **barra
> critica** que solo aparece si hay alertas activas, tres chips de
> estado, cuatro cards con la actividad del dia y tres accesos
> rapidos."*

**Click en Triaje.**

> *"Triaje. Voy a registrar un paciente con saturacion de oxigeno
> a `85`, que dispara la regla `spo2_lt_92`."*

**Rellenas: Nombre = "Tribunal", SpO2 = 85. Click "Calcular prioridad".**

> *"Y aqui aparece el panel coral con **GRAVE**, la recomendacion
> generica — 'priorizar revision inmediata por profesional
> sanitario', sin frases de protocolo clinico real — y el motivo
> humanizado: saturacion de oxigeno por debajo del umbral. Cada
> decision lleva su trazabilidad."*

**Click en Alertas.**

> *"Alertas. Aqui aparece **el mismo paciente** que acabo de
> registrar, ahora como alerta critica `triage_severe`. Cero
> estado nuevo persistido — esto se ha calculado al consultar."*

**Click en Clasificador.**

> *"Y el bloque clave: el clasificador. Selecciono una radiografia
> real del dataset, `HOSP-PRES-001`."*

**Click "Clasificar imagen".**

> *"Resultado: COVID-19. Y mirad la meta: version del modelo,
> `Umbral COVID-19: 0.35` — que es la regla `covid_threshold_0.35`
> humanizada — y el timestamp. Abrimos el detalle del modelo..."*

**Click expander "Ver detalle del modelo".**

> *"...y aqui esta la **matriz de confusion** que pide el enunciado,
> con el recall por clase. El recall de COVID-19, destacado, es de
> `0,820`."*

**Pausa breve antes del cierre de la demo.**

> *"Lo que acabais de ver: cinco vistas funcionando contra una API
> real, con la regla de decision aplicada y trazada en la respuesta.
> Y si la API se cayera ahora mismo, el dashboard seguiria
> respondiendo, los chips del sidebar pasarian a rojo y el operador
> veria exactamente que componente no responde."*

**Mensaje clave:** El sistema funciona end-to-end, no son slides.

**📂 Archivos a la mano si te preguntan:**

- `src/dashboard/app.py` — **entrada del dashboard** y router de
  vistas.
- `src/dashboard/api_client.py` — cliente HTTP que consume la API
  (demuestra que el dashboard es **API-only**).
- `src/dashboard/views/overview.py` — vista Inicio (la primera de
  la demo).
- `src/dashboard/views/triage.py` — vista Triaje (donde introduces
  SpO2=85).
- `src/dashboard/views/alerts.py` — vista Alertas (donde aparece el
  paciente como `triage_severe`).
- `src/dashboard/views/classifier.py` — vista Clasificador (donde
  abres la matriz de confusion).
- `src/dashboard/views/patients.py`, `runs.py`, `quality.py` — las
  vistas que pasan por encima.
- `src/dashboard/config.py` — config del dashboard (URL de la API).
- `decisions/ADR-007-dashboard-streamlit-imagen-independiente.md` —
  **el ADR clave**: por que imagen Docker aparte y por que API-only.
- `specs/dashboard.md` — spec aprobada del dashboard.

**Si te preguntan "¿como pruebo que es API-only?"** → abre
`src/dashboard/` y muestra que **no hay imports** de `pymongo`,
`sqlite3` ni `minio` en ningun archivo. Solo `api_client.py` con
`httpx`.

---

## Slide 11 — Vibe Coding + SDD + Diario IA · 12:00 - 12:45 (45 s)

> *"El enunciado dedica un bloque entero al desarrollo asistido por
> IA — Vibe Coding — y lo trata como **uso obligatorio, no
> opcional**."*

**Pausa.**

> *"Hemos usado **Claude Code** como herramienta principal, con
> revisiones puntuales con Codex cuando una decision era delicada
> — eso mitiga la tendencia del modelo a no cuestionar su propio
> trabajo. Y hemos aplicado **Spec-Driven Development** como
> metodologia: para cada feature, una spec aprobada antes de
> escribir codigo. Seis specs, diez ADRs, treinta y una sesiones
> de IA documentadas en `docs/diario-ia.md`."*

**Pausa.**

> *"El diario de IA es entregable obligatorio. Incluye herramientas
> usadas, ejemplos de prompts, casos donde la IA acerto y casos
> donde tuvimos que corregirla, reflexion critica y estimacion de
> impacto en productividad."*

**Pausa breve.**

> *"La frase con la que lo cerramos en la memoria: **la IA generativa
> es un multiplicador de capacidad, no un sustituto. SDD es la
> disciplina que hace seguro ese multiplicador**."*

**Mensaje clave:** Eje obligatorio del enunciado, cubierto con
disciplina, no improvisado.

**📂 Archivos a la mano si te preguntan:**

- `docs/diario-ia.md` — **las 31 sesiones documentadas**. Si te
  piden "ensename una sesion" → abre cualquier entrada con
  aciertos, correcciones y leccion.
- `specs/` (carpeta) — las 6 specs aprobadas. Cada una tiene RF,
  RNF, CB, CA y dudas abiertas.
- `decisions/` (carpeta) — los 10 ADRs.
- `tasks/lessons.md` — patrones de error a evitar (la entrada del
  LR alto en el modelo, por ejemplo).
- `tasks/backlog.md` — features priorizadas.
- `CLAUDE.md` — el mapa del repo para agentes de IA.

**Si te preguntan "¿que es una spec aprobada?"** → abre
`specs/clasificacion-radiografias.md` y muestra la cabecera con
`Estado: approved` + el changelog con fechas.

---

## Slide 12 — Etica, limitaciones y reflexion critica · 12:45 - 13:30 (45 s)

> *"El enunciado declara este bloque **obligatorio**. Y lo abordamos
> sin maquillaje."*

**Pausa.**

> *"Etico y legal. **Datos sinteticos por diseno**: Faker con seed
> fija, cero PII real. El dataset Kaggle se usa con la licencia que
> el autor publica, no asumimos licencia generica. Y la posicion
> central: **asistencia, no diagnostico**. La decision clinica la
> mantiene siempre el profesional sanitario."*

**Pausa.**

> *"Limitaciones declaradas. El recall de COVID-19 con la regla
> sigue siendo `0,820`: aun perdemos sesenta y cinco de cada
> trescientos sesenta y uno positivos. **Sin deteccion
> out-of-domain** — una imagen que no sea radiografia devolveria
> igualmente una clase. **Sin interpretabilidad** tipo Grad-CAM —
> es el trabajo futuro prioritario. **Sin autenticacion ni
> replicacion**: es entrega academica, no produccion real. Y el
> **triaje usa umbrales academicos**, no validados clinicamente."*

**Pausa.**

> *"Y donde NO usariamos este sistema sin cambios estructurales:
> decisiones clinicas con consecuencia para un paciente, entornos
> con PII real, hospitales con SLA de produccion. Sin certificacion
> CE/FDA. Es la lectura honesta de lo que es y lo que no es este
> sistema."*

**Mensaje clave:** Honestidad total. Los cuatro puntos de etica del
enunciado: sesgos, riesgos, privacidad, limitaciones.

**📂 Archivos a la mano si te preguntan:**

- `docs/memoria-tecnica.md` — **capitulo 14 (Etica y limitaciones)**
  y capitulo 17 (Trabajo futuro). Si te citan "el sistema no esta
  listo para hospital" → abre capitulo 14.5.
- `src/pipeline/ingesters/` — donde se carga el dataset sintetico
  con Faker (no PII real).
- `decisions/ADR-010-covid-threshold.md` — la cifra del 0,820 y
  por que aun se pierden 65/361.
- `decisions/ADR-008-triaje-basado-en-reglas.md` — por que los
  umbrales son academicos, no clinicos.

**Si te preguntan "¿donde declarais que no es production-ready?"** →
`docs/memoria-tecnica.md` capitulo 14.5 y CLAUDE.md.

---

## Slide 13 — Cierre · 13:30 - 14:00 (30 s) + Q&A

**Cambio de tono: ahora vendes. Mira al tribunal. Voz un punto mas firme.**

> *"Para cerrar: **que se lleva el hospital hoy**."*

**Pausa de 1 segundo.**

> *"Un sistema que arranca con un solo comando. Un cuadro de mando
> que responde **en tiempo real** las dos preguntas que el operador
> tenia cada manana — que requiere mi atencion ahora, y cuanto puedo
> confiar en mis datos. Un modelo cuya regla de decision esta
> trazada en cada prediccion y se puede ajustar sin reentrenar. Y un
> informe diario reproducible que demuestra que el sistema **no
> inventa numeros**: misma fecha, mismo fichero, garantizado."*

**Pausa.**

> *"Las cifras: accuracy `0,8766`, recall COVID-19 `0,820`, suite
> de `417 tests verdes` mas uno controlado."*

**Pausa.**

> *"**Que le queda por delante.** Subir el recall de COVID-19 por
> encima del `0,90` con transfer learning. Anadir interpretabilidad
> visual con Grad-CAM en cada prediccion. Deteccion de imagenes
> fuera del dominio clinico. Y, si llegara a uso clinico real,
> certificacion como producto sanitario."*

**Pausa larga (2 segundos). Cambia el tono — aqui cierras la venta.**

> *"Lo que entregamos hoy es una **base solida, honesta y
> reproducible** sobre la que se construye un sistema sanitario
> real. En consultoria en salud, esa honestidad — saber exactamente
> para que sirve un sistema y para que no — vale mas que vender
> humo."*

**Pausa larga. Mira al tribunal directamente.**

> *"Gracias por la atencion. **¿Preguntas?**"*

**Y ahora cierras la boca y esperas. No rellenes el silencio.**

**Lo que el tribunal tiene que sentir al oirte cerrar:** que has
entregado un proyecto serio, que conoces sus limitaciones, que sabes
para que sirve y para que no, y que has pensado el camino hacia un
producto real. Eso es lo que vende — la combinacion de **lo entregado

+ lo declarado + el camino**.

**📂 Archivos a la mano si te preguntan:**

- `docs/memoria-tecnica.md` — documento de cierre, lectura completa.
  Capitulos clave: 4 (Modelo), 7 (Justificaciones), 14 (Etica), 17
  (Trabajo futuro).
- `CHANGELOG.md` — entregas notables del proyecto.
- `README.md` (raiz del repo) — punto de entrada del repositorio.
- `decisions/` (carpeta entera) — para defender cualquier decision
  tecnica con su ADR.

---

## Anexo — Preguntas que pueden caer en Q&A y respuestas defendibles

Las **diez mas probables**, ordenadas por probabilidad descendente:

### 1. ¿Por que CNN custom y no transfer learning?

> *"Tres razones: alineacion literal con el Bloque 6 del Master que
> enseña CNN custom; modelo dentro del techo de cincuenta megabytes
> del requisito no funcional; sin dependencias externas en arranque.
> Decision formalizada en ADR-005. Y transfer learning es nuestro
> trabajo futuro prioritario — esta en el capitulo 17 de la memoria."*

### 2. ¿Por que umbral 0,35 y no 0,30?

> *"Lo elegimos sobre el split de **validacion**, no de test, para
> no contaminar la decision. Probamos `0,30`, `0,35` y `0,40`.
> `0,30` maximiza recall pero baja precision a `0,71`, demasiado
> agresivo. `0,40` solo sube recall a `0,76`, mejora marginal. `0,35`
> da el mejor balance. Documentado en ADR-010."*

### 3. ¿Por que post-hoc y no reentrenais?

> *"El cambio es **reversible en una constante**. Reentrenar abre
> dependencias — refactor de train.py, regenerar artefactos, validar
> otra vez. El umbral post-hoc es la mejora barata; reentrenar es
> el siguiente paso. ADR-010 lo declara explicitamente como parche,
> no solucion."*

### 4. ¿Por que tres almacenes si pedian dos?

> *"Cada tipo de dato vive donde encaja. Mongo para la jerarquia
> paciente-admisiones-radiografias, que es naturalmente documental.
> SQLite para metadatos operativos tabulares con queries analiticas
> — alineado con el Bloque 7 que enseña SQLAlchemy. MinIO para
> binarios. Mongo y MinIO ya cumplian los dos del enunciado; SQLite
> **refuerza** la arquitectura. ADR-002 y ADR-004."*

### 5. ¿Como evitasteis que la IA alucinara?

> *"Tres mecanismos. Uno: dudas marcadas con `[NEEDS CLARIFICATION]`
> antes de codificar. Dos: tests TDD generados desde los criterios
> de aceptacion de cada spec. Tres: revisiones cruzadas con otro
> proveedor cuando una decision era delicada, para mitigar la
> tendencia del LLM a no cuestionar su propio trabajo. Y cuando algo
> iba mal, paraba y pedia clarificacion. Esta documentado sesion a
> sesion en docs/diario-ia.md."*

### 6. ¿Por que reglas en triaje y no ML?

> *"No existe dataset etiquetado con la gravedad real. Entrenar
> sobre etiquetas que inventamos nosotros seria **fabricar ground
> truth**, no aprenderlo. Las reglas IF-THEN dan trazabilidad
> directa: cada decision lleva las reglas disparadas. ADR-008."*

### 7. ¿Como sabes que el sistema no inventa datos?

> *"El informe diario es **idempotente byte-a-byte**: si las fuentes
> no cambian, dos ejecuciones del mismo dia producen exactamente el
> mismo sha256. El cuerpo del Markdown no contiene `generated_at`.
> Es la firma de que el sistema es determinista sobre el estado."*

### 8. ¿Esto se podria desplegar manana en un hospital?

> *"No. Y la memoria lo dice en el capitulo 14.5. Es **asistencia,
> no diagnostico**. Falta certificacion CE/FDA, manejo de PII real,
> autenticacion, replicacion, alta disponibilidad, generalizacion
> validada en otros hospitales. Es entrega academica reproducible,
> no producto sanitario."*

### 9. ¿Y si llega una imagen que no es radiografia?

> *"El modelo devolveria una clase con confianza arbitraria. Es la
> limitacion **mas seria** del clasificador para uso real, declarada
> en el capitulo 14.1 de la memoria. El trabajo futuro prioritario
> incluye un clasificador binario previo 'es radiografia de torax,
> si o no'."*

### 10. ¿Que haríais diferente si lo empezarais hoy?

> *"Cuatro cosas, en este orden. Uno: transfer learning desde el
> principio — DenseNet o EfficientNet con pesos medicos como
> CheXNet — para subir el recall COVID por encima de `0,90`.
> Dos: Grad-CAM por defecto en cada prediccion. Tres: deteccion
> out-of-domain. Cuatro: persistir alertas con historico auditable
> reabriendo ADR-009. Todas estan en el capitulo 17 de la memoria."*

---

## Recordatorio final — antes de salir al estrado

**Repite mentalmente:**

1. **Asistencia, no diagnostico.** (la posicion etica)
2. **Tres almacenes, dos paradigmas, cuatro mecanismos de automatizacion.** (lo que entregas vs lo que pedian)
3. **Recall COVID 0,820 con la regla, 0,695 con argmax.** (la cifra clave)
4. **Citaciones ADR-XXX cuando defiendes una decision.** (autoridad documental)
5. **"Como pide el enunciado..."** (referencia directa al brief)

**No digas:**

- "El modelo funciona muy bien" — di "alcanza accuracy `0,8766`".
- "Detecta COVID-19" — di "asiste en la clasificacion en tres clases".
- "Es production-ready" — di "es entrega academica reproducible".

**Y respira antes de cada slide. Si te trabas, pausa de 2 segundos —
parece pensar, no parece olvido.**

---

## Anexo II — El equilibrio entre vender y mantener honestidad

> Uno de los profesores os dijo que **teniais que vendersela**. Esta
> nota explica donde esta el limite — para que no te pases ni te
> quedes corto.

### Que SI es venta en este guion

- Abrir con el **dolor del cliente** (slide 1), no con presentarte.
- Posicionarte como **consultora**, no como estudiante.
- En cada slide tecnico, una frase **"lo que esto le da al hospital"**.
- Cerrar con **lo entregado + lo declarado + el camino** (slide 13).
- Citar el **enunciado por su nombre** cuando lo cumples ("como pide
  el enunciado, hicimos la matriz de confusion...").

### Que NUNCA es venta — y NO debes hacer

- **NO inventes capacidades** que el sistema no tiene. Si el recall
  COVID es `0,820`, NO digas "casi perfecto". Di "0,820 con la regla,
  18% de positivos perdidos".
- **NO ocultes limitaciones.** El slide 12 es obligatorio y se
  defiende mejor declarando las limitaciones que escondiendolas.
- **NO digas "production-ready", "listo para hospital", "validado
  clinicamente"**. NO lo es. Decirlo te quita credibilidad delante
  del tribunal.
- **NO uses superlativos vacios** ("excelente", "innovador",
  "vanguardia"). En consultoria sanitaria, los superlativos son
  red flag de equipo que no sabe lo que entrega.

### La regla maestra

> *"Vendes lo que tiene + el camino claro hacia lo que necesita
> tener. No vendes lo que NO tiene."*

Aplicado al cierre del slide 13: dices que el sistema es **base
solida sobre la que se construye un sistema sanitario real** — no
que **YA ES** un sistema sanitario real. Esa diferencia es lo que el
profesor probablemente esta valorando.

### Si te ataca con "¿esto se vende manana a un hospital?"

> *"Hoy no, y la memoria lo dice en el capitulo catorce. Lo que
> vendemos hoy es el **proceso, la metodologia y la base tecnica** —
> el sistema completo, reproducible, con sus limitaciones declaradas.
> Para venderlo manana al hospital como producto, hay un camino claro:
> certificacion CE/FDA, manejo de PII real, autenticacion, y la
> mejora del recall via transfer learning. Lo que entregamos hoy es
> el primer kilometro de ese camino, no el destino. Pero el primer
> kilometro esta hecho de manera que el resto es construir, no
> rehacer."*

Esa respuesta cierra la pregunta del tribunal por arriba — vendiendo
el camino sin inventar capacidades. Es el tipo de respuesta que un
consultor serio da a un cliente que pregunta lo mismo.
