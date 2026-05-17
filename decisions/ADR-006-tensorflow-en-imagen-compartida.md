# ADR-006: TensorFlow en la imagen Docker compartida `hospital-pipeline`

> Estado: accepted
> Fecha: 2026-05-16
> Supersede: —

## Contexto

La feature `clasificacion-radiografias` requiere TensorFlow/Keras
(decidido en ADR-003) tanto para entrenamiento offline como para
inferencia online en la API. El proyecto hoy tiene una unica imagen
Docker `hospital-pipeline` que cubre tres servicios:

- `pipeline` (bootstrap ETL one-shot)
- `api` (FastAPI / uvicorn, long-running)
- `watcher` (watchdog daemon, long-running)

La imagen ya carga PySpark 3.5.1 + Java JRE + pymongo + minio + FastAPI
+ uvicorn + SQLAlchemy + watchdog. Anadir TensorFlow la hace mas pesada
(~600 MB adicionales con `tensorflow-cpu`).

Hay dos arquitecturas posibles:

- **A. Una sola imagen compartida** (`hospital-pipeline`) con TF dentro
- **B. Dos imagenes especializadas**: `hospital-pipeline` sin TF para
  el ETL, y una nueva `hospital-ml` con TF para `api` (que sirve
  predicciones) y para un servicio `trainer` efimero

## Decision

**Opcion A: una sola imagen compartida con TensorFlow dentro.**

La imagen `hospital-pipeline` incorpora `tensorflow-cpu` como
dependencia mas, sumandose a PySpark. Todos los servicios (`pipeline`,
`api`, `watcher`) usan la misma imagen, igual que hasta ahora. El
entrenamiento se ejecuta como un comando puntual en el contenedor
`pipeline`:

```
docker compose run --rm pipeline python -m src.ml.train
```

## Alternativas consideradas

| Opcion | Pros | Contras |
|--------|------|---------|
| **A. Imagen compartida con TF (elegida)** | Operativa simple: una sola imagen para construir, una sola para mantener. Reutiliza el caching de Docker y el flujo `docker compose build` actual. Entrenamiento dentro del compose, sin gestion de imagenes auxiliares. Compatibilidad inmediata con tests existentes (ya corren en `hospital-pipeline`) | Imagen mas pesada (~1.5 GB → ~2.1 GB). Build mas lento (~2-3 min extra primera vez, ~30s con cache). Servicios que no usan TF (`pipeline`, `watcher`) cargan la dependencia aunque no la usen |
| B. Dos imagenes (`hospital-pipeline` sin TF + `hospital-ml` con TF) | Imagenes mas finas, cada una con lo que necesita. Build paralelo posible. Servicios optimizados por funcion | Complica `docker-compose.yml` (otro `build:` block, otro `image:`). Duplica la base (Python 3.11, dependencias comunes) en disco salvo que se haga multi-stage compartido. Anade un servicio `trainer` o tener que arrancar `api` para entrenar. Cambio mas grande, mas riesgo a 4 dias de la entrega |
| C. Imagen monolitica con TF + GPU (CUDA) | Inferencia y entrenamiento mas rapidos en hosts con GPU | Imagen >5 GB. CUDA dependencies pesadas. Innecesario: el evaluador probablemente no tiene GPU. Sin justificacion para el volumen del proyecto |

## Consecuencias

**Positivas:**
- (+) **Cambio minimo:** anadir una linea a `requirements-pipeline.txt`
  + rebuild. Cero refactor del compose
- (+) **Entrenamiento dentro del compose:** evaluador puede regenerar
  el modelo sin instalar nada extra en host, solo con
  `docker compose run pipeline python -m src.ml.train`
- (+) **Tests siguen funcionando:** los tests que viven en
  `tests/ml/` y `tests/api/` se ejecutan en el mismo contenedor que
  ya usan los demas tests; no hay fragmentacion
- (+) **Predictor cargado en la API:** ya tiene TF disponible sin
  necesidad de cambiar la imagen del servicio `api`

**Negativas:**
- (-) **Build mas pesado:** primera build sube de ~2 min a ~4 min.
  Mitigado por el cache de Docker para builds sucesivos
- (-) **Disco:** la imagen ocupa ~2.1 GB. Para un proyecto de
  demostracion es aceptable; en produccion se replantearia
- (-) **`pipeline` y `watcher` cargan TF sin usarlo en runtime:** no
  hay coste de ejecucion (TF solo se carga al importar), pero la
  imagen igualmente lo contiene. Asumible

## Requisitos relacionados

- **Spec `clasificacion-radiografias`:** RF-1 (script reproducible
  para entrenar), RF-4 (modelo cargado al arrancar API), RNF-1
  (Keras/TF)
- **ADR-003:** fija Keras/TF como framework. Este ADR decide donde
  vive ese framework en la infra Docker

## Notas

Si en una iteracion futura la imagen se vuelve dolorosa de mantener
(>3 GB, build > 10 min) se reabrira esta decision con un ADR que
proponga la separacion en dos imagenes. Para la entrega actual, la
simplicidad gana.
