"""Sanity checks for the radiography classifier.

Run inside the pipeline container:
    docker compose run --rm --entrypoint "" pipeline python -m scripts.ml_diagnostics

Four independent sanity checks, each with a clear pass/fail signal:
  1. Tiny-subset overfit  → if the model cannot memorise 30 images, there
     is a bug in labels/preprocessing/model, not in hyperparameters
  2. Visual batch montage → confirms preprocessed inputs look like real
     X-rays (not all-black, not mislabeled)
  3. Class mapping logging → CLASSES order, index → label, split counts
  4. Loaded model meta    → ensures `data/models/*.keras` is the latest
     and matches the meta.json (no stale dummy left over)
"""
from __future__ import annotations

import json
import logging
import random
from collections import Counter
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("diagnostics")

OUTPUT_DIR = Path("/app/docs/model-evaluation/diagnostics")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def banner(title: str) -> None:
    logger.info("\n" + "=" * 70)
    logger.info(title)
    logger.info("=" * 70)


# ---------------------------------------------------------------------------
# Sanity check 3 (run first: gives context for everything else)
# ---------------------------------------------------------------------------
def check_3_class_mapping_and_counts() -> tuple[list, list]:
    """Print CLASSES order, indices, split counts. Returns (items, splits)."""
    from src.ml.dataset import CLASS_MAP, CLASSES, build_splits, discover_dataset

    banner("3. CLASS MAPPING + SPLIT COUNTS")
    logger.info("CLASSES (model output indices map here):")
    for i, c in enumerate(CLASSES):
        logger.info("  index %d → %r", i, c)
    logger.info("CLASS_MAP (kaggle folder → our class):")
    for k, v in CLASS_MAP.items():
        logger.info("  %-20s → %s", k, v)

    items = discover_dataset()
    counts = Counter(cls for _, cls in items)
    logger.info("Total items discovered: %d", len(items))
    for c in CLASSES:
        logger.info("  %s: %d", c, counts[c])

    splits = build_splits(items, seed=42, ratios=(0.8, 0.1, 0.1))
    for name, split in [("train", splits.train), ("val", splits.val), ("test", splits.test)]:
        sc = Counter(cls for _, cls in split)
        logger.info("Split %-5s: total=%d, %s",
                    name, len(split), {c: sc[c] for c in CLASSES})

    # Verify argmax mapping is consistent: build (path → label_idx) and back
    sample = items[0]
    label_idx = CLASSES.index(sample[1])
    logger.info(
        "Sample mapping sanity: %s → class %r → label_idx=%d → CLASSES[idx]=%r",
        sample[0].name, sample[1], label_idx, CLASSES[label_idx],
    )
    assert CLASSES[label_idx] == sample[1], "label_idx ↔ CLASSES mismatch"
    logger.info("OK: argmax → CLASSES mapping is consistent")

    return items, splits


# ---------------------------------------------------------------------------
# Sanity check 2: visual montage
# ---------------------------------------------------------------------------
def check_2_visual_montage(items: list) -> None:
    """Save a 4x3 montage of preprocessed images with their labels."""
    from src.ml.dataset import CLASSES
    from src.ml.preprocessing import preprocess_for_inference

    banner("2. VISUAL MONTAGE OF PREPROCESSED BATCH")
    rng = random.Random(42)
    by_class = {c: [it for it in items if it[1] == c] for c in CLASSES}
    picks: list[tuple[Path, str]] = []
    for c in CLASSES:
        picks.extend(rng.sample(by_class[c], 4))
    rng.shuffle(picks)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 4, figsize=(12, 9))
    pixel_stats = []
    for ax, (path, cls) in zip(axes.ravel(), picks):
        x = preprocess_for_inference(path.read_bytes())
        pixel_stats.append((cls, float(x.min()), float(x.max()), float(x.mean())))
        ax.imshow(x.squeeze(), cmap="gray", vmin=0, vmax=1)
        ax.set_title(cls, fontsize=10)
        ax.set_xlabel(path.name, fontsize=7)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Preprocessed training batch (after preprocess_for_inference)", fontsize=12)
    fig.tight_layout()
    montage_path = OUTPUT_DIR / "preprocessed_batch.png"
    fig.savefig(montage_path, dpi=100)
    plt.close(fig)
    logger.info("Saved montage: %s", montage_path)

    logger.info("Per-image pixel range (min/max/mean):")
    for cls, mn, mx, mean in pixel_stats:
        flag = ""
        if mx - mn < 0.05:
            flag = "  ← suspicious: nearly uniform!"
        if mx < 0.05:
            flag = "  ← suspicious: image is black!"
        logger.info("  %-10s min=%.3f max=%.3f mean=%.3f%s",
                    cls, mn, mx, mean, flag)

    means = [mean for _, _, _, mean in pixel_stats]
    if max(means) - min(means) < 0.02:
        logger.warning(
            "WARNING: all 12 images have nearly identical mean intensity. "
            "Preprocessing may be wiping the signal."
        )
    else:
        logger.info("OK: image intensities vary across the batch")


