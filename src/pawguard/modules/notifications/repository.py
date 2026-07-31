"""Data access for notifications."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.modules.notifications.models import Notification, NotificationPreference


class NotificationRepository:
    SEARCH_FIELDS = ("title", "body", "notification_type")
    SORTABLE_FIELDS = {"created_at", "sent_at", "title", "notification_type"}

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, notification: Notification) -> Notification:
        self._session.add(notification)
        await self._session.flush()
        await self._session.refresh(notification)
        return notification

    async def create_broadcast(self, notification: Notification) -> Notification:
        return await self.create(notification)

    async def list_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        user_id: uuid.UUID | None = None,
        search_term: str | None = None,
        notification_type: str | None = None,
        is_read: bool | None = None,
    ) -> tuple[Sequence[Notification], int]:
        stmt = select(Notification).where(Notification.deleted_at.is_(None))

        if user_id is not None:
            stmt = stmt.where(Notification.user_id == user_id)
        if notification_type is not None:
            stmt = stmt.where(Notification.notification_type == notification_type)
        if is_read is not None:
            stmt = stmt.where(Notification.is_read.is_(is_read))

        search_filter = build_search_filter(Notification, search_term, self.SEARCH_FIELDS)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        stmt = apply_sorting(stmt, sort, self.SORTABLE_FIELDS)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page.offset).limit(page.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def mark_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification | None:
        stmt = (
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(is_read=True, read_at=func.now())
        )
        await self._session.execute(stmt)
        return await self.get(notification_id)

    async def mark_all_read(self, user_id: uuid.UUID) -> None:
        stmt = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True, read_at=func.now())
        )
        await self._session.execute(stmt)

    async def get(self, notification_id: uuid.UUID) -> Notification | None:
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_unread(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(Notification.id))
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def soft_delete(self, notification_id: uuid.UUID) -> Notification | None:
        notification = await self.get(notification_id)
        if notification is None:
            return None
        notification.deleted_at = datetime.now(UTC)
        return notification

    async def delete(self, notification_id: uuid.UUID) -> bool:
        stmt = select(Notification).where(Notification.id == notification_id)
        notification = (await self._session.execute(stmt)).scalar_one_or_none()
        if notification is None:
            return False
        await self._session.delete(notification)
        return True

    async def bulk_soft_delete(self, ids: list[uuid.UUID]) -> int:
        stmt = (
            update(Notification)
            .where(Notification.id.in_(ids), Notification.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined,no-any-return]


class NotificationPreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user(self, user_id: uuid.UUID) -> NotificationPreference | None:
        stmt = select(NotificationPreference).where(
            NotificationPreference.user_id == user_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self, user_id: uuid.UUID, **kwargs: bool | str | None
    ) -> NotificationPreference:
        existing = await self.get_by_user(user_id)
        if existing:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            return existing
        pref = NotificationPreference(user_id=user_id, **kwargs)
        self._session.add(pref)
        await self._session.flush()
        await self._session.refresh(pref)
        return pref
