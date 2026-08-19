"""NotificationService: in-app notification business behaviour (RULE-003)."""

import uuid

from arq import ArqRedis

from pawguard.core.exceptions import NotFoundError, ValidationFailedError
from pawguard.core.logging import get_logger
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

logger = get_logger(__name__)


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
            from datetime import UTC, datetime

            from pawguard.modules.auth.repository import UserRepository
            user_repo = UserRepository(self._repo._session)
            role_user_ids = await user_repo.get_user_ids_by_roles(payload.target_roles)
            if not role_user_ids:
                return []
            now = datetime.now(UTC)
            notifications = [
                Notification(
                    user_id=uid,
                    title=payload.title,
                    body=payload.body,
                    notification_type=payload.notification_type,
                    action_url=payload.action_url,
                    sent_at=now,
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

            if payload.send_push and role_user_ids:
                await self._send_push_to_users(
                    role_user_ids, payload.title, payload.body, payload.action_url
                )

            return created

        # Single-user notification (legacy path)
        if payload.user_id is None:
            raise ValidationFailedError("Either user_id or target_roles must be provided.")
        
        from datetime import UTC, datetime
        notification = Notification(
            user_id=payload.user_id,
            title=payload.title,
            body=payload.body,
            notification_type=payload.notification_type,
            action_url=payload.action_url,
            sent_at=datetime.now(UTC),
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

        if payload.send_email and user_email:
            enqueued = False
            if self._arq:
                try:
                    await self._arq.enqueue_job(
                        "send_notification_email_job",
                        to=user_email,
                        subject=payload.title,
                        body=payload.body,
                    )
                    enqueued = True
                except Exception as exc:
                    logger.warning("arq_enqueue_failed_falling_back_to_outbox", error=str(exc))
            if not enqueued:
                from pawguard.modules.outbox.service import OutboxService
                await OutboxService.enqueue_job(
                    self._repo._session,
                    "send_notification_email_job",
                    to=user_email,
                    subject=payload.title,
                    body=payload.body,
                )

        if payload.send_push:
            await self._send_push_to_users(
                [payload.user_id], payload.title, payload.body, payload.action_url
            )

        return created

    async def _send_push_to_users(
        self,
        user_ids: list[uuid.UUID],
        title: str,
        body: str,
        action_url: str | None = None,
    ) -> int:
        """Send push notifications to users who have FCM tokens and push enabled.

        Respects both the user-level ``push_notifications_enabled`` flag and the
        per-user ``NotificationPreference`` (``enable_push``, quiet hours). When
        a preference row exists it takes precedence over the user-level flag.
        """
        from datetime import UTC, datetime

        from sqlalchemy import select

        from pawguard.modules.auth.models import User
        from pawguard.services.push_service import send_push_notification_to_users

        if not user_ids:
            return 0

        # Fetch user-level push flag + fcm_token
        stmt = select(User.id, User.fcm_token, User.push_notifications_enabled).where(
            User.id.in_(user_ids),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            User.fcm_token.isnot(None),
            User.fcm_token != "",
        )
        result = await self._repo._session.execute(stmt)
        rows = result.all()

        if not rows:
            return 0

        # Fetch per-user notification preferences (enable_push, quiet_hours)
        pref_stmt = select(
            NotificationPreference.user_id,
            NotificationPreference.enable_push,
            NotificationPreference.quiet_hours_start,
            NotificationPreference.quiet_hours_end,
        ).where(NotificationPreference.user_id.in_(user_ids))
        pref_result = await self._repo._session.execute(pref_stmt)
        prefs_by_user = {row[0]: row for row in pref_result.all()}

        # Check quiet hours: current time within the quiet window
        now = datetime.now(UTC)
        in_quiet_hours = False
        # Only check if we have any users with quiet hours set — single check
        # applies to all recipients since quiet hours are per-user but we send
        # in batch. For simplicity we check against the first user's quiet hours
        # (all recipients share the same push context in a single batch).
        # Individual quiet hours are best-effort at batch scale.

        tokens: list[tuple[uuid.UUID, str]] = []
        for uid, fcm_token, push_enabled in rows:
            pref = prefs_by_user.get(uid)
            if pref is not None:
                pref_enable_push, pref_qh_start, pref_qh_end = pref[1], pref[2], pref[3]
                # Preference-level push opt-out
                if not pref_enable_push:
                    continue
                # Quiet hours check
                if pref_qh_start and pref_qh_end:
                    try:
                        start_h, start_m = (int(x) for x in pref_qh_start.split(":"))
                        end_h, end_m = (int(x) for x in pref_qh_end.split(":"))
                        current_minutes = now.hour * 60 + now.minute
                        start_minutes = start_h * 60 + start_m
                        end_minutes = end_h * 60 + end_m
                        if start_minutes <= end_minutes:
                            in_quiet_hours = start_minutes <= current_minutes < end_minutes
                        else:
                            # Overnight quiet hours (e.g. 22:00 - 07:00)
                            in_quiet_hours = current_minutes >= start_minutes or current_minutes < end_minutes
                        if in_quiet_hours:
                            continue
                    except (ValueError, IndexError):
                        pass  # Malformed quiet hours — ignore and send
            else:
                # No preference row — fall back to user-level flag
                if not push_enabled:
                    continue

            tokens.append((uid, fcm_token))

        if not tokens:
            return 0

        data = {"action_url": action_url} if action_url else None
        return await send_push_notification_to_users(
            tokens, title=title, body=body, data=data
        )

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
