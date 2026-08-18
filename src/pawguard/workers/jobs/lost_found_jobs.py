"""Background delivery jobs for lost-pet community alerts."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.auth.models import User
from pawguard.modules.lost_found.models import ReportStatus
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.schemas import BroadcastCreate
from pawguard.modules.notifications.service import NotificationService


async def broadcast_lost_pet_alert(ctx: dict[str, Any], *, report_id: str, **_: Any) -> int:
    """Fan out one active lost report, exactly once, to active users.

    The row lock and ``broadcasted_at`` marker make ARQ retries and concurrent
    worker executions safe. Notifications are written in bounded batches.
    Also sends push notifications via FCM.
    """
    del ctx
    async with AsyncSessionLocal() as session:
        repository = LostFoundRepository(session)
        report = await repository.get_lost_report_for_broadcast(uuid.UUID(report_id))
        if report is None or report.status != ReportStatus.ACTIVE or report.broadcasted_at:
            return 0

        recipients = await session.execute(
            select(User.id).where(
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.id != report.user_id,
            )
        )
        user_ids = list(recipients.scalars().all())
        notification_service = NotificationService(
            repository=NotificationRepository(session)
        )
        payload = BroadcastCreate(
            title=f"Lost pet alert: {report.pet_name}",
            body=(
                f"{report.pet_name} was reported lost near {report.location_address}. "
                "Please check the alert and report a sighting if you can help."
            ),
            notification_type="lost_pet_alert",
            action_url=f"/api/v1/lost-found/lost/{report.id}",
        )
        sent = 0
        for offset in range(0, len(user_ids), 500):
            batch = user_ids[offset : offset + 500]
            await notification_service.broadcast(payload, batch)
            sent += len(batch)

        # Send push notifications to all recipients
        push_title = f"Lost pet alert: {report.pet_name}"
        push_body = (
            f"{report.pet_name} was reported lost near {report.location_address}. "
            "Please check the alert and report a sighting if you can help."
        )
        for offset in range(0, len(user_ids), 500):
            batch = user_ids[offset : offset + 500]
            await notification_service._send_push_to_users(
                batch, push_title, push_body,
                f"/api/v1/lost-found/lost/{report.id}",
            )

        report.broadcasted_at = datetime.now(UTC)
        await session.commit()
        return sent
