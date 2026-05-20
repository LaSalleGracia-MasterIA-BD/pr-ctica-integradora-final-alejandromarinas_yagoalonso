# Design: Triaje de pacientes en alta manual

> Spec: specs/triage-pacientes.md
> ADR relacionado: decisions/ADR-008-triaje-basado-en-reglas.md

## Decision arquitectonica

Tres principios de diseño:

1. **Reglas como funcion pura**: la logica de triaje vive en
   `src/api/triage.py` como funcion `evaluate(payload) -> TriageResult`,
   sin dependencias de Mongo ni FastAPI. Permite tests unitarios
   triviales y separa el "que" (reglas de produccion academicas) del
   "como" (HTTP + persistencia). El enfoque encaja con la teoria del
   Master sobre sistemas basados en reglas como alternativa a los
   modelos aprendidos cuando no hay supervision disponible.
2. **Persistencia explicita con `insert_one`, no `upsert`**: se
   introduce un metodo nuevo `MongoWriter.insert_patient(doc)` que
   llama a `insert_one`. El alta manual **nunca puede sobrescribir un
   paciente existente** por construccion: si el indice unico `external_id`
   detecta colision, Mongo lanza `DuplicateKeyError` y el router
   reintenta con el siguiente `NNNN` hasta un limite pequeño (5). El
   metodo `bulk_upsert_patients` existente se reserva para el ETL.
3. **Dashboard API-only**: igual que las demas vistas, el formulario
   de triaje llama unicamente al cliente HTTP (`ApiClient`). Cero
   conexiones directas a MongoDB desde el dashboard (ADR-007).

El paciente queda persistido en el **dataset operativo `patients`** de
MongoDB. **No** se anade a los CSV raw del pipeline (`data/raw/*.csv`),
que solo se rellenan desde Faker y se procesan en batch; los pacientes
de triaje viven exclusivamente en la base documental.

```
   Usuario (operador) --HTTP-->  Dashboard / vista Triaje (Streamlit)
                                         |
                                         | api_client.create_triage_patient(payload)
                                         v
                                  +------------------------+
                                  |   API REST             |
                                  | POST /api/v1/triage/   |
                                  |        patients        |
                                  +------------------------+
                                         |
                          (1) Pydantic valida TriagePatientRequest
                          (2) evaluate(payload) -> TriageResult  [pure]
                          (3) genera external_id candidato
                              (TRIAGE-YYYYMMDD-NNNN)
                          (4) MongoWriter.insert_patient(doc)
                              -> insert_one (no upsert)
                              -> reintenta con NNNN+1 si
                                 DuplicateKeyError (max 5 reintentos)
                                         |
                                         v
                                  MongoDB: patients (dataset operativo)
                                  (con campo triage embebido)
```

## Trazabilidad spec -> componentes

| Requisito | Componente(s) | Archivos |
|-----------|--------------|----------|
| RF-1 (endpoint POST) | `src/api/routers/triage.py` | `src/api/routers/triage.py`, `src/api/main.py` |
| RF-2 (validacion 422) | Pydantic schema `TriagePatientRequest` | `src/api/models.py` |
| RF-3 (estructura `triage` en Mongo) | **Nuevo** `MongoWriter.insert_patient` (`insert_one`) + schema `TriageInfo` | `src/api/models.py`, `src/pipeline/storage/mongo_writer.py` (metodo nuevo) |
| RF-7 (insert no upsert + retry) | Router con manejo de `DuplicateKeyError` + `next_triage_id` | `src/api/routers/triage.py`, `src/api/triage.py` |
| RF-4 (GET /patients/{id} devuelve `triage`) | Extension de `Patient` con `triage: TriageInfo | None` | `src/api/models.py` |
| RF-5 (reglas grave/medio/leve) | Funcion `evaluate` pura | `src/api/triage.py` |
| RF-6 (generacion `external_id`) | Helper `next_triage_id(reader, date)` | `src/api/triage.py` (helper) |
| RF-7 (409 si duplicado) | Manejo de `DuplicateKeyError` en el router | `src/api/routers/triage.py` |
| RF-8 (GET /rules) | `src/api/routers/triage.py` | mismo router |
| RF-9 (vista dashboard) | `src/dashboard/views/triage.py` + `app.py` | dashboard nuevo + registro |
| RNF-3 (API-only dashboard) | Verificacion por `grep` en CA-8 | tests E2E + revision |
| RNF-5 (testeable sin Mongo) | Funcion pura `evaluate` | tests unitarios |
| RNF-6 (campo `triage` en schema) | `Patient.triage: TriageInfo | None` | `src/api/models.py` |

