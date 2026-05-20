# Spec: Triaje de pacientes en alta manual

> Estado: approved
> Ultima actualizacion: 2026-05-19

## Contexto y problema

El sistema hospitalario laSalle Health Center ya cubre el procesamiento
batch de pacientes (CSV -> MongoDB), la clasificacion automatica de
radiografias y la visualizacion via dashboard. Lo que **no tiene** es una
via para **dar de alta a un paciente nuevo** desde la propia plataforma y
asignarle un nivel de prioridad preliminar.

El profesor pide cubrir ese hueco: poder crear un paciente nuevo y que
el sistema le asigne un nivel de triaje (**grave / medio / leve**) a
partir de signos vitales y sintomas. La feature debe ser **defendible
academicamente** dentro de la teoria de Modelos de IA vista en el
Master, sin entrar en territorio de diagnostico medico vinculante.

No disponemos de un dataset etiquetado con la severidad
`grave | medio | leve`, por lo que NO se entrena un modelo nuevo. Se
implementa un **sistema basado en reglas** (reglas de produccion) con
umbrales academicos simplificados — la motivacion teorica conecta con
el bloque del Master que presenta los sistemas basados en reglas como
alternativa a los modelos aprendidos cuando no hay supervision
disponible y se prioriza la trazabilidad. La decision se formaliza en
ADR-008. El sistema se entrega como **asistencia al triaje**, NUNCA como
diagnostico ni como decision medica vinculante, manteniendo el mismo
posicionamiento etico que el clasificador de radiografias.

## Objetivo

Permitir que un operador del sistema (medico, residente, evaluador del
proyecto) cree un paciente nuevo desde el dashboard introduciendo:

- datos demograficos minimos;
- signos vitales basicos;
- sintomas principales y factores de riesgo opcionales;

y obtenga inmediatamente un **nivel de triaje** (grave/medio/leve) con
las **razones** que justifican esa clasificacion. El paciente queda
persistido en MongoDB con un objeto `triage` embebido y aparece de
inmediato en el resto de vistas del sistema.

## Actores y alcance

**Usuarios:**

- Operador del dashboard (medico/residente/evaluador): introduce los
  datos y consulta el resultado.
- Evaluador del proyecto: comprueba que el sistema crea el paciente
  correctamente y aplica las reglas de forma transparente.
- API REST: punto de entrada unico (el dashboard NO escribe directamente
  en MongoDB, sigue siendo API-only — ADR-007).

**Dentro del alcance:**

- Endpoint REST `POST /api/v1/triage/patients` que recibe payload JSON
  con datos demograficos + signos vitales + sintomas y devuelve el
  paciente creado + nivel de triaje + razones.
- Endpoint `GET /api/v1/triage/rules` que documenta las reglas
  vigentes (umbrales, dependencias). Sirve como auto-documentacion.
- Logica de reglas como funcion pura (`src/api/triage.py`),
  reutilizable y testeable sin Mongo ni FastAPI.
- Persistencia en MongoDB: paciente nuevo en la coleccion `patients` con
  un campo `triage` embebido (estructura definida en RF-3).
- Vista nueva "Triaje" en el dashboard: formulario Streamlit + resultado
  visual claro (grave/medio/leve con codigo de color) + link al detalle
  del paciente recien creado.
- Trazabilidad: el campo `triage.source = "manual_triage"` distingue
  estos pacientes de los del ETL.
- Tests: unitarios de las reglas, integracion del endpoint para los tres
  niveles, validacion de payload invalido, E2E con stack vivo.

**Fuera del alcance:**

- Autenticacion / autorizacion. Entorno de demostracion sin auth.
- Edicion posterior del triaje. Una vez creado, el triaje es inmutable
  Re-triajear un paciente existente queda fuera del alcance de esta
  iteracion (ver RF-7); si en el futuro se necesita, sera una nueva
  feature en otro ciclo SDD.
- Subida de imagenes asociadas al paciente. Las radiografias siguen el
  flujo definido en la feature de clasificacion (bootstrap o demo).
- Modelo ML entrenado para predecir gravedad. Justificacion en
  ADR-008: sin dataset etiquetado, las reglas son la unica
  via defendible.
- Diagnostico clinico vinculante. El sistema es asistencia al triaje.
- Integracion con sistemas hospitalarios reales (HIS, HL7, FHIR).
- Notificaciones / alertas automatizadas en caso de "grave". Pendiente
  de Feature 5 (Automatizacion) que sigue partial.

