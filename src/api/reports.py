"""Builder + render del informe diario (Feature 15).

Dos funciones puras:

* `build_daily_report(day, **state)` agrega los datos del dia y devuelve
  el dict JSON definido en spec RF-4.
* `render_markdown(report)` renderiza el dict a Markdown determinista.
  NO incluye `generated_at` ni cualquier otra cosa dependiente del reloj:
  asi se garantiza idempotencia byte-a-byte (RNF-6 + CA-11) para el
  script `daily_report.py`.

Ambas funciones son puras (sin IO, sin lectura de env): el endpoint
y el script las invocan tras hacer las lecturas necesarias.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Any

from src.api.alerts import evaluate


# -- Builder ------------------------------------------------------------


def build_daily_report(
    day: date,
    *,
    failed_runs_in_day: list[dict],
    runs_in_day: list[dict],
    quality_snapshots_in_day: list[dict],
    triage_patients_in_day: list[dict],
    severe_triage_patients_in_day: list[dict],
    counts_snapshot: dict,
    threshold: float,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Agrega el estado del dia en la estructura JSON de RF-4.

    `generated_at` es metadato del momento de calculo: el endpoint pasa
    `None` y se rellena con `datetime.now(UTC)`; el script lo deja en
    `None` tambien — el render NO lo usa, asi que da igual su valor.
    """
    triage_counts = _count_triage_by_level(triage_patients_in_day)
    quality_by_dim = _quality_summary_per_dimension(quality_snapshots_in_day)
    alerts = evaluate(
        failed_runs_in_day,
        quality_snapshots_in_day,
        severe_triage_patients_in_day,
        threshold=threshold,
    )
    return {
        "date": day.isoformat(),
        "generated_at": (
            generated_at or datetime.now(timezone.utc)
        ).isoformat(),
        "pipeline": {
            "last_run_of_day": _last_or_none(runs_in_day),
            "runs_in_day": len(runs_in_day),
            "failed_in_day": len(failed_runs_in_day),
        },
        "quality": quality_by_dim,
        "counts": dict(counts_snapshot),
        "triage": {
            **triage_counts,
            "in_day_total": sum(triage_counts.values()),
        },
        "alerts": [_alert_to_jsonable(a) for a in alerts],
        "threshold": threshold,
    }


def _last_or_none(runs: list[dict]) -> dict | None:
    """Ultimo run del dia segun `started_at`. None si no hay."""
    if not runs:
        return None
    return max(runs, key=lambda r: r["started_at"])


def _count_triage_by_level(patients: list[dict]) -> dict[str, int]:
    """Cuenta grave/medio/leve garantizando las 3 claves (cero si falta)."""
    counts = {"grave": 0, "medio": 0, "leve": 0}
    for p in patients:
        level = (p.get("triage") or {}).get("level")
        if level in counts:
            counts[level] += 1
    return counts


def _quality_summary_per_dimension(snapshots: list[dict]) -> dict[str, dict]:
    """Para cada dimension, ultimo snapshot del dia (por `recorded_at`)."""
    latest: dict[str, dict] = {}
    for snap in snapshots:
        dim = snap["dimension"]
        if dim not in latest or snap["recorded_at"] > latest[dim]["recorded_at"]:
            latest[dim] = snap
    return {
        dim: {
            "total": s["total"],
            "valid": s["valid"],
            "rejected": s["rejected"],
            "rejection_rate": s["rejection_rate"],
        }
        for dim, s in latest.items()
    }


def _alert_to_jsonable(alert) -> dict:
    """`asdict(Alert)` pero con `created_at` como ISO string."""
    d = asdict(alert)
    if isinstance(d.get("created_at"), datetime):
        d["created_at"] = d["created_at"].isoformat()
    return d


# -- Render -------------------------------------------------------------


def render_markdown(report: dict) -> str:
    """Renderiza el report dict a Markdown byte-a-byte estable.

    NO incluye `generated_at` ni nada dependiente del reloj. Las listas
    se ordenan por claves estables (id, dimension, source_id).
    """
    lines: list[str] = []
    lines.append(f"# Informe diario - {report['date']}")
    lines.append("")

    # -- Pipeline -------------------------------------------------------
    lines.append("## Pipeline")
    lines.append("")
    pipe = report["pipeline"]
    lines.append(f"- Runs del dia: {pipe['runs_in_day']}")
    lines.append(f"- Runs fallidos: {pipe['failed_in_day']}")
    last = pipe.get("last_run_of_day")
    if last:
        lines.append(
            f"- Ultimo run: `{last['id']}` "
            f"(status={last['status']}, trigger={last.get('trigger_type', '?')})"
        )
    else:
        lines.append("- Ultimo run: sin actividad en el dia")
    lines.append("")

    # -- Calidad de datos ----------------------------------------------
    lines.append("## Calidad de datos")
    lines.append("")
    quality = report["quality"]
    if not quality:
        lines.append("- Sin snapshots de calidad en el dia")
    else:
        for dim in sorted(quality.keys()):
            q = quality[dim]
            lines.append(
                f"- {dim}: total={q['total']} valid={q['valid']} "
                f"rejected={q['rejected']} rate={q['rejection_rate']:.4f}"
            )
    lines.append("")

    # -- Conteos --------------------------------------------------------
    lines.append("## Conteos")
    lines.append("")
    counts = report["counts"]
    for key in sorted(counts.keys()):
        lines.append(f"- {key}: {counts[key]}")
    lines.append("")

    # -- Triaje --------------------------------------------------------
    lines.append("## Triaje")
    lines.append("")
    tri = report["triage"]
    lines.append(f"- Total triajes del dia: {tri.get('in_day_total', 0)}")
    for level in ("grave", "medio", "leve"):
        lines.append(f"- {level}: {tri.get(level, 0)}")
    lines.append("")

    # -- Alertas -------------------------------------------------------
    lines.append("## Alertas")
    lines.append("")
    alerts = report.get("alerts", [])
    if not alerts:
        lines.append("- Sin alertas en el dia")
    else:
        # Re-ordenar por (severity_order, source_id) para estabilidad
        # determinista incluso si llegan en orden distinto. `evaluate`
        # ya ordena por created_at, pero usamos source_id como tie-break
        # estable.
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        ordered = sorted(
            alerts,
            key=lambda a: (
                severity_order.get(a["severity"], 99),
                a.get("created_at", ""),
                a.get("source_id") or "",
            ),
        )
        for a in ordered:
            lines.append(
                f"- [{a['severity'].upper()}] {a['title']} "
                f"({a['source']}#{a.get('source_id', '-') or '-'})"
            )
    lines.append("")

    return "\n".join(lines)
