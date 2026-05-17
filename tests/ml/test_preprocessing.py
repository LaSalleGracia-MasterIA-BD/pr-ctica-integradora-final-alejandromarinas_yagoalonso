"""Tests for src.ml.preprocessing.

Two contracts matter most: the same `preprocess_for_inference` is used in
training and serving (no train-serve skew), and small/garbage inputs are
rejected explicitly (CB-3, CB-7).
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.ml.preprocessing import (
    IMAGE_SIZE,
    MIN_IMAGE_DIM,
    InvalidImageError,
    preprocess_for_inference,
)


def _make_png_bytes(size: tuple[int, int], mode: str = "L") -> bytes:
    img = Image.new(mode, size, color=128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_preprocess_returns_correct_shape_dtype_range():
    raw = _make_png_bytes((224, 224))

    x = preprocess_for_inference(raw)

    assert x.shape == (IMAGE_SIZE[0], IMAGE_SIZE[1], 1)
    assert x.dtype == np.float32
    assert x.min() >= 0.0
    assert x.max() <= 1.0


def test_preprocess_grayscale_conversion_from_rgb():
    raw = _make_png_bytes((100, 100), mode="RGB")

    x = preprocess_for_inference(raw)

    assert x.shape == (IMAGE_SIZE[0], IMAGE_SIZE[1], 1)
    # All values lie in [0, 1] regardless of input mode
    assert np.all((x >= 0.0) & (x <= 1.0))


def test_preprocess_resizes_smaller_input_up_to_image_size():
    raw = _make_png_bytes((MIN_IMAGE_DIM, MIN_IMAGE_DIM))  # exactly the threshold

    x = preprocess_for_inference(raw)

    assert x.shape == (IMAGE_SIZE[0], IMAGE_SIZE[1], 1)


def test_preprocess_rejects_image_too_small():
    raw = _make_png_bytes((MIN_IMAGE_DIM - 1, MIN_IMAGE_DIM - 1))

    with pytest.raises(InvalidImageError) as exc_info:
        preprocess_for_inference(raw)
    assert "small" in str(exc_info.value).lower() or "32" in str(exc_info.value)


def test_preprocess_rejects_one_by_one_dummy():
    """The bootstrap's 17 dummy PNGs are 1x1 and must NOT be classifiable."""
    raw = _make_png_bytes((1, 1))

    with pytest.raises(InvalidImageError):
        preprocess_for_inference(raw)


def test_preprocess_rejects_garbage_bytes():
    with pytest.raises(InvalidImageError):
        preprocess_for_inference(b"not a png at all")


def test_preprocess_rejects_empty_bytes():
    with pytest.raises(InvalidImageError):
        preprocess_for_inference(b"")


def test_preprocess_is_deterministic_for_same_input():
    raw = _make_png_bytes((100, 100))

    x1 = preprocess_for_inference(raw)
    x2 = preprocess_for_inference(raw)

    np.testing.assert_array_equal(x1, x2)


def test_training_pipeline_does_not_use_horizontal_flip():
    """A horizontal flip would invert left/right anatomy on a chest X-ray."""
    from src.ml.preprocessing import build_augmentation_pipeline

    aug = build_augmentation_pipeline()

    # Inspect the keras Sequential's layer types
    layer_types = [type(layer).__name__ for layer in aug.layers]
    assert "RandomFlip" not in layer_types, (
        "RandomFlip would invert anatomical left/right and must not be used"
    )
