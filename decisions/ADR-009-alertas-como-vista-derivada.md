# ADR-009: Alertas operativas como vista derivada, no como estado persistido

> Estado: accepted
> Fecha: 2026-05-20
> Supersede: —
> Relacionado: specs/automatizacion-alertas.md, design/automatizacion-alertas.md,
> ADR-004 (polyglot persistence), ADR-008 (triaje basado en reglas)

## Contexto

La feature `automatizacion-alertas` (spec aprobada el 2026-05-20) anade
al sistema dos endpoints REST y una vista de dashboard que muestran
**alertas operativas**: runs del pipeline fallidos, snapshots de
calidad de datos por debajo de un umbral, y pacientes triajeados como
graves. El enunciado del proyecto pide explicitamente "alertas o
notificaciones ante fallos en el procesamiento (puede ser un log, un
email simulado o **una entrada en el dashboard**)".

Hay dos arquitecturas razonables para implementar esto:

- **A. Alertas como vista derivada (read-side calculado)**: las alertas
  se calculan al vuelo cada vez que el endpoint se llama, leyendo las
  fuentes existentes (`pipeline_runs`, `data_quality_summary`,
  `patients.triage`). Cero estado nuevo persistido. La salida es una
  funcion de las fuentes en ese momento.
- **B. Alertas como entidades persistidas**: tabla `alerts` nueva en
  SQLite (o coleccion en MongoDB) con `alert_id`, `type`, `severity`,
  `source`, `source_id`, `created_at`, `acknowledged_at`,
  `resolved_at`. Algun proceso (cron, hook tras escritura, etc.)
  inserta filas cuando se cumple la condicion. El endpoint devuelve la
  tabla.

El proyecto ya aplica una decision similar al modelar la persistencia
(ADR-004: cada dato vive donde su forma encaja, sin duplicar fuente de
verdad). Y el sistema de reglas del triaje (ADR-008) ya usa funciones
puras como elemento de calculo. Estos dos precedentes orientan la
decision actual.

## Decision

**Implementar las alertas como vista derivada (Opcion A): calculadas
al vuelo desde las fuentes existentes, sin tabla ni coleccion nueva.**

La logica vive como funcion pura `evaluate(state) -> list[Alert]` en
`src/api/alerts.py`, siguiendo el mismo patron que el sistema de
triaje (ADR-008). La funcion recibe tres listas de lecturas (runs
fallidos, snapshots de calidad, pacientes graves) y devuelve una lista
ordenada de objetos `Alert` con `type`, `severity`, `title`, `detail`,
`source`, `source_id`, `created_at`.

El endpoint HTTP `GET /api/v1/alerts` orquesta:

1. Leer `failed_runs`, `quality_snapshots`, `severe_triage_patients`
   desde los `Reader`s existentes con ventana temporal configurable.
2. Llamar a `evaluate(state, threshold)`.
3. Aplicar filtro opcional por `severity`.
4. Devolver JSON serializado.

**Cero tablas nuevas. Cero colecciones nuevas. Cero indices nuevos.**

## Conexion con la teoria del Master

Referencias **explicitas** del temario que justifican la solucion:

- **Sistemas basados en reglas** (Yuri, Modelos de IA — Sesion 07,
  carpeta `ruleBasedSystem/`): las alertas son reglas IF-THEN
  deterministas aplicadas a metricas operativas. Misma familia que el
  sistema de triaje (ADR-008), aplicada en otro contexto. La funcion
  `evaluate(state) -> list[Alert]` reproduce el patron del
  `ruleEngine.py` de la sesion 07.
- **Diseno de APIs con FastAPI + SQLAlchemy + SQLite** (Eric, Big Data
  — Bloque 7 `07-design-apis/`): los dos endpoints nuevos
  (`/api/v1/alerts` y `/api/v1/reports/daily`) siguen el mismo patron
  FastAPI + Pydantic que el resto de endpoints del proyecto, leyendo
  desde SQLite via SQLAlchemy.
- **Pipelines de datos y reportes** (Eric, Big Data — laboratorios de
  ETL): el informe diario es un reporte agregado del estado del
  pipeline, igual idea que las metricas de salida de los laboratorios
  de Spark/ETL del temario.

**Patron interno del proyecto** (no es teoria de clase, es como se ha
estructurado este sistema): separacion `Reader` / `Writer` por almacen
(`MongoReader`/`MongoWriter`, `SqlReader`/`SqlWriter`), establecida en
ADR-004. Las alertas son una **lectura**, asi que viven en el lado
`Reader` y consumen los `Reader`s existentes.

## Alternativas consideradas

