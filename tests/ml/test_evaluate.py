"""Tests for src.ml.evaluate.generate_report.

Only test the artefacts and shape; the model used is a dummy (random
weights) so accuracy is uninformative — we don't assert any numeric
performance here.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

tf = pytest.importorskip("tensorflow")
plt = pytest.importorskip("matplotlib.pyplot")

from src.ml.dataset import CLASSES
from src.ml.evaluate import generate_report
from src.ml.model import build_model


def _tiny_dataset(n_per_class: int = 4):
    """Build a tiny tf.data.Dataset with random images for evaluation."""
    images = np.random.RandomState(0).rand(n_per_class * 3, 224, 224, 1).astype(np.float32)
    labels = np.array([0] * n_per_class + [1] * n_per_class + [2] * n_per_class)
    return tf.data.Dataset.from_tensor_slices((images, labels)).batch(4)


def _fake_history():
    """Fake keras History-like dict for the learning-curves plot."""
    return {
        "loss": [1.2, 0.9, 0.7, 0.6],
        "val_loss": [1.3, 1.0, 0.8, 0.7],
        "accuracy": [0.3, 0.5, 0.6, 0.7],
        "val_accuracy": [0.3, 0.4, 0.55, 0.65],
    }


def test_generate_report_produces_all_artifacts(tmp_path: Path):
    model = build_model()
    ds = _tiny_dataset()

    generate_report(
        model,
        ds,
        output_dir=tmp_path,
        history=_fake_history(),
        hyperparams={"seed": 42, "epochs": 4, "batch_size": 32},
        model_version="test-v0",
    )

    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "confusion_matrix.png").exists()
    assert (tmp_path / "learning_curves.png").exists()
    assert (tmp_path / "report.md").exists()


def test_metrics_json_includes_per_class_recall_and_confusion_matrix(tmp_path: Path):
    model = build_model()
    ds = _tiny_dataset()

    generate_report(
        model, ds, output_dir=tmp_path, history=_fake_history(),
        hyperparams={"seed": 42}, model_version="test-v0",
    )

    metrics = json.loads((tmp_path / "metrics.json").read_text())

    assert "accuracy" in metrics
    assert "macro_f1" in metrics
    assert "per_class" in metrics
    for cls in CLASSES:
        entry = metrics["per_class"][cls]
        assert "precision" in entry
        assert "recall" in entry
        assert "f1" in entry
    # 3x3 confusion matrix
    cm = metrics["confusion_matrix"]
    assert len(cm) == 3
    assert all(len(row) == 3 for row in cm)


def test_report_md_contains_clinical_analysis_section(tmp_path: Path):
    model = build_model()
    ds = _tiny_dataset()

    generate_report(
        model, ds, output_dir=tmp_path, history=_fake_history(),
        hyperparams={"seed": 42}, model_version="test-v0",
    )

    md = (tmp_path / "report.md").read_text()

    assert "Analisis clinico" in md or "Análisis clínico" in md
    # Mentions the FN-grave clinical hypothesis
    assert "COVID" in md and "recall" in md.lower()


def test_report_md_documents_split_strategy(tmp_path: Path):
    """CA-4: the report must say how the split was made."""
    model = build_model()
    ds = _tiny_dataset()

    generate_report(
        model, ds, output_dir=tmp_path, history=_fake_history(),
        hyperparams={"seed": 42, "split": "stratified-80-10-10"},
        model_version="test-v0",
    )

    md = (tmp_path / "report.md").read_text().lower()
    assert "split" in md
    assert "80" in md or "stratified" in md
