"""Unit tests for StorageService with mocked repository and S3 client."""

import base64
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.modules.storage.models import StoredFile
from pawguard.modules.storage.repository import StorageRepository
from pawguard.modules.storage.service import StorageService

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

        result = await service.confirm_upload(file_id)

        assert result.is_uploaded is True
        assert result.file_size == 2048
        assert result.mime_type == "image/png"
        mock_s3.delete_object.assert_not_called()

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
