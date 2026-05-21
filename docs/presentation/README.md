# Presentación final — defensa del Máster

> Fichero: `presentation.html` (reveal.js, HTML estático, sin build).
> Duración objetivo: **12 minutos** + Q&A.
> Audiencia: tribunal del Máster en AI & Big Data.

## Cómo abrirla

```bash
open docs/presentation/presentation.html
```

O, si prefieres servirla por HTTP (necesario si tu navegador bloquea los plugins
de reveal.js desde `file://` por CORS):

```bash
python3 -m http.server 8080 --directory docs/presentation
# luego abre: http://localhost:8080/presentation.html
```

reveal.js + el resto de plugins se cargan desde CDN (jsdelivr). Necesita conexión.

### Si no tienes conexión el día de la presentación

Hay un **fallback en Markdown plano** en `docs/presentation/fallback.md` con el
mismo contenido por slide. Se lee con cualquier visor de Markdown (VSCode,
GitHub, `glow`, `mdcat`) y no depende de internet ni de JavaScript. Ábrelo
si reveal.js no carga.

Si prefieres servir reveal.js localmente para evitar el CDN, descarga el bundle
a `docs/presentation/vendor/reveal.js-5.1.0/` y cambia las URLs `<link>` y
`<script>` de `presentation.html` por rutas locales relativas.

## Atajos de teclado durante la presentación

| Tecla | Acción |
|---|---|
| `Espacio` / `Flecha derecha` | Siguiente slide |
| `Flecha izquierda` | Slide anterior |
| `S` | Abrir **vista de speaker** (notas + cronómetro + preview del siguiente) |
| `F` | Pantalla completa |
| `Esc` o `O` | Vista general (overview) de todos los slides |
| `B` | Pantalla en negro (pausar visualmente) |
| `?` | Ayuda de atajos |

La **vista de speaker** (`S`) es lo más útil: muestra las notas detalladas con el
cronómetro objetivo de cada slide. Se abre en una ventana aparte; ideal con dos
pantallas (la principal proyecta los slides, la secundaria muestra las notas).

## Estructura — 12 minutos de contenido + Q&A

| # | Slide | Tema | Tiempo objetivo |
|---|-------|------|---|
| 1 | Portada | Identidad + autoría | 0:00 - 0:30 |
| 2 | El problema | Tres fuentes fragmentadas | 0:30 - 1:15 |
| 3 | Qué pedía el enunciado | 8 ejes + cómo los cubrimos | 1:15 - 2:00 |
| 4 | Arquitectura general | Diagrama + 7 servicios Docker | 2:00 - 3:00 |
| 5 | Datos | Persistencia poliglota (Mongo + SQLite + MinIO) | 3:00 - 3:45 |
| 6 | Pipeline ETL | Etapas + idempotencia + performance | 3:45 - 4:30 |
| 7 | Modelo CNN | Arquitectura + métricas (acc 0,8766, macro-F1 0,8594) | 4:30 - 5:30 |
| 8 | Threshold COVID 0,35 | ADR-010, +12,5 pp recall vs baseline argmax 0,695 | 5:30 - 6:30 |
| 9 | Triaje por reglas | ADR-008, sin ground truth → reglas IF-THEN | 6:30 - 7:15 |
| 10 | Alertas + informe | ADR-009, vista derivada, CLI idempotente | 7:15 - 8:00 |
| 11 | **Dashboard / demo** | 7 vistas, demo en vivo | 8:00 - 11:00 |
| 12 | IA + SDD | Eje obligatorio del enunciado | 11:00 - 11:45 |
| 13 | Ética + limitaciones | Datos sintéticos, asistencia, no diagnóstico | 11:45 - 12:30 |
| 14 | Conclusión + Q&A | Tres cifras finales, trabajo futuro, preguntas | 12:30 - cierre |

## Preflight checklist — antes de presentar

Ejecutar 30 minutos antes (margen para imprevistos):

### Paso 1 — Arrancar el stack

