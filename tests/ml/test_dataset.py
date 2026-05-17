"""Tests for src.ml.dataset: discovery, class mapping, and stratified splits.

The dataset on disk follows the Kaggle structure: each class has an `images/`
subdir (and a `masks/` we ignore). `Lung_Opacity` is discarded entirely.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.ml.dataset import (
    CLASSES,
    CLASS_MAP,
    DatasetNotFoundError,
    build_splits,
    discover_dataset,
)


def _make_kaggle_layout(root: Path, counts: dict[str, int]) -> None:
    """Create the canonical Kaggle layout under `root` with empty PNG files.

    counts maps the original Kaggle class name (e.g. "COVID") to the number
    of fake PNGs to create under `{class}/images/`.
    """
    for klass, n in counts.items():
        images = root / klass / "images"
        masks = root / klass / "masks"
        images.mkdir(parents=True)
        masks.mkdir(parents=True)
        for i in range(n):
            (images / f"{klass}-{i}.png").touch()
            (masks / f"{klass}-{i}.png").touch()  # never indexed


def test_discover_returns_only_mapped_classes(tmp_path: Path):
    _make_kaggle_layout(tmp_path, {"COVID": 2, "Normal": 2, "Viral Pneumonia": 2})

    items = discover_dataset(root=tmp_path)

    found_classes = {cls for _, cls in items}
    assert found_classes == set(CLASS_MAP.values())


def test_discover_skips_lung_opacity(tmp_path: Path):
    _make_kaggle_layout(
        tmp_path,
        {"COVID": 1, "Normal": 1, "Viral Pneumonia": 1, "Lung_Opacity": 5},
    )

    items = discover_dataset(root=tmp_path)

    classes = {cls for _, cls in items}
    assert "Lung_Opacity" not in classes
    assert len(items) == 3  # only one per kept class


def test_discover_maps_class_names_correctly(tmp_path: Path):
    _make_kaggle_layout(tmp_path, {"COVID": 1, "Normal": 1, "Viral Pneumonia": 1})

    items = discover_dataset(root=tmp_path)
    by_class = {cls: path for path, cls in items}

    assert "COVID-19" in by_class
    assert "Normal" in by_class
    assert "Pneumonia" in by_class
    assert "COVID" not in by_class  # raw name should not leak through
    assert "Viral Pneumonia" not in by_class


def test_discover_walks_into_images_subdir_and_ignores_masks(tmp_path: Path):
    _make_kaggle_layout(tmp_path, {"COVID": 3, "Normal": 0, "Viral Pneumonia": 0})

    items = discover_dataset(root=tmp_path)

    assert len(items) == 3
    for path, _ in items:
        assert path.parent.name == "images"
        assert "masks" not in path.parts


def test_discover_raises_if_root_missing(tmp_path: Path):
    missing = tmp_path / "does_not_exist"

    with pytest.raises(DatasetNotFoundError) as exc_info:
        discover_dataset(root=missing)
    assert "docs/runbooks" in str(exc_info.value).lower()


def test_discover_raises_if_images_subdir_missing(tmp_path: Path):
    # Create a COVID class WITHOUT the `images/` subdir
    (tmp_path / "COVID" / "masks").mkdir(parents=True)
    (tmp_path / "Normal" / "images").mkdir(parents=True)
    (tmp_path / "Viral Pneumonia" / "images").mkdir(parents=True)

    with pytest.raises(DatasetNotFoundError) as exc_info:
        discover_dataset(root=tmp_path)
    msg = str(exc_info.value)
    assert "images" in msg.lower()
    assert "COVID" in msg


def test_classes_constant_has_canonical_order():
    """Index order matters: model output index i must map to CLASSES[i]."""
    assert CLASSES == ["Normal", "Pneumonia", "COVID-19"]


def test_build_splits_is_stratified(tmp_path: Path):
    items: list[tuple[Path, str]] = []
    for cls in CLASSES:
        for i in range(100):
            items.append((tmp_path / f"{cls}-{i}.png", cls))

    splits = build_splits(items, seed=42, ratios=(0.8, 0.1, 0.1))

    # Each split keeps ~80/10/10 per class
    for cls in CLASSES:
        n_train = sum(1 for _, c in splits.train if c == cls)
        n_val = sum(1 for _, c in splits.val if c == cls)
        n_test = sum(1 for _, c in splits.test if c == cls)
        assert abs(n_train - 80) <= 1
        assert abs(n_val - 10) <= 1
        assert abs(n_test - 10) <= 1
        assert n_train + n_val + n_test == 100


def test_build_splits_is_deterministic_with_seed(tmp_path: Path):
    items = [(tmp_path / f"img-{i}.png", CLASSES[i % 3]) for i in range(30)]

    s1 = build_splits(items, seed=42)
    s2 = build_splits(items, seed=42)

    assert s1.train == s2.train
    assert s1.val == s2.val
    assert s1.test == s2.test


def test_build_splits_changes_with_different_seed(tmp_path: Path):
    items = [(tmp_path / f"img-{i}.png", CLASSES[i % 3]) for i in range(30)]

    s1 = build_splits(items, seed=1)
    s2 = build_splits(items, seed=2)

    # Statistically the splits should differ (not guaranteed, but with 30
    # items and shuffling the chance of identical order is ~0)
    assert s1.train != s2.train or s1.val != s2.val