## Componentes

### `src/api/triage.py` (nuevo, **logica pura**)

**Responsabilidad:** evaluar las reglas de triaje sobre un payload
validado y devolver un resultado estructurado. No abre conexiones ni
escribe nada.

**Funciones publicas:**

```python
def evaluate(payload: TriagePayload) -> TriageResult:
    """Evalua las reglas y devuelve level + score + reasons.

    payload: TriagePayload (dataclass o TypedDict) con signos vitales
    y sintomas validados.

    Returns: TriageResult con:
      - level: Literal["grave", "medio", "leve"]
      - score: int (suma simple de reglas disparadas; informativo)
      - reasons: list[str] con identificadores estables
        (`spo2_lt_92`, `fr_gt_30`, `alteracion_conciencia`, etc.)
    """

def get_rules_definition() -> dict:
    """Devuelve la version y descripcion de las reglas vigentes.

    Usado por GET /api/v1/triage/rules. Estructura:
    {
      "version": "1.0",
      "levels": {
        "grave": [{"id": "spo2_lt_92", "description": "..."}],
        "medio": [...],
      }
    }
    """

def next_triage_id(reader: MongoReader, today: date) -> str:
    """Genera el siguiente external_id para hoy.

    Cuenta los pacientes con prefijo `TRIAGE-YYYYMMDD-` ya existentes
    y devuelve el siguiente. Garantia de unicidad por el indice unico
    `external_id` (si dos peticiones colisionan, una falla con
    DuplicateKeyError y reintenta — manejado en el router).
    """
```

**Reglas implementadas (RF-5):**

| Nivel | Regla | ID estable | Notas |
|---|---|---|---|
| grave | `oxygen_saturation < 92` | `spo2_lt_92` | Umbral estricto. SpO2=92 NO dispara grave. |
| grave | `systolic_bp < 90` | `sbp_lt_90` | |
| grave | `respiratory_rate > 30` | `fr_gt_30` | Umbral estricto. |
| grave | `heart_rate > 130` | `fc_gt_130` | Umbral estricto. |
| grave | sintoma `alteracion_conciencia` | `alteracion_conciencia` | Bandera booleana en `symptoms`. |
| grave | sintoma `dolor_toracico_fuerte` | `dolor_toracico_fuerte` | Bandera booleana en `symptoms`. |
| medio | `92 <= oxygen_saturation <= 94` | `spo2_92_94` | Solo si NO grave. |
| medio | `temperature_celsius >= 39` | `temp_ge_39` | Solo si NO grave. |
| medio | `22 <= respiratory_rate <= 30` | `fr_22_30` | Solo si NO grave. |
| medio | `110 <= heart_rate <= 130` | `fc_110_130` | Solo si NO grave. |
| medio | `age >= 70 AND (temp >= 38 OR sintoma respiratorio)` | `anciano_riesgo_respiratorio` | Solo si NO grave. Sintomas respiratorios: `tos`, `disnea`, `fiebre`. |
| leve | ninguna regla disparada | (none) | `reasons` vacio o `["sin_criterios"]`. |

### `src/api/routers/triage.py` (nuevo)

**Responsabilidad:** exponer el endpoint REST. Orquesta validacion ->
reglas -> persistencia. Maneja errores HTTP.

