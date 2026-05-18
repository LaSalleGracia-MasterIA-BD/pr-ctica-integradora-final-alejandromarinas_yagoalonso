# Skills, plugins y roles aplicados

Este documento detalla qué piezas concretas del kit SDD se han utilizado en
el proyecto, qué papel ha jugado cada una y qué se ha decidido **no** usar.
Sirve para que cualquier persona que revise el repositorio entienda no solo
el resultado, sino también el método y las herramientas que lo han hecho
posible.

## 1. Skills aplicadas (fases del SDD)

El SDD divide el desarrollo en cinco fases. Cada fase produce un artefacto
revisable antes de pasar a la siguiente. En este proyecto se han aplicado
las cinco a las features grandes.

| Fase | Pregunta que responde | Artefacto producido | Aplicada en |
|---|---|---|---|
| `/spec` | ¿Qué hay que construir y cómo sabremos que está bien? | `specs/<feature>.md` con RF, RNF, casos borde y criterios de aceptación | Las 4 features grandes |
| `/planificar` | ¿Cómo se va a construir técnicamente? | `design/<feature>.md` + ADRs cuando hay decisiones técnicas no triviales | Las 4 features grandes |
| `/tareas` | ¿En qué orden y con qué dependencias? | `tasks/<feature>.md` con descomposición S/M/L | Las 4 features grandes |
| `/implementar` | Código + tests siguiendo el plan | Código en `src/` + tests en `tests/` | Las 4 features grandes |
| `/revisar` | ¿Cumple los criterios de aceptación? | Matriz de trazabilidad + tests verdes | Las 4 features grandes |

A estas cinco fases se ha sumado, de forma transversal:

- **`/retomar`** al inicio de varias sesiones, para recuperar contexto
  leyendo `progress/current.md`, `tasks/lessons.md` y las specs/designs
  aprobadas. Evita que cada sesión empiece desde cero.
- **`/auditoria`** en espíritu (no como flujo formal con ficheros
  versionados): las features grandes se sometieron a revisión técnica del
  equipo y contraste contra la spec durante el desarrollo, y los hallazgos
  relevantes se incorporaron como cambios de código y como entradas en
  `tasks/lessons.md`. La auditoría interna del pipeline al cerrar T10 es
  el ejemplo con mayor impacto: detectó cuatro bloqueantes y queda
  reflejada en `CHANGELOG.md`.

## 2. Templates instanciados

El kit SDD propone una serie de plantillas. Las que se han instanciado en
el repo:

| Plantilla | Instanciada como | Una vez o por feature |
|---|---|---|
| `spec.md` | `specs/{pipeline-datos, sqlite-pipeline-metadata, clasificacion-radiografias, dashboard}.md` | Por feature (4) |
| `design.md` | `design/{...}.md` | Por feature (4) |
| `tasks.md` | `tasks/{...}.md` | Por feature (4) |
| `adr.md` | `decisions/ADR-001..ADR-007.md` | Por decisión técnica (7) |
| `backlog.md` | `tasks/backlog.md` | Una vez |
| `lessons.md` | `tasks/lessons.md` | Una vez (vivo, 57 entradas) |
| `diario-ia.md` | `docs/diario-ia.md` | Una vez (vivo, 28 sesiones) |
| `runbook.md` | `docs/runbooks/{download-radiography-dataset, use-real-radiograph-for-demo, presentation-demo}.md` | 3 procedimientos |
| `memoria-tecnica.md` | `docs/memoria-tecnica.md` | Una vez, al cierre (17 caps) |
| `progress-current.md` / `progress-history.md` | `progress/current.md` / `progress/history.md` | Una vez (vivo + append-only) |
| `changelog.md` | `CHANGELOG.md` | Una vez (vivo) |

## 3. Roles del SDD cubiertos

El SDD distingue conceptualmente tres roles principales en el desarrollo
de cualquier feature: arquitecto, implementador y revisor. En este
proyecto se han cubierto los tres a través de las skills correspondientes,
sin necesidad de instanciar subagentes separados.

| Rol | Cubierto por | Función en este proyecto |
|---|---|---|
| Arquitecto | `/planificar` + ADRs | Decidir arquitectura, contratos y trade-offs antes de tocar código (ADR-001 a ADR-007) |
| Implementador | `/implementar` | Convertir las tareas en código y tests sin alterar la decisión arquitectónica |
| Revisor | `/revisar` + revisión técnica del equipo | Verificar criterios de aceptación, mantener trazabilidad y registrar lecciones |

## 4. Plugins y herramientas externas usadas