## User Stories (recomendado)

### US-1 — Crear paciente con triaje grave (Prioridad: P1)

**Como** medico de urgencias
**Quiero** dar de alta a un paciente con signos vitales criticos
**Para** que el sistema lo marque como "grave" y deje constancia
auditable

**Por que esta prioridad:** es el caso con mayor impacto operativo si
el sistema falla (un grave clasificado como leve). Es la US que mas
hay que blindar con tests, especialmente en las fronteras de los
umbrales.

**Test independiente:** crear un paciente con SpO2 = 88 (o cualquier
otro criterio de grave) -> respuesta 201 con `triage.level = "grave"` y
`reasons` no vacio.

**Escenarios de aceptacion:**

1. **Dado** un paciente con SpO2 = 88 y resto normal, **cuando** se
   envia `POST /api/v1/triage/patients`, **entonces** la respuesta es
   201, `triage.level = "grave"` y `triage.reasons` incluye
   "SpO2 < 92".
2. **Dado** un paciente con frecuencia respiratoria = 32 y resto normal,
   **cuando** se envia el POST, **entonces** `triage.level = "grave"` y
   `triage.reasons` incluye "FR > 30".
3. **Dado** un paciente con sintoma "alteracion_conciencia" = true,
   **cuando** se envia el POST, **entonces** `triage.level = "grave"`
   independientemente del resto de signos vitales.

---

### US-2 — Crear paciente con triaje medio (Prioridad: P2)

**Como** medico de urgencias
**Quiero** que un paciente con signos intermedios sea marcado "medio"
**Para** priorizar su atencion sin saltar al protocolo de grave

**Por que esta prioridad:** caso comun pero no critico. Validar que las
fronteras (umbral 92 para SpO2, umbral 22 para FR, etc.) funcionan
correctamente.

**Test independiente:** SpO2 = 93 + resto normal -> `level = "medio"`.

**Escenarios de aceptacion:**

1. **Dado** SpO2 = 93 y resto normal, **cuando** POST, **entonces**
   `level = "medio"` y `reasons` incluye "SpO2 92-94".
2. **Dado** temperatura = 39.5 y resto normal, **cuando** POST,
   **entonces** `level = "medio"` y `reasons` incluye "T >= 39".
3. **Dado** edad = 75 y temperatura = 38.5 (fiebre), **cuando** POST,
   **entonces** `level = "medio"` y `reasons` menciona la combinacion
   edad >= 70 + fiebre.

---

### US-3 — Crear paciente con triaje leve (Prioridad: P3)

**Como** medico de urgencias
**Quiero** que un paciente con signos normales sea marcado "leve"
**Para** orientar la priorizacion sin saturar el flujo de urgencias

**Por que esta prioridad:** caso por defecto cuando ninguna regla
dispara. Es importante que NO se confunda con grave/medio por error.

**Test independiente:** paciente con signos vitales todos en rango
normal -> `level = "leve"`, `reasons` vacio o explicativo.

**Escenarios de aceptacion:**

1. **Dado** SpO2 = 98, FR = 16, FC = 75, T = 36.8, sistolica = 120,
   sin sintomas criticos, **cuando** POST, **entonces** `level = "leve"`.
2. **Dado** que `level = "leve"`, **entonces** `reasons` puede estar
   vacio (sin reglas disparadas) o contener un texto explicativo del
   tipo "sin criterios de gravedad ni medios".

## Requisitos funcionales

- **RF-1:** Existe un endpoint `POST /api/v1/triage/patients` que recibe
  un payload JSON con los siguientes campos obligatorios:
  - `name` (string, no vacio)
  - `gender` (string en `{"M", "F", "Other"}`)
  - **uno de los dos** debe estar presente: `birth_date` (string ISO
    YYYY-MM-DD) o `age` (int >= 0)
  - `vital_signs` (objeto con):
    - `temperature_celsius` (float, rango plausible 30-45)
    - `oxygen_saturation` (int, rango 0-100)
    - `heart_rate` (int, rango 0-300)
    - `respiratory_rate` (int, rango 0-100)
    - `systolic_bp` (int, rango 0-300)
  - `symptoms` (lista de strings) — ver glosario en design.
  - Y los siguientes opcionales:
  - `blood_type` (string)
  - `risk_factors` (lista de strings)