```python
router = APIRouter(prefix="/api/v1/triage", tags=["triage"])

@router.post("/patients", response_model=TriagePatientResponse, status_code=201)
def create_triage_patient(
    request: Request, body: TriagePatientRequest
) -> TriagePatientResponse:
    """Crea paciente nuevo y le asigna nivel de triaje.

    1. Pydantic ya valido el payload (422 automatico si invalido).
    2. evaluate(body) -> TriageResult
    3. next_triage_id(reader, today) -> external_id candidato
    4. Construir doc Mongo y llamar a writer.insert_patient(doc).
       - Si DuplicateKeyError -> calcular el siguiente NNNN y
         reintentar (max TRIAGE_MAX_RETRIES = 5).
       - Si tras los reintentos sigue fallando -> 409 Conflict.
    5. Devolver doc completo
    """

@router.get("/rules")
def get_rules(request: Request) -> dict:
    """Devuelve la definicion de las reglas vigentes (RF-8)."""
    return get_rules_definition()
```

**Errores:**

- 201: paciente creado.
- 422: payload invalido (Pydantic).
- 409: `external_id` duplicado tras `TRIAGE_MAX_RETRIES` (default 5)
  reintentos sucesivos con `NNNN`+1. Indica colision real (alta
  concurrencia o cupo diario agotado).
- 503: MongoDB no disponible.

### `src/pipeline/storage/mongo_writer.py` — extension

Se añade un metodo nuevo, no se modifica el comportamiento existente:

```python
def insert_patient(self, patient_doc: dict) -> str:
    """Inserta un paciente nuevo sin upsert.

    A diferencia de `bulk_upsert_patients` (usado por el ETL), este
    metodo:
      * Llama a `insert_one`, NO a un upsert.
      * NO modifica `admissions` ni `radiographies` (el doc llega
        tal cual lo construye el router de triaje).
      * Anade `created_at` y `updated_at` antes de persistir.

    Si Mongo lanza `pymongo.errors.DuplicateKeyError` por colision
    sobre el indice unico `external_id`, esta funcion **propaga** la
    excepcion sin intentar resolverla. El router decide si reintentar
    (RF-7) o devolver 409.

    Devuelve el `external_id` del paciente insertado.
    """
    now = datetime.now(timezone.utc)
    doc = {**patient_doc, "created_at": now, "updated_at": now}
    self.db.patients.insert_one(doc)
    return doc["external_id"]
```

**Por que metodo nuevo y no reutilizar `bulk_upsert_patients`:**

- `bulk_upsert_patients` hace `$set` con upsert. Si por accidente el
  router pasara un `external_id` que ya existe (p. ej. tras un bug
  en `next_triage_id`), el upsert **sobreescribiria** el paciente
  existente sin avisar. Con `insert_one`, Mongo lanza
  `DuplicateKeyError` y el sistema reintenta o devuelve 409.
- La semantica conceptual es distinta: el ETL hace **upsert** (re-procesar
  un CSV no debe duplicar), el alta manual hace **insercion**.
  Mantener metodos separados deja claro el contrato de cada uno.

### Schemas Pydantic — extension de `src/api/models.py`

```python
class VitalSigns(BaseModel):
    temperature_celsius: float = Field(ge=30, le=45)
    oxygen_saturation: int = Field(ge=0, le=100)
    heart_rate: int = Field(ge=0, le=300)
    respiratory_rate: int = Field(ge=0, le=100)
    systolic_bp: int = Field(ge=0, le=300)

class TriagePatientRequest(BaseModel):
    name: str = Field(min_length=1)
    gender: Literal["M", "F", "Other"]
    birth_date: str | None = None  # ISO YYYY-MM-DD
    age: int | None = Field(default=None, ge=0, le=130)
    blood_type: str | None = None
    vital_signs: VitalSigns
    symptoms: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_birth_or_age(self):
        if self.birth_date is None and self.age is None:
            raise ValueError("birth_date o age es obligatorio")
        return self

class TriageInfo(BaseModel):
    level: Literal["grave", "medio", "leve"]
    score: int
    reasons: list[str]
    vital_signs: VitalSigns
    symptoms: list[str]
    risk_factors: list[str]
    triaged_at: datetime
    source: str = "manual_triage"
    rules_version: str

# Extension de Patient:
class Patient(BaseModel):
    # ... campos existentes ...
    triage: TriageInfo | None = None

class TriagePatientResponse(Patient):
    """Devuelve el Patient completo (con `triage` poblado)."""
```

### `src/dashboard/views/triage.py` (nuevo)

**Responsabilidad:** formulario + envio al API + visualizacion del
resultado. Estilo coherente con las otras vistas (sin emojis, mismo
tema, banners de error via `error_banner`).

