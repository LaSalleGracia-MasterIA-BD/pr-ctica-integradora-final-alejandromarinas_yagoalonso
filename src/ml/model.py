"""CNN architecture for the radiography classifier.

The architecture follows the literal pattern taught in the Master's
Block 6 (Conv2D + MaxPooling2D + Dropout + Flatten + Dense + softmax).
See ADR-005 for the rationale of choosing custom-CNN over transfer
learning.

`padding="same"` on the Conv2D layers is mandatory: it guarantees that
spatial reduction only comes from the MaxPool2x2 layers, producing the
clean cascade 224 → 112 → 56 → 28 → 14 referenced in the design and
in the tests of `tests/ml/test_model.py`.
"""
from __future__ import annotations


def build_model(
    num_classes: int = 3,
    input_shape: tuple[int, int, int] = (224, 224, 1),
    dropout_conv: float = 0.5,
    dropout_dense: float = 0.3,
    learning_rate: float = 1e-3,
):
    """Build and compile the radiography classification CNN.

    Args:
        num_classes: softmax output size.
        input_shape: HWC input shape.
        dropout_conv: dropout applied after the last conv block, before
            Flatten. Default 0.5 matches the original design. Lower
            values (e.g. 0.3) help convergence when training does not
            reach a useful minimum with LR alone.
        dropout_dense: dropout between the two Dense layers. Default 0.3.
        learning_rate: Adam optimizer LR. Default 1e-3.

    Lazy-imports TensorFlow so importing this module is cheap when only
    the function signature is needed.
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
