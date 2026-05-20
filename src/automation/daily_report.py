"""CLI reproducible para generar el informe diario en Markdown.

Uso:
    python -m src.automation.daily_report                       # hoy UTC
    python -m src.automation.daily_report --date 2026-05-20     # fecha
    python -m src.automation.daily_report --date X --output Y   # destino

NO arranca FastAPI: lee directamente via `MongoReader` + `SqlReader` y
llama al mismo `build_daily_report` que usa el endpoint HTTP. La unica
diferencia es que el CLI renderiza a Markdown determinista (sin
`generated_at`) y escribe a fichero, mientras que el endpoint devuelve
JSON con `generated_at` dinamico.

"Automatizacion" en el sentido del enunciado = comando reproducible
(mismo estado + misma fecha -> mismo fichero), no scheduler.

Ver:
  * specs/automatizacion-alertas.md (RF-5, RNF-6, CA-5, CA-11)
  * design/automatizacion-alertas.md
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from src.api.reports import build_daily_report, render_markdown
from src.api.time_window import day_window_utc

logger = logging.getLogger(__name__)


# Wrappers parcheables: los tests sobreescriben estos nombres con factorias
# que devuelven readers fake (ver tests/automation/test_daily_report.py).
# La importacion real de los readers se aplaza al primer uso para que el
# modulo se pueda importar incluso sin pymongo / sqlalchemy instalados.

def get_sql_reader_from_env():
    """Lazy import: la importacion real ocurre al llamar la funcion."""
    from src.api.sql_reader import get_sql_reader_from_env as _factory
    return _factory()


def get_mongo_reader_from_env():
    """Lazy import: la importacion real ocurre al llamar la funcion."""
    from src.api.mongo_reader import get_mongo_reader_from_env as _factory
    return _factory()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="daily_report",
        description=(
            "Genera el informe diario del hospital en Markdown. "
            "Idempotente byte-a-byte a igualdad de (--date + estado)."
        ),
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Fecha ISO YYYY-MM-DD. Si se omite, hoy UTC.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ruta del fichero de salida. Default: docs/reports/<fecha>.md.",
    )
    return parser.parse_args(argv)


def _resolve_date(raw: str | None) -> date:
    if raw is None:
        return datetime.now(timezone.utc).date()
    return date.fromisoformat(raw)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        target_date = _resolve_date(args.date)
    except ValueError as exc:
        print(f"ERROR: --date invalida: {exc}", file=sys.stderr)
        return 2

    start, end = day_window_utc(target_date)
    threshold = float(os.environ.get("ALERT_REJECTION_RATE_THRESHOLD", "0.10"))

    sql_reader = get_sql_reader_from_env()
    mongo_reader = get_mongo_reader_from_env()
    try:
        state = {
            "failed_runs_in_day": sql_reader.list_failed_runs_between(start, end),
            "runs_in_day": sql_reader.list_runs_between(start, end),
            "quality_snapshots_in_day": sql_reader.list_quality_snapshots_between(
                start, end,
            ),
            "triage_patients_in_day": mongo_reader.list_triage_patients_between(
                start, end,
            ),
            "severe_triage_patients_in_day":
                mongo_reader.list_severe_triage_patients_between(start, end),
            "counts_snapshot": mongo_reader.get_total_counts(),
        }
    finally:
        sql_reader.close()
        mongo_reader.close()

    report = build_daily_report(
        target_date,
        threshold=threshold,
        **state,
    )
    md = render_markdown(report)  # determinista, sin generated_at

    output_path = (
        Path(args.output)
        if args.output
        else Path("docs") / "reports" / f"{target_date.isoformat()}.md"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    print(f"OK: informe escrito en {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