**Estructura:**

```python
st.title("Triaje")
st.caption("Asistencia al triaje, no diagnostico clinico vinculante.")

# Formulario
with st.form("triage_form"):
    col_demo, col_vitals = st.columns(2)
    with col_demo:
        name = st.text_input("Nombre completo")
        gender = st.selectbox("Genero", ["M", "F", "Other"])
        birth_date = st.date_input("Fecha de nacimiento", value=None)
        age = st.number_input("Edad (alternativa)", min_value=0, max_value=130, value=None)
        blood_type = st.text_input("Grupo sanguineo (opcional)")
    with col_vitals:
        temp = st.number_input("Temperatura (Celsius)", value=36.8, step=0.1)
        spo2 = st.number_input("Saturacion (%)", value=98, min_value=0, max_value=100)
        hr = st.number_input("Frec. cardiaca (lpm)", value=75, min_value=0, max_value=300)
        fr = st.number_input("Frec. respiratoria (rpm)", value=16, min_value=0, max_value=100)
        sbp = st.number_input("Tension sistolica (mmHg)", value=120, min_value=0, max_value=300)

    symptoms_input = st.multiselect(
        "Sintomas principales",
        ["alteracion_conciencia", "dolor_toracico_fuerte", "tos", "disnea", "fiebre", ...],
    )
    risk_factors_input = st.multiselect("Factores de riesgo (opcional)", [...])
    submitted = st.form_submit_button("Calcular y crear paciente")

if submitted:
    payload = { ... }
    data, err = api.create_triage_patient(payload)
    if err:
        show_api_error(err, context="/triage/patients")
    else:
        _render_triage_result(data)
```

**Visualizacion del resultado:**

```python
def _render_triage_result(patient: dict) -> None:
    triage = patient.get("triage", {})
    level = triage.get("level", "?")
    colors = {"grave": "#DC2626", "medio": "#D97706", "leve": "#15803D"}
    color = colors.get(level, "#64748B")

    st.markdown(
        f"""
        <div style="background:{color}; color:white; padding:24px;
                    border-radius:8px; font-size:1.5em; font-weight:600;">
            Nivel: {level.upper()}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("Razones:")
    for r in triage.get("reasons", []) or ["(sin criterios disparados)"]:
        st.markdown(f"- `{r}`")
    st.caption(f"Paciente creado: {patient['external_id']}")
```

### `src/dashboard/api_client.py` — metodos nuevos

```python
def create_triage_patient(self, payload: dict) -> ResultJson:
    return self._request_json(
        "POST", "/api/v1/triage/patients", json=payload,
    )

def get_triage_rules(self) -> ResultJson:
    return self._request_json("GET", "/api/v1/triage/rules")
```

### `src/dashboard/app.py` — registro de la pagina

Una linea nueva en la lista `pages` de `st.navigation`:

```python
st.Page(str(_VIEWS_DIR / "triage.py"), title="Triaje"),
```

Posicion sugerida: entre **Pacientes** (que muestra el resultado) y
**Clasificador** (otra accion de IA). El operador puede crear un
paciente en Triaje y verlo justo despues en Pacientes.

## Modelo de datos

### Documento `patients` con triaje

```json
{
  "external_id": "TRIAGE-20260518-0001",
  "name": "Juan Garcia Perez",
  "birth_date": "1955-03-15",
  "age": 71,
  "gender": "M",
  "blood_type": "A+",
  "admissions": [],
  "radiographies": [],
  "triage": {
    "level": "grave",
    "score": 2,
    "reasons": ["spo2_lt_92", "anciano_riesgo_respiratorio"],
    "vital_signs": {
      "temperature_celsius": 38.5,
      "oxygen_saturation": 89,
      "heart_rate": 105,
      "respiratory_rate": 24,
      "systolic_bp": 110
    },
    "symptoms": ["tos", "disnea"],
    "risk_factors": ["epoc"],
    "triaged_at": "2026-05-18T15:42:11Z",
    "source": "manual_triage",
    "rules_version": "1.0"
  },
  "created_at": "2026-05-18T15:42:11Z",
  "updated_at": "2026-05-18T15:42:11Z"
}
```

