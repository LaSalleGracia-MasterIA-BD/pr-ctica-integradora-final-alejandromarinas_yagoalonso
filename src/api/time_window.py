"""Helpers de ventana temporal usados por /reports/daily y daily_report.py.

Centraliza la definicion de "dia UTC" para que el endpoint y el script
CLI usen exactamente el mismo intervalo. Ver spec automatizacion-alertas
RF-4 + design.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone


def day_window_utc(day: date) -> tuple[datetime, datetime]:
    """Devuelve [00:00:00.000Z, 23:59:59.999999Z] UTC para `day`.

    Inclusivo en ambos extremos. Usado por:
      * GET /api/v1/reports/daily (router/reports.py)
      * src/automation/daily_report.py (CLI)

    Mantener un unico punto de calculo evita drift entre endpoint y
    script (ambos consultarian intervalos distintos por error).
    """
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end
