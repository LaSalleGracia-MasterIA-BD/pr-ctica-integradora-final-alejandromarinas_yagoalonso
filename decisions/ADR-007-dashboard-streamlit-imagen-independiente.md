# ADR-007: Streamlit + imagen Docker independiente para el dashboard

> Estado: accepted
> Fecha: 2026-05-17
> Supersede: —

## Contexto

La feature 4 (`dashboard`) requiere una aplicacion web que sirva como
frontend visible durante la presentacion + auditoria operativa del
sistema. La spec exige:

- Servicio Docker mas dentro de `docker-compose.yml`, levantado con
  el mismo `docker compose up` del resto del sistema (RNF-1)
- Construir la imagen en < 3 minutos y arrancar en < 15 segundos
  (RNF-5)
- 5 vistas (Overview, Calidad, Pacientes, Clasificador, Runs) con
  graficos, tablas y un boton de inferencia

Hay dos decisiones que se toman conjuntamente en este ADR porque
estan acopladas:

1. **Que framework de UI** (Streamlit / Dash / Reflex / React /
   HTML vanilla / etc)
2. **Que imagen Docker** (reutilizar `hospital-pipeline:latest` —
   que ya tiene Python 3.11 + httpx + matplotlib + pillow + TF +
   PySpark — o crear `hospital-dashboard:latest` ligera)

## Decision

**Streamlit 1.36** en un servicio Docker **independiente**
(`hospital-dashboard:latest`) con `Dockerfile.dashboard` propio,
construido sobre `python:3.11-slim` y con
`requirements-dashboard.txt` minimo (~240 MB de imagen final frente
a los ~2 GB de `hospital-pipeline:latest`).

El servicio escucha en el puerto 8501 (default de Streamlit) y
consume exclusivamente la API REST via `httpx` (sin acceso directo
a MongoDB, SQLite ni MinIO).

## Alternativas consideradas

### Sobre el framework UI

| Opcion | Pros | Contras |
|--------|------|---------|
| **Streamlit (elegida)** | Python-only (alineado con el resto del proyecto); sintaxis declarativa muy breve; `st.navigation` da multipagina nativa; comunidad amplia en demos academicas; alta densidad de widgets utiles (tablas, charts, sliders) en pocas lineas | "Vibe" notebook-like; layout limitado vs CSS puro; el script se re-ejecuta entero en cada interaccion (mitigado con `st.cache_data`) |
| Plotly Dash | Mas profesional visualmente; orientado a dashboards reales; los charts son de primera clase | Sintaxis basada en callbacks mucho mas verbosa; curva de aprendizaje mayor; iteracion mas lenta |
| Reflex (antes Pynecone) | Genera React desde Python; UI moderna; full-stack | Comunidad pequena; menos battle-tested; el equipo no lo ha usado antes |
| React + Next.js | UI muy profesional; ecosistema enorme; control total | Otro stack que el equipo no domina (Alejandro va con Python en el Master); 3x mas tiempo de implementacion para esta entrega |
| HTML + JS vanilla servido por FastAPI | Cero dependencias nuevas | Muchisimo boilerplate; sin componentes de chart serios; no aporta nada profesional para un proyecto de Master |

**Por que Streamlit gana:** quedan 3 dias hasta la entrega
(2026-05-20), Streamlit es el framework con mejor relacion
"lineas de codigo / valor visible" para alguien que ya programa en
Python. La spec no pide UX premium, pide demo funcional.

### Sobre la imagen Docker

