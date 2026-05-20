# ADR-008: Triaje basado en reglas explicitas, no en un modelo de Machine Learning

> Estado: accepted
> Fecha: 2026-05-18
> Supersede: —
> Relacionado: specs/triage-pacientes.md, design/triage-pacientes.md

## Contexto

La feature `triage-pacientes` (spec aprobada el 2026-05-18) anade al
sistema la capacidad de **dar de alta a un paciente nuevo** desde el
dashboard introduciendo signos vitales y sintomas, y obtener un nivel
de prioridad **grave / medio / leve**.

Hay dos vias razonables para asignar ese nivel:

- **A. Sistema basado en reglas explicitas** (reglas de produccion):
  un conjunto de condiciones IF-THEN sobre los signos vitales que
  derivan el nivel.
- **B. Modelo de Machine Learning supervisado** entrenado con datos
  etiquetados con la severidad `grave | medio | leve`.

El proyecto debe encajar con la **teoria de Modelos de IA vista en el
Master**, no con estandares clinicos externos. El Master presenta los
sistemas basados en reglas como una alternativa legitima a los modelos
aprendidos cuando faltan condiciones para aprendizaje supervisado
(falta de datos etiquetados, requerimiento de trazabilidad,
auditabilidad, etc.).

Condiciones actuales del proyecto:

- El dataset de pacientes generado por Faker
  (`data/raw/patients.csv`) **no contiene** una etiqueta de
  severidad clinica. Las columnas son demograficas y de admisiones, no
  hay signos vitales ni un label `grave/medio/leve`.
- El COVID-19 Radiography Database (Kaggle) etiqueta imagenes en
  Normal/Pneumonia/COVID-19, **no** severidad del paciente.
- No se planea recolectar un dataset clinico real con permisos para
  este proyecto. El alcance es academico.

## Decision

**Implementar el triaje como un sistema basado en reglas explicitas
(reglas de produccion academicas), NO como un modelo de Machine
Learning.**

La logica vive como funcion pura `evaluate(payload) -> TriageResult`
en `src/api/triage.py`. Las reglas son condiciones IF-THEN
deterministas sobre los signos vitales y los sintomas (detalladas en
`specs/triage-pacientes.md` RF-5 y `design/triage-pacientes.md`):

- el nivel **grave** se asigna si alguno de los signos vitales cruza
  un umbral critico (p. ej. SpO2 < 92, FR > 30) o si esta presente un
  sintoma critico (`alteracion_conciencia`, `dolor_toracico_fuerte`);
- el nivel **medio** se asigna si NO grave y alguno de los signos
  vitales esta en una franja intermedia o aplica una regla combinada
  (edad >= 70 + sintoma respiratorio);
- el nivel **leve** es el caso por defecto cuando ninguna regla
  dispara.

Los umbrales son **valores academicos simplificados** elegidos para
que las tres clases queden representadas con casos verosimiles. No
implementan ningun protocolo medico real ni estan validados
clinicamente.

Cada decision se acompaña de una lista de `reasons` con
identificadores estables (`spo2_lt_92`, `fr_gt_30`, etc.) que permiten
auditar **por que** un paciente fue clasificado como esta — propiedad
ausente por construccion en un modelo entrenado sobre datos sin
etiquetar.

## Alternativas consideradas

| Opcion | Pros | Contras |
|--------|------|---------|
| **A. Sistema basado en reglas (elegida)** | Encaja con la teoria del Master sobre reglas de produccion. Auditable: cada decision lleva sus `reasons`. Deterministico y reproducible. Cero coste en datos: no requiere dataset etiquetado. Tests unitarios triviales (funcion pura). Defendible academicamente sin necesidad de citar protocolos externos | Los umbrales son una eleccion del equipo, no aprendida de datos. Riesgo de tono medico si no se documenta claramente que es asistencia, no diagnostico |
| B. Modelo ML supervisado | Si hubiera dataset etiquetado, podria capturar correlaciones no triviales. Permite escalar a mas variables sin reescribir reglas | NO hay dataset etiquetado con severidad disponible. Entrenar sobre datos sinteticos etiquetados por el equipo seria inventar ground truth. Modelo opaco: explicar por que clasifica grave requiere XAI adicional. Coste de tiempo alto para una entrega academica donde la prioridad es la coherencia del sistema completo |
| C. Heuristica numerica (score) sin reglas explicitas | Compacto: un solo numero | Pierde trazabilidad: no se ve por que un paciente cae en grave. Menos defendible academicamente que reglas IF-THEN explicitas |
| D. No implementar la feature | Cero esfuerzo | El profesor pidio explicitamente la funcionalidad de triaje |

