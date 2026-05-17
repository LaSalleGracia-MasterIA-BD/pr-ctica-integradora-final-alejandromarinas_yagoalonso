"""Wrapper around minio-py with hospital-specific defaults."""
from __future__ import annotations

import io
import os
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)


class MinIOClient:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = False,
    ) -> None:
        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    def ensure_bucket(self, bucket: str) -> None:
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)
            logger.info("Created bucket %s", bucket)

    def bucket_exists(self, bucket: str) -> bool:
        return self._client.bucket_exists(bucket)

    def remove_bucket(self, bucket: str) -> None:
        self._client.remove_bucket(bucket)

    def upload_file(self, bucket: str, key: str, file_path: Path) -> None:
        self._client.fput_object(bucket, key, str(file_path))
        logger.info("Uploaded %s to %s/%s", file_path, bucket, key)

    def upload_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        stream = io.BytesIO(data)
        self._client.put_object(
            bucket,
            key,
            data=stream,
            length=len(data),
            content_type=content_type,
        )

    def download_file(self, bucket: str, key: str, file_path: Path) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        self._client.fget_object(bucket, key, str(file_path))

    def download_bytes(self, bucket: str, key: str) -> bytes:
        """Read an object entirely into memory.

        Used by the classification endpoint, which needs the bytes for
        in-memory preprocessing without round-tripping through the
        filesystem. Propagates `S3Error` (e.g. `NoSuchKey`) unmodified
        so the caller can map it to a 404.
        """
        response = self._client.get_object(bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self._client.stat_object(bucket, key)
            return True
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                return False
            raise

    def list_objects(self, bucket: str, prefix: str | None = None) -> list[str]:
        return [
            obj.object_name
            for obj in self._client.list_objects(bucket, prefix=prefix, recursive=True)
        ]

    def remove_object(self, bucket: str, key: str) -> None:
        self._client.remove_object(bucket, key)


def get_minio_client_from_env() -> MinIOClient:
    endpoint = f"{os.environ['MINIO_HOST']}:{os.environ['MINIO_PORT']}"
    return MinIOClient(
        endpoint=endpoint,
        access_key=os.environ["MINIO_ROOT_USER"],
        secret_key=os.environ["MINIO_ROOT_PASSWORD"],
        secure=False,
    )
