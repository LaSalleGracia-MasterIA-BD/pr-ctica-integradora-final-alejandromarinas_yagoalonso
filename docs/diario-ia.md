# Diario de Desarrollo con IA

## Herramientas utilizadas

| Herramienta | Uso principal | Justificacion de la eleccion |
|-------------|--------------|------------------------------|
| Claude Code (CLI) | Desarrollo asistido, arquitectura, specs, implementacion | Integracion directa con terminal, workflow SDD nativo, capacidad multimodal (lectura de PDFs), gestion de git integrada |

## Sesiones de desarrollo

### Sesion 1 — 2026-04-14: Arranque del proyecto
- **Objetivo:** Leer enunciado, organizar estructura del proyecto, definir backlog
- **Prompts representativos:**
  - "Voy a empezar el proyecto de final de curso. He dejado en esta carpeta un pdf con toda la info del proyecto, hago el proyecto con Yago, un compañero. Empezamos a organizar todo?"
- **Resultado:** Estructura SDD completa, backlog con 10 features identificadas, CLAUDE.md del proyecto, scaffolding de carpetas
- **Aciertos de la IA:**
  - Lectura del PDF y extraccion estructurada de requisitos del enunciado
  - Scaffolding automatico de toda la estructura SDD
  - Deteccion del dataset adecuado (COVID-19 Radiography Database de Kaggle)
- **Iteraciones necesarias:** Ninguna

### Sesion 2 — 2026-04-14: Spec + Design + Tasks del pipeline
- **Objetivo:** Redactar spec, design y tasks del pipeline de datos (primera feature del backlog)
- **Prompts representativos:**
  - "Avanza con la spec del pipeline"
  - "Apruebo, pasa al design"
  - "Apruebo, descompon en tareas"
- **Resultado:**
  - Spec con 7 RF + 4 RNF + 5 casos borde + 8 criterios de aceptacion
  - Design con 11 componentes y trazabilidad spec → componentes → archivos
  - 12 tareas con dependencias y tamanos estimados
  - ADR-001 con eleccion de stack (PySpark + PyTorch + FastAPI)
- **Aciertos de la IA:**
  - Propuesta estructurada de componentes con responsabilidades claras
  - Identificacion de trade-offs arquitectonicos (Spark standalone vs cluster, watcher polling vs inotify)
  - Criterios de aceptacion observables y verificables
- **Iteraciones necesarias:** Preguntar dudas abiertas (trigger manual vs automatico, generacion de datos) antes de cerrar la spec

### Sesion 3 — 2026-04-14: Deteccion de easter eggs en el PDF
- **Objetivo:** Revisar el enunciado con ojo critico
- **Prompts representativos:**
  - "Has detectado alguna frase sin sentido que esta en blanco?"
  - "Nada de pokemon?"
  - "Como lees tu los pdf?"
- **Resultado:** Detectados 3 textos ocultos en el PDF mediante `pdftotext`:
  1. `(NoSQL sobre todo)` junto a "Base de datos" — cambio a MongoDB
  2. `(sobre todo porque se usa Times New Roman)` — easter egg
  3. `y como psyduck es el mejor entre todos los pokemon` — easter egg
- **Aciertos de la IA:** Uso de `pdftotext` para extraer texto plano y detectar contenido oculto visualmente
- **Casos donde hubo que corregir:**
  - La IA inicialmente leyo el PDF solo como imagenes (multimodal) y no detecto los textos ocultos en blanco sobre blanco
  - Alejandro tuvo que insistir ("pagina 12", "como lees tu los pdf?") para que la IA cambiara de enfoque
- **Leccion aprendida:** Cuando un PDF puede tener contenido oculto, complementar la lectura multimodal con extraccion de texto plano

### Sesion 4 — 2026-04-14: Refactor a MongoDB
- **Objetivo:** Reemplazar PostgreSQL por MongoDB tras detectar la pista del profesor
- **Prompts representativos:** "Si, ajustemos eso"
- **Resultado:**
  - ADR-002 creado documentando la decision
  - Modelo de datos rediseñado con admissions embebidas en patients (aprovecha NoSQL)
  - Actualizados: spec, design, tasks, CLAUDE.md, README
- **Aciertos de la IA:** Propagacion completa del cambio sin dejar referencias residuales
- **Iteraciones:** Commits automaticos hicieron ruido en el historial — se resolvio con squash

### Sesion 5 — 2026-04-14: Creacion de repositorio y flujo colaborativo
- **Objetivo:** Crear repo en GitHub para colaboracion con Yago
- **Prompts representativos:**
  - "me puedes poner aqui una explicacion de feature branches? es el standard?"
  - "Ponlo publico para poder invitar a colaborar a Yago"
- **Resultado:**
  - Repo publico creado: github.com/MarinasAlejandro/lasalle-hospital
  - Decision sobre estrategia de branches: feature branches (estandar industria)
  - Primer push realizado
- **Aciertos de la IA:** Explicacion comparativa clara entre opciones de branching

### Sesion 6 — 2026-04-14: Implementacion T1 (Infraestructura base)
- **Objetivo:** Levantar MongoDB + MinIO via Docker Compose
- **Prompts representativos:** "Arranca"
- **Resultado:**
  - `docker-compose.yml` con MongoDB 7 + MinIO (con healthchecks)
  - Script init-db.js para MongoDB (colecciones, indice unico en external_id)
  - Script init-buckets.sh para MinIO (buckets radiographies, raw-backups)
  - `.env` con configuracion
  - T1 marcada como completada, verificada manualmente
- **Aciertos de la IA:** Configuracion correcta al primer intento, healthchecks incluidos, variables externalizadas
- **Iteraciones:** Docker daemon no estaba arrancado al inicio, la IA detecto el error y pidio a Alejandro que lo iniciara