| Opcion | Pros | Contras |
|--------|------|---------|
| **A. Vista derivada (elegida)** | Cero estado nuevo persistido. Cero codigo de mantenimiento (no hay que insertar filas, no hay que limpiar antiguas, no hay sincronizacion con las fuentes). Coherente con la filosofia API-only del proyecto (ADR-007) y con la separacion `Reader`/`Writer` interna del proyecto (ADR-004). Reglas como funcion pura -> tests triviales (mismo patron que ADR-008) | Sin histórico de alertas: si un run failed se "recupera" o sale de la ventana temporal, su alerta desaparece. Sin estado leida/no-leida. Cada peticion al endpoint recalcula |
| B. Persistir alertas en tabla SQL nueva | Permite histórico, auditoria temporal, estado leido/no-leido, contadores por dia | Anade superficie de estado nueva que mantener. Requiere mecanismo de insercion (hook, cron, observer) y de limpieza. Duplica informacion que ya esta en las fuentes (`pipeline_runs.error_message`, `triage.level`, ...). Fuera de alcance segun el enunciado |
| C. Persistir alertas en coleccion Mongo | Mismo histórico que B, pero en Mongo | Mismos contras que B. Ademas Mongo no es la base natural para datos tabulares como alertas (ver ADR-004: SQLite es el almacen tabular del proyecto) |
| D. Eventos en cola (Redis Streams, Kafka) | Modelo de eventos real, escalable | Requiere infraestructura nueva (cola), fuera del temario, fuera del alcance academico |
| E. No implementar | Cero esfuerzo | El enunciado lo pide explicitamente. Inaceptable |

## Consecuencias

**Positivas:**

- (+) **Cero superficie de estado nueva**: ninguna tabla, ninguna
  coleccion, ningun indice. Verificable con `git diff` sobre
  `src/pipeline/storage/sql_models.py` y
  `docker/mongo-init/init-db.js` tras la implementacion.
- (+) **Reglas como funcion pura**: tests unitarios triviales,
  reutilizando el patron ya validado por ADR-008.
- (+) **Coherente con la arquitectura ya existente**: usa los
  `Reader`s del proyecto, mantiene la separacion lectura/escritura
  interna ya consolidada (ADR-004), dashboard sigue API-only
  (ADR-007).
- (+) **Misma filosofia que el triaje**: el proyecto contiene ahora
  dos sistemas basados en reglas (triaje clinico + alertas operativas)
  + un sistema aprendido (clasificador de radiografias). Esto ilustra
  los dos paradigmas del Master con un caso de uso para cada uno.
- (+) **Reproducible y deterministico**: a igualdad de estado del
  sistema y de configuracion (`ALERT_REJECTION_RATE_THRESHOLD`,
  `ALERT_WINDOW_HOURS`), el endpoint devuelve siempre el mismo JSON.
  Mismo principio se aplica al script `daily_report.py` (RNF-6).
- (+) **Sin coste de mantenimiento**: no hay que escribir codigo de
  insercion, ni de limpieza, ni de sincronizacion entre las fuentes y
  la "tabla de alertas".

**Negativas:**

- (-) **Sin histórico**: si un evento sale de la ventana temporal o se
  resuelve, la alerta desaparece. Para auditoria a posteriori
  ("¿cuantas alertas critical hubo el mes pasado?") habria que
  reabrir la decision.
- (-) **Sin estado "leida"**: dos operadores leen las mismas alertas
  sin distincion. Para entorno multi-operador real habria que
  persistir el estado.
- (-) **Re-calculo en cada peticion**: cada `GET /alerts` hace 3
  queries. En el dataset academico actual es trivial (<100 ms);
  en produccion con millones de eventos seria un problema. La
  mitigacion (cache del endpoint con TTL corto) ya esta en el
  dashboard (`st.cache_data(ttl=10s)`) pero la API responde sin
  cache.

**Neutras:**

- Coste de implementacion: similar al de una tabla con eventos
  insertados — el calculo es simple. La diferencia esta en el coste
  de **mantenimiento a largo plazo**, no de implementacion inicial.

## Requisitos relacionados

- **Spec `automatizacion-alertas`:** RF-1, RF-2, RF-3 (endpoint
  /alerts), RNF-3 (cero estado nuevo), RNF-5 (funcion pura).
- **ADR-004:** polyglot persistence — esta decision encaja en el
  mismo principio (cada cosa vive donde mejor encaja; las alertas
  son una vista, no un dato persistente).
- **ADR-007:** dashboard API-only — la vista "Alertas" del dashboard
  cumple esto.
- **ADR-008:** triaje basado en reglas — mismo patron de funcion pura
  `evaluate(payload) -> result`.

## Notas

Si en una iteracion futura el proyecto necesita:

- **Histórico de alertas** (auditoria temporal, "¿cuantas critical
  hubo el mes pasado?"), o
- **Estado leida/no-leida** (entorno multi-operador), o
- **Acknowledgment + resolucion** (workflow operativo real),

se reabre esta decision con un ADR posterior que proponga una tabla
`alerts` en SQLite con esquema:

```sql
CREATE TABLE alerts (
    id              VARCHAR(36) PRIMARY KEY,    -- UUID v4
    type            VARCHAR(50) NOT NULL,
    severity        VARCHAR(20) NOT NULL,
    title           TEXT NOT NULL,
    detail          TEXT,
    source          VARCHAR(50) NOT NULL,
    source_id       VARCHAR(100),
    raised_at       DATETIME NOT NULL,
    acknowledged_at DATETIME,
    resolved_at     DATETIME
);
```

El endpoint `/api/v1/alerts` migraria a leer de ahi, con la misma
firma HTTP. La logica de calculo (`evaluate`) seguiria viviendo como
funcion pura, y el cambio seria mover el punto donde se invoca:
ahora vive en el router; entonces viviria en un componente que se
ejecuta tras cada cambio relevante (hook del orchestrator, del
endpoint de triaje, etc.) e inserta filas en la tabla. La
**funcion `evaluate` se mantiene tal cual**: ese es el valor de
diseno de tener las reglas separadas del IO.
