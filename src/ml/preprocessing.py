"""Preprocesado de imagenes para el clasificador de radiografias.

`preprocess_for_inference` es el unico contrato compartido entre entrenamiento
y serving. Todo lo que toque una entrada del modelo DEBE pasar por aqui; asi
evitamos el clasico bug de train-serve skew (distinta normalizacion o resize
en entrenamiento frente a produccion).

El pipeline de augmentation (usado solo en entrenamiento) excluye intencionadamente
RandomFlip: voltear horizontalmente una radiografia de torax invertiria la
lateralidad anatomica izquierda/derecha y confundiria al modelo sobre el lado
de las lesiones.
"""
from __future__ import annotations

import io
import logging

import numpy as np
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


IMAGE_SIZE: tuple[int, int] = (224, 224)
MIN_IMAGE_DIM: int = 32  # CB-7: por debajo casi seguro no es una radiografia real


class InvalidImageError(ValueError):
    """La imagen no se puede convertir de forma segura en entrada del modelo (CB-3, CB-7)."""


def preprocess_for_inference(image_bytes: bytes) -> np.ndarray:
    """Decodifica + redimensiona + normaliza una imagen a un tensor listo para el modelo.

    Shape de salida: (IMAGE_SIZE[0], IMAGE_SIZE[1], 1), dtype float32, valores
    en [0.0, 1.0]. Escala de grises por diseno (las radiografias son monocromaticas
    y el modelo tiene un unico canal de entrada — ver ADR-005).

    Lanza `InvalidImageError` para payloads vacios, bytes ilegibles o imagenes
    por debajo de `MIN_IMAGE_DIM` en cualquier lado.
    """
    if not image_bytes:
        raise InvalidImageError("Empty image payload")

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError(f"Cannot decode image: {exc}") from exc

    width, height = img.size
    if width < MIN_IMAGE_DIM or height < MIN_IMAGE_DIM:
        raise InvalidImageError(
            f"Image too small ({width}x{height}); minimum is "
            f"{MIN_IMAGE_DIM}x{MIN_IMAGE_DIM}"
        )

    if img.mode != "L":
        img = img.convert("L")
    img = img.resize(IMAGE_SIZE, Image.Resampling.BILINEAR)

    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr.reshape(IMAGE_SIZE[0], IMAGE_SIZE[1], 1)


def build_augmentation_pipeline():
    """Construye el Sequential de data-augmentation usado solo durante el entrenamiento.

    Hace lazy-import de keras para que los tests unitarios que no necesitan
    TF aun puedan importar este modulo. Las augmentations son deliberadamente
    conservadoras y conscientes del dominio radiografico:
        * RandomRotation(+-10 grados): los pacientes no siempre estan perfectamente alineados
        * RandomZoom(+-10%): variabilidad de escala entre maquinas
        * RandomBrightness(+-10%): variabilidad de exposicion
    Notablemente ausente: RandomFlip — ver docstring del modulo.
    """
    from tensorflow import keras  # import local: mantener el modulo ligero

    return keras.Sequential(
        [
            keras.layers.RandomRotation(10 / 360, fill_mode="constant"),
            keras.layers.RandomZoom(0.1, fill_mode="constant"),
            keras.layers.RandomBrightness(0.1),
        ],
        name="radiography_augmentation",
    )