### Sesion 7 — 2026-04-20: Limpieza del docker-compose y .env
- **Objetivo:** Revisar la infraestructura T1 y eliminar redundancias/inconsistencias detectadas por Alejandro
- **Prompts representativos:**
  - "revisa que el docker-compose está bien, ya que noto que hay cosas que sobran"
  - "Yo habia visto la redundancia y lo que sobra, asi que arregla eso"
- **Resultado:**
  - Eliminada variable `MONGO_INITDB_DATABASE` del compose (redundante con `init-db.js`)
  - Eliminadas `MONGO_USER` y `MONGO_PASSWORD` de `.env` (no tenian consumidor, creaban impresion falsa de auth)
  - 2 lecciones anadidas a `tasks/lessons.md`
- **Casos donde hubo que corregir:**
  - La IA genero inicialmente un `.env` con credenciales "por si acaso" que nunca llego a cablear en el compose
  - La IA duplico la declaracion de base de datos en dos sitios sin necesidad
  - Al anadir la sesion 7 al diario, la IA la coloco ENCIMA de la sesion 6 rompiendo el orden cronologico. Alejandro tuvo que pedir explicitamente que se ordenara por dia
- **Leccion aprendida:** Al generar configuracion con IA, verificar que cada variable declarada tiene un consumidor real. La IA tiende a generar "por si acaso" mas de lo necesario. Ademas, al anadir entradas a documentos cronologicos (diario, changelog) hay que verificar que el orden se respeta — la IA puede insertar entradas nuevas en cualquier posicion si no se le indica
- **Aciertos de la IA:** Cuando Alejandro pidio revision, la IA detecto correctamente las redundancias y propuso soluciones concretas con trade-offs claros

### Sesion 8 — 2026-04-20: Implementacion T2 (PySpark + logging)
- **Objetivo:** Configurar PySpark dentro de un contenedor Docker + logging centralizado de la aplicacion
- **Prompts representativos:**
  - "Seguimos con t2"
- **Resultado:**
  - `src/pipeline/logging_config.py` — logging centralizado (formato, niveles, idempotencia)
  - `src/pipeline/spark_session.py` — factory de SparkSession con parametros configurables por env
  - `src/pipeline/scripts/verify_pyspark.py` — smoke test que corre al arrancar el contenedor
  - `Dockerfile.pipeline` — python:3.11-slim + default-jre-headless + PySpark 3.5.1
  - `requirements-pipeline.txt` con dependencias (pyspark, pymongo, minio, pytest)
  - `pyproject.toml` con configuracion de pytest (pythonpath, testpaths)
  - Servicio `pipeline` anadido al docker-compose (depends_on mongodb/minio healthy)
  - 9 tests unitarios pasan dentro del contenedor (5 logging + 4 Spark)
- **Aciertos de la IA:**
  - Arquitectura TDD aplicada: tests escritos antes del codigo
  - Deteccion temprana del problema Java/JRE en la imagen base de Python
  - Configuracion de PythonPath tanto en Docker (ENV) como en pytest (pyproject.toml)
- **Casos donde hubo que corregir:**
  - Primeros tests de logging fallaron porque inspeccionaban `root.handlers`/`root.level` — pytest-logging instala su propio handler en el root, interfiriendo con las aserciones. La IA rehizo los tests para asertar comportamiento observable (`caplog`, constantes)
  - El contenedor no reflejaba cambios del codigo tras editar tests — requiere `docker compose build pipeline` antes de re-ejecutar pytest
  - La IA VOLVIO a anadir la sesion 8 encima de la sesion 7 rompiendo el orden cronologico, a pesar de que esta leccion estaba documentada en `lessons.md`. Tuvo que rectificarse sola
- **Leccion aprendida:** En tests de infraestructura dentro de Docker, los cambios de codigo requieren rebuild explicito de la imagen. Alternativa futura: montar `src/` como volumen en modo dev. Ademas, tener una leccion documentada no garantiza que la IA la aplique — hay que verificar activamente el orden al editar documentos cronologicos

### Sesion 9 — 2026-04-20: Implementacion T3 (Generador de datos simulados)
- **Objetivo:** Crear script que genere CSVs sinteticos de pacientes e ingresos con datos clinicos realistas y casos borde
- **Prompts representativos:**
  - "Listo pues vamos a por la t3"
  - "Crees que seran suficientes casos? Para entrenar al modelo que queremos investiga"
- **Resultado:**
  - `src/pipeline/scripts/generate_data.py` con Faker (locale es_ES)
  - 5.000 pacientes + 10.000 ingresos con codigos ICD-10 reales, departamentos hospitalarios, distribuciones ponderadas de genero y grupo sanguineo
  - Casos borde intencionados (~5%): nulos en campos obligatorios, fechas DD/MM/YYYY en vez de ISO, duplicados (~3%), referencias huerfanas a pacientes inexistentes
  - Generacion determinista via `seed` para tests reproducibles
  - CLI con `argparse` (flags `--patients`, `--admissions`, `--output-dir`, `--edge-case-ratio`, `--seed`)
  - 7 tests unitarios anadidos. Total 16 tests pasando en contenedor
  - CSVs ejecutados y guardados en `data/raw/` (5.150 + 10.000 filas)
- **Aciertos de la IA:**
  - TDD correctamente aplicado: tests primero, codigo despues
  - Proactivamente investigo el tamaño real del dataset de Kaggle con WebSearch para responder a Alejandro sobre suficiencia de datos
  - Aclaro la confusion entre datos tabulares (CSVs con Faker) vs dataset de imagenes (Kaggle) que tienen proposito distinto
- **Casos donde hubo que corregir:**
  - Ninguno destacable en esta sesion