| Opcion | Pros | Contras |
|--------|------|---------|
| **Imagen independiente (elegida)** | Imagen base 240 MB (sin TF, sin PySpark, sin Java, sin Pillow); arranque <15s; build <2 min; el dashboard no se acopla al ciclo de rebuild del pipeline cada vez que cambia ML; cumple RNF-5 holgadamente | Otro Dockerfile mas; duplica `python:3.11-slim` en disco si Docker no comparte capas (en la practica lo hace) |
| Reutilizar `hospital-pipeline:latest` | Una sola imagen para todo el stack; cero archivos nuevos | Imagen de 2 GB para servir 5 vistas simples; arranque >20s porque streamlit espera a que importemos lo necesario (y el container ya cargo TF antes); cada vez que se reentrena ML y se rebuilda la imagen, el dashboard se "rebuilda" tambien sin razon |
| Imagen `node:20-alpine` + dashboard JS | Inmejorable peso/perf para servir HTML | Saca todo el stack de Python — no aplica si elegimos Streamlit |

**Por que imagen independiente gana:** RNF-5 (build <3min, arranque
<15s) es complicado con la imagen del pipeline (TF tarda ~5s solo en
importarse al arrancar). Una imagen ligera elimina riesgo. El coste
de un Dockerfile + requirements adicional es trivial (cabe en 20
lineas total).

## Consecuencias

**Positivas:**
- (+) **Arranque rapido**: < 15s con holgura. Esto importa porque el
  evaluador hace `docker compose up` y espera que todo este listo
  cuando termine
- (+) **Implementacion rapida**: Streamlit corta ~70% del tiempo de
  implementacion vs React. A 3 dias de entrega, es decisivo
- (+) **Iteracion visual rapida**: cambiar layout en Streamlit es
  cambiar 1-2 lineas Python; el equipo (Alejandro + Yago) puede
  modificarlo sin saber CSS
- (+) **Stack coherente**: todo el proyecto es Python; un solo
  lenguaje en el codebase facilita revision y mantenimiento
- (+) **Cero acoplamiento con el resto del pipeline**: el dashboard
  vive en su propia imagen, su propio requirements, su propio
  Dockerfile
- (+) **Encaja con el encuadre de producto "Centro de Control
  Hospitalario"**: un unico `docker compose up` levanta pipeline +
  API + watcher + dashboard, y la barra persistente de estado del
  sistema en el sidebar hace visible la salud del stack desde
  cualquier vista

**Negativas:**
- (-) **UI "Streamlit-y"**: el evaluador puede notar que es una demo
  notebook-like, no una app web "de producto". Mitigacion:
  `st.set_page_config(page_title=..., layout="wide")` +
  `.streamlit/config.toml` con paleta sobria (primaryColor `#2563EB`,
  fondo blanco) + cero emojis (convencion ASCII del repo) da una
  imagen razonablemente profesional para un proyecto academico
- (-) **Re-ejecucion del script en cada interaccion**: cualquier
  click recarga el script entero. Mitigacion: `st.cache_data(ttl=10s)`
  en todas las queries GET (`ttl=60s` en `/model/evaluation`); los
  POST (classify) se sirven con `st.spinner` para que el usuario vea
  progreso
- (-) **Mantener dos imagenes Docker en el repo**: cada cambio en
  python version o pillow obliga a actualizar ambas. Mitigacion:
  esta entrega no requiere mantenimiento continuo; el coste real
  es despreciable
- (-) **El servicio dashboard depende del servicio api healthy** —
  si la API tarda en arrancar, el dashboard tambien. Esto es
  correcto (no hay nada que mostrar sin API) pero hay que tenerlo
  en cuenta para el orden de arranque

## Requisitos relacionados

- **Spec `dashboard`:**
  - RNF-1 (servicio Docker dentro del compose)
  - RNF-2 (sin estado propio)
  - RNF-5 (build <3min, arranque <15s)
  - RNF-6 (navegador moderno)
- **CLAUDE.md del proyecto:** ya mencionaba Streamlit como dashboard
  candidato — este ADR formaliza la decision y la justifica

## Notas

Si en una iteracion futura el proyecto necesita una UI de produccion
con auth, multi-usuario, control de roles y look corporativo, se
reabre la decision con un ADR-NNN que proponga Next.js + Tailwind.
Para esta entrega, Streamlit basta.
