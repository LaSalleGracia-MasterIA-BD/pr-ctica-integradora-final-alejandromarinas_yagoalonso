"""Predictor: the inference-side facade of the radiography classifier.

One instance is constructed at API startup (in `build_app`'s lifespan) and
kept on `app.state.predictor` for the lifetime of the process. The
endpoints in `src/api/routers/classify.py` call `.predict(image_bytes)`
on it.

Thread-safety: TensorFlow / Keras `model.predict` has historically not
been safe to call from multiple threads concurrently. FastAPI serves
sync route handlers from a threadpool, so we serialise calls with a
`threading.Lock`.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.ml.preprocessing import preprocess_for_inference

logger = logging.getLogger(__name__)


DEFAULT_MODEL_PATH = Path("/app/data/models/radiography_classifier.keras")
DEFAULT_META_PATH = Path("/app/data/models/radiography_classifier.meta.json")

COVID_CLASS = "COVID-19"
COVID_THRESHOLD = 0.35
DECISION_RULE = f"covid_threshold_{COVID_THRESHOLD:.2f}"


class ModelNotAvailableError(RuntimeError):
    """Raised when the model artefact or its meta is missing on disk."""


@dataclass(frozen=True)
class Prediction:
    """The structured result of a single inference."""
    predicted_class: str
    probabilities: dict[str, float]
    model_version: str
    decision_rule: str


class Predictor:
    """Load once, predict many. Thread-safe wrapper around a Keras model."""

    def __init__(self, model_path: Path, meta_path: Path) -> None:
        if not model_path.exists():
            raise ModelNotAvailableError(
                f"Model artefact not found at '{model_path}'. "
                "Train the model with `docker compose run --rm pipeline "
                "python -m src.ml.train` or place a pretrained artefact "
                "at that path."
            )
        if not meta_path.exists():
            raise ModelNotAvailableError(
                f"Model meta not found at '{meta_path}'. The .keras file "
                "exists but its sibling .meta.json is missing."
            )

        # Lazy-import TF so even importing this module is cheap when the
        # model is not present (the API still needs to start).
        from tensorflow import keras

        self._model = keras.models.load_model(model_path)
        self._meta = json.loads(meta_path.read_text())
        self._classes: list[str] = list(self._meta["classes"])
        self._model_version: str = str(self._meta["model_version"])
        self._lock = threading.Lock()
        logger.info(
            "Predictor loaded: version=%s, classes=%s",
            self._model_version, self._classes,
        )

    @property
    def model_version(self) -> str:
        return self._model_version

    def predict(self, image_bytes: bytes) -> Prediction:
        """Run a single-image inference. Raises InvalidImageError on bad input.

        Decision rule (post-hoc threshold tuning, see ADR-010):
          if P(COVID-19) >= COVID_THRESHOLD -> predicted_class = "COVID-19"
          else                               -> argmax between Normal/Pneumonia
        The probabilities returned are the raw softmax outputs of the model.
        """
        x = preprocess_for_inference(image_bytes)
        x_batched = x[np.newaxis, ...]

        with self._lock:
            probs = self._model.predict(x_batched, verbose=0)[0]

        probabilities = {c: float(p) for c, p in zip(self._classes, probs)}
        predicted_class = self._apply_decision_rule(probabilities)

        return Prediction(
            predicted_class=predicted_class,
            probabilities=probabilities,
            model_version=self._model_version,
            decision_rule=DECISION_RULE,
        )

    def _apply_decision_rule(self, probabilities: dict[str, float]) -> str:
        """Apply the COVID-threshold decision rule on raw softmax probabilities."""
        if probabilities.get(COVID_CLASS, 0.0) >= COVID_THRESHOLD:
            return COVID_CLASS
        non_covid = {c: p for c, p in probabilities.items() if c != COVID_CLASS}
        return max(non_covid, key=non_covid.get)

    @classmethod
    def from_env(cls) -> "Predictor":
        """Build a Predictor reading paths from environment variables.

        Env overrides (with defaults):
          - MODEL_PATH (default `/app/data/models/radiography_classifier.keras`)
          - MODEL_META_PATH (default sibling `.meta.json` of MODEL_PATH)
        """
        model_path = Path(os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH))
        meta_default = (
            Path(os.environ["MODEL_META_PATH"])
            if "MODEL_META_PATH" in os.environ
            else model_path.with_suffix(".meta.json")
        )
        return cls(model_path=model_path, meta_path=meta_default)