- **context7** (consulta de documentación de librerías externas) —
  activado automáticamente al implementar features que dependen de APIs
  externas con versiones recientes (Streamlit 1.39, FastAPI, Keras/TF
  2.16, PySpark 3.5.1, Plotly, SQLAlchemy 2.0). No produce artefactos en
  el repo; su efecto queda implícito en la coherencia del código con la
  API oficial de cada librería.
- **Editor con soporte Markdown** para revisar specs, designs, tasks y
  ADRs sin renderizar a PDF.
- **Docker Compose** como entorno reproducible: un único comando levanta
  todo el sistema y permite verificar criterios de aceptación E2E.

## 5. Reglas operativas aplicadas

Más allá de las skills, el SDD impone una serie de reglas que se han
respetado durante todo el desarrollo:

- **Trazabilidad obligatoria**: cada requisito tiene un ID (`RF-1`,
  `RNF-1`, `CB-1`, `CA-1`) que se referencia desde el design, las tareas
  y los tests. Ningún componente se ha implementado sin estar atado a un
  requisito de una spec aprobada.
- **Dudas como bloqueantes**: cualquier ambigüedad detectada en una spec
  se marca como `[NEEDS CLARIFICATION]` y bloquea el avance hasta su
  cierre. Solo en la spec del dashboard se cerraron seis dudas antes de
  pasar a `/planificar`.
- **ADRs en el momento de tomar la decisión**: no a posteriori. Cada ADR
  documenta el contexto, las alternativas consideradas, la elección y
  sus consecuencias. Si una decisión cambia, se crea un ADR nuevo que
  supersede al anterior (ADR-003 supersede parcial de ADR-001).
- **Spec viva con changelog**: cualquier cambio post-aprobación se
  registra en la tabla "Changelog" al final de la spec, con fecha,
  cambio, motivo y fase.
- **Gates entre fases**: no se pasa a la siguiente fase sin aprobación
  explícita. El diario IA registra esos puntos de aprobación.
- **Criterios de aceptación observables**: cada CA es verificable con
  un comando concreto (`docker compose up`, `curl ...`, `pytest ...`)
  o por inspección documental (en el caso del análisis clínico
  cualitativo del modelo).
- **Documentos vivos vs históricos**: `progress/current.md` se vacía al
  cerrar cada sesión; `progress/history.md` es append-only; `lessons.md`
  y `diario-ia.md` viven durante todo el proyecto.
- **Conventional Commits en castellano**: `feat:`, `fix:`, `docs:`,
  `refactor:`, `test:`, `chore:`. Permite leer el historial de un vistazo.
- **Verificar antes de afirmar**: cualquier afirmación sobre cifras,
  ficheros o estado del repo debe confirmarse con un comando antes de
  escribirla. Una violación de esta regla quedó registrada como lección
  en la sesión 28 del diario.

## 6. Lo que NO se ha usado y por qué

Para que el cuadro sea honesto, conviene documentar también lo que el
SDD ofrece y no se ha empleado en este proyecto:

| Mecanismo del SDD | Estado en este proyecto | Motivo |
|---|---|---|
| Subagentes propios (`architect`, `implementer`, `reviewer`) como entidades separadas | No instanciados | El flujo de skills cubre los roles. Para un proyecto académico de tamaño contenido, instanciar subagentes separados añadiría complejidad sin valor proporcional |
| Agent Teams (3-5 asistentes paralelos con ownership de archivos) | No usado | Las features se desarrollaron de forma lineal (una a una) con dependencias entre ellas. Agent Teams encajaría mejor en features cross-layer independientes |
| Flujo formal `/auditoria` con ficheros de auditoría versionados | No aplicado en su forma documental | Las revisiones cruzadas se hicieron conversacionales y sus conclusiones se incorporaron al código y a `tasks/lessons.md`. No se preservaron ficheros de auditoría versionados |
| `init.sh` como script de validación pre-sesión | No creado | El `docker compose up` con healthchecks cumple funcionalmente la validación del entorno |

## 7. Resumen defendible

> El SDD ha aportado el orden y la trazabilidad. Las skills `/spec`,
> `/planificar`, `/tareas`, `/implementar` y `/revisar` se han usado en
> las cuatro features grandes. Los templates del kit se han instanciado
> como specs, designs, tasks, ADRs, runbooks, memoria, diario y backlog,
> todos versionados. Los roles de arquitecto, implementador y revisor se
> han cubierto vía las skills, sin necesidad de subagentes separados.
> Las reglas operativas (trazabilidad, dudas bloqueantes, ADRs en el
> momento, gates entre fases) se han respetado durante todo el desarrollo.