Para una **demo limpia** (recomendado el día de la presentación, garantiza
estado conocido y reproducible):

```bash
docker compose down -v && docker compose up -d --build
```

Esto borra los volúmenes de Mongo, MinIO y SQLite, reconstruye las imágenes
si han cambiado y lanza el bootstrap desde cero. El bootstrap registra los
`HOSP-PRES-*` reales **solo si** el dataset Kaggle está en
`data/raw/covid_radiography/`.

Para una **demo rápida** (si quieres conservar volúmenes con datos previos):

```bash
docker compose up -d
docker compose run --rm pipeline          # reejecuta el bootstrap idempotente
```

La segunda línea es importante: garantiza que `bootstrap.py` vuelva a pasar
por el bloque que registra `HOSP-PRES-001..006` si el dataset apareció
localmente entre arranques. El bootstrap es idempotente: si las `HOSP-PRES-*`
ya están registradas, no las duplica.

### Paso 2 — Healthchecks

```bash
docker compose ps                 # todo healthy

# API + modelo
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
# Esperado: {"status": "ok", "predictor_loaded": true}

# Dashboard
curl -sI http://localhost:8501/_stcore/health | head -1
# Esperado: HTTP/1.1 200 OK
```

### Paso 3 — Datos cargados

```bash
# Total de pacientes
curl -s "http://localhost:8000/api/v1/patients?limit=1" | python3 -c \
  "import sys,json; print('Total pacientes:', json.load(sys.stdin)['total'])"
# Esperado: ~4.790 (el numero exacto depende de la generacion sintetica)

# Radiografías HOSP-PRES-* (solo si tienes el dataset Kaggle descargado)
curl -s "http://localhost:8000/api/v1/radiographies?limit=50" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); \
   print('HOSP-PRES en bucket:', sum(1 for it in d['items'] \
   if it['minio_object_key'].startswith('HOSP-PRES-')))"
# Esperado: 6 (si es 0, harás la demo con HOSP-DEMO-001 sintética avisando)
```

## Plan B si algo falla durante la demo

| Síntoma | Causa probable | Acción inmediata |
|---|---|---|
| Dashboard pinta "API no disponible" en todas las vistas | `hospital-api` parado | `docker compose start api`; mientras tanto, enseñar que los chips del sidebar pasan a rojo/gris correctamente como ejemplo de manejo de errores |
| Chip "Modelo" en rojo | `data/models/radiography_classifier.keras` no se cargó | `docker compose up -d --force-recreate api`; si no hay tiempo, ir directo al slide 10 |
| Clasificador devuelve 422 con una imagen | CB-7: imagen demasiado pequeña | Elegir otra `HOSP-PRES-*` del dropdown |
| No hay `HOSP-PRES-*` en el dropdown | Dataset Kaggle no descargado | Usar `HOSP-DEMO-001` y **avisar** explícitamente que es sintética |
| El navegador no carga `http://localhost:8501` | Puerto ocupado | `lsof -i :8501` y matar el proceso, o reiniciar `dashboard` |
| Conexión a internet caída (CDN de reveal.js no carga) | Sin red | Tener el repo abierto en VSCode con la memoria técnica como respaldo |

Detalle completo del recorrido en `docs/runbooks/presentation-demo.md`.

## Ensayos recomendados

- **Ensayo 1**: lectura en voz alta con cronómetro mirando solo las notas.
- **Ensayo 2**: con el dashboard arriba, hacer la demo del slide 9 sin mirar las notas.
- **Ensayo 3**: completo, con interrupciones simuladas (parar `api`, recuperar).

## Edición de la presentación

El fichero es **HTML plano + reveal.js desde CDN**. Para editar contenido, abre
`presentation.html` y modifica los `<section>` dentro de `<div class="slides">`.
Las notas del presentador van en `<aside class="notes">...</aside>`. El cronómetro
de cada slide está al inicio de la nota, entre corchetes (ej. `[2:30 - 4:00]`).