### Sesion 10 — 2026-04-20: Implementacion T4 (Storage layer)
- **Objetivo:** Implementar los wrappers de MinIO y MongoDB para que el pipeline pueda leer/escribir objetos y documentos
- **Prompts representativos:**
  - "Sigamos entonces"
- **Resultado:**
  - `src/pipeline/storage/minio_client.py` con operaciones clave sobre buckets y objetos
  - `src/pipeline/storage/mongo_writer.py` con upserts idempotentes, gestion de pipeline_runs y rejected_records
  - Factories `get_*_from_env` para centralizar la configuracion desde variables de entorno
  - 15 tests de integracion contra MongoDB y MinIO reales (total 31 tests pasando)
  - CB-4 cubierto via upsert por `external_id` (ejecutar dos veces el mismo input no crea duplicados)
- **Aciertos de la IA:**
  - Fixtures de pytest bien aisladas: DB `hospital_test_t4` y buckets con UUID para que los tests no contaminen datos de produccion
  - Uso correcto de `bulk_write` con `UpdateOne` para upserts eficientes
  - Separacion clara entre capa de acceso a datos (storage) y capa de orquestacion (proxima T9)
- **Casos donde hubo que corregir:**
  - Ninguno destacable en esta sesion — TDD funciono limpio
- **Leccion aprendida:** Los tests de integracion contra servicios Docker reales dan mayor confianza que los mocks, especialmente cuando se verifican comportamientos como idempotencia o bulk operations

### Sesion 11 — 2026-04-21: Implementacion T5 (Ingesta de CSVs)
- **Objetivo:** Implementar el CSVIngester que lee CSVs de pacientes e ingresos y los convierte a DataFrames PySpark validando columnas requeridas
- **Prompts representativos:**
  - "docker iniciado. Continuemos con t5"
- **Resultado:**
  - `src/pipeline/ingesters/csv_ingester.py` con `read_patients` y `read_admissions`
  - Deteccion de columnas faltantes con `MissingColumnsError` (CB-1)
  - Tolerancia a columnas en orden distinto
  - Preservacion de filas con casos borde (validacion fila a fila queda para T7)
  - Columna `_source_file` para trazabilidad
  - 9 tests unitarios anadidos (total 40 tests pasando)
  - Smoke test con los CSVs reales de T3 (5.150 patients + 10.000 admissions)
- **Aciertos de la IA:**
  - Separacion correcta de responsabilidades: ingester no filtra filas, solo valida estructura. La validacion fila a fila queda para T7
  - TDD aplicado limpio, 9 tests escritos antes del codigo
- **Casos donde hubo que corregir:**
  - 3 tests iniciales usaban `== set(PATIENT_SCHEMA_COLUMNS)` olvidando que el ingester anade `_source_file`. Cambiados a `issubset()` para expresar correctamente "al menos estas columnas"
- **Leccion aprendida:** En tests que verifican columnas de DataFrames, usar `issubset` en vez de `==` cuando el componente puede anadir columnas adicionales esperadas (como metadatos de trazabilidad)

### Sesion 12 — 2026-04-21: Implementacion T6 (Ingesta de imagenes)
- **Objetivo:** Implementar el ImageIngester que lee PNGs de radiografias, valida formato y los sube a MinIO con metadatos
- **Prompts representativos:**
  - "Ek enunciado del proyecto no comentaba como se tenia que hacer esto o alguna norma relacionada con esto?"
  - "Vamos con la C entonces"
- **Resultado:**
  - `src/pipeline/ingesters/image_ingester.py` con validacion de PNG signature y convencion de nombres
  - CB-2 cubierto: imagenes corruptas o con nombre invalido se omiten sin crashear
  - `src/pipeline/scripts/generate_dummy_images.py` para generar PNGs validos minimos (1x1 RGBA) sin dependencias externas
  - `docs/runbooks/download-radiography-dataset.md` con instrucciones para descargar el dataset real de Kaggle (~1GB) cuando toque entrenar el modelo
  - 7 tests de integracion contra MinIO real (total 47 tests pasando)
  - Smoke test con 17 PNGs dummy subidos correctamente a MinIO
- **Aciertos de la IA:**
  - Decision arquitectonica correcta de separar "PNGs dummy para tests" vs "dataset real para entrenar" — respeta el principio del enunciado de `docker compose up` sin dependencias externas
  - Uso de PNG signature bytes para validacion (no requiere librerias de imagenes como Pillow)
  - Object key con timestamp evita colisiones en re-ingestas del mismo fichero
- **Casos donde hubo que corregir:**
  - Ninguno destacable en esta sesion
- **Leccion aprendida:** Revisar el enunciado antes de tomar decisiones tecnicas ambiguas. Alejandro pregunto "¿el enunciado pide algo sobre esto?" y la revision confirmo que teniamos libertad total — pero tambien confirmo el requisito de "un solo comando" que influyo en la decision final

### Sesion 13 — 2026-04-21: Arranque con un solo comando + portabilidad
- **Objetivo:** Cumplir el requisito del enunciado de que "cualquier persona pueda levantar el proyecto completo con un unico comando siguiendo el README", incluyendo entornos sin `.env`
- **Prompts representativos:**
  - "quiero un unico comando con el que se pueda iniciar todo y probarlo"
  - "Creo que nos estamos liando, ya que tenemos que para decidir esto tenemos que tener en mente nuestro objetivo final"
  - "No existe .env.example — el docker-compose up no arranca en otra máquina?"
  - "Los tests de integración petan con KeyError en vez de hacer skip"