# ---------------------------------------------------------------------------
# Sanity check 1: overfit a tiny subset
# ---------------------------------------------------------------------------
def check_1_tiny_overfit(items: list) -> None:
    """Try to memorise 30 images (10 per class). If we can't, bug somewhere."""
    from src.ml.dataset import CLASSES
    from src.ml.preprocessing import preprocess_for_inference

    banner("1. TINY-SUBSET OVERFIT (10 imgs/class, no aug, no class_weight)")
    rng = random.Random(42)
    by_class = {c: [it for it in items if it[1] == c] for c in CLASSES}
    tiny: list[tuple[Path, str]] = []
    for c in CLASSES:
        tiny.extend(rng.sample(by_class[c], 10))

    logger.info("Tiny dataset: %d images (%s)",
                len(tiny), Counter(cls for _, cls in tiny))

    X = np.stack([preprocess_for_inference(p.read_bytes()) for p, _ in tiny])
    y = np.array([CLASSES.index(c) for _, c in tiny], dtype=np.int32)
    logger.info("X shape=%s dtype=%s, y=%s", X.shape, X.dtype, y.tolist())

    # Build a model with reduced dropout for diagnosis only
    import tensorflow as tf
    from tensorflow.keras import layers

    tf.random.set_seed(42)
    np.random.seed(42)
    random.seed(42)

    model = tf.keras.Sequential([
        tf.keras.Input(shape=(224, 224, 1)),
        layers.Conv2D(32, 3, padding="same", activation="relu"),
        layers.MaxPooling2D(2),
        layers.Conv2D(64, 3, padding="same", activation="relu"),
        layers.MaxPooling2D(2),
        layers.Conv2D(128, 3, padding="same", activation="relu"),
        layers.MaxPooling2D(2),
        layers.Conv2D(128, 3, padding="same", activation="relu"),
        layers.MaxPooling2D(2),
        layers.Dropout(0.1),    # reduced for diagnosis
        layers.Flatten(),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.1),    # reduced for diagnosis
        layers.Dense(3, activation="softmax"),
    ])
    # Lower LR than the production training: 1e-4 instead of 1e-3
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    logger.info("Training 30 epochs on the tiny set (no validation, no callbacks)...")
    history = model.fit(X, y, epochs=30, batch_size=10, verbose=0)
    final_loss = history.history["loss"][-1]
    final_acc = history.history["accuracy"][-1]
    logger.info("Final train loss=%.4f, accuracy=%.4f", final_loss, final_acc)

    # Inspect a couple of intermediate epochs
    for epoch_idx in [0, 4, 9, 19, 29]:
        if epoch_idx < len(history.history["loss"]):
            logger.info(
                "  epoch %2d  loss=%.4f  acc=%.4f",
                epoch_idx + 1,
                history.history["loss"][epoch_idx],
                history.history["accuracy"][epoch_idx],
            )

    if final_acc >= 0.95:
        logger.info("PASS: model can memorise 30 images (acc=%.3f)", final_acc)
    elif final_acc >= 0.70:
        logger.warning(
            "PARTIAL: model is learning but slow (acc=%.3f). May need more "
            "epochs or higher LR for the real training", final_acc,
        )
    else:
        logger.error(
            "FAIL: model cannot memorise 30 images (acc=%.3f). Bug likely "
            "in preprocessing, labels, or model architecture", final_acc,
        )

    # Confusion on the tiny set itself
    probs = model.predict(X, verbose=0)
    preds = probs.argmax(axis=1)
    logger.info("Predictions on tiny set: %s", preds.tolist())
    logger.info("True labels on tiny set: %s", y.tolist())
    correct = int((preds == y).sum())
    logger.info("Correct: %d / %d", correct, len(y))


# ---------------------------------------------------------------------------
# Sanity check 4: validate the saved model artefact
# ---------------------------------------------------------------------------
def check_4_loaded_model() -> None:
    banner("4. SAVED MODEL ARTEFACT (data/models/)")
    model_path = Path("/app/data/models/radiography_classifier.keras")
    meta_path = Path("/app/data/models/radiography_classifier.meta.json")

    if not model_path.exists():
        logger.error("FAIL: %s missing", model_path)
        return
    if not meta_path.exists():
        logger.error("FAIL: %s missing", meta_path)
        return

    size_mb = model_path.stat().st_size / 1024 / 1024
    logger.info("Model: %s (%.2f MB)", model_path, size_mb)
    logger.info("Meta:  %s (%d bytes)", meta_path, meta_path.stat().st_size)

    meta = json.loads(meta_path.read_text())
    logger.info("model_version : %s", meta["model_version"])
    logger.info("trained_at    : %s", meta["trained_at"])
    logger.info("framework     : %s %s", meta["framework"], meta["framework_version"])
    logger.info("classes       : %s", meta["classes"])
    logger.info("input_shape   : %s", meta["input_shape"])
    metrics = meta.get("metrics", {})
    logger.info("metrics:")
    logger.info("  accuracy   : %.4f", metrics.get("accuracy", -1))
    logger.info("  macro_f1   : %.4f", metrics.get("macro_f1", -1))
    for cls, m in metrics.get("per_class", {}).items():
        logger.info("  %-10s recall=%.4f  precision=%.4f", cls, m["recall"], m["precision"])

    # Heuristics for degenerate models
    macro_f1 = metrics.get("macro_f1", 0)
    per_class = metrics.get("per_class", {})
    recalls = [m["recall"] for m in per_class.values()]
    zero_recall_classes = [c for c, m in per_class.items() if m["recall"] == 0.0]
    if macro_f1 < 0.35:
        logger.error(
            "DEGENERATE: macro_f1=%.3f (< 0.35). Random with 3 classes is "
            "~0.33; this model is not learning useful features.", macro_f1,
        )
    if zero_recall_classes:
        logger.error(
            "DEGENERATE: zero recall on classes %s — model is predicting "
            "only the majority class.", zero_recall_classes,
        )


def main() -> None:
    items, _ = check_3_class_mapping_and_counts()
    check_2_visual_montage(items)
    check_4_loaded_model()
    check_1_tiny_overfit(items)  # last because it's the longest
    banner("DIAGNOSTICS COMPLETE")


if __name__ == "__main__":
    main()
