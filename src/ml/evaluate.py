"""Generate the evaluation report for the radiography classifier.

Produces:
  * `metrics.json` — machine-readable metrics for downstream automation
  * `confusion_matrix.png` — heatmap with counts
  * `learning_curves.png` — loss / accuracy per epoch
  * `report.md` — human-readable report with the **clinical analysis**
    that the project requires (CA-3)

All metrics are computed on the **test split**. The validation split is
only used during training (EarlyStopping, ModelCheckpoint, hyperparam
tuning) — see the regla estricta documented in train.py.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from src.ml.dataset import CLASSES

logger = logging.getLogger(__name__)


def _collect_predictions(model, test_dataset) -> tuple[np.ndarray, np.ndarray]:
    """Run inference over the whole test dataset and return (y_true, y_pred)."""
    y_true_chunks: list[np.ndarray] = []
    y_pred_chunks: list[np.ndarray] = []
    for batch_x, batch_y in test_dataset:
        probs = model.predict(batch_x, verbose=0)
        y_pred_chunks.append(np.argmax(probs, axis=1))
        y_true_chunks.append(np.asarray(batch_y))
    return np.concatenate(y_true_chunks), np.concatenate(y_pred_chunks)


def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Aggregate accuracy, macro-F1, per-class P/R/F1, and confusion matrix."""
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
    )

    accuracy = float(accuracy_score(y_true, y_pred))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    report = classification_report(
        y_true, y_pred,
        labels=list(range(len(CLASSES))),
        target_names=CLASSES,
        output_dict=True,
        zero_division=0,
    )
    per_class = {
        cls: {
            "precision": float(report[cls]["precision"]),
            "recall": float(report[cls]["recall"]),
            "f1": float(report[cls]["f1-score"]),
            "support": int(report[cls]["support"]),
        }
        for cls in CLASSES
    }
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(CLASSES))))

    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_matrix": cm.tolist(),
    }


def _save_confusion_matrix_png(cm: list[list[int]], output_path: Path) -> None:
    """Render the confusion matrix as a heatmap PNG."""
    import matplotlib.pyplot as plt

    cm_np = np.asarray(cm)
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm_np, cmap="Blues")
    ax.set_xticks(range(len(CLASSES)))
    ax.set_yticks(range(len(CLASSES)))
    ax.set_xticklabels(CLASSES)
    ax.set_yticklabels(CLASSES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion matrix (test split)")
    # annotate cells
    for i in range(len(CLASSES)):
        for j in range(len(CLASSES)):
            ax.text(
                j, i, int(cm_np[i, j]),
                ha="center", va="center",
                color="white" if cm_np[i, j] > cm_np.max() / 2 else "black",
            )
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)


def _save_learning_curves_png(history: dict[str, list[float]], output_path: Path) -> None:
    """Render training curves (loss + accuracy, train vs val) as a PNG."""
    import matplotlib.pyplot as plt

    fig, (ax_loss, ax_acc) = plt.subplots(1, 2, figsize=(10, 4))
    epochs = range(1, len(history.get("loss", [])) + 1)

    ax_loss.plot(epochs, history.get("loss", []), label="train")
    if "val_loss" in history:
        ax_loss.plot(epochs, history["val_loss"], label="val")
    ax_loss.set_xlabel("Epoch")
    ax_loss.set_ylabel("Loss")
    ax_loss.set_title("Loss")
    ax_loss.legend()

    ax_acc.plot(epochs, history.get("accuracy", []), label="train")
    if "val_accuracy" in history:
        ax_acc.plot(epochs, history["val_accuracy"], label="val")
    ax_acc.set_xlabel("Epoch")
    ax_acc.set_ylabel("Accuracy")
    ax_acc.set_title("Accuracy")
    ax_acc.legend()

    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)


