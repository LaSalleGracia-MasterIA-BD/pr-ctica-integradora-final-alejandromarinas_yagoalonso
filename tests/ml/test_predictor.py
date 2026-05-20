"""Tests for src.ml.predictor.Predictor.

Use a tiny model trained on the fly for two epochs over synthetic data so
the test is hermetic (no real model checkpoint needed) but still exercises
the load → preprocess → predict → result path end to end.
"""
from __future__ import annotations

import io
import json
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

tf = pytest.importorskip("tensorflow")

from src.ml.dataset import CLASSES
from src.ml.model import build_model
from src.ml.predictor import (
    COVID_CLASS,
    COVID_THRESHOLD,
    DECISION_RULE,
    ModelNotAvailableError,
    Predictor,
    Prediction,
)


def _png_bytes(size: tuple[int, int] = (224, 224), color: int = 128) -> bytes:
    img = Image.new("L", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def tiny_trained_model_path(tmp_path: Path) -> tuple[Path, Path]:
    model = build_model()
    # Two-epoch fit over synthetic data so the model has non-random weights
    x = np.random.RandomState(0).rand(12, 224, 224, 1).astype(np.float32)
    y = np.array([i % 3 for i in range(12)])
    model.fit(x, y, epochs=2, batch_size=4, verbose=0)

    model_path = tmp_path / "test_model.keras"
    meta_path = tmp_path / "test_model.meta.json"
    model.save(model_path)
    meta_path.write_text(json.dumps({
        "model_version": "test-v1.0",
        "classes": list(CLASSES),
        "input_shape": [224, 224, 1],
    }))
    return model_path, meta_path


def test_predictor_raises_model_not_available_if_files_missing(tmp_path: Path):
    with pytest.raises(ModelNotAvailableError):
        Predictor(
            model_path=tmp_path / "missing.keras",
            meta_path=tmp_path / "missing.meta.json",
        )


def test_predictor_raises_model_not_available_if_only_meta_missing(
    tiny_trained_model_path, tmp_path: Path
):
    model_path, _ = tiny_trained_model_path
    with pytest.raises(ModelNotAvailableError):
        Predictor(model_path=model_path, meta_path=tmp_path / "missing.meta.json")


def test_predict_returns_correct_structure(tiny_trained_model_path):
    model_path, meta_path = tiny_trained_model_path
    predictor = Predictor(model_path=model_path, meta_path=meta_path)

    result = predictor.predict(_png_bytes())

    assert isinstance(result, Prediction)
    assert result.predicted_class in CLASSES
    assert set(result.probabilities.keys()) == set(CLASSES)
    # Probabilities sum to ~1.0
    assert abs(sum(result.probabilities.values()) - 1.0) < 1e-4
    assert all(0.0 <= p <= 1.0 for p in result.probabilities.values())
    assert result.model_version == "test-v1.0"
    assert result.decision_rule == DECISION_RULE


def test_decision_rule_tag_matches_active_threshold():
    """The traceability tag must encode the active threshold."""
    assert COVID_CLASS == "COVID-19"
    assert COVID_THRESHOLD == 0.35
    assert DECISION_RULE == "covid_threshold_0.35"


def test_predicted_class_follows_threshold_rule(tiny_trained_model_path):
    """Given the model's raw probs, predicted_class respects the threshold."""
    model_path, meta_path = tiny_trained_model_path
    predictor = Predictor(model_path=model_path, meta_path=meta_path)

    result = predictor.predict(_png_bytes())
    probs = result.probabilities

    if probs[COVID_CLASS] >= COVID_THRESHOLD:
        assert result.predicted_class == COVID_CLASS
    else:
        non_covid = {c: p for c, p in probs.items() if c != COVID_CLASS}
        assert result.predicted_class == max(non_covid, key=non_covid.get)


def test_predict_propagates_invalid_image_error(tiny_trained_model_path):
    from src.ml.preprocessing import InvalidImageError

    model_path, meta_path = tiny_trained_model_path
    predictor = Predictor(model_path=model_path, meta_path=meta_path)

    with pytest.raises(InvalidImageError):
        predictor.predict(b"not a real png")


def test_predict_rejects_image_too_small(tiny_trained_model_path):
    from src.ml.preprocessing import InvalidImageError

    model_path, meta_path = tiny_trained_model_path
    predictor = Predictor(model_path=model_path, meta_path=meta_path)

    with pytest.raises(InvalidImageError):
        predictor.predict(_png_bytes(size=(1, 1)))


def test_predict_is_thread_safe(tiny_trained_model_path):
    """Concurrent calls must not crash and must return consistent shape.

    The Predictor wraps model.predict in a Lock to serialise concurrent
    callers (TF/Keras predict is not historically thread-safe).
    """
    model_path, meta_path = tiny_trained_model_path
    predictor = Predictor(model_path=model_path, meta_path=meta_path)

    img = _png_bytes()
    results = []
    errors = []

    def worker():
        try:
            r = predictor.predict(img)
            results.append(r)
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 8
    # All results identical since the input is the same
    first = results[0]
    for r in results[1:]:
        assert r.predicted_class == first.predicted_class


def test_predictor_model_version_property(tiny_trained_model_path):
    model_path, meta_path = tiny_trained_model_path
    predictor = Predictor(model_path=model_path, meta_path=meta_path)

    assert predictor.model_version == "test-v1.0"
