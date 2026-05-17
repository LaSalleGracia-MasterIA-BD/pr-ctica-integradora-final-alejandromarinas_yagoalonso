# Runbook: Demo de presentacion

> Ultima verificacion: 2026-05-17
> Responsable: Alejandro Marinas
>
> Que tener abierto durante la demo:
> - Dashboard:  http://localhost:8501
> - API Swagger: http://localhost:8000/docs (opcional, para defender el contrato HTTP)
> - Terminal con `docker compose logs -f api` (opcional, para mostrar logs reales si surge la pregunta)

## Cuando usar este runbook

- Defensa del proyecto del Master.
- Cualquier demo del sistema ante una audiencia no familiarizada con
  el codigo.

## Prerequisitos

1. Estar en la raiz del repo `lasalle-hospital`.
2. Tener Docker Desktop arrancado.
3. (Recomendado) Dataset COVID-19 Radiography Database descargado en
   `data/raw/covid_radiography/` siguiendo
   `docs/runbooks/download-radiography-dataset.md`. Sin el, el
   bootstrap se salta `HOSP-PRES-*` y el Clasificador solo tiene la
   `HOSP-DEMO-001` sintetica (la demo funciona igual, pero pierde el
   "wow" de las radiografias reales).
4. (Recomendado) ~5 GB libres en disco para Docker.

## Levantar demo limpia

```bash
docker compose down -v        # opcional: tira volumenes para arrancar de cero
docker compose up -d --build  # primera vez tarda unos minutos (TF + Streamlit)
```

Esperar a:
- `Bootstrap complete. System is ready.` en `docker compose logs pipeline`
- `hospital-api` y `hospital-dashboard` con estado `(healthy)` en
  `docker compose ps`

Verificacion rapida desde host:

```bash
curl -s http://localhost:8000/api/v1/health
curl -s http://localhost:8501/_stcore/health
```

Ambos deben devolver 200 OK.

## Pre-carga de radiografias HOSP-PRES-* (automatico)

Si `data/raw/covid_radiography/COVID-19_Radiography_Dataset/` existe
cuando se ejecuta `docker compose up`, el bootstrap registra
**automaticamente** 6 radiografias reales como pacientes
`HOSP-PRES-001`..`HOSP-PRES-006` (2 por clase: COVID, Normal, Viral
Pneumonia). Las imagenes NO se commitean al repo; solo se copian al
bucket MinIO durante el bootstrap si el dataset esta disponible en
local.

Para verificarlo despues de `docker compose up`:

```bash
curl -s "http://localhost:8000/api/v1/radiographies?limit=50" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
    print('total=', d['total']); \
    [print(' ', it['minio_object_key']) for it in d['items'] \
     if it['minio_object_key'].startswith('HOSP-PRES-')]"
```

Si NO aparece ningun `HOSP-PRES-*`, el dataset no esta en local. Para
una demo con valor clinico:
1. Descarga el dataset (ver `download-radiography-dataset.md`).
2. `docker compose run --rm pipeline` (re-ejecuta el bootstrap, que es
   idempotente: solo sube lo que falta).
3. Recarga la vista Clasificador.

## Flujo recomendado de presentacion (10-15 min)

Abrir `http://localhost:8501`. El recorrido sigue el orden de las 5
vistas, que cuenta la historia "del dato al modelo":

### 1. Overview (1-2 min) — Estado general

- 4 cards arriba: cuantos pacientes/admisiones/radiografias hay en
  el sistema + si el modelo esta cargado.
- Ultimo run del pipeline: confirma que el ETL acabo con `success`.
- Strip de evaluacion abajo: accuracy y macro-F1 del modelo, version
  del artefacto cargado.
- Sidebar (siempre visible): 3 chips API/Modelo/Ultimo run en verde →
  prueba "en vivo" de que el stack esta sano.

Mensaje clave: "el sistema esta arriba, los datos cargados, el modelo
listo para inferir".

### 2. Calidad de datos (2 min) — Auditoria del pipeline

- Tabla "Ultimo snapshot relevante": por dimension (patients /
  admissions), cuantos registros entraron, cuantos pasaron validacion,
  cuantos se rechazaron y la tasa de rechazo.
- Grafico de historico: evolucion de la tasa de rechazo en runs
  recientes.
- (Nota tecnica) Por defecto se ocultan los runs muy pequenos (de
  tests automaticos). Si surge la pregunta "y los demas?", activar el
  toggle "Mostrar todos los snapshots" para ensenar transparencia.

Mensaje clave: "el pipeline rechaza datos malos de forma controlada y
queda traza".

### 3. Pacientes (2 min) — Modelo documental

- Tabla paginada de pacientes (4.745 reales del dataset sintetico +
  HOSP-DEMO-001 + HOSP-PRES-* si las hay).
- Click en una fila → se abre el detalle del paciente abajo: campos
  basicos, lista de admisiones embebidas (con diagnosis_category) y
  lista de radiografias embebidas (con su clasificacion si la tiene).

Mensaje clave: "MongoDB nos deja embeber admisiones y radiografias
sin joins, lo que encaja con el dominio clinico".

