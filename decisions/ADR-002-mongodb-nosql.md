# ADR-002: MongoDB como base de datos principal en lugar de PostgreSQL

> Estado: accepted
> Fecha: 2026-04-14

## Contexto

El enunciado pide explicitamente "uso combinado de al menos dos tipos
de almacenamiento" y pone como ejemplo "PostgreSQL para datos
estructurados + MinIO/S3 o MongoDB...". PostgreSQL aparece como
**ejemplo**, no como obligacion: el enunciado deja a criterio del
equipo que combinacion concreta de almacenes usar mientras sean al
menos dos y encajen con los datos del proyecto.

Los datos clinicos del hospital (pacientes con sus ingresos y los
metadatos de sus radiografias) tienen una jerarquia natural
**paciente -> admisiones -> radiografias** y campos semi-estructurados
(p. ej. el `raw_data` de los registros rechazados, que tiene forma
distinta segun el motivo de rechazo). Esta forma encaja mejor con un
modelo documental que con tablas relacionales con joins.

## Decision

Usar **MongoDB** como base de datos principal para los datos clinicos
del proyecto. MinIO se mantiene para el almacenamiento de imagenes
PNG. La combinacion MongoDB + MinIO ya cumple por si sola el requisito
de "al menos dos tipos de almacenamiento". Posteriormente, en ADR-004,
se anade SQLite + SQLAlchemy como tercer almacen para los metadatos
estructurados del pipeline (auditoria de runs y agregados de calidad),
alineado con lo que enseña Eric en el Bloque 7 del Master.

## Alternativas consideradas

| Opcion | Pros | Contras |
|--------|------|---------|
| MongoDB (elegida) | Documentos JSON encajan con la jerarquia paciente -> admisiones -> radiografias y con los `raw_data` heterogeneos. Una sola BBDD para todos los datos clinicos. Consultable como JSON directamente, util para la demo | Menos familiar para el equipo al inicio, sin joins nativos |
| PostgreSQL (descartada) | Familiar, ACID completo, SQL estandar | Requeriria joins entre patients, admissions y radiographies. El payload heterogeneo de `rejected_records.raw_data` no encaja bien con un schema fijo |
| PostgreSQL + MongoDB (ambas) | Cubre ambos paradigmas | Dos BBDD que mantener sin una razon clara que lo justifique para el alcance del proyecto |

## Consecuencias

- (+) El modelo embebido (admisiones y metadatos de radiografias dentro
  del documento del paciente) evita joins y refleja la jerarquia
  natural de los datos.
- (+) Cumple el requisito del enunciado ("al menos dos tipos de
  almacenamiento") combinandose con MinIO desde el primer dia.
- (+) Mas sencillo de demostrar en la presentacion: los datos se
  inspeccionan directamente como JSON.
- (+) Permite que `rejected_records` guarde el `raw_data` original
  con la forma que tenga cada motivo de rechazo, sin tener que
  forzarlo a un schema relacional fijo.
- (-) Sin transacciones ACID tan robustas como en PostgreSQL.
  Aceptable para este proyecto: los datos son sinteticos y el
  pipeline no requiere multi-document transactions.

## Requisitos relacionados

- RF-5: Persistencia de datos procesados.
- Pipeline de datos a escala (almacenamiento).
- Requisito del enunciado: uso combinado de al menos dos tipos de
  almacenamiento.
