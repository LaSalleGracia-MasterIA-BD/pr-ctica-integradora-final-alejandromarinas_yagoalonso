# SDD del proyecto

Esta carpeta resume como se ha aplicado **SDD (Spec-Driven Development)** en el proyecto. No sustituye a `specs/`, `design/`, `tasks/` ni `decisions/`: funciona como indice explicativo para revisar el metodo de trabajo de forma rapida.

## Idea principal

El proyecto no se ha desarrollado empezando directamente por codigo. Las features grandes han seguido este flujo:

```text
/spec  ->  /planificar  ->  /tareas  ->  /implementar  ->  /revisar
 QUE         COMO          EN QUE        CODIGO          CUMPLE?
                           ORDEN
```

La regla de trabajo ha sido:

> Antes de implementar una feature relevante, tenia que existir una especificacion revisable, un diseno tecnico, una lista de tareas y criterios de aceptacion verificables.

## Artefactos principales

| Carpeta | Papel dentro del SDD | Ejemplo |
|---|---|---|
| `specs/` | Define que se quiere construir: requisitos, restricciones, casos borde y criterios de aceptacion | `specs/dashboard.md` |
| `design/` | Explica como se construye: arquitectura, componentes, contratos, riesgos y plan de tests | `design/dashboard.md` |
| `tasks/` | Divide el trabajo en tareas pequenas con dependencias y criterio de done | `tasks/dashboard.md` |
| `decisions/` | Guarda ADRs: decisiones tecnicas, alternativas descartadas y consecuencias | `decisions/ADR-007-dashboard-streamlit-imagen-independiente.md` |
| `src/` | Implementacion final | `src/dashboard/` |
| `tests/` | Verificacion automatica por capas | `tests/dashboard/`, `tests/e2e/` |
| `docs/diario-ia.md` | Diario de sesiones y reflexion sobre el uso de IA generativa | `docs/diario-ia.md` |
| `tasks/lessons.md` | Lecciones aprendidas y reglas de trabajo que se fueron incorporando | `tasks/lessons.md` |

## Features trabajadas con SDD completo

| Feature | Spec | Design | Tasks | ADRs principales |
|---|---|---|---|---|
| Pipeline de datos | `specs/pipeline-datos.md` | `design/pipeline-datos.md` | `tasks/pipeline-datos.md` | ADR-001, ADR-002 |
| Metadatos SQL del pipeline | `specs/sqlite-pipeline-metadata.md` | `design/sqlite-pipeline-metadata.md` | `tasks/sqlite-pipeline-metadata.md` | ADR-004 |
| Clasificacion de radiografias | `specs/clasificacion-radiografias.md` | `design/clasificacion-radiografias.md` | `tasks/clasificacion-radiografias.md` | ADR-003, ADR-005, ADR-006 |
| Dashboard | `specs/dashboard.md` | `design/dashboard.md` | `tasks/dashboard.md` | ADR-007 |

## Cifras de referencia

| Indicador | Valor |
|---|---:|
| Specs aprobadas | 4 |
| ADRs documentadas | 7 |
| Sesiones en el diario IA | 28 |
| Lecciones registradas | 57 |
| Tests verdes | 275 |

## Como revisar el SDD en 3 minutos

1. Abrir `tasks/backlog.md` para ver el mapa de features.
2. Abrir una feature completa, por ejemplo dashboard:
   - `specs/dashboard.md`
   - `design/dashboard.md`
   - `tasks/dashboard.md`
   - `decisions/ADR-007-dashboard-streamlit-imagen-independiente.md`
   - `src/dashboard/`
   - `tests/dashboard/`
3. Comprobar que la cadena existe:

```text
requisito -> diseno -> tarea -> codigo -> test/evidencia
```

## Documentos de esta carpeta

- `flujo.md`: explica como funciona el flujo SDD usado (las cinco fases).
- `trazabilidad.md`: matriz de trazabilidad desde features hasta codigo y tests.
- `agentes-y-herramientas.md`: skills aplicadas (`/spec`, `/planificar`, `/tareas`, `/implementar`, `/revisar`), templates instanciados, roles cubiertos, plugins usados (context7), reglas operativas y lo que se decidio no usar.

