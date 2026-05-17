# Runbook: Descargar dataset real de radiografias (COVID-19 Radiography Database)

> Ultima verificacion: 2026-05-16
> Responsable: Alejandro Marinas

## Cuando usar este runbook
- Cuando vayamos a **entrenar el modelo de clasificacion** de radiografias (feature 2 del backlog, spec `clasificacion-radiografias`)
- Cuando queramos hacer una demo con imagenes medicas reales en lugar de los PNGs dummy 1x1 del bootstrap
- **No hace falta** para correr los tests del dia a dia ni el pipeline ETL: esos funcionan con los PNGs generados por `src/pipeline/scripts/generate_dummy_images.py`

## Prerequisitos
- Cuenta en Kaggle (gratuita)
- [Kaggle API instalada](https://github.com/Kaggle/kaggle-api): `pip install kaggle`
- Token de Kaggle en `~/.kaggle/kaggle.json` (Settings → API → Create New Token)
- Aceptar las condiciones del dataset en https://www.kaggle.com/datasets/tawsifurrahman/covid19-radiography-database (entrar a la pagina al menos una vez con el navegador)

## Pasos

1. Configurar permisos del token (solo primera vez):
   ```bash
   chmod 600 ~/.kaggle/kaggle.json
   ```

2. Crear el directorio destino (ya esta en `.gitignore`):
   ```bash
   mkdir -p data/raw/covid_radiography
   ```

3. Descargar el dataset (~1 GB comprimido, ~1.5 GB descomprimido):
   ```bash
   cd data/raw/covid_radiography
   kaggle datasets download -d tawsifurrahman/covid19-radiography-database
   ```

4. Descomprimir (el zip crea una carpeta `COVID-19_Radiography_Dataset/` dentro):
   ```bash
   unzip covid19-radiography-database.zip
   rm covid19-radiography-database.zip
   ```

5. Estructura esperada tras descomprimir (cada clase tiene `images/` y `masks/`; **nosotros solo usamos `images/`**, `masks/` se ignora):
   ```
   data/raw/covid_radiography/
   └── COVID-19_Radiography_Dataset/
       ├── COVID/
       │   ├── images/          # 3.616 PNGs   ← clasificada como COVID-19
       │   └── masks/           # ignorado
       ├── Normal/
       │   ├── images/          # 10.192 PNGs  ← clasificada como Normal
       │   └── masks/           # ignorado
       ├── Viral Pneumonia/
       │   ├── images/          # 1.345 PNGs   ← clasificada como Pneumonia
       │   └── masks/           # ignorado
       └── Lung_Opacity/
           ├── images/          # 6.012 PNGs   ← DESCARTADA (no encaja en
           │                                     la clasificacion triple
           │                                     Normal/Pneumonia/COVID-19)
           └── masks/           # ignorado
   ```

## Verificacion

```bash
# 4 carpetas de clase
ls data/raw/covid_radiography/COVID-19_Radiography_Dataset/
# Debe mostrar: COVID  Lung_Opacity  Normal  'Viral Pneumonia'

# Subcarpetas images existen en cada clase
find data/raw/covid_radiography -maxdepth 4 -name "images" -type d
# Debe listar 4 paths terminados en /images

# Conteo total de imagenes (~21 K incluyendo Lung_Opacity, ~15 K sin ella)
find data/raw/covid_radiography -path "*/images/*.png" | wc -l
# Esperado: 21165 (todo)

# Conteo solo de las 3 clases que usamos (~15 K)
find data/raw/covid_radiography/COVID-19_Radiography_Dataset/COVID/images \
     data/raw/covid_radiography/COVID-19_Radiography_Dataset/Normal/images \
     data/raw/covid_radiography/COVID-19_Radiography_Dataset/Viral\ Pneumonia/images \
     -name "*.png" | wc -l
# Esperado: ~15153 (3616 + 10192 + 1345)
```

## Variable de configuracion

El modulo `src/ml/dataset.py` lee la raiz del dataset desde la variable de
entorno **`DATASET_PATH`**, con default
`/app/data/raw/covid_radiography/COVID-19_Radiography_Dataset` (dentro
del contenedor `pipeline`). En el host, esa ruta se monta como
`./data/raw/covid_radiography/COVID-19_Radiography_Dataset` (ver
`docker-compose.yml`, servicio `pipeline`, volumen `data/raw:ro`).

## Si algo sale mal

- **Error 401 Unauthorized**: el token no es valido o no esta en `~/.kaggle/kaggle.json`
- **Error 403 Forbidden**: primero hay que aceptar las condiciones del dataset en la pagina de Kaggle
- **Descarga lenta**: la Kaggle API descarga en serie. Es normal que tarde 5-15 minutos
- **`DatasetNotFoundError` al ejecutar `train.py`**: verificar que `DATASET_PATH` apunta a la carpeta que contiene las subcarpetas de clase (`COVID/`, `Normal/`, `Viral Pneumonia/`), no a la carpeta inmediatamente superior

## Notas sobre uso

- **No se commitea al repo** (`data/raw/covid_radiography/` esta en `.gitignore`)
- Cada miembro del equipo descarga su copia local
- `Lung_Opacity` se descarta — la spec de clasificacion es triple
  (`Normal` / `Pneumonia` / `COVID-19`)
- Las mascaras (`masks/`) se ignoran — no las necesitamos para clasificacion

## Historial de ejecuciones
| Fecha | Quien | Resultado | Notas |
|-------|-------|----------|-------|