- **RF-2:** Si el payload es invalido (campos obligatorios ausentes,
  tipos incorrectos, valores fuera de rango), la API responde **422
  Unprocessable Entity** con `detail` legible.

- **RF-3:** Tras validar el payload, la API:
  1. Genera un `external_id` candidato (formato definido en RF-6).
  2. Evalua las reglas de triaje (RF-5) y obtiene `level + reasons`.
  3. Persiste el paciente en el **dataset operativo `patients` de
     MongoDB** (no en los CSV raw del pipeline, que solo se rellenan
     desde Faker en `data/raw/`) mediante una operacion explicita de
     **insercion** (`insert_one`, no upsert) con la siguiente
     estructura:
     ```
     {
       "external_id": "<generado>",
       "name": "<input>",
       "birth_date": "<input o derivada de age>",
       "age": <int>,
       "gender": "<input>",
       "blood_type": "<input opcional>",
       "admissions": [],
       "radiographies": [],
       "triage": {
         "level": "grave|medio|leve",
         "score": <int>,
         "reasons": ["<rule_id_1>", "<rule_id_2>"],
         "vital_signs": { ... },
         "symptoms": [...],
         "risk_factors": [...],
         "triaged_at": "<UTC ISO>",
         "source": "manual_triage",
         "rules_version": "1.0"
       }
     }
     ```
     Si el `external_id` candidato ya existe (colision contra el indice
     unico `external_id`), la API **NO actualiza al paciente existente**:
     reintenta con el siguiente `NNNN` (ver RF-7).
  4. Devuelve **201 Created** con el documento serializado.

- **RF-4:** El paciente creado debe ser consultable inmediatamente via
  `GET /api/v1/patients/{external_id}` con el campo `triage` poblado.

- **RF-5:** La logica de reglas vive en `src/api/triage.py` como funcion
  pura `evaluate(payload) -> TriageResult`. Reglas (version 1.0):
  - **grave** si alguno de:
    - `oxygen_saturation < 92`
    - `systolic_bp < 90`
    - `respiratory_rate > 30`
    - `heart_rate > 130`
    - sintoma `alteracion_conciencia` presente
    - sintoma `dolor_toracico_fuerte` presente
  - **medio** si NO grave y alguno de:
    - `92 <= oxygen_saturation <= 94`
    - `temperature_celsius >= 39`
    - `22 <= respiratory_rate <= 30`
    - `110 <= heart_rate <= 130`
    - edad >= 70 con temperatura >= 38 o sintoma respiratorio
      (`tos`, `disnea`, etc.)
  - **leve** en caso contrario.

- **RF-6:** El servidor genera el `external_id` con formato
  `TRIAGE-YYYYMMDD-NNNN`, donde `NNNN` es un contador secuencial diario
  (4 digitos, padding con cero, maximo 9999 triajes por dia).
  Garantiza:
  - No colision con el patron del ETL (`^HOSP-\d{6}$`).
  - Trazabilidad visual del origen del paciente.
  - Orden cronologico natural.

- **RF-7:** La persistencia usa `insert_one` (no `upsert`). El
  servidor calcula `NNNN` como `(numero de pacientes con prefijo
  `TRIAGE-YYYYMMDD-` ya existentes) + 1`. Si la insercion lanza
  `DuplicateKeyError` (por colision concurrente del indice unico
  `external_id`), la API **reintenta con el siguiente `NNNN`** hasta
  un maximo configurable (`TRIAGE_MAX_RETRIES`, default 5). Si tras
  esos reintentos sigue habiendo colision, devuelve **409 Conflict**
  con `detail` legible. Esta semantica garantiza que **nunca se
  actualiza** un paciente existente por error.

- **RF-8:** Endpoint `GET /api/v1/triage/rules` que devuelve un JSON
  con las reglas vigentes y la `rules_version`. Util para auditoria y
  para que el dashboard pueda mostrar las reglas al usuario.

- **RF-9:** El dashboard tiene una **vista nueva "Triaje"** registrada
  en `src/dashboard/app.py`. Contenido:
  - Formulario con los campos del payload.
  - Boton "Calcular y crear paciente".
  - Resultado visual claro: cuadro grande con `level` en color
    (rojo/ambar/verde) + lista de `reasons`.
  - Link al detalle del paciente (`/patients?external_id=...` o
    instruccion textual).
  - Banner permanente: "Asistencia al triaje, no diagnostico clinico
    vinculante" (mismo posicionamiento que el clasificador).

