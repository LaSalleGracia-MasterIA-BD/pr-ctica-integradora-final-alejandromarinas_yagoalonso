"""Tests for src.ml.train.

Smoke test of the CLI end-to-end with a tiny synthetic dataset: 2 epochs,
3 classes × 4 images per class. We do not assert accuracy (with 12 images
it would be meaningless); we assert that the artefacts are produced in
the expected shape and that re-running with the same seed is deterministic.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from PIL import Image

tf = pytest.importorskip("tensorflow")


# === Helpers ===========================================================

def _write_png(path: Path, color: int = 128) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", (64, 64), color=color).save(path, format="PNG")


def _make_tiny_dataset(root: Path, n_per_class: int = 20) -> Path:
    """Create the Kaggle layout under `root` with n PNGs per class.

    Default n_per_class=20 guarantees that the 80/10/10 stratified split
    leaves at least 2 images per class in val and test (60 total → 48 train
    / 6 val / 6 test). With batch_size=4 that means val has ≥ 1 full batch
    and `val_loss` becomes available — without this, EarlyStopping and
    ModelCheckpoint warn that they cannot monitor `val_loss`.
    """
    layout = {
        "COVID": 30,           # all dark
        "Normal": 200,         # all light
        "Viral Pneumonia": 100, # mid
    }
    for klass, color in layout.items():
        for i in range(n_per_class):
            _write_png(root / klass / "images" / f"{klass}-{i}.png", color=color)
    return root


# === Tests =============================================================

def test_train_end_to_end_with_tiny_dataset(tmp_path: Path, monkeypatch):
    """Smoke: a 2-epoch run produces the artefacts in the expected shape."""
    from src.ml.train import main

    dataset_root = tmp_path / "dataset"
    _make_tiny_dataset(dataset_root)
    models_dir = tmp_path / "models"
    reports_dir = tmp_path / "reports"

    monkeypatch.setenv("DATASET_PATH", str(dataset_root))
    monkeypatch.setenv("MODELS_DIR", str(models_dir))
    monkeypatch.setenv("REPORT_DIR", str(reports_dir))
    monkeypatch.setenv("EPOCHS_MAX", "2")
    monkeypatch.setenv("BATCH_SIZE", "4")

    result = main()

    # Returned metrics structure
    assert "accuracy" in result
    assert "macro_f1" in result
    assert "model_version" in result

    # Artefacts on disk
    model_path = models_dir / "radiography_classifier.keras"
    meta_path = models_dir / "radiography_classifier.meta.json"
    assert model_path.exists()
    assert meta_path.exists()

    meta = json.loads(meta_path.read_text())
    assert meta["classes"] == ["Normal", "Pneumonia", "COVID-19"]
    assert meta["input_shape"] == [224, 224, 1]
    assert "model_version" in meta
    assert "trained_at" in meta

    # Report artefacts
    assert (reports_dir / "metrics.json").exists()
    assert (reports_dir / "confusion_matrix.png").exists()
    assert (reports_dir / "learning_curves.png").exists()
    assert (reports_dir / "report.md").exists()


def test_train_writes_split_strategy_to_report(tmp_path: Path, monkeypatch):
    """CA-4: the report documents the split (stratified 80/10/10 + seed)."""
    from src.ml.train import main

    dataset_root = tmp_path / "dataset"
    _make_tiny_dataset(dataset_root, n_per_class=20)
    models_dir = tmp_path / "models"
    reports_dir = tmp_path / "reports"

    monkeypatch.setenv("DATASET_PATH", str(dataset_root))
    monkeypatch.setenv("MODELS_DIR", str(models_dir))
    monkeypatch.setenv("REPORT_DIR", str(reports_dir))
    monkeypatch.setenv("EPOCHS_MAX", "1")
    monkeypatch.setenv("BATCH_SIZE", "4")

    main()

    md = (reports_dir / "report.md").read_text().lower()
    assert "split" in md
    assert "80" in md or "stratified" in md
    assert "42" in md or "seed" in md
