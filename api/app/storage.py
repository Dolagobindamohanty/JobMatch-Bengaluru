"""Private resume blob storage implementations.

The adapter deliberately exposes only write/delete operations to the API layer.
Resume bytes are parsed during upload but are never returned by an endpoint.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


S3_SETTINGS = (
    "S3_ENDPOINT_URL",
    "S3_BUCKET",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
)


class StorageError(RuntimeError):
    """A configured storage backend could not complete an operation."""


class ResumeStorage(Protocol):
    def put(self, key: str, content: bytes, content_type: str | None = None) -> None: ...

    def delete(self, key: str) -> None: ...


class LocalResumeStorage:
    def __init__(self, root: Path):
        self.root = root

    def put(self, key: str, content: bytes, content_type: str | None = None) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def delete(self, key: str) -> None:
        path = self.root / key
        if path.exists():
            path.unlink()


class S3ResumeStorage:
    def __init__(self, endpoint_url: str, bucket: str, access_key_id: str, secret_access_key: str):
        try:
            import boto3
        except ImportError as error:
            raise StorageError(
                "S3 storage is configured but boto3 is not installed; install the project's s3 extra"
            ) from error
        self.bucket = bucket
        try:
            self.client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
            )
        except Exception as error:
            raise StorageError("Unable to initialize configured S3 storage") from error

    def put(self, key: str, content: bytes, content_type: str | None = None) -> None:
        kwargs = {"Bucket": self.bucket, "Key": key, "Body": content}
        if content_type:
            kwargs["ContentType"] = content_type
        try:
            self.client.put_object(**kwargs)
        except Exception as error:
            raise StorageError("Unable to store resume in configured object storage") from error

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            raise StorageError("Unable to delete resume from configured object storage") from error


def storage_configuration() -> tuple[str, ...]:
    return tuple(name for name in S3_SETTINGS if os.getenv(name))


def get_resume_storage(resume_dir: Path) -> ResumeStorage:
    configured = storage_configuration()
    if configured and len(configured) != len(S3_SETTINGS):
        missing = ", ".join(name for name in S3_SETTINGS if not os.getenv(name))
        raise StorageError(f"Incomplete S3 storage configuration; missing: {missing}")
    if len(configured) == len(S3_SETTINGS):
        return S3ResumeStorage(*(os.environ[name] for name in S3_SETTINGS))
    return LocalResumeStorage(resume_dir)
