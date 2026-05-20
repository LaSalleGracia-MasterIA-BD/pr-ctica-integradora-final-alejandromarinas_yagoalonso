# Spec: Pipeline de datos hospitalario

> Estado: approved
> Ultima actualizacion: 2026-04-14

## Contexto y problema
El hospital laSalle Health Center genera grandes volumenes de datos (historiales clinicos, registros de pacientes, radiografias, logs). Actualmente no tiene herramientas para procesarlos de forma sistematica. Se necesita un pipeline que ingeste, limpie, transforme y sirva estos datos para su consumo por el modelo de IA, el dashboard y la API.

## Objetivo
Disenar e implementar un pipeline de datos completo que cubra ingesta, almacenamiento, procesamiento y servicio, utilizando PySpark como framework de procesamiento distribuido. El pipeline debe estar disenado para escalar, aunque trabaje con volumen simulado.

## Actores y alcance
- **Usuarios:** Equipo medico (consume resultados), equipo tecnico (opera el pipeline), modelo de ML (consume datos procesados)
- **Dentro del alcance:**
  - Ingesta automatizada de datos (CSVs de pacientes, radiografias, logs)
  - Almacenamiento dual: MongoDB (datos clinicos) + MinIO (imagenes)
  - Procesamiento con PySpark (limpieza, transformacion, validacion)
  - Servicio de datos procesados via API REST
  - Validacion de calidad de datos
- **Fuera del alcance:**
  - Streaming en tiempo real (se trabaja en batch)
  - Integracion con sistemas HIS/HL7 reales del hospital
  - Datos reales de pacientes (todo simulado)

## Requisitos funcionales
- **RF-1:** El pipeline debe ingestar ficheros CSV con datos de pacientes (demograficos, diagnosticos, ingresos) desde un directorio de entrada o endpoint
- **RF-2:** El pipeline debe ingestar imagenes de radiografias (PNG) y almacenarlas en MinIO con metadatos asociados
- **RF-3:** El pipeline debe limpiar datos: detectar y manejar valores nulos, duplicados, formatos inconsistentes
- **RF-4:** El pipeline debe transformar los datos con PySpark: normalizacion, agregaciones, enriquecimiento de registros
- **RF-5:** Los datos estructurados procesados deben persistirse en MongoDB
- **RF-6:** Los datos procesados deben estar disponibles para consumo via API REST
- **RF-7:** El pipeline debe poder ejecutarse de forma automatizada (no requiere intervencion manual para procesar nuevos datos)

## Requisitos no funcionales
- **RNF-1:** El pipeline debe ejecutarse completamente dentro de contenedores Docker
- **RNF-2:** El procesamiento con PySpark debe estar disenado para escalar horizontalmente (aunque se ejecute en modo local)
- **RNF-3:** El pipeline debe completar el procesamiento del dataset simulado (~5000 registros + ~21000 imagenes) en menos de 10 minutos en un equipo con 16GB RAM
- **RNF-4:** Cada fase del pipeline debe generar logs que permitan trazar el procesamiento

## Casos borde y errores
- **CB-1:** Un CSV de entrada tiene columnas faltantes o en orden distinto al esperado
- **CB-2:** Una imagen de radiografia esta corrupta o en formato no soportado
- **CB-3:** Un registro de paciente tiene campos obligatorios vacios (nombre, ID)
- **CB-4:** Se intenta ingestar un fichero que ya fue procesado previamente (duplicado)
- **CB-5:** La conexion con MongoDB o MinIO no esta disponible al iniciar el pipeline

## Dudas abiertas
- ~~¿Generamos los datos simulados de pacientes (CSVs) nosotros mismos con un script, o usamos algun dataset publico de datos clinicos?~~ **RESUELTO:** Los generamos nosotros con un script (faker o similar)
- ~~¿El pipeline se ejecuta on-demand (manual trigger) o con un scheduler?~~ **RESUELTO:** Ambos — endpoint para trigger manual + watcher automatico que detecte ficheros nuevos

## Criterios de aceptacion
- [ ] **CA-1** (RF-1): Al colocar un CSV en el directorio de entrada, el pipeline lo procesa y los datos aparecen en MongoDB
- [ ] **CA-2** (RF-2): Al colocar imagenes PNG en el directorio de entrada, se almacenan en MinIO con sus metadatos
- [ ] **CA-3** (RF-3, CB-1, CB-3): Registros con valores nulos en campos obligatorios se marcan como rechazados con motivo, no rompen el pipeline
- [ ] **CA-4** (RF-4): Los datos en MongoDB estan normalizados y enriquecidos (ej: edad calculada desde fecha de nacimiento, categorias estandarizadas)
- [ ] **CA-5** (RF-5, RF-6): Los datos procesados son consultables via endpoint GET de la API
- [ ] **CA-6** (RF-7, CB-4): Ejecutar el pipeline dos veces con los mismos datos no genera duplicados
- [ ] **CA-7** (RNF-1): Todo el pipeline arranca con `docker-compose up`
- [ ] **CA-8** (RNF-4, CB-5): Si MinIO o MongoDB no estan disponibles, el pipeline loguea el error y no crashea silenciosamente

## Changelog
| Fecha | Cambio | Motivo | Fase |
|-------|--------|--------|------|
| 2026-04-14 | Creacion inicial | Arranque del proyecto | spec |
| 2026-04-14 | Dudas cerradas, spec aprobada | Alejandro confirma: datos generados + trigger dual | spec |
| 2026-04-14 | PostgreSQL reemplazado por MongoDB | PostgreSQL aparece en el enunciado como ejemplo (no como obligacion); la jerarquia paciente -> admisiones -> radiografias encaja mejor en documental. Ver ADR-002 | spec/design |
