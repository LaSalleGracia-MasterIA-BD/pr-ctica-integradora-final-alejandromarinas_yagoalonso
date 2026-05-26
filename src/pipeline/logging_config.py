"""Configuracion centralizada de logging para el pipeline del hospital."""
from __future__ import annotations

import logging
import os
import sys

DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str | None = None, log_format: str | None = None) -> None:
    """Configura el root logger una unica vez para todo el pipeline.

    Las llamadas posteriores son no-op para evitar duplicar handlers.
    """
    root = logging.getLogger()
    if root.handlers:
        return

    resolved_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    fmt = log_format or DEFAULT_LOG_FORMAT

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt=DEFAULT_DATE_FORMAT))

    root.addHandler(handler)
    root.setLevel(resolved_level)


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger que comparte la configuracion global del pipeline."""
    setup_logging()
    return logging.getLogger(name)
