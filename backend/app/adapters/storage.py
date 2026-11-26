"""File storage: S3-compatible bucket in an Indian region; local disk or memory otherwise."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.adapters.errors import AdapterError, NotConfiguredError
from app.core.config import Settings


class Storage(Protocol):
    name: str
    sandbox: bool

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


@dataclass
class MemoryStorage:
    name: str = "memory"
    sandbox: bool = True
    blobs: dict[str, bytes] = field(default_factory=dict)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.blobs[key] = data
        return key

    def get(self, key: str) -> bytes:
        if key not in self.blobs:
            raise AdapterError(f"missing blob {key}")
        return self.blobs[key]

    def delete(self, key: str) -> None:
        self.blobs.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self.blobs


class LocalStorage:
    name = "local"
    sandbox = True

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root):
            raise AdapterError("invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise AdapterError(f"missing blob {key}") from exc

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3Storage:
    name = "s3"
    sandbox = False

    def __init__(self, settings: Settings) -> None:
        if not (settings.s3_bucket and settings.s3_access_key_id):
            raise NotConfiguredError("S3_BUCKET / S3_ACCESS_KEY_ID missing")
        import boto3

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return key

    def get(self, key: str) -> bytes:
        return bytes(self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read())

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return False
        return True
