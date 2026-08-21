"""Data access for the Storage module.

Repositories never contain business decisions (RULE-002).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.storage.models import StoredFile


class StorageRepository:
    SEARCH_FIELDS = ("original_filename", "folder", "mime_type")
    SORTABLE_FIELDS = {
        "created_at",
        "updated_at",
        "uploaded_at",
        "original_filename",
        "file_size",
        "folder",
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, file: StoredFile) -> StoredFile:
        self._session.add(file)
        await self._session.flush()
        await self._session.refresh(file)
        return file

    async def get_by_id(self, file_id: uuid.UUID) -> StoredFile | None:
        stmt = select(StoredFile).where(StoredFile.id == file_id, StoredFile.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_key(self, object_key: str) -> StoredFile | None:
        stmt = select(StoredFile).where(
            StoredFile.object_key == object_key, StoredFile.deleted_at.is_(None)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        folder: str | None = None,
        mime_type: str | None = None,
        is_uploaded: bool | None = None,
        user_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[StoredFile], int]:
        stmt = select(StoredFile).where(StoredFile.deleted_at.is_(None))

        search_filter = build_search_filter(StoredFile, search_term, self.SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        if folder is not None:
            stmt = stmt.where(StoredFile.folder == folder)
        if mime_type is not None:
            stmt = stmt.where(StoredFile.mime_type == mime_type)
        if is_uploaded is not None:
            stmt = stmt.where(StoredFile.is_uploaded == is_uploaded)
        if user_id is not None:
            stmt = stmt.where(StoredFile.user_id == user_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS)
        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_by_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        page: PageParams,
        sort: SortParams,
        folder: str | None = None,
    ) -> tuple[Sequence[StoredFile], int]:
        stmt = select(StoredFile).where(
            StoredFile.deleted_at.is_(None),
            StoredFile.entity_type == entity_type,
            StoredFile.entity_id == entity_id,
        )

        if folder is not None:
            stmt = stmt.where(StoredFile.folder == folder)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS)
        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def list_by_ids(self, ids: list[uuid.UUID]) -> Sequence[StoredFile]:
        stmt = select(StoredFile).where(StoredFile.id.in_(ids), StoredFile.deleted_at.is_(None))
        return (await self._session.execute(stmt)).scalars().all()

    async def soft_delete(self, file_id: uuid.UUID) -> StoredFile | None:
        file = await self.get_by_id(file_id)
        if file is None:
            return None
        from datetime import UTC, datetime

        file.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return file

    async def bulk_soft_delete(self, ids: list[uuid.UUID]) -> int:
        from datetime import UTC, datetime

        stmt = (
            update(StoredFile)
            .where(StoredFile.id.in_(ids), StoredFile.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]