### Indices Mongo

No se anaden indices nuevos. Los existentes son suficientes:

- `external_id` unico (garantiza unicidad del paciente).
- `radiographies.minio_object_key` (irrelevante para triaje).

## Contratos de datos

### Datos de entrada (POST /api/v1/triage/patients)

| Campo | Formato | Obligatorio | Validaciones | Que pasa si falta/falla |
|--------|---------|-------------|-------------|------------------------|
| `name` | string no vacio | si | `min_length=1` | 422 |
| `gender` | enum `M/F/Other` | si | `Literal` | 422 |
| `birth_date` | ISO YYYY-MM-DD | parcial | uno de los dos (validador) | 422 si ambos None |
| `age` | int 0-130 | parcial | `ge=0, le=130` | 422 |
| `blood_type` | string | no | — | acepta cualquier valor |
| `vital_signs.*` | int/float | si | rangos plausibles | 422 |
| `symptoms` | lista de strings | no | — | default `[]` |
| `risk_factors` | lista de strings | no | — | default `[]` |

### Datos de salida (201 Created)

`TriagePatientResponse` es una **clase explicita** heredando de
`Patient` (`class TriagePatientResponse(Patient): ...`). Da mejor
documentacion en OpenAPI/Swagger que un alias y permite anadir
campos especificos de la respuesta en el futuro sin tocar
`Patient`.

### Glosario de sintomas activos

Sintomas que disparan reglas (todos los demas son metadato libre):

| Sintoma | Tipo de regla |
|---------|---------------|
| `alteracion_conciencia` | dispara grave (RF-5) |
| `dolor_toracico_fuerte` | dispara grave (RF-5) |
| `tos`, `disnea`, `fiebre` | sintomas respiratorios; pueden disparar `anciano_riesgo_respiratorio` (medio) si edad >= 70 |

Cualquier otro string en `symptoms` se persiste pero no activa reglas.

## Trade-offs

| Decision | Alternativa descartada | Razon |
|----------|----------------------|-------|
| Vista nueva "Triaje" | Bloque dentro de "Pacientes" | La vista Pacientes es read-only por diseño. Mezclar creacion rompe coherencia. Una vista propia separa formulario y visualizacion |
| Reglas en codigo (no ML) | Modelo ML supervisado | Sin dataset etiquetado de gravedad, ML aqui seria inventar ground truth. Reglas son auditables (`reasons`). Ver ADR-008 |
| `TRIAGE-YYYYMMDD-NNNN` | `HOSP-MANUAL-NNNNNN` | Prefijo distinto evita que el pipeline confunda pacientes manuales con sinteticos. Coste: el campo no es compatible con el patron `^HOSP-\d{6}$` del validador (ventaja: queda claro el origen) |
| **`insert_one` via metodo nuevo `insert_patient`** | Reutilizar `bulk_upsert_patients` | Un upsert podria sobrescribir silenciosamente un paciente existente si el `external_id` colisiona. `insert_one` lanza `DuplicateKeyError` y el router decide (reintentar +1 o devolver 409). Garantia dura: el alta manual nunca actualiza un paciente |
| `triage` como subdocumento unico | Array `triages[]` con historico | YAGNI: si en el futuro hace falta re-triajear, se anade en una iteracion posterior. Por ahora, un triaje = un paciente |
| Reglas hardcoded en `src/api/triage.py` | Config JSON externa con umbrales | YAGNI: las reglas no se planea cambiarlas en runtime. Codigo + tests + ADR documentan la version |
| `level` como `Literal["grave","medio","leve"]` | Numerico (1/2/3) | Literal es mas auto-descriptivo en logs, payloads y dashboard. Coherente con el resto del proyecto (UI en castellano) |

## Plan de tests

- `tests/api/test_triage_rules.py` — **unitarios puros**:
  - Una clase por nivel: `TestGrave`, `TestMedio`, `TestLeve`.
  - Una test funcion por regla: `test_grave_spo2_lt_92`, `test_grave_alteracion_conciencia`, etc.
  - Casos borde: `test_spo2_91_es_grave`, `test_spo2_92_es_medio`,
    `test_spo2_94_es_medio`, `test_spo2_95_es_leve`.
  - Combinaciones: paciente que cumple varias reglas grave -> sigue
    siendo grave con `reasons` que incluye las varias reglas.

