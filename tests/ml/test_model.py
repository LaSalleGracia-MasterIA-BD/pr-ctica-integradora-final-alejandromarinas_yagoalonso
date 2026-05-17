"""Tests for src.ml.model.build_model.

Smoke tests that ensure the architecture matches the design (ADR-005):
4 Conv2D `padding="same"` + MaxPool blocks, Dropout, Flatten, Dense, softmax.
"""
from __future__ import annotations

import numpy as np
import pytest

tf = pytest.importorskip("tensorflow")

from src.ml.model import build_model


def test_build_model_returns_compiled_keras_model():
    model = build_model()

    assert isinstance(model, tf.keras.Model)
    assert model.optimizer is not None
    assert model.loss == "sparse_categorical_crossentropy"


def test_forward_pass_with_dummy_input_returns_softmax_3_classes():
    model = build_model(num_classes=3)
    dummy = np.zeros((2, 224, 224, 1), dtype=np.float32)

    out = model.predict(dummy, verbose=0)

    assert out.shape == (2, 3)
    # Softmax rows sum to ~1.0
    np.testing.assert_allclose(out.sum(axis=1), [1.0, 1.0], atol=1e-5)


def test_intermediate_shapes_match_design():
    """224 → 112 → 56 → 28 → 14 — only achievable with padding='same'."""
    model = build_model()

    expected_filters = [32, 64, 128, 128]
    expected_spatial = [112, 56, 28, 14]
    pool_idx = 0
    for layer in model.layers:
        if isinstance(layer, tf.keras.layers.MaxPooling2D):
            out_shape = layer.output.shape  # (None, h, w, c)
            assert out_shape[1] == expected_spatial[pool_idx], (
                f"MaxPool {pool_idx} spatial={out_shape[1]} but expected "
                f"{expected_spatial[pool_idx]} — padding must be 'same'"
            )
            assert out_shape[3] == expected_filters[pool_idx]
            pool_idx += 1
    assert pool_idx == 4, "Expected exactly 4 MaxPooling2D layers"


def test_all_conv_layers_use_padding_same():
    model = build_model()

    conv_layers = [
        layer for layer in model.layers
        if isinstance(layer, tf.keras.layers.Conv2D)
    ]
    assert len(conv_layers) == 4
    for layer in conv_layers:
        assert layer.padding == "same", (
            f"Conv layer {layer.name} has padding={layer.padding!r}, "
            "must be 'same' to keep spatial shapes predictable"
        )


def test_has_flatten_not_global_pooling():
    """Architecture follows the literal Master Block 6 pattern (Flatten)."""
    model = build_model()

    layer_types = [type(layer).__name__ for layer in model.layers]
    assert "Flatten" in layer_types
    assert "GlobalAveragePooling2D" not in layer_types


def test_param_count_is_in_expected_range():
    model = build_model()

    n = model.count_params()
    assert 1_500_000 < n < 2_500_000, (
        f"Expected ~1.8M params per design, got {n:,}"
    )


def test_output_layer_is_softmax_with_num_classes():
    model = build_model(num_classes=3)

    last = model.layers[-1]
    assert isinstance(last, tf.keras.layers.Dense)
    assert last.units == 3
    # Softmax activation, either as the layer's activation or a separate layer
    assert last.activation.__name__ == "softmax"
