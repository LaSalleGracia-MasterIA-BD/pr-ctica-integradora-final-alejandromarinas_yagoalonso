"""Predictor: la fachada del lado de inferencia del clasificador de radiografias.

Se construye una instancia al arrancar la API (en el lifespan de `build_app`)
y se mantiene en `app.state.predictor` durante toda la vida del proceso.
Los endpoints de `src/api/routers/classify.py` llaman a `.predict(image_bytes)`
sobre ella.

Thread-safety: el `model.predict` de TensorFlow / Keras historicamente no
ha sido seguro llamandolo desde multiples threads concurrentes. FastAPI
sirve los route handlers sincronos desde un threadpool, asi que
serializamos las llamadas con un `threading.Lock`.
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
    """Se lanza cuando el artefacto del modelo o su meta no estan en disco."""


@dataclass(frozen=True)
class Prediction:
    """El resultado estructurado de una inferencia."""
    predicted_class: str
    probabilities: dict[str, float]
    model_version: str
    decision_rule: str


class Predictor:
    """Carga una vez, predice muchas. Wrapper thread-safe alrededor de un modelo Keras."""

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

        # Lazy-import de TF para que importar este modulo sea barato cuando
        # el modelo no esta presente (la API aun necesita arrancar).
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
        """Ejecuta inferencia sobre una imagen. Lanza InvalidImageError si la entrada es invalida.

        Regla de decision (tuning de umbral post-hoc, ver ADR-010):
          si P(COVID-19) >= COVID_THRESHOLD -> predicted_class = "COVID-19"
          si no                              -> argmax entre Normal/Pneumonia
        Las probabilidades devueltas son las salidas softmax raw del modelo.
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
        """Aplica la regla de decision del umbral COVID sobre las probabilidades softmax raw."""
        if probabilities.get(COVID_CLASS, 0.0) >= COVID_THRESHOLD:
            return COVID_CLASS
        non_covid = {c: p for c, p in probabilities.items() if c != COVID_CLASS}
        return max(non_covid, key=non_covid.get)

    @classmethod
    def from_env(cls) -> "Predictor":
        """Construye un Predictor leyendo los paths desde variables de entorno.

        Overrides via env (con defaults):
          - MODEL_PATH (default `/app/data/models/radiography_classifier.keras`)
          - MODEL_META_PATH (default `.meta.json` hermano de MODEL_PATH)
        """
        model_path = Path(os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH))
        meta_default = (
            Path(os.environ["MODEL_META_PATH"])
            if "MODEL_META_PATH" in os.environ
            else model_path.with_suffix(".meta.json")
        )
        return cls(model_path=model_path, meta_path=meta_default)
