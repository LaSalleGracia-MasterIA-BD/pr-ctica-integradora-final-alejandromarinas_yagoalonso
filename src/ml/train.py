"""CLI to train the radiography classifier end-to-end.

Usage (typically inside the `pipeline` container):
    docker compose run --rm pipeline python -m src.ml.train

Strict split usage (see design `clasificacion-radiografias`):
  * `train` → `model.fit` (weight updates)
  * `validation` → callbacks ONLY (EarlyStopping, ModelCheckpoint).
    Never enters the final report
  * `test` → final report ONLY (one-shot evaluation). The model never
    sees this split during training, so the reported metrics are not
    contaminated by hyperparameter selection

Reproducibility (RNF-5): seeds are fixed for Python `random`, NumPy and
TensorFlow. `tf.config.experimental.enable_op_determinism()` is enabled
where available; even so, full bit-for-bit reproducibility is not
guaranteed (documented limitation).
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from src.ml.dataset import CLASSES, build_splits, discover_dataset
from src.ml.evaluate import generate_report
from src.ml.model import build_model

logger = logging.getLogger(__name__)


DEFAULT_MODELS_DIR = Path("/app/data/models")
DEFAULT_REPORT_DIR = Path("/app/docs/model-evaluation")
DEFAULT_IMAGE_SIZE = (224, 224)


# ----------------------------------------------------------------------
# Reproducibility helpers
# ----------------------------------------------------------------------

def _set_global_seed(seed: int) -> None:
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    import tensorflow as tf
    tf.random.set_seed(seed)
    try:
        tf.config.experimental.enable_op_determinism()
    except Exception as exc:  # pragma: no cover  (TF version may not support it)
        logger.warning("enable_op_determinism not available: %s", exc)


# ----------------------------------------------------------------------
# tf.data pipeline
# ----------------------------------------------------------------------

def _load_and_preprocess(path_bytes_tensor, label_idx):
    """tf.py_function wrapper around our shared `preprocess_for_inference`."""
    import tensorflow as tf

    def _py(path_bytes):
        from pathlib import Path as _P

        from src.ml.preprocessing import preprocess_for_inference

        path = _P(path_bytes.numpy().decode("utf-8"))
        x = preprocess_for_inference(path.read_bytes())
        return x.astype(np.float32)

    x = tf.py_function(_py, [path_bytes_tensor], Tout=tf.float32)
    x.set_shape((DEFAULT_IMAGE_SIZE[0], DEFAULT_IMAGE_SIZE[1], 1))
    return x, label_idx


def _build_tf_dataset(items, batch_size: int, augment: bool, shuffle: bool):
    """Build a `tf.data.Dataset` of (image_tensor, class_index) batches."""
    import tensorflow as tf

    from src.ml.preprocessing import build_augmentation_pipeline

    paths = [str(p) for p, _ in items]
    labels = [CLASSES.index(c) for _, c in items]

    ds = tf.data.Dataset.from_tensor_slices((paths, labels))
    if shuffle:
        ds = ds.shuffle(buffer_size=max(64, len(items)), seed=42, reshuffle_each_iteration=True)
    ds = ds.map(_load_and_preprocess, num_parallel_calls=tf.data.AUTOTUNE)
    ds = ds.batch(batch_size)

    if augment:
        aug = build_augmentation_pipeline()
        ds = ds.map(lambda x, y: (aug(x, training=True), y), num_parallel_calls=tf.data.AUTOTUNE)

    return ds.prefetch(tf.data.AUTOTUNE)


# ----------------------------------------------------------------------
# Class weights
# ----------------------------------------------------------------------

def _compute_class_weight(train_items, mode: str = "balanced") -> dict[int, float] | None:
    """Class weights for `model.fit(class_weight=...)`.

    Modes:
      * `balanced` — sklearn standard: w = n_samples / (n_classes * n_in_class).
        Aggressive on heavily imbalanced datasets; the extreme weight for
        the minority class can destabilise training.
      * `sqrt`     — softer version: take the square root of the balanced
        weights and renormalise so the mean weight stays around 1. Damps
        the gradient kicks from minority-class batches.
      * `none`     — return None (caller should pass class_weight=None).
    """
    if mode == "none":
        return None

    from sklearn.utils.class_weight import compute_class_weight

    y_idx = np.array([CLASSES.index(c) for _, c in train_items])
    classes_idx = np.arange(len(CLASSES))
    weights = compute_class_weight(class_weight="balanced", classes=classes_idx, y=y_idx)

    if mode == "sqrt":
        soft = np.sqrt(weights)
        soft = soft / soft.mean()  # keep mean ≈ 1 so loss magnitude is comparable
        weights = soft
    elif mode != "balanced":
        raise ValueError(f"Unknown CLASS_WEIGHT_MODE: {mode!r}")

    return {int(i): float(w) for i, w in zip(classes_idx, weights)}


# ----------------------------------------------------------------------
# Main pipeline
# ----------------------------------------------------------------------

def main() -> dict[str, Any]:
    """Run training, evaluation and persistence. Returns the metrics dict."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Defaults reproduce the v3 model (commiteado en data/models/, see
    # docs/model-evaluation/report.md). Running the script with no env vars
    # regenerates the SAME model — not the broken first attempt.
    seed = int(os.environ.get("SEED", "42"))
    batch_size = int(os.environ.get("BATCH_SIZE", "32"))
    epochs_max = int(os.environ.get("EPOCHS_MAX", "35"))
    learning_rate = float(os.environ.get("LEARNING_RATE", "1e-4"))
    class_weight_mode = os.environ.get("CLASS_WEIGHT_MODE", "sqrt")
    dropout_conv = float(os.environ.get("DROPOUT_CONV", "0.3"))
    dropout_dense = float(os.environ.get("DROPOUT_DENSE", "0.3"))
    early_stop_patience = int(os.environ.get("EARLY_STOP_PATIENCE", "5"))
    early_stop_min_delta = float(os.environ.get("EARLY_STOP_MIN_DELTA", "0.001"))
    models_dir = Path(os.environ.get("MODELS_DIR", DEFAULT_MODELS_DIR))
    report_dir = Path(os.environ.get("REPORT_DIR", DEFAULT_REPORT_DIR))

    _set_global_seed(seed)
    logger.info(
        "Training config: seed=%d, batch_size=%d, epochs_max=%d, lr=%.1e, "
        "class_weight=%s, dropout=(%.2f, %.2f), early_stop=(patience=%d, min_delta=%g)",
        seed, batch_size, epochs_max, learning_rate, class_weight_mode,
        dropout_conv, dropout_dense, early_stop_patience, early_stop_min_delta,
    )

    # === 1. Dataset discovery + stratified split =====================
    items = discover_dataset()
    logger.info("Total images discovered: %d", len(items))
    splits = build_splits(items, seed=seed, ratios=(0.8, 0.1, 0.1))
    logger.info(
        "Splits: train=%d, val=%d, test=%d",
        len(splits.train), len(splits.val), len(splits.test),
    )

    # === 2. Class weights (CB-6: imbalanced classes) =================
    class_weight = _compute_class_weight(splits.train, mode=class_weight_mode)
    logger.info("Class weights (%s): %s", class_weight_mode, class_weight)

    # === 3. tf.data pipelines ========================================
    train_ds = _build_tf_dataset(splits.train, batch_size, augment=True, shuffle=True)
    val_ds = _build_tf_dataset(splits.val, batch_size, augment=False, shuffle=False)
    test_ds = _build_tf_dataset(splits.test, batch_size, augment=False, shuffle=False)

    # === 4. Build & compile model ====================================
    import tensorflow as tf
    model = build_model(
        num_classes=len(CLASSES),
        dropout_conv=dropout_conv,
        dropout_dense=dropout_dense,
        learning_rate=learning_rate,
    )

    # === 5. Callbacks (val only) =====================================
    models_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=early_stop_patience,
            min_delta=early_stop_min_delta,
            restore_best_weights=True,
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=str(models_dir / "best.keras"),
            monitor="val_loss",
            save_best_only=True,
        ),
        tf.keras.callbacks.CSVLogger(
            str(report_dir / "training_log.csv"),
        ),
    ]

    # === 6. Fit (train + val) ========================================
    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=epochs_max,
        callbacks=callbacks,
        class_weight=class_weight,
        verbose=2,
    )

    # === 7. Evaluation on the test split only ========================
    model_version = f"v1.0-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    hyperparams: dict[str, Any] = {
        "seed": seed,
        "batch_size": batch_size,
        "epochs_max": epochs_max,
        "epochs_run": len(history.history.get("loss", [])),
        "learning_rate": learning_rate,
        "class_weight_mode": class_weight_mode,
        "class_weight": class_weight,
        "dropout_conv": dropout_conv,
        "dropout_dense": dropout_dense,
        "early_stop_patience": early_stop_patience,
        "early_stop_min_delta": early_stop_min_delta,
        "split": "stratified-80-10-10",
        "input_shape": [DEFAULT_IMAGE_SIZE[0], DEFAULT_IMAGE_SIZE[1], 1],
        "architecture": (
            f"Conv2D(32)+Pool+Conv2D(64)+Pool+Conv2D(128)+Pool+Conv2D(128)+Pool"
            f"+Dropout({dropout_conv})+Flatten+Dense(64)+Dropout({dropout_dense})"
            f"+Dense(3,softmax)"
        ),
    }
    metrics = generate_report(
        model=model,
        test_dataset=test_ds,
        output_dir=report_dir,
        history=history.history,
        hyperparams=hyperparams,
        model_version=model_version,
    )

    # === 8. Persist model + meta =====================================
    model_path = models_dir / "radiography_classifier.keras"
    meta_path = models_dir / "radiography_classifier.meta.json"
    model.save(model_path)

    meta = {
        "model_version": model_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "classes": list(CLASSES),
        "input_shape": [DEFAULT_IMAGE_SIZE[0], DEFAULT_IMAGE_SIZE[1], 1],
        "framework": "tensorflow",
        "framework_version": tf.__version__,
        "metrics": {
            "accuracy": metrics["accuracy"],
            "macro_f1": metrics["macro_f1"],
            "per_class": metrics["per_class"],
        },
        "training": hyperparams,
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    logger.info(
        "Training complete. Model saved to %s (version=%s, accuracy=%.4f, macro_f1=%.4f)",
        model_path, model_version, metrics["accuracy"], metrics["macro_f1"],
    )

    return {**metrics, "model_version": model_version}


if __name__ == "__main__":
    main()
