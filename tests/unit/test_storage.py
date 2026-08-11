"""Unit tests for StorageService with mocked repository and S3 client."""

import base64
import uuid
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.modules.storage.models import StoredFile
from pawguard.modules.storage.repository import StorageRepository
from pawguard.modules.storage.service import StorageService
from pawguard.services.storage_service import StorageError
from pawguard.services.storage_service import StorageService as S3StorageService

# A real 1x1 PNG so python-magic's signature detection recognizes it.
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _jpeg_bytes() -> bytes:
    """A real small JPEG so python-magic's signature detection recognizes it."""
    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(0, 128, 255)).save(buf, format="JPEG")
    return buf.getvalue()

# A real 1x1 PNG so python-magic's signature detection recognizes it.
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _make_file(**kw):
    now = datetime.now(UTC)
    vals = dict(
        object_key="dogs/abc.jpg", original_filename="abc.jpg", mime_type="image/jpeg",
        file_size=1024, folder="dogs", is_uploaded=False, created_at=now, updated_at=now,
    )
    vals.update(kw)
    return StoredFile(**vals)


class TestStorageService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=StorageRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_s3(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo, mock_s3):
        return StorageService(mock_repo, mock_s3)

    @pytest.mark.asyncio
    async def test_confirm_upload_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.confirm_upload(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_confirm_upload_verifies_real_object(self, service, mock_repo, mock_s3):
        file_id = uuid.uuid4()
        stored = _make_file(id=file_id, mime_type="image/png", file_size=999)
        mock_repo.get_by_id.return_value = stored
        mock_s3.get_object_size.return_value = 2048
        mock_s3.get_object_prefix_bytes.return_value = _PNG_BYTES
        mock_s3.get_object.return_value = _PNG_BYTES

        result = await service.confirm_upload(file_id)

        assert result.is_uploaded is True
        assert result.file_size == 2048
        assert result.mime_type == "image/png"
        mock_s3.delete_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_upload_generates_thumbnail(self, service, mock_repo, mock_s3):
        file_id = uuid.uuid4()
        stored = _make_file(id=file_id, mime_type="image/jpeg", file_size=999)
        mock_repo.get_by_id.return_value = stored
        mock_s3.get_object_size.return_value = len(_jpeg_bytes())
        mock_s3.get_object_prefix_bytes.return_value = _jpeg_bytes()
        mock_s3.get_object.return_value = _jpeg_bytes()

        result = await service.confirm_upload(file_id)

        mock_s3.put_object.assert_called_once()
        put_kwargs = mock_s3.put_object.call_args.kwargs
        assert put_kwargs["object_key"] == "dogs/abc_thumb.jpg"
        assert put_kwargs["content_type"] == "image/jpeg"
        assert result.thumbnail_object_key == "dogs/abc_thumb.jpg"

    @pytest.mark.asyncio
    async def test_confirm_upload_thumbnail_failure_does_not_reject(self, service, mock_repo, mock_s3):
        file_id = uuid.uuid4()
        stored = _make_file(id=file_id, mime_type="image/jpeg", file_size=999)
        mock_repo.get_by_id.return_value = stored
        mock_s3.get_object_size.return_value = len(_jpeg_bytes())
        mock_s3.get_object_prefix_bytes.return_value = _jpeg_bytes()
        # Undecodable object bytes -> thumbnail generation returns None.
        mock_s3.get_object.return_value = b"garbage not an image"

        result = await service.confirm_upload(file_id)

        assert result.is_uploaded is True
        assert result.thumbnail_object_key is None
        mock_s3.put_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_upload_rejects_oversized_object(self, service, mock_repo, mock_s3):
        file_id = uuid.uuid4()
        stored = _make_file(id=file_id)
        mock_repo.get_by_id.return_value = stored
        mock_s3.get_object_size.return_value = 60 * 1024 * 1024

        with pytest.raises(ValidationFailedError, match="exceeds maximum size"):
            await service.confirm_upload(file_id)

        mock_s3.delete_object.assert_called_once_with(object_key=stored.object_key)
        assert stored.is_uploaded is False

    @pytest.mark.asyncio
    async def test_confirm_upload_rejects_disallowed_signature(self, service, mock_repo, mock_s3):
        file_id = uuid.uuid4()
        stored = _make_file(id=file_id, mime_type="image/jpeg")
        mock_repo.get_by_id.return_value = stored
        mock_s3.get_object_size.return_value = 128
        # Executable/script signature, not in the allowlist.
        mock_s3.get_object_prefix_bytes.return_value = b"#!/bin/sh\necho pwned\n"

        with pytest.raises(ValidationFailedError):
            await service.confirm_upload(file_id)

        mock_s3.delete_object.assert_called_once_with(object_key=stored.object_key)
        assert stored.is_uploaded is False

    @pytest.mark.asyncio
    async def test_confirm_upload_rejects_oversized_batch(
        self, service, mock_repo, mock_s3
    ):
        """When batch_file_ids are provided the combined size is checked
        against the 50 MB cap before the individual file is confirmed."""
        file_id = uuid.uuid4()
        stored = _make_file(id=file_id, mime_type="image/png", file_size=1024)
        mock_repo.get_by_id.return_value = stored
        mock_repo.list_by_ids.return_value = [
            _make_file(id=uuid.uuid4(), file_size=30 * 1024 * 1024),
            _make_file(id=uuid.uuid4(), file_size=25 * 1024 * 1024),
        ]
        mock_s3.get_object_size.return_value = 1024
        mock_s3.get_object_prefix_bytes.return_value = _PNG_BYTES

        with pytest.raises(ValidationFailedError, match="exceeds the 50 MB limit"):
            await service.confirm_upload(
                file_id,
                batch_file_ids=[f.id for f in mock_repo.list_by_ids.return_value],
            )


class TestS3PresignedUploadUrl:
    """Regression tests for the shared S3 presigned-upload contract.

    Root cause of the recurring "photo upload blocked (permission denied)"
    report: the upload URL used to be signed for ``content-type``, so S3
    rejected any PUT whose Content-Type header did not byte-for-byte match
    the value passed to ``/…/media-upload-url``. Real clients (Flutter,
    mobile webviews, generic fetch/upload wrappers) often omit or rewrite
    that header, producing a 403 that looked like an auth failure. The URL
    must be signed for ``host`` only.
    """

    def _service(self, mock_client: MagicMock) -> S3StorageService:
        with patch("pawguard.services.storage_service.boto3.client", return_value=mock_client):
            return S3StorageService()

    def test_upload_url_does_not_sign_content_type(self) -> None:
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://bucket/signed?X-Amz-SignedHeaders=host"
        svc = self._service(mock_client)

        url = svc.generate_presigned_upload_url(
            object_key="rescue/evidence.jpg", content_type="image/jpeg"
        )

        _, kwargs = mock_client.generate_presigned_url.call_args
        params = kwargs["Params"]
        assert params["Bucket"] == "pawguard-media"
        assert params["Key"] == "rescue/evidence.jpg"
        assert "ContentType" not in params, (
            "Content-Type must NOT be signed or clients that omit/mismatch "
            "the header get 403 permission denied."
        )
        assert "SignedHeaders=host" in url

    def test_upload_url_raises_storage_error_instead_of_fake_url(self) -> None:
        mock_client = MagicMock()
        mock_client.generate_presigned_url.side_effect = RuntimeError("boom")
        svc = self._service(mock_client)

        with pytest.raises(StorageError):
            svc.generate_presigned_upload_url(
                object_key="rescue/evidence.jpg", content_type="image/jpeg"
            )