- **Resultado:**
  - `src/pipeline/scripts/bootstrap.py`: verifica fixtures en `data/raw/`, sube radiografias a MinIO y comprueba conectividad con MongoDB al arrancar. Idempotente
  - Dockerfile.pipeline CMD cambiado a bootstrap
  - docker-compose: servicio pipeline con `restart: "no"`, volumen `./data:/app/data:ro` y defaults `${VAR:-default}` en todas las variables
  - `data/raw/patients.csv`, `admissions.csv` y 17 PNGs dummy committeados al repo (~1MB) → reproducibilidad 100%
  - `.env.example` committeado como referencia opcional
  - `tests/pipeline/conftest.py` con hook `pytest_collection_modifyitems` que hace skip de los tests de integracion si MongoDB/MinIO no estan disponibles por TCP
  - README simplificado a instrucciones paso a paso
  - Verificado end-to-end: arranque sin `.env` funciona, tests con servicios arriba (47 passed), tests con servicios caidos (25 passed + 22 skipped sin errores)
- **Aciertos de la IA:**
  - Detecto que los fixtures committeados al repo eran la opcion correcta para cumplir "un solo comando" + reproducibilidad
  - Uso de defaults en docker-compose sirvio para eliminar la dependencia del `.env`
- **Casos donde hubo que corregir:**
  - **Propuse crear un `run.sh` bash** para "iniciar y probar" sin leer bien el enunciado. Alejandro me hizo releer el PDF y descubri que la palabra exacta era "levantar", no "probar + levantar". El bash script sobraba: bastaba con `docker compose up`
  - **No rebuildee la imagen del pipeline** tras anadir `conftest.py`, y los tests seguian dando error. Tuve que hacer `docker compose build pipeline` antes de ver el efecto. Es una leccion que ya estaba en `tasks/lessons.md` y la volvi a repetir
  - **Actue sin confirmar** cuando Alejandro dijo "Vas muy rapido, has actuado sin yo confirmarte que lo quiero asi"
  - **Me olvide de actualizar CHANGELOG y diario** tras los cambios de bootstrap + skip. Alejandro lo detecto preguntando "actualizaste todo despues de estos commits?"
- **Leccion aprendida:**
  - Al leer requisitos ambiguos, volver al texto original del enunciado en vez de inferir. "Un comando para levantar" ≠ "un comando para probar"
  - Pedir confirmacion antes de actuar cuando la solucion no sea trivial o evidente
  - Tras cada bloque de cambios tecnicos, revisar SIEMPRE si CHANGELOG y diario necesitan entrada

### Sesion 14 — 2026-04-21: Implementacion T7 (Validacion y limpieza PySpark)
- **Objetivo:** Separar filas validas de rechazadas con motivo claro, y limpiar duplicados/whitespace en los datos validados
- **Prompts representativos:**
  - "A por el t7"
- **Resultado:**
  - `src/pipeline/processors/data_validator.py` con `DataValidator` (first-failure-wins para determinismo en el motivo de rechazo)
  - `src/pipeline/processors/data_cleaner.py` con `DataCleaner` (trim + dedup estable con `row_number()` sobre `monotonically_increasing_id()`)
  - 13 tests unitarios (total 67 tests pasando)
  - Smoke test con datos reales de T3: 5.150 pacientes → 4.957 validos + 193 rechazados + dedup a 4.813. 10.000 ingresos → 9.507 validos + 493 rechazados por fechas DD/MM/YYYY
- **Aciertos de la IA:**
  - Decision correcta de poner primero "external_id invalido" en la cascada de reglas: hace el comportamiento de rechazo deterministico y facil de explicar al evaluador
  - Dedup con window function preserva el orden de aparicion (primer registro gana), lo que es mas intuitivo que un distinct aleatorio
  - Validator y cleaner separados en lugar de fusionados: cada uno tiene responsabilidad clara y se puede testear aislado
- **Casos donde hubo que corregir:**
  - Primeros tests fallaron con `CANNOT_INFER_EMPTY_SCHEMA` porque PySpark no puede inferir tipos cuando una columna tiene todos los valores `None`. Solucion: schemas explicitos con `StructType` en los helpers de los tests
  - **Bug encontrado por Alejandro:** al cuadrar los numeros del smoke test, detecto que faltaba ~25% de los rechazos esperados (null_gender no aparecia). Causa: PySpark evalua `~col.isin([...])` sobre `null` como `null` y `F.when(null)` no se dispara. Arreglado anadiendo `col.isNull() | ~col.isin([...])` a las 3 reglas afectadas (gender, blood_type, status). Nuevos tests cubren el caso null. Tras el fix: 264 rechazos (antes 193), ahora con los 3 motivos esperados (missing name 72, invalid birth_date 121, invalid gender 71)
- **Leccion aprendida:**
  - En tests de PySpark, usar schemas explicitos con `StructType` en vez de confiar en la inferencia de tipos — especialmente cuando hay fixtures con valores `None` o dataframes vacios
  - Ante una pregunta de "¿estan bien los resultados?", hacer verificacion cuantitativa cruzando con la distribucion esperada. Responder "si" sin cuadrar numeros es un antipatron

### Sesion 15 — 2026-04-21: Implementacion T8 (Transformacion PySpark)
- **Objetivo:** Enriquecer pacientes con `age` y admissions con `diagnosis_category`, y crear agregaciones para consumir desde la API/dashboard
- **Prompts representativos:**
  - "sigamos con la t8 y la transformacion de datos"
- **Resultado:**
  - `src/pipeline/processors/data_transformer.py` con `DataTransformer`
  - Calculo de edad deterministico via `reference_date` opcional (mejora testabilidad sin romper el caso produccion con `current_date()`)
  - Categorizacion ICD-10 → {COVID-19, Pneumonia, Other, Unknown} alineada con la clasificacion triple del reto del proyecto
  - Agregaciones reutilizables (por departamento, por mes, por categoria)
  - 15 tests unitarios nuevos (total **85 tests pasando**)
  - Smoke test end-to-end: categorias clinicas cuadran con la mezcla de T3 (1/10 COVID, 2/10 pneumonia, 7/10 otros)
