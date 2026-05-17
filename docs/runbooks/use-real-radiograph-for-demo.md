# Runbook: Usar una radiografia REAL en la demo del Clasificador

> Ultima verificacion: 2026-05-17
> Responsable: Alejandro Marinas

## Cuando usar este runbook

- **Demo ante profesores / evaluador** del Master.
- Quieres ensenar el Clasificador con una imagen que tenga patron
  clinico real (no `HOSP-DEMO-001`, que es **sintetica** y se
  documenta como tal en la UI).

## Por que el bootstrap NO incluye una radiografia real por defecto

- El bootstrap usa `HOSP-DEMO-001` (256x256 generada con `numpy` +
  Pillow) para que el dashboard funcione out-of-the-box sin pedir
  descarga del dataset ni asumir nada sobre su licencia. Es **fixture
  tecnico, no demo clinica**. Ver `data/raw/images-demo/README.md`.
- El dataset real pesa ~1.5 GB y NO se commitea al repo (`.gitignore`).
  Su origen y licencia exactos son los que indique el proveedor desde
  donde se haya descargado; consultar `docs/runbooks/download-radiography-dataset.md`
  para la fuente concreta usada por este proyecto.

## Prerequisitos

- Stack levantado: `docker compose up -d`
- Dataset descargado siguiendo
  `docs/runbooks/download-radiography-dataset.md`.
  Verificacion: `ls data/raw/covid_radiography/COVID-19_Radiography_Dataset/`

## Pasos

### 1. Elegir una imagen real con valor de demo

Cada clase tiene su carpeta `images/`. Recomendaciones por clase:

- **COVID** → `COVID-1.png` (caso claro, util porque el modelo deberia
  predecir COVID-19 con alta confianza si esta bien entrenado)
- **Normal** → `Normal-1.png`
- **Viral Pneumonia** → `Viral Pneumonia-1.png`

Para la demo basta con UNA imagen. Si la presentacion tiene tiempo,
mostrar las 3 ensena el comportamiento del modelo en cada clase.

### 2. Subir la imagen al bucket MinIO + registrar el paciente en MongoDB

Desde la raiz del repo, con el stack levantado:

```bash
docker compose run --rm --entrypoint "" pipeline python - <<'PY'
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.storage.minio_client import get_minio_client_from_env
from src.pipeline.storage.mongo_writer import get_mongo_writer_from_env

# === EDITAR estas 3 lineas para apuntar a la imagen elegida ===
SRC = Path("/app/data/raw/covid_radiography/COVID-19_Radiography_Dataset/COVID/images/COVID-1.png")
PATIENT_ID = "HOSP-PRES-001"
PRESENTED_AS = "COVID-19"  # solo para el log; el modelo decide
# =============================================================

KEY = f"{PATIENT_ID}/{SRC.name}"

minio = get_minio_client_from_env()
minio.upload_file("radiographies", KEY, SRC)
print(f"OK: subida {KEY} ({SRC.stat().st_size} bytes)")

writer = get_mongo_writer_from_env()
try:
    writer.bulk_upsert_patients([{
        "external_id": PATIENT_ID,
        "name": "Presentacion clinica",
        "birth_date": "1985-06-15",
        "age": 40,
        "gender": "M",
        "blood_type": "O+",
    }])
    writer.add_radiography_to_patient(PATIENT_ID, {
        "minio_object_key": KEY,
        "original_filename": SRC.name,
        "file_size_bytes": SRC.stat().st_size,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "classification": None,
    })
    print(f"OK: paciente {PATIENT_ID} registrado con radiografia real "
          f"(supuesta clase real: {PRESENTED_AS})")
finally:
    writer.close()
PY
```

### 3. Verificar en el Dashboard

1. Abre `http://localhost:8501/classifier`
2. En el dropdown debe aparecer `HOSP-PRES-001/COVID-1.png` (o el
   nombre que hayas elegido). Como el orden alfabetico pone primero
   `HOSP-DEMO-*` y luego `HOSP-PRES-*`, la real queda en segundo
   bloque
3. Selecciona la imagen real. **Confirma que NO aparece la advertencia
   amarilla** de "imagen sintetica de demo" (esa solo sale para keys
   `HOSP-DEMO-*`)
4. Pulsa "Clasificar". El modelo devolvera la clase predicha + las
   probabilidades

### 4. (Opcional) Pre-clasificar varias imagenes antes de la presentacion

Para tener resultados "ya cacheados" en MongoDB y que `GET /classification`
los sirva instantaneamente desde la vista Pacientes:

```bash
for key in HOSP-PRES-001/COVID-1.png HOSP-PRES-002/Normal-1.png HOSP-PRES-003/Viral\ Pneumonia-1.png; do
  curl -s -X POST http://localhost:8000/api/v1/radiographies/classify \
    -H "Content-Type: application/json" \
    -d "{\"minio_object_key\": \"$key\"}" | python3 -m json.tool
done
```

## Si algo sale mal

- **El dropdown no muestra la imagen nueva** tras subir: pulsa el
  boton "Recargar" del Clasificador. Si no aparece, verifica que la
  API la ve: `curl "http://localhost:8000/api/v1/radiographies?limit=500" | grep HOSP-PRES`
- **"Image too small" (422)**: la imagen tiene < 32 px por lado. No
  pasa con las del COVID-19 Radiography Database (todas son 299x299),
  pero por si acaso.
- **No tienes el dataset descargado**: tienes 5-15 min de descarga +
  ~1.5 GB de disco antes de poder hacer demo real. Considera la
  sintetica solo si el evaluador acepta la advertencia.

## Notas eticas

- Usa una imagen real del dataset descargado localmente, documentando
  la fuente y licencia exactas indicadas por el proveedor del dataset.
  Antes de publicar capturas/demos hacia fuera (web, redes, paper),
  verifica los terminos concretos de la fuente original donde lo
  descargaste (Kaggle, Figshare, mirror oficial, etc.) y citalos tal
  cual los publica el autor. NO asumas una licencia generica
- El modelo se entrega como **asistencia diagnostica** (RNF-2 de
  `specs/clasificacion-radiografias.md`), NO como diagnostico final.
  Ningun paciente real deberia ser tratado en base a una prediccion
  del modelo sin revision clinica humana

## Historial de ejecuciones
| Fecha | Quien | Resultado | Notas |
|-------|-------|----------|-------|
