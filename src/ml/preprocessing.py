"""Image preprocessing for the radiography classifier.

`preprocess_for_inference` is the single contract shared between training
and serving. Anything that touches a model input MUST go through it; this
is how we avoid the classic train-serve skew bug (different normalisation
or resize in training vs. production).

The augmentation pipeline (used only in training) intentionally excludes
RandomFlip: flipping a chest X-ray horizontally would invert anatomical
left/right and confuse the model about lesion sides.
"""
from __future__ import annotations

import io
import logging

import numpy as np
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


IMAGE_SIZE: tuple[int, int] = (224, 224)
MIN_IMAGE_DIM: int = 32  # CB-7: smaller than this is almost certainly not a real X-ray


class InvalidImageError(ValueError):
    """Image cannot be safely turned into a model input (CB-3, CB-7)."""


def preprocess_for_inference(image_bytes: bytes) -> np.ndarray:
    """Decode + resize + normalise an image to a model-ready tensor.

    Output shape: (IMAGE_SIZE[0], IMAGE_SIZE[1], 1), dtype float32, values
    in [0.0, 1.0]. Grayscale by design (X-rays are monochromatic and the
    model has a single input channel — see ADR-005).

    Raises `InvalidImageError` for empty payloads, unreadable bytes, or
    images below `MIN_IMAGE_DIM` per side.
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
    """Build the data-augmentation Sequential used during training only.

    Lazy-imports keras so unit tests that don't need TF can still import
    this module. The augmentations are deliberately conservative and
    radiography-aware:
        * RandomRotation(±10°): patients are not always perfectly aligned
        * RandomZoom(±10%): scale variability between machines
        * RandomBrightness(±10%): exposure variability
    Notably absent: RandomFlip — see module docstring.
    """
    from tensorflow import keras  # local import: keep module light-weight

    return keras.Sequential(
        [
            keras.layers.RandomRotation(10 / 360, fill_mode="constant"),
            keras.layers.RandomZoom(0.1, fill_mode="constant"),
            keras.layers.RandomBrightness(0.1),
        ],
        name="radiography_augmentation",
    )