## Requisitos no funcionales

- **RNF-1:** El endpoint responde en menos de **1 segundo** sobre el
  stack levantado con `docker compose up` en una maquina de desarrollo
  media. No hay inferencia ML implicada.
- **RNF-2:** Las reglas son **deterministas y trazables**: la salida
  `reasons` permite reproducir manualmente por que un paciente esta
  clasificado como grave/medio/leve.
- **RNF-3:** El dashboard sigue siendo **API-only** (ADR-007): NO abre
  conexion directa a MongoDB; toda la persistencia pasa por
  `POST /api/v1/triage/patients`.
- **RNF-4:** La feature **no toca el ETL ni el modelo de
  radiografias**. Pacientes manuales no aparecen en CSVs y el pipeline
  no los puede referenciar.
- **RNF-5:** La logica de reglas debe ser **testeable sin Mongo ni
  FastAPI**: funcion pura con entradas y salidas explicitas. Cobertura
  unitaria al menos para los tres niveles + cada regla individual de
  grave/medio.
- **RNF-6:** El campo `triage` debe estar **declarado en el schema
  Pydantic** (`Patient.triage: TriageInfo | None`) para que el
  dashboard, la vista de Pacientes y `GET /patients/{id}` lo
  serialicen correctamente. Sin esta declaracion, `extra="ignore"`
  lo descartaria silenciosamente.

## Casos borde y errores

- **CB-1:** Payload con todos los campos validos pero
  `oxygen_saturation = 91`: cae justo en el umbral grave. La regla es
  estricta `< 92`, asi que 91 va a grave. Tests deben cubrir 91 y 92.
- **CB-2:** Edad calculada desde `birth_date` cuando no se da `age`:
  usar `date.today() - birth_date` redondeando a anos enteros (mes a
  mes). Si ambos se dan, prevalece `age`.
- **CB-3:** Lista de `symptoms` vacia: aceptado. Las reglas solo
  miran signos vitales en ese caso.
- **CB-4:** Lista de `symptoms` con valores no reconocidos (texto
  libre fuera del glosario): aceptados sin error (no se rechaza el
  payload), pero esos sintomas no disparan reglas. El glosario define
  los **keywords activos**; el resto es metadato libre.
- **CB-5:** Generacion del `external_id`: si dos peticiones simultaneas
  intentan crear el contador `NNNN`, la unicidad del indice
  `external_id` en Mongo (ya existe) garantiza que solo una gana. La
  otra reintenta con el siguiente NNNN. Maximo 9999 triajes por dia
  (rango suficiente para el alcance del proyecto; ampliarlo es
  trabajo futuro si la presion de uso lo justifica).
- **CB-6:** MongoDB no disponible al hacer POST: la API responde **503
  Service Unavailable** con mensaje claro, sin crashear.
- **CB-7:** Caracteres especiales en `name` (acentos, comillas): se
  aceptan sin transformacion. Mongo y Pydantic los manejan nativamente.

## Dudas abiertas

Ninguna. Todas cerradas en la revision del 2026-05-18 con Alejandro:

1. **Formato del `external_id`**: `TRIAGE-YYYYMMDD-NNNN` (4 digitos
   diarios, padding con cero).
2. **Re-triaje**: NO en esta iteracion. Cada paciente tiene un unico
   campo `triage`. Re-triajear queda como trabajo futuro fuera de
   alcance.
3. **Maximo diario**: 9999 pacientes por dia es suficiente para la
   entrega; si se excede, la API devuelve 409 (RF-7).
4. **Admision virtual asociada**: NO. La feature crea solo el
   paciente con su `triage`.
5. **Histograma en SQLite**: NO. No se anade tabla nueva.
6. **Boton descargar JSON en el dashboard**: NO.
7. **Endpoint `GET /api/v1/triage/rules`**: SI (RF-8).
8. **ADR explicito sobre reglas vs ML**: SI. Se crea
   `decisions/ADR-008-triaje-basado-en-reglas.md`.

**Sintomas (decision de diseno, no duda):** se acepta texto libre en
`symptoms`. Las reglas se aplican solo a los keywords activos del
glosario (`alteracion_conciencia`, `dolor_toracico_fuerte`, `tos`,
`disnea`, `fiebre`). Cualquier otro texto se persiste como metadato
sin disparar reglas (CB-4).