- `tests/api/test_triage_endpoint.py` — **integracion con MongoDB**:
  - `test_post_grave_returns_201_with_triage`
  - `test_post_medio_returns_201_with_triage`
  - `test_post_leve_returns_201_with_triage`
  - `test_post_missing_field_returns_422`
  - `test_post_invalid_range_returns_422` (p.ej. spo2=150)
  - `test_post_birth_date_xor_age` (ambos ausentes -> 422)
  - `test_external_id_format` (regex match `TRIAGE-\d{8}-\d{4}`)
  - `test_external_id_counter_increments` (dos POST mismo dia -> N y N+1)
  - `test_get_rules_returns_definition`

- `tests/e2e/test_triage_e2e.py` — **con stack vivo**:
  - `test_create_triage_then_get_patient`: POST -> 201, capturar
    external_id -> GET /patients/{id} -> 200 con campo `triage`
    poblado.
  - `test_create_triage_then_list_patients`: paciente aparece en
    `GET /patients` con paginacion adecuada.

- `tests/dashboard/test_api_client_triage.py` (opcional, si se
  considera relevante):
  - Verifica que `create_triage_patient` mapea 422 a
    `ApiError(kind="validation")` (httpx.MockTransport).

**Cobertura objetivo:** funciones de reglas al 100% (es codigo puro,
trivial de cubrir). Endpoint cubierto al menos por los 3 niveles + 2
errores. E2E al menos un flujo end-to-end.

## Riesgos del diseño

| Riesgo | Probabilidad | Impacto | Mitigacion |
|--------|--------------|---------|------------|
| El campo `triage` no se serializa en `GET /patients/{id}` por `extra="ignore"` | Alta si no se cubre | Alto: la vista de Pacientes no veria el campo | Test explicito CA-5 + declaracion `Patient.triage: TriageInfo | None` |
| Race condition al generar el counter `NNNN` con dos POST simultaneos | Baja | Bajo: el indice unico de Mongo aborta la operacion | Manejar `DuplicateKeyError` con retry +1 en `next_triage_id` |
| Reglas mal calibradas: clasificacion no coincide con la intuicion del operador en las fronteras | Media | Medio: percepcion de error si se interpreta como decision medica | Banner explicito + ADR-008 + `reasons` auditables + tests de frontera (SpO2=91/92/94/95, etc.) que documentan la decision |
| El profesor pregunta por que no entrenar un modelo | Alta | Bajo si esta documentado | ADR-008 documenta la razon: sin dataset etiquetado, ML no es defendible |
| Los tests E2E necesitan Mongo limpio (sin contadores residuales del dia) | Media | Bajo | Usar fixture que cuente pacientes con prefijo del dia ANTES del test y verifique incremento esperado |

## Estimacion de tamano

- `src/api/triage.py`: ~80 lineas (funcion pura + helper)
- `src/api/routers/triage.py`: ~60 lineas
- Schemas Pydantic en `models.py`: ~40 lineas anadidas
- `src/dashboard/views/triage.py`: ~120 lineas
- `src/dashboard/api_client.py`: 2 metodos (~15 lineas)
- `src/dashboard/app.py`: 1 linea
- Tests: ~200-250 lineas
- ADR-008: ~80 lineas

**Total estimado:** ~700 lineas de codigo nuevo + tests. Tamaño **M**
(1-3 dias de implementacion).

## Notas para fases siguientes

- El formato `TRIAGE-YYYYMMDD-NNNN` queda fijado por la spec (RF-6).
  Mantener el regex `r"^TRIAGE-\d{8}-\d{4}$"` en los tests para
  detectar regresiones si el formato cambia en futuras iteraciones.
- Si se decide soportar re-triajear (`triages[]`), reabrir este
  design: el modelo Mongo cambia y el helper `next_triage_id` debe
  manejar pacientes existentes.
- Si en algun momento se anade la admision virtual asociada al triaje,
  ese cambio puede ir en una iteracion posterior **sin tocar este
  endpoint** (otra capa, otro test).
