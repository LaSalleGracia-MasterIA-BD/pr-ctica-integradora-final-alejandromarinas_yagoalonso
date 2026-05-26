"""Vigila un directorio de entrada y dispara el pipeline cuando llegan ambos CSVs.

El watcher es deliberadamente simple: espera hasta que `patients.csv` y
`admissions.csv` esten presentes en el directorio de entrada, llama una
unica vez al callback proporcionado con sus paths, y mueve los archivos a
`incoming/processed/` para que el siguiente batch arranque limpio.

Esto cubre el lado del trigger automatico de RF-7 (el otro lado es un
endpoint manual de la API provisto por T10).
"""
from __future__ import annotations

import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)

PATIENTS_FILENAME = "patients.csv"
ADMISSIONS_FILENAME = "admissions.csv"

OnReadyCallback = Callable[[Path, Path], None]


class IncomingFilesWatcher:
    """Vigila `incoming_dir` esperando la llegada de los CSVs de pacientes+ingresos."""

    def __init__(
        self,
        incoming_dir: Path,
        on_ready: OnReadyCallback,
        processed_subdir: str = "processed",
    ) -> None:
        self._incoming_dir = Path(incoming_dir)
        if not self._incoming_dir.exists():
            raise FileNotFoundError(
                f"Incoming directory does not exist: {self._incoming_dir}"
            )

        self._processed_dir = self._incoming_dir / processed_subdir
        self._processed_dir.mkdir(parents=True, exist_ok=True)

        self._on_ready = on_ready
        self._observer: Observer | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._observer is not None:
            return
        handler = _IncomingEventHandler(self._check_and_trigger)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._incoming_dir), recursive=False)
        self._observer.start()
        logger.info("Watching %s for incoming CSVs", self._incoming_dir)

        # Disparar un chequeo inicial por si los archivos ya estaban antes del start
        self._check_and_trigger()

    def stop(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=2.0)
        self._observer = None

    def _check_and_trigger(self) -> None:
        with self._lock:
            patients = self._incoming_dir / PATIENTS_FILENAME
            admissions = self._incoming_dir / ADMISSIONS_FILENAME
            if not (patients.exists() and admissions.exists()):
                return

            logger.info("Both CSVs detected, invoking callback")
            try:
                self._on_ready(patients, admissions)
            except Exception:
                logger.exception("Callback raised; files will NOT be moved to processed/")
                return

            self._move_to_processed(patients)
            self._move_to_processed(admissions)

    def _move_to_processed(self, path: Path) -> None:
        target = self._processed_dir / path.name
        if target.exists():
            target.unlink()
        shutil.move(str(path), str(target))
        logger.info("Moved %s -> %s", path.name, target)


class _IncomingEventHandler(FileSystemEventHandler):
    def __init__(self, on_event: Callable[[], None]) -> None:
        super().__init__()
        self._on_event = on_event

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        filename = Path(event.src_path).name
        if filename in (PATIENTS_FILENAME, ADMISSIONS_FILENAME):
            self._on_event()
