"""NotificationService: in-app notification business behaviour (RULE-003)."""

import uuid

from arq import ArqRedis

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.modules.notifications.models import Notification, NotificationPreference
from pawguard.modules.notifications.repository import (
    NotificationPreferenceRepository,
    NotificationRepository,
)
from pawguard.modules.notifications.schemas import (
    BroadcastCreate,
    NotificationCreate,
    NotificationResponse,
    NotificationSend,
)
from pawguard.services.audit_service import AuditService


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository,
        arq_pool: ArqRedis | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repository
        self._arq = arq_pool
        self._audit = audit_service

    async def create_notification(
        self, payload: NotificationCreate,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=payload.user_id,
            title=payload.title,
            body=payload.body,
            notification_type=payload.notification_type,
            action_url=payload.action_url,
        )
        result = await self._repo.create(notification)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.NOTIFICATION_SENT,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"notification_id": str(result.id)},
            )
        return result

    async def broadcast(
        self, payload: BroadcastCreate,
        user_ids: list[uuid.UUID],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> list[Notification]:
        # Merge explicit user_ids with users resolved from target_roles
        target_ids = set(user_ids)
        if payload.target_roles:
            from pawguard.modules.auth.repository import UserRepository
            user_repo = UserRepository(self._repo._session)
            role_user_ids = await user_repo.get_user_ids_by_roles(payload.target_roles)
            target_ids.update(role_user_ids)

        if not target_ids:
            return []

        notifications = [
            Notification(
                user_id=uid,
                title=payload.title,
                body=payload.body,
                notification_type=payload.notification_type,
                is_broadcast=True,
                action_url=payload.action_url,
            )
            for uid in target_ids
        ]
        created = await self._repo.create_many(notifications)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.NOTIFICATION_SENT,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "notification_ids": [str(n.id) for n in created],
                    "count": len(created),
                    "target_roles": payload.target_roles,
                },
            )
        return created

    async def list_paginated(
        self,
        page: PageParams,
        sort: SortParams,
        user_id: uuid.UUID | None = None,
        search_term: str | None = None,
        notification_type: str | None = None,
        is_read: bool | None = None,
    ) -> PaginatedResponse[NotificationResponse]:
        results, total = await self._repo.list_paginated(
            page=page,
            sort=sort,
            user_id=user_id,
            search_term=search_term,
            notification_type=notification_type,
            is_read=is_read,
        )
        return PaginatedResponse(
            data=[NotificationResponse.model_validate(n) for n in results],
            meta=build_pagination_meta(total=total, params=page),
        )

    async def mark_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification:
        notification = await self._repo.mark_read(notification_id, user_id)
        if notification is None:
            raise NotFoundError("Notification not found.")
        return notification

    async def mark_all_read(self, user_id: uuid.UUID) -> None:
        await self._repo.mark_all_read(user_id)

    async def count_unread(self, user_id: uuid.UUID) -> int:
        return await self._repo.count_unread(user_id)

    async def delete_notification(
        self, notification_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> None:
        if user_id is not None:
            notification = await self._repo.get(notification_id)
            if notification is None or notification.user_id != user_id:
                raise NotFoundError("Notification not found.")
        result = await self._repo.soft_delete(notification_id)
        if result is None:
            raise NotFoundError("Notification not found.")

    async def bulk_delete(
        self, ids: list[uuid.UUID],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> int:
        return await self._repo.bulk_soft_delete(ids)

    async def send_notification(
        self, payload: NotificationSend,
        user_email: str | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> Notification | list[Notification]:
        """Send a notification to a specific user or to all users with target_roles."""
        # Role-targeted fan-out
        if payload.target_roles:
            from pawguard.modules.auth.repository import UserRepository
            user_repo = UserRepository(self._repo._session)
            role_user_ids = await user_repo.get_user_ids_by_roles(payload.target_roles)
            if not role_user_ids:
                return []
            notifications = [
                Notification(
                    user_id=uid,
                    title=payload.title,
                    body=payload.body,
                    notification_type=payload.notification_type,
                    action_url=payload.action_url,
                )
                for uid in role_user_ids
            ]
            created = await self._repo.create_many(notifications)
            await self._repo._session.flush()
            if self._audit and actor_id:
                await self._audit.record(
                    event_type=AuthAuditEventType.NOTIFICATION_SENT,
                    actor_id=actor_id,
                    ip_address=ip_address or "",
                    user_agent="",
                    metadata={
                        "notification_ids": [str(n.id) for n in created],
                        "count": len(created),
                        "target_roles": payload.target_roles,
                    },
                )
            return created

        # Single-user notification (legacy path)
        if payload.user_id is None:
            raise ValidationFailedError("Either user_id or target_roles must be provided.")
        notification = Notification(
            user_id=payload.user_id,
            title=payload.title,
            body=payload.body,
            notification_type=payload.notification_type,
            action_url=payload.action_url,
        )
        created = await self._repo.create(notification)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.NOTIFICATION_SENT,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"notification_id": str(created.id)},
            )

        if payload.send_email and self._arq and user_email:
            await self._arq.enqueue_job(
                "send_notification_email_job",
                to=user_email,
                subject=payload.title,
                body=payload.body,
            )

        return created

    async def broadcast_to_all_users(
        self,
        payload: BroadcastCreate,
        user_ids: list[uuid.UUID],
        *,
        send_email: bool = False,
        user_emails: dict[uuid.UUID, str] | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> list[Notification]:
        notifications = [
            Notification(
                user_id=uid,
                title=payload.title,
                body=payload.body,
                notification_type=payload.notification_type,
                is_broadcast=True,
                action_url=payload.action_url,
            )
            for uid in user_ids
        ]
        created = await self._repo.create_many(notifications)
        await self._repo._session.flush()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.NOTIFICATION_SENT,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={"notification_ids": [str(n.id) for n in created], "count": len(created)},
            )

        if send_email and self._arq and user_emails:
            for _uid, email in user_emails.items():
                await self._arq.enqueue_job(
                    "send_notification_email_job",
                    to=email,
                    subject=payload.title,
                    body=payload.body,
                )

        return created


class NotificationPreferenceService:
    def __init__(self, repository: NotificationPreferenceRepository) -> None:
        self._repo = repository

    async def get_preferences(
        self, user_id: uuid.UUID
    ) -> NotificationPreference:
        prefs = await self._repo.get_by_user(user_id)
        if prefs is None:
            prefs = await self._repo.upsert(user_id=user_id)
        return prefs

    async def update_preferences(
        self, user_id: uuid.UUID, **kwargs: bool | str | None
    ) -> NotificationPreference:
        return await self._repo.upsert(user_id=user_id, **kwargs)
