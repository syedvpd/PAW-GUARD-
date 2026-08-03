"""StorageService: owns file upload/download lifecycle business behaviour (RULE-003).

Wraps the shared S3 StorageService for presigned URL generation and manages
StoredFile metadata records in the database.
"""

import uuid
from datetime import UTC, datetime
from io import BytesIO

from PIL import Image as PILImage

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.core.logging import get_logger
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.core.upload import (
    MAX_FILE_SIZE_BYTES,
    UploadError,
    create_thumbnail,
    verify_mime_type,
)
from pawguard.modules.storage.models import StoredFile
from pawguard.modules.storage.repository import StorageRepository
from pawguard.modules.storage.schemas import (
    DownloadUrlResponse,
    StoredFileCreate,
    StoredFileResponse,
    UploadUrlResponse,
)
from pawguard.services.storage_service import StorageService as S3StorageService

logger = get_logger(__name__)


class StorageService:
    def __init__(
        self, repository: StorageRepository, s3: S3StorageService
    ) -> None:
        self._repo = repository
        self._s3 = s3

    async def request_upload_url(
        self,
        payload: StoredFileCreate,
        *,
        user_id: uuid.UUID | None = None,
    ) -> UploadUrlResponse:
        object_key = self._s3.build_object_key(
            folder=payload.folder.value, filename=payload.original_filename
        )
        stored = StoredFile(
            user_id=user_id,
            object_key=object_key,
            original_filename=payload.original_filename,
            mime_type=payload.mime_type,
            file_size=payload.file_size,
            folder=payload.folder.value,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
        )
        stored = await self._repo.create(stored)

        upload_url = self._s3.generate_presigned_upload_url(
            object_key=object_key, content_type=payload.mime_type
        )
        return UploadUrlResponse(
            upload_url=upload_url,
            object_key=object_key,
            file_id=stored.id,
        )

    async def confirm_upload(self, file_id: uuid.UUID) -> StoredFile:
        """Verifies the object actually uploaded to S3 before trusting it.

        The presigned-URL flow means the client uploads bytes straight to S3;
        the declared mime_type/file_size on StoredFile are otherwise just
        client-supplied claims. This re-checks real size and file-signature
        (magic bytes) against the object S3 received, deleting it and
        rejecting confirmation if it doesn't match what was declared.
        """
        stored = await self._repo.get_by_id(file_id)
        if stored is None:
            raise NotFoundError("Stored file not found.")

        try:
            actual_size = self._s3.get_object_size(object_key=stored.object_key)
            if actual_size > MAX_FILE_SIZE_BYTES:
                raise UploadError(
                    f"Uploaded file exceeds maximum size of "
                    f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB (got {actual_size} bytes)."
                )
            prefix = self._s3.get_object_prefix_bytes(object_key=stored.object_key)
            detected_mime = verify_mime_type(prefix, stored.mime_type)
        except UploadError as exc:
            self._s3.delete_object(object_key=stored.object_key)
            await self._repo._session.delete(stored)
            await self._repo._session.flush()
            raise ValidationFailedError(str(exc)) from exc

        stored.mime_type = detected_mime
        stored.file_size = actual_size
        stored.is_uploaded = True
        stored.uploaded_at = datetime.now(UTC)
        if detected_mime.startswith("image/") and stored.thumbnail_object_key is None:
            await self._generate_thumbnail(stored)
        await self._repo._session.flush()
        await self._repo._session.refresh(stored)
        return stored

    async def _generate_thumbnail(self, stored: StoredFile) -> None:
        """Create and store an EXIF-free thumbnail for an image upload.

        Thumbnailing is best-effort: a failure to decode or re-encode the image
        must never reject an upload that already verified, so it is logged and
        the stored file simply keeps ``thumbnail_object_key`` unset.
        """
        try:
            content = self._s3.get_object(object_key=stored.object_key)
            thumbnail = create_thumbnail(content, max_size=400)
            if thumbnail is None:
                return
            fmt = PILImage.open(BytesIO(thumbnail)).format
            base = stored.object_key.rsplit(".", 1)[0]
            if "." not in stored.object_key:
                base = stored.object_key
            if fmt == "PNG":
                thumbnail_key = f"{base}_thumb.png"
                thumbnail_mime = "image/png"
            else:
                thumbnail_key = f"{base}_thumb.jpg"
                thumbnail_mime = "image/jpeg"
            self._s3.put_object(
                object_key=thumbnail_key, content=thumbnail, content_type=thumbnail_mime
            )
            stored.thumbnail_object_key = thumbnail_key
        except Exception:
            logger.warning(
                "thumbnail_generation_failed",
                object_key=stored.object_key,
                exc_info=True,
            )

    async def get_download_url(self, file_id: uuid.UUID) -> DownloadUrlResponse:
        stored = await self._repo.get_by_id(file_id)
        if stored is None:
            raise NotFoundError("Stored file not found.")
        download_url = self._s3.generate_presigned_download_url(
            object_key=stored.object_key
        )
        return DownloadUrlResponse(
            download_url=download_url,
            object_key=stored.object_key,
            file_id=stored.id,
        )

    async def get_file(self, file_id: uuid.UUID) -> StoredFile:
        stored = await self._repo.get_by_id(file_id)
        if stored is None:
            raise NotFoundError("Stored file not found.")
        return stored

    async def list_files_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        folder: str | None = None,
        mime_type: str | None = None,
        is_uploaded: bool | None = None,
        user_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[StoredFileResponse]:
        results, total = await self._repo.list_paginated(
            page=page,
            sort=sort,
            search_term=search_term,
            folder=folder,
            mime_type=mime_type,
            is_uploaded=is_uploaded,
            user_id=user_id,
        )
        return PaginatedResponse(
            data=[StoredFileResponse.model_validate(f) for f in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def delete_file(self, file_id: uuid.UUID) -> None:
        stored = await self._repo.get_by_id(file_id)
        if stored is None:
            raise NotFoundError("Stored file not found.")
        stored.deleted_at = datetime.now(UTC)
        await self._repo._session.flush()

    async def list_by_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        page: PageParams,
        sort: SortParams,
        folder: str | None = None,
    ) -> PaginatedResponse[StoredFileResponse]:
        results, total = await self._repo.list_by_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            page=page,
            sort=sort,
            folder=folder,
        )
        return PaginatedResponse(
            data=[StoredFileResponse.model_validate(f) for f in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def bulk_delete_files(self, ids: list[uuid.UUID]) -> int:
        count = 0
        for file_id in ids:
            stored = await self._repo.get_by_id(file_id)
            if stored is not None:
                stored.deleted_at = datetime.now(UTC)
                count += 1
        await self._repo._session.flush()
        return count
