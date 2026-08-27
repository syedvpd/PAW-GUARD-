"""ARQ jobs for companion-pet vaccination and medication reminders."""

from datetime import UTC, datetime, timedelta
from typing import Any

from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.service import deliver_reminder_once
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService


async def notify_safety_tag_scan(
    ctx: dict[str, Any],
    user_id: str,
    title: str,
    body: str,
    action_url: str,
) -> int:
    """Deliver the push notification when a pet's safety tag is scanned.

    Runs as a background job so the latency-sensitive, publicly rate-limited
    scan endpoint never blocks on the (network-bound) FCM call.
    """
    import uuid

    from pawguard.db.session import AsyncSessionLocal
    from pawguard.modules.notifications.repository import NotificationRepository
    from pawguard.modules.notifications.service import NotificationService

    pool = ctx.get("redis")
    async with AsyncSessionLocal() as session:
        notification_service = NotificationService(NotificationRepository(session), arq_pool=pool)
        return await notification_service._send_push_to_users(
            [uuid.UUID(user_id)], title, body, action_url
        )


async def send_companion_pet_reminders(ctx: dict[str, Any]) -> int:
    """Deliver reminders due within the next 24 hours.

    Only reminders whose ``due_at`` falls between now and now + 1 day are
    delivered.  This ensures owners receive a notification **1 day before**
    a vaccination or medication is due, rather than being spammed with
    reminders weeks in advance.

    Each delivery has a unique reminder/user/scheduled-for key. Re-running an
    ARQ job after a timeout therefore creates no duplicate notification.
    """
    now = datetime.now(UTC)
    window_end = now + timedelta(days=1)
    delivered = 0
    async with AsyncSessionLocal() as session:
        repository = CompanionPetRepository(session)
        pool = ctx.get("redis")
        notification_service = NotificationService(NotificationRepository(session), arq_pool=pool)
        reminders = await repository.list_due_reminders(now, window_end)
        for reminder in reminders:
            if await deliver_reminder_once(repository, notification_service, reminder):
                delivered += 1
            await session.commit()
    return delivered