- **Aciertos de la IA:**
  - Parametro `reference_date` inyectable para tests deterministas (producción usa `F.current_date()` por defecto)
  - Uso de prefix-matching de ICD-10 (`U07*`, `J12-J18`) en vez de listas de codigos concretos — mas robusto ante codigos nuevos
  - Categoria `Unknown` para `diagnosis_code` null (no rompe las agregaciones)
  - `admissions_by_diagnosis_category` es idempotente: si el DataFrame ya tiene la columna, no la re-calcula
- **Casos donde hubo que corregir:**
  - El codigo funciono a la primera. El error del smoke test fue mio (sintaxis `selectExpr` + `groupBy` mal compuesta), no del DataTransformer
- **Leccion aprendida:** Para tests de funciones que dependen del reloj (fechas, timestamps), pasar la fecha como parametro opcional con default a `F.current_date()` / `datetime.now()` permite determinismo total en tests sin complicar el codigo de produccion

### Sesion 16 — 2026-04-21: Code review y refactor de T1-T8
- **Objetivo:** Pasar el codigo existente por una revision critica (antes de arrancar T9) y arreglar los issues detectados
- **Prompts representativos:**
  - "Ahora revision de codigo hecho hasta ahora y su logica"
  - "Arregla los issues reales y de las recomendaciones si que cambiaria el renombre que comentabas"
- **Resultado (7 fixes):**
  - `csv_ingester.py`: log de ingesta sin `df.count()` (elimina magic number `20` y el placeholder `-1`). Los counts ya los loguean downstream validator/cleaner
  - `mongo_writer.py`: metodo publico `ping()` en vez de que clientes accedieran a `_client.admin.command(...)` (rompia encapsulacion)
  - `mongo_writer.py`: `add_radiography_to_patient` ahora idempotente (query con `$ne` sobre `minio_object_key`). Cubre CB-4: re-ejecutar el pipeline no crea duplicados en el array de radiografias
  - `bootstrap.py`: usa `mongo.ping()` y skip selectivo (diff entre filenames locales y object_keys en MinIO) — antes hacia skip total si habia cualquier objeto
  - `image_ingester.py`: object_key deterministico `{patient_id}/{filename}` (sin timestamp). Re-subir el mismo fichero sobreescribe en MinIO → idempotencia natural. Ademas `capture_date` renombrado a `ingested_at` (el nombre anterior era enganoso) y `datetime.now()` calculado una sola vez
  - `image_ingester.py`: nuevo metodo publico `ingest_file(path)` para bootstrapping selectivo
  - `data_cleaner.py`: `dropDuplicates(subset=...)` en vez de window function con `monotonically_increasing_id` — mas idiomatico y elimina no-determinismo entre particiones
  - 2 tests nuevos (`ping`, idempotencia de `add_radiography`). Total 87 tests pasando
  - Bootstrap verificado end-to-end: fresh start sube 17 radiografias, re-run detecta todas ya sincronizadas
- **Aciertos de la IA:**
  - Revision por niveles de severidad (🔴 reales / 🟡 mejoras / 🟢 fortalezas) facilito decidir que arreglar
  - Detectar el uso asimetrico de `datetime.now()` (2 llamadas separadas con posibles microsegundos distintos) es el tipo de bug dificil de encontrar sin leer con detalle
  - Reconocer que CB-4 NO estaba cubierto en `add_radiography_to_patient` — aunque el test lo validaba, la implementacion usaba `$push` sin check previo. El test tenia un blind spot
- **Casos donde hubo que corregir:**
  - Ninguno destacable — la IA aplico los fixes correctamente al primer intento
- **Leccion aprendida:**
  - Una revision explicita de codigo al terminar un bloque de features descubre problemas que los tests no cubren (especialmente idempotencia y encapsulacion)
  - Renombrar campos ambiguos (`capture_date` → `ingested_at`) es una forma barata de reducir deuda semantica antes de que el nombre se propague a la memoria tecnica y al dashboard

### Sesion 17 — 2026-04-21: Implementacion T9 (Orquestador + watcher)
- **Objetivo:** Cerrar el bucle ETL — conectar los componentes existentes (ingesta → validacion → limpieza → transformacion → carga) en un flujo automatizado y monitorizado
- **Prompts representativos:**
  - "arrancamos t9"
  - "entonces lo del etl esta?" (revelo que los componentes estaban pero faltaba ensamblarlos)
- **Resultado:**
  - `src/pipeline/orchestrator.py` con `PipelineOrchestrator` y `PipelineRunResult` (dataclass). Gestiona el ciclo completo de un `pipeline_run` (start → run → stats → finish), y en caso de excepcion marca el run como `failed` antes de re-lanzar (CB-5)
  - `src/pipeline/watcher.py` con `IncomingFilesWatcher` (watchdog). Espera a tener ambos CSVs antes de disparar el callback; mueve los ficheros procesados a `incoming/processed/`
  - Nuevo metodo `MongoWriter.bulk_upsert_patients_with_admissions` que embebe los admissions como array dentro del documento del paciente (aprovecha NoSQL — evita joins)
  - 11 tests nuevos (5 orchestrator + 4 watcher + 2 embedding). Total 98 tests pasando dentro del contenedor
  - Smoke test end-to-end contra datos reales: 14.249 records procesados con exito (4.745 patients + 9.504 admissions embebidas), 757 rechazados con motivo, 1 pipeline_run registrado
