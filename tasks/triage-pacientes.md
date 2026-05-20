# Tasks: Triaje de pacientes en alta manual

> Spec: specs/triage-pacientes.md
> Design: design/triage-pacientes.md

## Formato

Cada tarea sigue: `T### [P?] [US#?] descripcion con path concreto`

- `T###` — ID secuencial.
- `[P]` — paralelizable.
- `[US#]` — pertenece a esa user story.

## Regla TDD

Dentro de cada US, el test que valida un comportamiento se planifica
**antes** que la implementacion. Las tareas T2, T5, T8 (tests
unitarios de reglas) van antes que T3 (logica de reglas) en orden
cronologico aunque no haya dependencia tecnica estricta — esto refleja
que las reglas se diseñan desde los criterios de aceptacion.

## Tabla de tareas

| # | Tarea | Requisitos | Dependencias | Tamaño | Estado |
|---|-------|-----------|-------------|--------|--------|
| T1 | Crear `decisions/ADR-008-triaje-basado-en-reglas.md` con contexto, decision (reglas vs ML), alternativas, consecuencias. Justifica la eleccion conectando con la teoria de Modelos de IA del Master | RF-5 | — | S | done (creado el 2026-05-18 en fase documental) |
| T2 | [US1][US2][US3] Escribir `tests/api/test_triage_rules.py` con tests unitarios puros: una clase por nivel + test por regla individual + casos borde (SpO2=91 grave, =92 medio, =94 medio, =95 leve). Confirmar que **fallan** (rojo) — la funcion `evaluate` aun no existe | CA-6, RF-5, RNF-5 | — | M | done |
| T3 | [US1][US2][US3] Implementar `src/api/triage.py` con `evaluate(payload) -> TriageResult`, `get_rules_definition()` y `next_triage_id(reader, today)`. Funcion pura, sin Mongo ni FastAPI. Hacer pasar T2 | RF-5, RF-6, RF-8, RNF-5 | T2 | M | done |
| T4 | Extender `src/api/models.py` con: `VitalSigns`, `TriagePatientRequest` (con `@model_validator` que exige birth_date o age), `TriageInfo`, anadir `triage: TriageInfo \| None = None` a `Patient`, definir clase explicita `class TriagePatientResponse(Patient): ...` heredando de `Patient` (mejor OpenAPI que un alias) | RF-1, RF-2, RNF-6 | — | S | done |
| T4b | Anadir metodo `MongoWriter.insert_patient(doc) -> str` en `src/pipeline/storage/mongo_writer.py` que llama a `insert_one` (no upsert). Tests en `tests/pipeline/test_mongo_writer.py` (extension): inserta paciente nuevo OK; segundo `insert_patient` con mismo `external_id` lanza `pymongo.errors.DuplicateKeyError` (no se sobrescribe el paciente existente) | RF-3, RF-7 | — | S | done |
| T5 | [US1] Escribir `tests/api/test_triage_endpoint.py::test_post_grave_returns_201_with_triage` (test rojo) + variantes 422 (campo ausente, rango invalido, birth_date xor age) | CA-1, CA-4 | T4 | S | done |
| T6 | Crear `src/api/routers/triage.py` con `POST /api/v1/triage/patients` y `GET /api/v1/triage/rules`. Maneja: 201 success, 422 validacion (automatico via Pydantic), retry +1 con `next_triage_id` si `DuplicateKeyError` (max `TRIAGE_MAX_RETRIES=5`), 409 tras agotar reintentos, 503 si Mongo cae. Usa `MongoWriter.insert_patient` (NO upsert). Wire en `src/api/main.py` con `app.include_router(triage_router.router)`. Hacer pasar T5 | RF-1, RF-2, RF-3, RF-7, RF-8 | T3, T4, T4b, T5 | M | done |
| T7 | [US2] Escribir `tests/api/test_triage_endpoint.py::test_post_medio_returns_201_with_triage` + variante con edad >= 70 + fiebre que dispara `anciano_riesgo_respiratorio` | CA-2, RF-5 | T6 | S | done |
| T8 | [US3] Escribir `tests/api/test_triage_endpoint.py::test_post_leve_returns_201_with_triage` con todos los signos normales y sin sintomas criticos | CA-3, RF-5 | T6 | S | done |
| T9 | Tests adicionales del endpoint en `tests/api/test_triage_endpoint.py`: `test_external_id_format` (regex), `test_external_id_counter_increments`, `test_get_rules_returns_definition`, `test_get_patient_after_create_returns_triage` (CA-5) | CA-5, RF-4, RF-6, RF-8 | T6 | M | done |
| T10 | [P] Anadir metodos `create_triage_patient(payload)` y `get_triage_rules()` a `src/dashboard/api_client.py`. Tests unitarios en `tests/dashboard/test_api_client.py` (extension) con `httpx.MockTransport`: mapeo 201, 422 -> `ApiError(kind="validation")`, 503, error de red | RF-9 | T6 | S | done |
| T11 | [US1][US2][US3] Crear `src/dashboard/views/triage.py`: formulario con dos columnas (demograficos + signos vitales), `st.multiselect` para sintomas y factores de riesgo, banner "Asistencia al triaje, no diagnostico clinico vinculante", boton "Calcular y crear paciente", visualizacion del resultado con `_render_triage_result` (cuadro grande con color por nivel + lista de razones + link al paciente). Manejo de errores via `show_api_error` | RF-9, CA-7 | T10 | M | done |
| T12 | Registrar la nueva pagina en `src/dashboard/app.py` anadiendo `st.Page(str(_VIEWS_DIR / "triage.py"), title="Triaje")` en la lista `pages`. Posicion sugerida: entre "Pacientes" y "Clasificador" | RF-9, CA-7 | T11 | S | done |
| T13 | [P] Tests E2E en `tests/e2e/test_triage_e2e.py`: `test_create_triage_then_get_patient` (POST -> GET /patients/{id}), `test_create_triage_then_list_patients` (paginacion incluye al nuevo). Stack vivo via fixture | CA-1..CA-5 | T6 | M | done |
| T14 | Smoke E2E manual con stack vivo: `docker compose up -d`. Abrir el dashboard -> vista "Triaje" -> rellenar formulario grave (SpO2=88) -> verificar nivel rojo + reasons. Verificar que el paciente aparece en `GET /api/v1/patients?limit=500` con `triage` poblado. Repetir con medio y leve | CA-7 | T12 | S | done |
| T15 | Verificar CA-8 (RNF-3, dashboard API-only): `grep -rE "pymongo\|minio\|sqlite3\|sqlalchemy" src/dashboard/` debe devolver 0 ocurrencias | CA-8, RNF-3 | T11 | S | done |
| T16 | Documentacion viva: `CHANGELOG.md` entrada Added (endpoint POST /triage/patients + GET /triage/rules + vista dashboard); `docs/diario-ia.md` sesion nueva; `tasks/lessons.md` si hay aprendizaje nuevo; `tasks/backlog.md` anadir feature "Triaje de pacientes" como done; actualizar `README.md` (seccion "Ejemplos de uso de la API" con ejemplo curl del POST); referenciar en `docs/memoria-tecnica.md` si hay tiempo (cap 6 o nuevo cap si se decide) | — | T14, T15 | S | done |

