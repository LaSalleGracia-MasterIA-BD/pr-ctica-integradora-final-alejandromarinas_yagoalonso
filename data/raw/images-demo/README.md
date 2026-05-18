# Radiografia de demostracion sintetica (`HOSP-DEMO-001`)

> **AVISO IMPORTANTE**: esta imagen **NO es una radiografia real**.
> Es un fixture tecnico generado con numpy + Pillow para que el
> dashboard arranque con datos.
> - NO usarla como evidencia clinica.
> - NO usarla como "demo de IA" frente a profesores sin advertir
>   explicitamente que es sintetica.
> - El propio dashboard la muestra con un banner de advertencia
>   amarillo cuando la seleccionas en el Clasificador.

## Que es y para que sirve

El bootstrap genera una imagen sintetica con `numpy` + Pillow durante
`docker compose up` y la sube al bucket `radiographies` bajo la key
`HOSP-DEMO-001/HOSP-DEMO-001_xray1.png`, registrandola como
radiografia del paciente `HOSP-DEMO-001`.

Su unico proposito es **tecnico**: que la vista **Clasificador** del
dashboard (`http://localhost:8501`) tenga al menos una radiografia
clasificable out-of-the-box, sin pedir al evaluador que descargue el
dataset (~0.9 GB en la version local utilizada) ni asumir nada sobre
su licencia.

## Para una demo con valor clinico

Sigue el runbook `docs/runbooks/use-real-radiograph-for-demo.md`. En
~3 min subes una radiografia real del dataset descargado localmente
bajo otra key (p. ej. `HOSP-PRES-001/...`). El origen y la licencia
exactos son los que indique el proveedor desde el que descargues:
consultar `docs/runbooks/download-radiography-dataset.md` para la
fuente concreta usada en este proyecto y citarla tal cual. En el
dropdown del Clasificador las imagenes reales **`HOSP-PRES-*` aparecen
primero**, y `HOSP-DEMO-001` queda detras: al seleccionar una
`HOSP-PRES-*` **NO** salta el banner de advertencia sintetica.

## Origen y licencia

- **Generacion**: imagen creada sinteticamente con `numpy` durante el
  bootstrap (ver `src/pipeline/scripts/bootstrap.py`, funcion
  `_generate_demo_radiograph`).
- **Caracteristicas**: PNG 256x256 grayscale, ruido gaussiano +
  gradiente vertical suave + dos elipses oscuras (simulan pulmones).
  NO es una radiografia real. NO se ha extraido de ningun dataset
  publico ni privado.
- **Licencia**: imagen generada por nosotros, sin copyright externo.
  Libre uso dentro del proyecto.

## Por que sintetica y no una imagen del dataset real

- Cualquier imagen del dataset real tiene una licencia y autoria
  concretas (las que indique el proveedor desde el que se descargue).
  Commitearla al repo obliga a citarla tal y como el autor lo publica
  en cada lugar donde se distribuye el codigo, y no aporta nada
  funcionalmente para la demo (la prediccion sera arbitraria
  igualmente porque la imagen es estatica). Una imagen sintetica
  elimina cualquier ambiguedad legal sin coste funcional.
- La demo NO valida la *correccion* del modelo (eso esta en
  `docs/model-evaluation/report.md` con metricas reales sobre el test
  split). La demo solo valida el *flujo end-to-end*: subir imagen,
  pedir prediccion, ver probabilidades, persistir en MongoDB.

## Como se prueba

Tras `docker compose up`, la imagen aparece en el dropdown del
Clasificador como `HOSP-DEMO-001/HOSP-DEMO-001_xray1.png`. Cuando no
hay `HOSP-PRES-*` cargadas, es la primera opcion seleccionable; si el
dataset Kaggle esta presente localmente y el bootstrap registra las
`HOSP-PRES-*`, estas se anteponen y `HOSP-DEMO-001` queda detras. Al
pulsar "Clasificar", el modelo devuelve una clase arbitraria con sus
probabilidades — el flujo funciona aunque la prediccion no tenga
sentido clinico para esta imagen sintetica.

## Si quieres usar una radiografia real para la demo

1. Descarga el dataset siguiendo `docs/runbooks/download-radiography-dataset.md`.
2. Sube manualmente una imagen al bucket via `docker compose exec ...`
   o `mc cp`.
3. Inserta un paciente en MongoDB que la referencie.
4. La radiografia real aparecera en el dropdown **antes** que
   `HOSP-DEMO-001` (las `HOSP-PRES-*` se priorizan en el orden).

No documentamos ese flujo aqui porque es opcional y especifico del
evaluador.