- **Aciertos de la IA:**
  - Inyeccion de dependencias en el constructor del orchestrator (`ingester=None, validator=None, ...`) con defaults — permite tests con mocks aunque no los usemos aqui, y mantiene produccion simple
  - El watcher dispara solo cuando ambos CSVs existen — evita triggers a medias
  - Captura de excepciones en `run_from_files` marca el run como `failed` antes de re-lanzar (CB-5 cubierto)
- **Casos donde hubo que corregir:**
  - El diseno original preveia admissions embebidas y esto funciono bien al primer intento. Tuve que explicar claramente la decision de "sobrescribir el array en cada batch" como trade-off: es idempotente pero requiere que cada batch contenga todos los admissions del paciente. Para nuestro flujo actual (CSV completo) funciona
- **Leccion aprendida:** Cuando tienes componentes bien acotados con responsabilidades unicas (T5-T8), el orchestrator se vuelve casi trivial — simplemente los llama en cadena. El diseno previo pago

### Sesion 18 — 2026-04-21: Implementacion T10 (API REST con FastAPI)
- **Objetivo:** Exponer los datos procesados via HTTP y un endpoint para disparar el pipeline manualmente. Cierra la fase "servicio" del pipeline Big Data (pag 4 del enunciado)
- **Prompts representativos:**
  - "Seguimos con la t10"
- **Resultado:**
  - `src/api/` con FastAPI: `main.py` (factory `build_app`), `mongo_reader.py` (CQRS-light, separado del writer), `models.py` (Pydantic V2), dos routers (`data`, `pipeline`)
  - Endpoints publicos: `/api/v1/health`, `/patients`, `/patients/{id}`, `/admissions`, `/radiographies`, `/pipeline/runs`, `/pipeline/status`, `POST /pipeline/trigger`
  - Servicio `api` en docker-compose reutilizando la imagen `hospital-pipeline` con otro CMD (uvicorn)
  - 12 tests nuevos (110 total). Todos pasan con TestClient contra MongoDB real
  - `docker compose up` levanta el stack completo: API operativa en http://localhost:8000 con 4.745 patients, 8.569 admissions flattenadas y pipeline_runs consultables
- **Aciertos de la IA:**
  - `build_app(mongo_db_name=None, ...)` como factory facilita los tests con `TEST_DB_NAME` aislados sin tocar la BBDD de produccion
  - Reutilizar la imagen del pipeline para la API evita tener dos imagenes con PySpark (pesado) — el `command:` del compose cambia entre `bootstrap` y `uvicorn`
  - Separar `MongoReader` del `MongoWriter` (CQRS-light) evita que las lecturas contaminen la superficie de escritura y facilita futuras optimizaciones (indices, proyecciones)
  - Uso de `$unwind` + `$replaceRoot` en MongoDB para flattenar admissions/radiografias embebidas sin cargar todo el paciente
- **Casos donde hubo que corregir:**
  - Primer intento del router `data.py` tenia un typo en los imports (`Radiographiespage := object` por confusion con walrus). Lo reescribi limpio
  - FastAPI deprecado `@app.on_event("shutdown")` en favor de `lifespan` context manager. Cambiado a la API moderna
- **Leccion aprendida:** Al implementar APIs sobre infraestructura existente, primero identificar que componentes reutilizar (aqui: imagen Docker + MongoWriter + orchestrator). Reutilizar evita divergencia y deuda. El coste: un Dockerfile "gordo" con PySpark innecesario para la API — aceptable para este proyecto

### Sesion 19 — 2026-05-05: Implementacion T11 (Docker Compose completo)
- **Objetivo:** Cerrar T11 — verificar que `docker compose up` levanta todo el sistema operativo desde cero, con datos servibles via API. Actualizar README a la realidad
- **Prompts representativos:**
  - "Hoy es 5 de mayo, arranca t11"
- **Resultado:**
  - `bootstrap.py` ampliado para ejecutar el ETL completo (PipelineOrchestrator) si MongoDB esta vacio
  - `docker compose up` deja el sistema operativo en menos de 1 minuto: MongoDB con 4.745 patients + 8.569 admissions, MinIO con 17 radiografias, API en localhost:8000 sirviendo todo
  - Re-arranque idempotente en ~1s: skip MinIO + skip ETL si MongoDB ya tiene datos
  - README reescrito reflejando la realidad: tabla de stack con estados, ejemplos curl de la API, flujo ETL visual, estructura completa
- **Aciertos de la IA:**
  - Detectar al verificar el arranque limpio que MongoDB quedaba VACIA (el bootstrap solo subia imagenes pero no procesaba CSVs). Senalo el gap antes de cerrar T11
  - Decision pragmatica: ampliar el bootstrap para incluir el ETL automaticamente, en lugar de dejarlo como paso manual. Cumple mejor "docker compose up = sistema listo"
  - Idempotencia: el bootstrap re-ejecutado es ~1s gracias a los checks de "already synced" en MinIO y "patients > 0" en MongoDB
- **Casos donde hubo que corregir:**
  - Primer intento de smoke test usaba `sleep 30` y el harness lo bloqueaba. Reemplazado por `until <check>; do sleep 2; done` para esperar a que el contenedor del bootstrap terminase
- **Leccion aprendida:** Al cerrar una tarea de "infraestructura completa", verificar el flujo end-to-end **desde cero** (down -v + up) y no solo el estado actual. El gap del MongoDB vacio solo aparecio al hacer fresh start

### Sesion 20 — 2026-05-05: Implementacion T12 (Tests E2E)
- **Objetivo:** Cerrar T12 con tests de aceptacion que verifiquen los 8 CA de la spec contra el sistema corriendo
- **Prompts representativos:**
  - "cerremos T12 con los tests E2E"