### 4. Clasificador (3-4 min) — Demo de IA

#### Caso A — Dataset descargado (HOSP-PRES-* disponibles)

- Selecciona en el dropdown una `HOSP-PRES-001` (es real, dataset
  COVID-19 Radiography Database descargado localmente; la fuente y
  licencia exactas son las que el proveedor publica para esa version
  del dataset, ver `data/raw/images-demo/README.md`).
- La imagen aparece en el panel izquierdo.
- Pulsa "Clasificar". El modelo devuelve clase + probabilidades.
- Al final de la pagina: matriz de confusion 3x3 + tabla de
  precision/recall/F1 por clase. **Detenerse aqui** y comentar que el
  FN de COVID-19 es el error mas grave clinicamente (recall ~0.70).

#### Caso B — Dataset NO descargado (solo HOSP-DEMO-001)

- Activa el toggle "Mostrar imagenes no clasificables" SOLO si quieres
  ensenar el caso borde CB-7 (dummy 1x1 → mensaje de rechazo).
- En modo normal: selecciona `HOSP-DEMO-001`. La UI mostrara una
  advertencia amarilla "imagen sintetica de demo — no es una
  radiografia real". Pulsa "Clasificar" igualmente para ensenar el
  flujo end-to-end, pero **decir explicitamente** que la prediccion
  NO es evidencia clinica (la imagen es sintetica).

Mensaje clave: "la asistencia diagnostica funciona end-to-end:
imagen → preprocesado → CNN → resultado persistido, en <3s".

### 5. Pipeline runs (1-2 min) — Operacion y trazabilidad

- Tabla con los runs del ETL (bootstrap + watcher).
- Por defecto se ocultan los runs de test; activa el toggle si quieres
  ensenar la transparencia "este sistema sabe diferenciar runs reales
  de runs tecnicos".
- Si hay algun fallo, el `error_message` se ve expandible.

Mensaje clave: "cada ejecucion deja traza auditable en SQLite, no en
ficheros sueltos".

## Si el dataset real NO esta descargado

- El bootstrap se salta `HOSP-PRES-*` sin error.
- El dropdown del Clasificador solo tiene `HOSP-DEMO-001`.
- La demo funciona, pero hay que **avisar** que la imagen es
  sintetica y la prediccion no tiene valor clinico.
- Si te lo preguntan: "elimine las imagenes reales del repo por temas
  de licencia; cuando descargas el dataset localmente y haces
  `docker compose up`, el bootstrap las anade automaticamente". Ver
  `docs/runbooks/use-real-radiograph-for-demo.md`.

## Notas sobre la imagen sintetica HOSP-DEMO-001

- Es una imagen 256x256 generada con `numpy` + Pillow al arrancar el
  sistema. No procede de ningun dataset clinico ni paciente real.
- Se mantiene en el sistema porque:
  1. Cumple el RNF de "el dashboard funciona out-of-the-box" sin
     pedir nada extra.
  2. Sirve como fixture tecnico para tests E2E que requieren al menos
     una imagen >= 32 px en el bucket.
- La UI del Clasificador la marca explicitamente (banner amarillo +
  caption con la nota "imagen sintetica de demo — no es una
  radiografia real") para que NO se confunda con clinica.

## Si algo sale mal durante la demo

| Sintoma | Causa probable | Solucion |
|---|---|---|
| Dashboard pinta "API no disponible" en todas las vistas | `hospital-api` parado | `docker compose start api` y esperar healthy |
| Chip "Modelo" en rojo | Artefacto `data/models/radiography_classifier.keras` no se cargo | Verificar que el fichero existe; recrear `api`: `docker compose up -d --force-recreate api` |
| Clasificador devuelve 422 con una imagen real | Bug raro o imagen corrupta | Elegir otra `HOSP-PRES-*` del dropdown |
| El navegador no carga `http://localhost:8501` | Puerto ocupado por otro proceso | `lsof -i :8501` y matar el proceso, o cambiar `DASHBOARD_PORT` en env |
| El stack tarda mucho en arrancar tras `docker compose up` | Primera vez: build de la imagen pipeline (TF + PySpark, ~5 min) | Pre-construir antes de la demo con `docker compose build` |

## Notas eticas

- Las imagenes `HOSP-PRES-*` provienen del dataset descargado en local
  por ti. Su origen y licencia exactos son los que indica el proveedor
  desde donde lo descargaste; cita esos terminos tal cual los publica
  el autor original antes de difundir capturas o resultados fuera de
  esta demo. No asumas una licencia generica.
- El modelo se entrega como **asistencia diagnostica** (RNF-2 de
  `specs/clasificacion-radiografias.md`), NUNCA como diagnostico
  final. Cualquier paciente real requiere revision clinica humana.
- El recall de COVID-19 en el split de test es ~0.70: el modelo
  pierde ~30% de los positivos. Esto se documenta en
  `docs/model-evaluation/report.md` y se mencion explicitamente en la
  vista Clasificador (matriz de confusion + recall por clase).

## Historial de ejecuciones
| Fecha | Quien | Resultado | Notas |
|-------|-------|----------|-------|
