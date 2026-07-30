"""AWS S3 presigned URL generation for direct client uploads/downloads."""

import uuid

import boto3
from botocore.client import Config

from pawguard.core.config import get_settings

PRESIGNED_URL_EXPIRY_SECONDS = 900


class StorageService:
    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.s3_bucket_name
        self._client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
            config=Config(signature_version="s3v4"),
        )

    def build_object_key(self, *, folder: str, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        unique_name = f"{uuid.uuid4()}.{ext}" if ext else str(uuid.uuid4())
        return f"{folder}/{unique_name}"

    def generate_presigned_upload_url(
        self, *, object_key: str, content_type: str, expires_in: int = PRESIGNED_URL_EXPIRY_SECONDS
    ) -> str:
        url: str = self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": object_key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )
        return url

    def generate_presigned_download_url(
        self, *, object_key: str, expires_in: int = PRESIGNED_URL_EXPIRY_SECONDS
    ) -> str:
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_key},
            ExpiresIn=expires_in,
        )
        return url