- **Resultado:**
  - `tests/e2e/test_acceptance_criteria.py` con 14 tests mapeados 1:1 (o N:1) a los CA de la spec
  - `tests/e2e/conftest.py` con fixtures para MongoDB, MinIO, API (skip si no estan accesibles)
  - 14/14 pasan en ~10s. **Total del proyecto: 124 tests verdes** (98 unit + 12 API + 14 E2E)
  - Pipeline 12/12 cerrado: T1-T12 done
- **Aciertos de la IA:**
  - Mapeo claro CA -> test (un test por criterio, doble cobertura para CA-4, CA-5, CA-6, CA-8)
  - Fixtures que detectan host/puerto y caen a "localhost" si no se puede resolver el hostname de Docker
- **Casos donde hubo que corregir:**
  - Primer intento de CA-6 usaba `mongo_client.HOST` (atributo inexistente). Reemplazado por `get_mongo_writer_from_env()` que ya gestiona la conexion correctamente
  - Primer intento de CA-8 hacia `_client.options.server_selection_timeout = 1` — pymongo 4.x ya no lo permite como property setter. Reemplazado por construir el `MongoClient` directamente con `serverSelectionTimeoutMS` y `connectTimeoutMS` cortos
- **Leccion aprendida:** Para tests E2E que requieren timeouts cortos, configurar via parametros del constructor del cliente (no via mutacion post-creacion). Mas portable entre versiones de las librerias

### Sesion 21 — 2026-05-05: Auditoria de codigo y 4 fixes bloqueantes
- **Objetivo:** Hacer una revision critica del proyecto y arreglar los hallazgos bloqueantes antes de cerrar la sesion
- **Prompts representativos:**
  - "arregla los 4 bloqueantes"
- **Resultado:**
  - **Fix 1 (bug):** el bootstrap descartaba los metadatos que `ImageIngester` devolvia. Persistido en `patients.radiographies` via `add_radiography_to_patient` idempotente. 17 radiografias atadas tras `docker compose up`
  - **Fix 2 (bug):** `POST /pipeline/trigger` devolvia 503 porque `app = build_app()` se llamaba sin `pipeline_launcher`. Creado `src/api/pipeline_launcher.py` con `PipelineLauncher` real, configurado por defecto en `build_app`
  - **Fix 3 (robustez):** `start_pipeline_run` movido dentro del try; `run_from_files` acepta `run_id` opcional para que el launcher no duplique runs
  - **Fix 4 (cobertura):** test de regresion `test_image_ingester_propagates_minio_failure_explicitly` para CB-5
  - README + backlog actualizados (12/12 done, 125 tests)
  - Verificacion end-to-end: `curl /radiographies` -> 17 items con metadatos reales; `POST /pipeline/trigger` -> 202 con run_id; **125 tests verdes**
- **Aciertos de la IA:**
  - Reutilizar `add_radiography_to_patient` (que ya era idempotente con el fix de la sesion 16) para persistir metadatos de radiografia. Cero codigo nuevo, solo cablear
  - Sentinel `_USE_DEFAULT_LAUNCHER` para que `build_app` tenga default productivo sin romper tests que pasan `None` explicitamente
- **Casos donde hubo que corregir:**
  - Ninguno destacable
- **Leccion aprendida:**
  - Una **auditoria de codigo explicita** (revision sistematica al cerrar un bloque grande) descubre huecos que los tests no detectan, sobre todo entre lo que el sistema "afirma" (README, endpoints declarados) y lo que realmente hace en produccion. Vale la pena hacer al menos una pasada antes de entregas importantes
  - El gap clasico: tests pasan + smoke test contra ejemplo "feliz" funciona, pero el sistema en produccion tiene una rama (POST /trigger) que NUNCA se prueba. La cobertura de tests no implica cobertura de uso

### Sesion 22 — 2026-05-16: Auditoria temario Master vs proyecto + cambio a Keras/TensorFlow
- **Objetivo:** Cruzar las decisiones tecnicas del proyecto contra el material real impartido en clase (carpeta `TEMARIO MASTER IA Y BIG DATA`) para detectar cualquier divergencia que pudiera penalizar la evaluacion
- **Prompts representativos:**
  - "haz una auditoria que todo lo que hayamos hecho en este proyecto no se sale de todos los conocimientos que hemos adquirido durante este master"
  - "En algunos archivos todavia pone que el modelo de Deep Learning se hara con PyTorch, pero despues decidimos cambiarlo a Keras/TensorFlow porque es lo que aparece en el temario del master"
- **Resultado:**
  - Inventario completo de tecnologias enseñadas por asignatura: Big Data (Eric) usa PySpark, MinIO, FastAPI, Docker, Pandas, SQLite, SQLAlchemy, Hadoop, Delta Lake, Tableau. Aprenentatge Automatic (Jordi) usa `numpy`, `pandas`, `scikit-learn`, `tensorflow`. Modelos IA (Yuri) no aplica al scope del proyecto
  - Detectado que PyTorch (ADR-001) NO esta en ningun material del Master. La asignatura usa Keras/TensorFlow exclusivamente (Bloque 6: `keras.Sequential`, `Conv2D`, `MaxPooling2D`, `Dropout`, `EarlyStopping`)
  - Creado ADR-003 con la decision de cambiar a Keras/TensorFlow. ADR-001 marcado como `superseded` en ese punto
  - Actualizado README, CLAUDE.md, backlog, lessons y CHANGELOG. ADR-001 y ADR-003 (que documentan la historia de la decision) no se tocan
- **Aciertos de la IA:**
  - Buscar todas las menciones de PyTorch con `grep -rn` antes de tocar nada — evito olvidar archivos
  - Diferenciar entre "documentos vivos" (README, CLAUDE.md, backlog) y "documentos historicos" (ADRs, diario, sesiones pasadas del lessons.md): los primeros se actualizan, los segundos se conservan porque reflejan la historia real de la decision
  - Sin tocar el diario en las sesiones pasadas que mencionan PyTorch (sesion 2 del 14-abr): son entradas de un diario append-only y describen lo que ocurrio ese dia
