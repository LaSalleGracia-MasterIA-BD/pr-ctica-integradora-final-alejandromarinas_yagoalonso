"""Descubrimiento y split de la COVID-19 Radiography Database.

El dataset de Kaggle esta organizado como `{class}/images/*.png` (mas un
subdir `masks/` que ignoramos). Usamos solo tres de sus cuatro clases —
`Lung_Opacity` se descarta porque no encaja en la clasificacion triple
del proyecto (Normal / Pneumonia / COVID-19).

El orden de indices de clase en `CLASSES` es el contrato canonico usado
por la salida softmax del modelo y por el predictor; no reordenar.
"""
from __future__ import annotations

import logging
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# Mapeo del nombre raw de la carpeta de Kaggle a nuestra etiqueta de clase interna.
# `Lung_Opacity` esta deliberadamente ausente: se omite en el discovery.
CLASS_MAP: dict[str, str] = {
    "COVID": "COVID-19",
    "Normal": "Normal",
    "Viral Pneumonia": "Pneumonia",
}

# Indice de clase canonico -> etiqueta. Usado por el softmax del modelo y por el predictor.
CLASSES: list[str] = ["Normal", "Pneumonia", "COVID-19"]


DEFAULT_DATASET_PATH = Path(
    "/app/data/raw/covid_radiography/COVID-19_Radiography_Dataset"
)


class DatasetNotFoundError(FileNotFoundError):
    """Se lanza cuando el dataset falta o esta malformado en disco."""


@dataclass(frozen=True)
class Splits:
    """Splits estratificados train/val/test.

    Cada elemento es una tupla `(image_path, class_label)`, donde class_label
    es un valor de `CLASSES`.
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
    """Lista todas las imagenes clasificadas en el dataset.

    Devuelve `[(image_path, mapped_class_label)]` recorriendo `{class}/images/*.png`
    bajo `root`. Las clases fuera de `CLASS_MAP` (en particular `Lung_Opacity`)
    se omiten silenciosamente. Lanza `DatasetNotFoundError` con un puntero al
    runbook si el root falta o si una clase retenida no tiene directorio `images/`.
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
    """Split estratificado 80/10/10 (o personalizado) por clase.

    Dentro de cada clase los items se barajan con la seed dada y luego
    se cortan en los ratios configurados. Determinista para un (items, seed) dado.
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

    for cls in sorted(by_class):  # ordenar para que el orden sea determinista
        bucket = list(by_class[cls])
        rng.shuffle(bucket)
        n = len(bucket)
        n_train = int(round(n * ratios[0]))
        n_val = int(round(n * ratios[1]))
        train.extend(bucket[:n_train])
        val.extend(bucket[n_train : n_train + n_val])
        test.extend(bucket[n_train + n_val :])

    return Splits(train=train, val=val, test=test)
