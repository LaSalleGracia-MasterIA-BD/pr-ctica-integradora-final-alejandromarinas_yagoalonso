"""Arquitectura CNN para el clasificador de radiografias.

La arquitectura sigue el patron literal ensenado en el Bloque 6 del Master
(Conv2D + MaxPooling2D + Dropout + Flatten + Dense + softmax).
Ver ADR-005 para la justificacion de elegir una CNN custom frente a
transfer learning.

`padding="same"` en las capas Conv2D es obligatorio: garantiza que la
reduccion espacial proceda unicamente de las capas MaxPool2x2, produciendo
la cascada limpia 224 -> 112 -> 56 -> 28 -> 14 referenciada en el design
y en los tests de `tests/ml/test_model.py`.
"""
from __future__ import annotations


def build_model(
    num_classes: int = 3,
    input_shape: tuple[int, int, int] = (224, 224, 1),
    dropout_conv: float = 0.5,
    dropout_dense: float = 0.3,
    learning_rate: float = 1e-3,
):
    """Construye y compila la CNN de clasificacion de radiografias.

    Args:
        num_classes: tamano de la salida softmax.
        input_shape: shape HWC de entrada.
        dropout_conv: dropout aplicado tras el ultimo bloque conv, antes de
            Flatten. El default 0.5 coincide con el diseno original. Valores
            mas bajos (p.ej. 0.3) ayudan a la convergencia cuando el
            entrenamiento no alcanza un minimo util solo con el LR.
        dropout_dense: dropout entre las dos capas Dense. Default 0.3.
        learning_rate: LR del optimizador Adam. Default 1e-3.

    Hace lazy-import de TensorFlow para que importar este modulo sea barato
    cuando solo se necesita la firma de la funcion.
    """
    from tensorflow import keras
    from tensorflow.keras import layers

    model = keras.Sequential(
        [
            keras.Input(shape=input_shape, name="radiography"),
            layers.Conv2D(32, 3, padding="same", activation="relu", name="conv1"),
            layers.MaxPooling2D(2, name="pool1"),
            layers.Conv2D(64, 3, padding="same", activation="relu", name="conv2"),
            layers.MaxPooling2D(2, name="pool2"),
            layers.Conv2D(128, 3, padding="same", activation="relu", name="conv3"),
            layers.MaxPooling2D(2, name="pool3"),
            layers.Conv2D(128, 3, padding="same", activation="relu", name="conv4"),
            layers.MaxPooling2D(2, name="pool4"),
            layers.Dropout(dropout_conv, name="dropout_conv"),
            layers.Flatten(name="flatten"),
            layers.Dense(64, activation="relu", name="dense_hidden"),
            layers.Dropout(dropout_dense, name="dropout_dense"),
            layers.Dense(num_classes, activation="softmax", name="output"),
        ],
        name="radiography_cnn",
    )

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=learning_rate),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    return model
