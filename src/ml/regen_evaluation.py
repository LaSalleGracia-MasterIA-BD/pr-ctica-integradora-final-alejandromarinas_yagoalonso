"""Regenerate the evaluation artefacts WITHOUT retraining the model.

Loads the persisted .keras artefact, rebuilds the same stratified
test split (seed=42, 80/10/10) used by `train.py`, runs inference and
rewrites:

  * docs/model-evaluation/metrics.json
  * docs/model-evaluation/report.md
  * docs/model-evaluation/confusion_matrix.png

The history (learning curves) is preserved from the previous metrics.json
because we cannot recover Keras History without retraining; the PNG is
left untouched.

Why this script exists: Feature 16 applies a post-hoc decision rule
(`covid_threshold_0.35`) on the model's raw softmax outputs. The metrics
on disk were computed under argmax; this script regenerates them under
the new rule so the docs/model-evaluation/* artefacts reflect what the
API actually serves.

Usage (inside the pipeline container):
    python -m src.ml.regen_evaluation
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import tensorflow as tf

from src.ml.dataset import (
    CLASSES,
    DEFAULT_DATASET_PATH,
    build_splits,
    discover_dataset,
)
from src.ml.evaluate import (
    _apply_threshold_rule,
    _compute_metrics,
    _render_markdown_report,
    _save_confusion_matrix_png,
)
from src.ml.predictor import COVID_THRESHOLD, DECISION_RULE
from src.ml.preprocessing import preprocess_for_inference

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


MODEL_PATH = Path("/app/data/models/radiography_classifier.keras")
META_PATH = Path("/app/data/models/radiography_classifier.meta.json")
OUTPUT_DIR = Path("/app/docs/model-evaluation")


def _load_image(path: Path) -> np.ndarray:
    with open(path, "rb") as f:
        return preprocess_for_inference(f.read())


def _label_to_idx(label: str) -> int:
    return CLASSES.index(label)


def _predict_all(model, items: list, batch_size: int = 32) -> np.ndarray:
    """Return probs of shape (N, 3) in the same order as `items`."""
    probs = np.zeros((len(items), 3), dtype=np.float32)
    batch: list[np.ndarray] = []
    indices: list[int] = []
    for i, (path, _label) in enumerate(items):
        batch.append(_load_image(path))
        indices.append(i)
        if len(batch) == batch_size:
            y = model.predict(np.stack(batch, axis=0), verbose=0)
            for j, idx in enumerate(indices):
                probs[idx] = y[j]
            batch, indices = [], []
    if batch:
        y = model.predict(np.stack(batch, axis=0), verbose=0)
        for j, idx in enumerate(indices):
            probs[idx] = y[j]
    return probs


def main() -> None:
    logger.info("Loading model from %s", MODEL_PATH)
    model = tf.keras.models.load_model(MODEL_PATH)

    logger.info("Discovering dataset at %s", DEFAULT_DATASET_PATH)
    items = discover_dataset(DEFAULT_DATASET_PATH)
    splits = build_splits(items, seed=42, ratios=(0.8, 0.1, 0.1))
    test_items = splits.test
    logger.info("Test split: %d images", len(test_items))

    logger.info("Running inference on the test split...")
    probs = _predict_all(model, test_items)
    y_true = np.array([_label_to_idx(label) for _, label in test_items], dtype=np.int64)

    y_pred_threshold = _apply_threshold_rule(probs)
    y_pred_argmax = np.argmax(probs, axis=1)

    metrics = _compute_metrics(y_true, y_pred_threshold)
    metrics["comparison_argmax"] = _compute_metrics(y_true, y_pred_argmax)

    meta = json.loads(META_PATH.read_text())
    model_version = str(meta.get("model_version", "unknown"))
    metrics["model_version"] = model_version
    metrics["classes"] = list(CLASSES)
    metrics["decision_rule"] = DECISION_RULE
    metrics["covid_threshold"] = COVID_THRESHOLD

    # Preserve hyperparameters from the previous metrics.json if present so
    # the report still documents how the model was trained.
    prev_path = OUTPUT_DIR / "metrics.json"
    if prev_path.exists():
        prev = json.loads(prev_path.read_text())
        if "hyperparameters" in prev:
            metrics["hyperparameters"] = prev["hyperparameters"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    _save_confusion_matrix_png(metrics["confusion_matrix"], OUTPUT_DIR / "confusion_matrix.png")
    (OUTPUT_DIR / "report.md").write_text(
        _render_markdown_report(metrics, metrics.get("hyperparameters", {}), model_version)
    )

    logger.info(
        "Regen done. accuracy=%.4f macro_f1=%.4f decision_rule=%s",
        metrics["accuracy"], metrics["macro_f1"], DECISION_RULE,
    )
    logger.info(
        "Argmax baseline: accuracy=%.4f macro_f1=%.4f (kept under 'comparison_argmax')",
        metrics["comparison_argmax"]["accuracy"],
        metrics["comparison_argmax"]["macro_f1"],
    )


if __name__ == "__main__":
    main()