def _render_markdown_report(
    metrics: dict[str, Any],
    hyperparams: dict[str, Any],
    model_version: str,
) -> str:
    """Produce the human-readable Markdown report (CA-2, CA-3, CA-4)."""
    accuracy = metrics["accuracy"]
    macro_f1 = metrics["macro_f1"]
    per_class = metrics["per_class"]
    cm = metrics["confusion_matrix"]

    md = []
    md.append(f"# Reporte de evaluacion del clasificador de radiografias")
    md.append("")
    md.append(f"**Version del modelo:** `{model_version}`")
    md.append("")

    md.append("## 1. Resumen de metricas (split de test)")
    md.append("")
    md.append(f"- **Accuracy global:** {accuracy:.4f}")
    md.append(f"- **Macro-F1:** {macro_f1:.4f}")
    md.append("")
    md.append("| Clase | Precision | Recall | F1 | Soporte |")
    md.append("|-------|-----------|--------|-----|---------|")
    for cls in CLASSES:
        p = per_class[cls]
        md.append(
            f"| {cls} | {p['precision']:.4f} | "
            f"**{p['recall']:.4f}** | {p['f1']:.4f} | {p['support']} |"
        )
    md.append("")
    md.append(
        "El **recall** se destaca en negrita porque es la metrica clave "
        "desde el punto de vista clinico: mide la sensibilidad para detectar "
        "casos reales de cada clase. Un recall bajo en COVID-19 o Pneumonia "
        "implica pacientes enfermos clasificados como sanos."
    )
    md.append("")

    md.append("## 2. Matriz de confusion (test split)")
    md.append("")
    md.append("![Confusion matrix](confusion_matrix.png)")
    md.append("")
    md.append("Conteos absolutos (filas = clase real, columnas = clase predicha):")
    md.append("")
    md.append("| Real \\ Predicha | " + " | ".join(CLASSES) + " |")
    md.append("|---|" + "|".join(["---"] * len(CLASSES)) + "|")
    for i, cls in enumerate(CLASSES):
        md.append(f"| **{cls}** | " + " | ".join(str(v) for v in cm[i]) + " |")
    md.append("")

    md.append("## 3. Analisis clinico (CA-3)")
    md.append("")
    md.append(
        "La matriz de confusion 3x3 tiene 6 tipos de error con consecuencias "
        "clinicas distintas (ver `specs/clasificacion-radiografias.md`, anexo "
        "'Criterios clinicos'). Los **FN COVID** (paciente COVID-19 clasificado "
        "como Sano) son el error mas grave en el contexto hospitalario porque "
        "implican no aislar a un contagioso. Por debajo en gravedad estan los "
        "**FN Pneumonia** (paciente con neumonia no detectado) y las **confusiones "
        "COVID/Pneumonia**, con riesgo epidemiologico. Los **FP** (paciente sano "
        "clasificado como enfermo) son menos graves: generan pruebas adicionales "
        "pero no ponen en riesgo al paciente ni al hospital."
    )
    md.append("")
    covid_idx = CLASSES.index("COVID-19")
    pneumonia_idx = CLASSES.index("Pneumonia")
    normal_idx = CLASSES.index("Normal")

    # FN COVID = pacientes COVID-19 NO clasificados como COVID-19 (toda la
    # fila menos la diagonal). Hay que detallar a que clase se desvian
    # porque el peso clinico es distinto: COVID→Normal es el mas grave
    # (alta sin aislar), COVID→Pneumonia tiene riesgo epidemiologico.
    covid_to_normal = cm[covid_idx][normal_idx]
    covid_to_pneumonia = cm[covid_idx][pneumonia_idx]
    fn_covid_total = covid_to_normal + covid_to_pneumonia

    # FN Pneumonia = Pneumonia no clasificada como Pneumonia (fila menos
    # diagonal).
    pneumonia_to_normal = cm[pneumonia_idx][normal_idx]
    pneumonia_to_covid = cm[pneumonia_idx][covid_idx]
    fn_pneumonia_total = pneumonia_to_normal + pneumonia_to_covid

    md.append(
        f"En la evaluacion realizada, el modelo muestra **{covid_to_normal} "
        f"COVID-19 clasificados como Normal y {covid_to_pneumonia} como "
        f"Pneumonia; total {fn_covid_total} COVID-19 no detectados como "
        f"COVID-19**. De los FN COVID, el subtipo mas grave clinicamente es "
        f"COVID→Normal ({covid_to_normal}) porque implica no aislar a un "
        f"contagioso; COVID→Pneumonia ({covid_to_pneumonia}) anade riesgo "
        f"epidemiologico aunque al menos dispara protocolo respiratorio. "
        f"Para Pneumonia hay {pneumonia_to_normal} clasificadas como "
        f"Normal y {pneumonia_to_covid} como COVID-19 (total "
        f"{fn_pneumonia_total} FN Pneumonia). "
        f"El recall observado es: "
        f"COVID-19 = {per_class['COVID-19']['recall']:.4f}, "
        f"Pneumonia = {per_class['Pneumonia']['recall']:.4f}, "
        f"Normal = {per_class['Normal']['recall']:.4f}. "
        "La aceptabilidad clinica del modelo se argumenta a partir de estos "
        "numeros: el sistema se entrega como **asistencia diagnostica** y "
        "NO sustituye a la decision medica. Cualquier prediccion debe ser "
        "revisada por personal clinico antes de actuar."
    )
    md.append("")

    md.append("## 4. Hiperparametros y reproducibilidad")
    md.append("")
    md.append("```json")
    md.append(json.dumps(hyperparams, indent=2))
    md.append("```")
    if "split" in hyperparams:
        md.append("")
        md.append(f"**Estrategia de split:** {hyperparams['split']}")
    md.append("")
    md.append("![Learning curves](learning_curves.png)")
    md.append("")

    md.append("## 5. Limitaciones")
    md.append("")
    md.append(
        "- El modelo se entrena sobre el COVID-19 Radiography Database. "
        "Generalizacion a otros centros o equipamientos no garantizada\n"
        "- Sin deteccion out-of-domain: una imagen que no sea una radiografia "
        "de torax devolvera una clase con confianza arbitraria\n"
        "- Sin interpretabilidad (Grad-CAM, etc.): el modelo dice **que** "
        "predice pero no **por que**"
    )
    md.append("")

    return "\n".join(md)


def generate_report(
    model,
    test_dataset,
    output_dir: Path,
    history: dict[str, list[float]],
    hyperparams: dict[str, Any],
    model_version: str = "unknown",
) -> dict[str, Any]:
    """Compute metrics on `test_dataset`, persist artefacts, return metrics dict."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    y_true, y_pred = _collect_predictions(model, test_dataset)
    metrics = _compute_metrics(y_true, y_pred)
    metrics["hyperparameters"] = hyperparams
    metrics["model_version"] = model_version
    metrics["classes"] = list(CLASSES)

    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    _save_confusion_matrix_png(metrics["confusion_matrix"], output_dir / "confusion_matrix.png")
    _save_learning_curves_png(history, output_dir / "learning_curves.png")
    (output_dir / "report.md").write_text(
        _render_markdown_report(metrics, hyperparams, model_version)
    )

    logger.info(
        "Report generated in %s: accuracy=%.4f, macro_f1=%.4f",
        output_dir, metrics["accuracy"], metrics["macro_f1"],
    )
    return metrics