Tamaños: S (< 1h) | M (1-4h) | L (> 4h, considerar dividir)
Estados: pending | in-progress | done | blocked

## Fases

### Fase 1 — Decision arquitectonica (sin `[US#]`) — completada

T1 (ADR-008) — `decisions/ADR-008-triaje-basado-en-reglas.md` creado
y aceptado el 2026-05-18. La fase de implementacion empieza
directamente en la Fase 2.

### Fase 2 — Foundational (sin `[US#]`)

T4 (schemas Pydantic) y T4b (`MongoWriter.insert_patient`) — bloquean
T5 en adelante. Son `[P]` entre si.

### Fase 3 — US-1 (P1) MVP: paciente grave (todas con `[US1]`)

T2 (test rojo) -> T3 (implementacion reglas) -> T5 (test endpoint
grave + variantes 422) -> T6 (router) -> verificacion grave funciona.

**Checkpoint:** un POST con SpO2=88 devuelve 201 con `level=grave`.
Si validas aqui, ya tienes el MVP entregable (sin dashboard, solo
API).

### Fase 4 — US-2 (P2): paciente medio (todas con `[US2]`)

T7 (test endpoint medio) → ya pasa porque T6 implementa todas las
reglas.

**Checkpoint:** POST con SpO2=93 devuelve 201 con `level=medio`.

### Fase 5 — US-3 (P3): paciente leve (todas con `[US3]`)

T8 (test endpoint leve) → ya pasa por T6.

**Checkpoint:** POST con todos los signos normales devuelve 201 con
`level=leve`.

### Fase 6 — Dashboard + tests adicionales (sin `[US#]`)

T9 (tests endpoint extra) → T10 (api_client) → T11 (vista) →
T12 (registro app.py) → T13 (E2E) → T14 (smoke real) → T15 (CA-8) →
T16 (docs).

## Reglas de paralelizacion

- `T1` y `T2` son `[P]`: si se aprueba ADR-008, T1 puede escribirse en
  paralelo con T2 sin bloquear.
- `T10` (api_client) es `[P]` respecto a `T7-T9` (tests del endpoint):
  el contrato HTTP esta fijado por la spec, no depende del orden.
- `T13` es `[P]` respecto a `T10-T12` (dashboard): los E2E API-only
  no necesitan el dashboard implementado.
- Dentro de la fase 3, las tareas siguen la secuencia TDD estricta:
  test rojo (T2, T5) antes que implementacion (T3, T6).

## Ruta critica

**T4 + T4b -> T2 -> T3 -> T5 -> T6 -> T11 -> T12 -> T14**

La ruta critica pasa por: schemas Pydantic + metodo `insert_patient`,
test rojo de reglas, implementacion de reglas, test del endpoint
grave, router, vista del dashboard, registro y smoke real.

## Estimacion total

| Fase | Tamaño | Tiempo |
|---|---|---|
| Fase 1 (ADR-008) | S | 30-60 min |
| Fase 2 (foundational) | S | 30 min |
| Fase 3 (US-1 MVP) | S+M+S+M | 4-6 h |
| Fase 4 (US-2) | S | 30-60 min |
| Fase 5 (US-3) | S | 30-60 min |
| Fase 6 (dashboard + cierre) | S+M+M+S+M+S+S+S | 6-8 h |

**Total estimado:** 12-17 horas. Tamaño feature: **M** (1-3 dias).

## Notas

- La regla TDD se aplica estrictamente: T2 antes que T3, T5 antes
  que T6. Cada test debe **fallar** primero (rojo) y pasar despues
  (verde).
- Las tareas del dashboard (T10-T12) se pueden hacer en paralelo con
  los tests E2E (T13) porque el contrato HTTP esta ya cerrado en T6.
- T1 (ADR-008) ya esta completada: el ADR se creo en la fase
  documental del 2026-05-18 con la justificacion de "reglas vs ML"
  conectada con la teoria del Master. Es la pregunta mas probable
  del profesor.
- T4b (`insert_patient`) anade un metodo nuevo a `MongoWriter` para
  garantizar que el alta manual usa `insert_one` y NUNCA hace upsert
  sobre un paciente existente.
