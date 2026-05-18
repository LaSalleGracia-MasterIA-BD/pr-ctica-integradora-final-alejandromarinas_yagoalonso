# Flujo SDD usado en el proyecto

Este documento describe el flujo de trabajo aplicado en las features principales.

## 1. `/spec`: definir el problema

La spec responde a la pregunta:

> Que hay que construir y como sabremos que esta bien?

Cada spec incluye, cuando aplica:

- contexto y problema;
- objetivo;
- actores y alcance;
- requisitos funcionales;
- requisitos no funcionales;
- casos borde y errores;
- dudas abiertas;
- criterios de aceptacion;
- changelog.

Ejemplos:

- `specs/pipeline-datos.md`
- `specs/clasificacion-radiografias.md`
- `specs/dashboard.md`

Regla aplicada:

> Si una duda afectaba al alcance o a la arquitectura, no se implementaba hasta cerrarla.

## 2. `/planificar`: convertir requisitos en diseno

El design responde a la pregunta:

> Como se va a construir tecnicamente lo definido en la spec?

Los documentos de `design/` incluyen:

- decision arquitectonica;
- componentes nuevos o modificados;
- contratos de datos/API;
- trazabilidad spec -> componentes;
- riesgos;
- plan de tests;
- decisiones que necesitan ADR.

Ejemplo claro:

```text
specs/dashboard.md
  -> design/dashboard.md
  -> decisions/ADR-007-dashboard-streamlit-imagen-independiente.md
```

## 3. `/tareas`: bajar el diseno a trabajo ejecutable

Las tareas responden a la pregunta:

> En que orden se implementa y que dependencias hay?

Cada documento de `tasks/` divide la feature en pasos pequenos:

- T1, T2, T3...
- tamano aproximado;
- dependencias;
- criterios de done;
- ruta critica.

Esto evita que una feature grande se implemente de golpe sin control.

Ejemplo:

```text
tasks/dashboard.md
```

divide el dashboard en endpoints API, infraestructura Docker, cliente API, componentes, vistas y cierre documental.

## 4. `/implementar`: codigo y pruebas

La implementacion se hizo despues de tener spec, design y tasks.

Ejemplos de correspondencia:

| Documento | Codigo |
|---|---|
| `tasks/pipeline-datos.md` | `src/pipeline/` |
| `tasks/clasificacion-radiografias.md` | `src/ml/`, `src/api/routers/classify.py` |
| `tasks/sqlite-pipeline-metadata.md` | `src/pipeline/storage/sql_*`, `src/api/sql_reader.py` |
| `tasks/dashboard.md` | `src/dashboard/`, `Dockerfile.dashboard` |

## 5. `/revisar`: validar contra la spec

La revision responde a la pregunta:

> Lo implementado cumple los criterios de aceptacion y no rompe decisiones previas?

Se uso:

- tests unitarios;
- tests de integracion;
- tests E2E;
- smoke tests del dashboard;
- revision tecnica del equipo;
- contraste contra specs, ADRs y criterios de aceptacion.

El proyecto termina con:

```text
275 tests verdes + 1 skip esperado
```

## Papel de la IA generativa

La IA se uso como herramienta de trabajo para acelerar:

- redaccion de specs;
- designs;
- tareas;
- codigo repetitivo;
- tests;
- documentacion;
- memoria y presentacion.

Pero el control del proceso lo daba SDD:

- la spec fijaba el alcance;
- el design justificaba la arquitectura;
- las tasks limitaban la implementacion;
- los tests validaban;
- los ADRs registraban decisiones;
- el diario IA documentaba el proceso.

La idea defendible es:

> La IA ayuda a producir, pero SDD obliga a ordenar, justificar y verificar.

