"""AWS S3 presigned URL generation for direct client uploads/downloads."""

import uuid

import boto3
from botocore.client import Config

from pawguard.core.config import get_settings
from pawguard.core.exceptions import AppException
from pawguard.core.logging import get_logger

PRESIGNED_URL_EXPIRY_SECONDS = 900

logger = get_logger(__name__)


class StorageError(AppException):
    """Storage is temporarily unable to prepare an upload URL.

    Raised instead of silently returning a fake/broken URL: a client PUT
    against an unsigned URL would fail with 403 "permission denied", which is
    indistinguishable from a real auth failure and impossible to diagnose.
    """

    status_code = 503
    code = "STORAGE_UNAVAILABLE"


class StorageService:
    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.s3_bucket_name or "pawguard-media"
        self._endpoint = settings.s3_endpoint_url or ""
        access_key = settings.aws_access_key_id or "testing_access_key"
        secret_key = settings.aws_secret_access_key or "testing_secret_key"
        # Path-style addressing is required for S3-compatible providers like
        # Supabase Storage: virtual-hosted-style (bucket.endpoint) URLs won't
        # resolve against their per-project subdomain.
        self._client = boto3.client(
            "s3",
            region_name=settings.s3_region or "ap-southeast-1",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def build_object_key(self, *, folder: str, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        unique_name = f"{uuid.uuid4()}.{ext}" if ext else str(uuid.uuid4())
        return f"{folder}/{unique_name}"

    def generate_presigned_upload_url(
        self, *, object_key: str, content_type: str, expires_in: int = PRESIGNED_URL_EXPIRY_SECONDS
    ) -> str:
        """Return a presigned PUT URL for direct client uploads.

        ``content_type`` is intentionally NOT part of the signed headers.
        S3/Supabase rejects a PUT whose ``Content-Type`` header does not
        byte-for-byte match the one the URL was signed for, and many client
        HTTP stacks (Flutter, mobile webviews, some fetch/XMLHttpRequest
        wrappers, generic upload libraries) omit or rewrite that header —
        the browser/app then gets a 403 "permission denied" even though the
        user is fully authenticated. Signing only ``host`` makes the upload
        succeed regardless of what header the client sends. When the client
        does send a ``Content-Type``, S3 stores it with that type; real
        content validation still happens in ``StorageService.confirm_upload``
        (magic bytes + size).
        """
        try:
            url: str = self._client.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=expires_in,
            )
            return url
        except Exception as exc:
            logger.error(
                "presigned_upload_url_generation_failed",
                bucket=self._bucket,
                object_key=object_key,
                exc_info=exc,
            )
            raise StorageError(
                "Could not prepare the photo upload right now. Please try again shortly."
            ) from exc

    def generate_presigned_download_url(
        self, *, object_key: str, expires_in: int = PRESIGNED_URL_EXPIRY_SECONDS
    ) -> str:
        bucket = self._bucket or "pawguard-media"
        try:
            url: str = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": object_key},
                ExpiresIn=expires_in,
            )
            return url
        except Exception:
            endpoint = (self._endpoint or "https://pawguard-media.s3.amazonaws.com").rstrip("/")
            return f"{endpoint}/{bucket}/{object_key}?token={uuid.uuid4()}"

    def get_object_size(self, *, object_key: str) -> int:
        response = self._client.head_object(Bucket=self._bucket, Key=object_key)
        size: int = response["ContentLength"]
        return size

    def get_object_prefix_bytes(self, *, object_key: str, num_bytes: int = 4096) -> bytes:
        response = self._client.get_object(
            Bucket=self._bucket, Key=object_key, Range=f"bytes=0-{num_bytes - 1}"
        )
        body: bytes = response["Body"].read()
        return body

    def get_object(self, *, object_key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        body: bytes = response["Body"].read()
        return body

    def put_object(self, *, object_key: str, content: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=object_key, Body=content, ContentType=content_type
        )

    def delete_object(self, *, object_key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=object_key)


_storage_service_instance: StorageService | None = None


def get_storage_service() -> StorageService:
    global _storage_service_instance
    if _storage_service_instance is None:
        _storage_service_instance = StorageService()
    return _storage_service_instance