## Criterios de aceptacion

- [ ] **CA-1** (RF-1, US-1, CB-1): Tras `docker compose up`,
  `POST /api/v1/triage/patients` con un payload de paciente grave
  (p.ej. SpO2 = 88) devuelve **201** y el body incluye
  `triage.level = "grave"` con `reasons` no vacio. El `external_id`
  generado sigue el patron acordado.
- [ ] **CA-2** (RF-1, US-2): POST con payload de paciente medio
  (p.ej. SpO2 = 93) devuelve **201** y `triage.level = "medio"`.
- [ ] **CA-3** (RF-1, US-3): POST con payload de paciente leve (todos
  los signos normales, sin sintomas criticos) devuelve **201** y
  `triage.level = "leve"`.
- [ ] **CA-4** (RF-2): POST sin campo obligatorio (p.ej. sin
  `oxygen_saturation`) o con tipo incorrecto devuelve **422** con
  `detail` legible que indica el campo problematico.
- [ ] **CA-5** (RF-4): Tras crear un paciente grave/medio/leve,
  `GET /api/v1/patients/{external_id}` devuelve el documento con el
  campo `triage` poblado correctamente.
- [ ] **CA-6** (RF-5, RNF-5): Tests unitarios en
  `tests/api/test_triage_rules.py` cubren al menos cada regla
  individual de grave (6 reglas) y de medio (4-5 reglas) + el caso
  leve.
- [ ] **CA-7** (RF-9): La vista nueva "Triaje" en el dashboard:
  - Aparece en la barra de navegacion entre Pacientes y Clasificador
    (o donde se decida en design).
  - Permite enviar el formulario con un paciente grave y muestra
    visualmente el resultado.
  - Muestra el banner "Asistencia al triaje, no diagnostico clinico
    vinculante".
- [ ] **CA-8** (RNF-3): El codigo del dashboard NO importa pymongo,
  minio ni sqlite3 (validable por inspeccion: `grep -r "pymongo\|minio\|sqlite3" src/dashboard/`).
- [ ] **CA-9** (RNF-2): El campo `triage.reasons` contiene
  identificadores estables (p.ej. `spo2_lt_92`, `fr_gt_30`) que
  permiten reproducir manualmente la decision.
- [ ] **CA-10** (RF-8): `GET /api/v1/triage/rules` devuelve el JSON
  con las reglas vigentes y la `rules_version`.

## Asunciones

- El operador conoce el sentido basico de los signos vitales y no
  introduce valores sin sentido. Las validaciones de rango son
  permisivas (rangos plausibles, no umbrales validados medicamente):
  cubren errores de tecleo, no juicio clinico.
- El enfoque es academico: el sistema basado en reglas se entrega
  como ejercicio aplicado de la teoria de Modelos de IA vista en el
  Master. **No es un sistema clinico validado** ni implementa ningun
  protocolo medico real.
- No hace falta autenticacion: el endpoint POST esta abierto en el
  entorno de demostracion. En produccion seria un endpoint protegido
  por OAuth/JWT (documentado como trabajo futuro).
- La feature se entrega despues de la presentacion principal o como
  ampliacion documentada; no rompe el flujo demo actual del dashboard
  (las 5 vistas siguen funcionando).

## Changelog

| Fecha | Cambio | Motivo | Fase |
|-------|--------|--------|------|
| 2026-05-18 | Creacion inicial (draft) | Solicitud del profesor: añadir funcionalidad de triaje al proyecto | spec |
| 2026-05-18 | 8 dudas cerradas + ajustes obligatorios | Revision con Alejandro: enmarcar como sistema basado en reglas conectado con la teoria del Master, sin justificarlo como adaptacion de estandares externos; aclarar que el dataset operativo es MongoDB y no los CSV raw del pipeline; sustituir upsert por `insert_one` con retry para que el alta nunca actualice un paciente existente; cerrar todas las dudas no bloqueantes con decisiones explicitas | spec |
| 2026-05-19 | Pase de coherencia documental previo a `/implementar` | RF-8 y CA-10 confirmados como obligatorios; estado del ADR-008 actualizado a aceptado en todas las referencias; cerradas las menciones a iteraciones documentales futuras; reglas marcadas como version 1.0; tope diario 9999 descrito como suficiente para el alcance | spec |