## Conexion con la teoria del Master

El bloque del Master sobre Modelos de IA presenta dos familias de
sistemas:

- **Modelos aprendidos**: aprenden parametros desde datos etiquetados
  (lo que el proyecto aplica al clasificador de radiografias, ADR-005).
- **Sistemas basados en reglas / reglas de produccion**: un conjunto
  de condiciones explicitas escritas por un experto del dominio.
  Defendibles cuando faltan datos etiquetados o se prioriza la
  trazabilidad sobre la capacidad predictiva fina.

La eleccion para esta feature es la segunda familia, aplicada como
ejercicio academico sobre signos vitales y sintomas. El proyecto
contiene asi **ambos paradigmas**: ML para radiografias (donde si hay
dataset etiquetado) y reglas para triaje (donde no lo hay).

## Consecuencias

**Positivas:**

- (+) **Defendible academicamente** sin recurrir a estandares clinicos
  externos: la eleccion se justifica desde la teoria del Master.
- (+) **Trazabilidad**: el campo `triage.reasons` lista las reglas
  disparadas. Reproducir manualmente la decision es trivial.
- (+) **Cero coste en datos**: no hace falta dataset etiquetado.
- (+) **Tests faciles**: funcion pura, una clase de tests por nivel
  + casos borde (SpO2=91/92/94/95, etc.).
- (+) **Coherencia con el resto del proyecto**: el clasificador de
  radiografias usa ML por que SI hay dataset etiquetado; el triaje
  usa reglas por que NO lo hay. La eleccion se basa en la
  disponibilidad de supervision, no en la moda del paradigma.
- (+) **Tono etico controlado**: el sistema es asistencia al triaje,
  no diagnostico medico vinculante. Los reasons hacen visible que la
  decision es un calculo determinista, no una "intuicion" del modelo.

**Negativas:**

- (-) Los umbrales son **academicos simplificados**, no validados
  clinicamente. Cualquier despliegue real requeriria revisar los
  umbrales con personal sanitario y, probablemente, una capa de
  modelos aprendidos sobre datos reales.
- (-) Las reglas no capturan correlaciones complejas entre signos
  vitales (p. ej. interaccion entre temperatura, FR y saturacion).
  Aceptable para el alcance academico.
- (-) Riesgo de percepcion medica indebida si el usuario interpreta
  el resultado como diagnostico. **Mitigacion**: banner explicito en
  la UI ("asistencia al triaje, no diagnostico ni decision medica
  vinculante"), `source: manual_triage` en el documento Mongo,
  `reasons` visibles en el dashboard.

**Neutras:**

- Las reglas viven hardcoded en `src/api/triage.py`. Si en una
  iteracion futura se quieren cambiar sin redeploy, se podrian mover a
  un fichero de configuracion JSON con `rules_version`. YAGNI para
  esta entrega.

## Requisitos relacionados

- **Spec `triage-pacientes`:** RF-5 (reglas), RF-8 (endpoint
  `/rules`), RNF-2 (deterministas y trazables), RNF-5 (testeable sin
  Mongo).
- **Spec `clasificacion-radiografias`:** RNF-2 (criterio clinico
  cualitativo, no umbral bloqueante) — la posicion etica del proyecto
  para asistencia ≠ diagnostico se mantiene en ambas features.
- **ADR-005:** CNN custom desde cero para radiografias (paradigma ML
  cuando SI hay dataset etiquetado). Este ADR-008 cubre el paradigma
  complementario cuando NO lo hay.

## Notas

Si en una iteracion futura del proyecto:

- aparece un dataset etiquetado con severidad real, o
- se recogen suficientes triajes manuales como para etiquetar y
  reentrenar,

se puede reabrir esta decision con un ADR posterior que proponga un
modelo aprendido como **complemento** (no sustituto) del sistema de
reglas. Manteniendo las reglas como capa explicable y el ML como
indicador adicional, se evitaria perder la trazabilidad que aporta el
campo `reasons`.
