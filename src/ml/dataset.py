"""Discovery and split of the COVID-19 Radiography Database.

The Kaggle dataset is laid out as `{class}/images/*.png` (plus a
`masks/` subdir we ignore). We use only three of its four classes —
`Lung_Opacity` is discarded because it does not fit the triple
classification of the project (Normal / Pneumonia / COVID-19).

The class index order in `CLASSES` is the canonical contract used by
the model's softmax output and by the predictor; do not reorder.
"""
from __future__ import annotations

import logging
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# Mapping from the raw Kaggle folder name to our internal class label.
# `Lung_Opacity` is deliberately absent: it gets skipped at discovery time.
CLASS_MAP: dict[str, str] = {
    "COVID": "COVID-19",
    "Normal": "Normal",
    "Viral Pneumonia": "Pneumonia",
}

# Canonical class index → label. Used by the model softmax and the predictor.
CLASSES: list[str] = ["Normal", "Pneumonia", "COVID-19"]


DEFAULT_DATASET_PATH = Path(
    "/app/data/raw/covid_radiography/COVID-19_Radiography_Dataset"
)


class DatasetNotFoundError(FileNotFoundError):
    """Raised when the dataset is missing or malformed on disk."""


@dataclass(frozen=True)
class Splits:
    """Stratified train/val/test splits.

    Each element is a `(image_path, class_label)` tuple, where class_label
    is a value from `CLASSES`.
    """
    train: list[tuple[Path, str]]
    val: list[tuple[Path, str]]
    test: list[tuple[Path, str]]


def _resolve_root(root: Path | None) -> Path:
    if root is not None:
        return root
    env_path = os.environ.get("DATASET_PATH")
    return Path(env_path) if env_path else DEFAULT_DATASET_PATH


def discover_dataset(root: Path | None = None) -> list[tuple[Path, str]]:
    """List every classified image in the dataset.

    Returns `[(image_path, mapped_class_label)]` walking `{class}/images/*.png`
    under `root`. Classes outside `CLASS_MAP` (notably `Lung_Opacity`) are
    silently skipped. Raises `DatasetNotFoundError` with a pointer to the
    runbook if the root is missing or a kept class has no `images/` dir.
    """
    root = _resolve_root(root)
    if not root.exists() or not root.is_dir():
        raise DatasetNotFoundError(
            f"Dataset root not found at '{root}'. "
            "Download the COVID-19 Radiography Database following "
            "docs/runbooks/download-radiography-dataset.md, then set "
            "DATASET_PATH or place it at the default location."
        )

    items: list[tuple[Path, str]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        raw_class = child.name
        if raw_class not in CLASS_MAP:
            logger.info("Skipping unmapped class folder: %s", raw_class)
            continue
        images_dir = child / "images"
        if not images_dir.is_dir():
            raise DatasetNotFoundError(
                f"Class '{raw_class}' has no 'images/' subdirectory under "
                f"'{child}'. The zip may be corrupt or wrongly extracted; "
                "see docs/runbooks/download-radiography-dataset.md"
            )
        mapped_class = CLASS_MAP[raw_class]
        for png in sorted(images_dir.glob("*.png")):
            items.append((png, mapped_class))

    logger.info("Discovered %d images across %d classes", len(items), len(CLASS_MAP))
    return items


def build_splits(
    items: list[tuple[Path, str]],
    seed: int = 42,
    ratios: tuple[float, float, float] = (0.8, 0.1, 0.1),
) -> Splits:
    """Stratified 80/10/10 (or custom) split by class.

    Within each class the items are shuffled with the given seed and then
    cut at the configured ratios. Deterministic for a given (items, seed).
    """
    if abs(sum(ratios) - 1.0) > 1e-6:
        raise ValueError(f"ratios must sum to 1.0, got {ratios}")

    by_class: dict[str, list[tuple[Path, str]]] = defaultdict(list)
    for path, cls in items:
        by_class[cls].append((path, cls))

    rng = random.Random(seed)
    train: list[tuple[Path, str]] = []
    val: list[tuple[Path, str]] = []
    test: list[tuple[Path, str]] = []

    for cls in sorted(by_class):  # sort to make ordering deterministic
        bucket = list(by_class[cls])
        rng.shuffle(bucket)
        n = len(bucket)
        n_train = int(round(n * ratios[0]))
        n_val = int(round(n * ratios[1]))
        train.extend(bucket[:n_train])
        val.extend(bucket[n_train : n_train + n_val])
        test.extend(bucket[n_train + n_val :])

    return Splits(train=train, val=val, test=test)
