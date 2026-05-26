"""Ingesta imagenes PNG de radiografias de torax a MinIO con metadatos extraidos."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.logging_config import get_logger
from src.pipeline.storage.minio_client import MinIOClient

logger = get_logger(__name__)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Se espera que los archivos sigan `{patient_external_id}_{suffix}.png`
# donde patient_external_id es HOSP-NNNNNN.
PATIENT_PREFIX_PATTERN = re.compile(r"^(HOSP-\d{6})_")


@dataclass(frozen=True)
class IngestedImage:
    patient_external_id: str
    original_filename: str
    minio_object_key: str
    file_size_bytes: int
    ingested_at: str  # timestamp ISO en UTC


class ImageIngester:
    def __init__(self, minio_client: MinIOClient, bucket: str) -> None:
        self._minio = minio_client
        self._bucket = bucket

    def ingest_directory(self, directory: Path) -> list[IngestedImage]:
        """Sube cada PNG valido en `directory` a MinIO y devuelve metadatos."""
        path = Path(directory)
        if not path.exists():
            raise FileNotFoundError(f"Image directory does not exist: {path}")

        self._minio.ensure_bucket(self._bucket)

        ingested: list[IngestedImage] = []
        for image_path in sorted(path.iterdir()):
            if not image_path.is_file():
                continue

            meta = self._ingest_one(image_path)
            if meta is not None:
                ingested.append(meta)

        logger.info(
            "Ingested %d images from %s into bucket %s",
            len(ingested),
            path,
            self._bucket,
        )
        return ingested

    def ingest_file(self, image_path: Path) -> IngestedImage | None:
        """Ingesta un unico PNG. Devuelve None si es invalido/corrupto/no soportado.

        Se expone para que los callers que ya saben que archivos sincronizar
        (p.ej. el bootstrap, que omite imagenes ya presentes en MinIO) puedan
        evitar re-escanear un directorio completo.
        """
        self._minio.ensure_bucket(self._bucket)
        return self._ingest_one(Path(image_path))

    def _ingest_one(self, image_path: Path) -> IngestedImage | None:
        if image_path.suffix.lower() != ".png":
            logger.debug("Skipping non-PNG file: %s", image_path.name)
            return None

        match = PATIENT_PREFIX_PATTERN.match(image_path.name)
        if not match:
            logger.warning(
                "Skipping file with unexpected name pattern: %s (expected HOSP-NNNNNN_*.png)",
                image_path.name,
            )
            return None
        patient_id = match.group(1)

        # Validar firma PNG — CB-2: las imagenes corruptas no deben romper el run.
        try:
            with image_path.open("rb") as f:
                header = f.read(len(PNG_SIGNATURE))
        except OSError as exc:
            logger.error("Could not read %s: %s", image_path.name, exc)
            return None

        if header != PNG_SIGNATURE:
            logger.warning("Skipping corrupt/invalid PNG: %s", image_path.name)
            return None

        # Object key determinista — re-subir el mismo archivo es idempotente
        # porque MinIO sobrescribe con la misma key.
        object_key = f"{patient_id}/{image_path.name}"
        file_size = image_path.stat().st_size
        now = datetime.now(timezone.utc)

        try:
            self._minio.upload_file(self._bucket, object_key, image_path)
        except Exception as exc:  # pragma: no cover - depende de que MinIO este arriba
            logger.error("Failed to upload %s: %s", image_path.name, exc)
            return None

        return IngestedImage(
            patient_external_id=patient_id,
            original_filename=image_path.name,
            minio_object_key=object_key,
            file_size_bytes=file_size,
            ingested_at=now.isoformat(),
        )