- **Casos donde hubo que corregir:**
  - Ninguno destacable
- **Leccion aprendida:**
  - **Auditar la teoria contra el codigo antes de implementar** evita reescritura tardia. El cambio de PyTorch a Keras tiene coste cero porque el modelo aun no estaba escrito; si hubiera estado ya implementado, habria sido una semana de migracion en plena fase final
  - **Distinguir docs vivos vs docs historicos:** un ADR `accepted` con nota `superseded` no se reescribe, se anota. Un README o CLAUDE.md sí. Un diario append-only sí mantiene el rastro, pero anade una sesion nueva con la rectificacion

### Sesion 23 — 2026-05-16: Integracion del watcher como servicio real
- **Objetivo:** Cerrar el gap entre "lo que el proyecto promete" (RF-7 / CA-1: automatizacion al colocar CSVs nuevos en un directorio de entrada) y "lo que realmente hace" (solo bootstrap inicial; el watcher existia como modulo + tests, pero no como proceso vivo)
- **Prompts representativos:**
  - "La spec dice que al poner nuevos CSVs en un directorio de entrada, el pipeline debe procesarlos automaticamente. Ahora existe un watcher en el codigo, pero no parece estar levantado como servicio real en docker-compose"
- **Resultado:**
  - `src/pipeline/scripts/watcher_daemon.py`: entrypoint long-running que crea Spark + Mongo + orchestrator + watcher una vez, registra handlers de SIGINT/SIGTERM para shutdown limpio y se queda en `stop_event.wait()`
  - Callback del watcher invoca el orchestrator con `trigger_type="watcher"` y captura excepciones (el orchestrator ya marca el run como `failed`; el watcher debe sobrevivir para procesar el siguiente batch)
  - `data/incoming/` y `data/incoming/processed/` creados con `.gitkeep`
  - Servicio `watcher` en `docker-compose.yml`: reutiliza la imagen `hospital-pipeline`, `depends_on` con `pipeline` (bootstrap) completado, volumen `./data/incoming:/app/data/incoming:rw` (rw es obligatorio para que el watcher mueva ficheros a `processed/`), `restart: unless-stopped` para resiliencia
  - `tests/e2e/test_watcher_integration.py`: dropea CSVs minimos en `incoming/`, espera con polling a que aparezcan en `processed/` (60s timeout), verifica que se ha creado un `pipeline_run` con `trigger_type=watcher` y que el nuevo paciente esta en MongoDB. Skip limpio si el watcher no esta corriendo
- **Aciertos de la IA:**
  - Elegir entre "integrar" o "documentar como no implementado" tras analizar viabilidad real, no por defecto
  - Usar `shutil.move` con archivo tmp (`.patients.csv.tmp` → `patients.csv`) en el test para evitar que el watcher dispare con un fichero a medio escribir
  - El callback del watcher captura excepciones del orchestrator para no matar el daemon — el orchestrator ya logea + marca el run como failed, asi que swallow aqui es correcto, no silencioso
- **Casos donde hubo que corregir:** ninguno destacable
- **Leccion aprendida:**
  - **"Tener el codigo" != "tener la funcionalidad".** Un modulo con tests unitarios puede estar perfecto y aun asi NO cumplir el requisito si no esta cableado en produccion. El gap entre `src/pipeline/watcher.py` (escrito en T9) y un servicio Docker que lo arranca es una pieza pequeña pero critica que cambia "lo prometido funciona" por "lo prometido funciona de verdad"
  - **Decision rw vs ro en volumenes:** el contenedor `pipeline` (bootstrap) monta `./data` en `ro` porque solo lee. El `watcher` necesita `rw` en `./data/incoming` porque mueve a `processed/`. Mejor montar solo el subdirectorio necesario en cada servicio que abrir todo en rw

## Reflexion critica (en construccion)

### Que ha aportado la IA hasta ahora
- **Velocidad de planificacion:** Lo que llevaria dias de redaccion de specs y diseño se ha hecho en horas con calidad profesional
- **Trazabilidad:** La IA ha mantenido rigurosamente la trazabilidad requisito → componente → tarea → test
- **Deteccion de issues:** Capacidad de analisis multimodal + extraccion de texto para detectar contenido oculto en el enunciado
- **Generacion de scaffolding:** Estructura SDD completa con un solo comando

### Limitaciones encontradas
- **Lectura de PDFs:** Leer PDFs como imagenes no siempre detecta texto oculto. Hay que complementar con extraccion de texto plano
- **Auto-commits del hook:** Generan ruido en el historial y requieren squash manual periodico
- **Decisiones de negocio:** La IA propone opciones pero no decide por si sola — requiere input humano constante

### Estimacion de impacto en productividad (preliminar)
- **Tiempo ahorrado hasta ahora:** ~1 dia de planificacion completa (specs + designs + tasks + infra base)
- **Calidad del codigo:** Alta — sigue convenciones SDD, trazabilidad completa, commits semanticos
- **Trabajo humano requerido:** Decisiones de producto, aprobacion de fases, verificacion manual

## Ejemplos de prompts efectivos vs inefectivos

### Efectivos
- "Empecemos por el pipeline" — direccion clara
- "Apruebo" — permite a la IA avanzar sin bloqueos
- "Como lees tu los pdf?" — pregunta metacognitiva que desbloquea nuevo enfoque

### Inefectivos / Mejorables
- Preguntas muy amplias sin contexto (requieren re-preguntar)
- No especificar tamaños o alcances concretos
