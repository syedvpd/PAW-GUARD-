"""ARQ jobs for companion-pet vaccination and medication reminders."""

from datetime import UTC, datetime, timedelta
from typing import Any

from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.service import deliver_reminder_once
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService


async def notify_safety_tag_scan(
    ctx: Any = None,
    user_id: str | None = None,
    title: str | None = None,
    body: str | None = None,
    action_url: str | None = None,
    **kwargs: Any,
) -> int:
    """Deliver the push notification when a pet's safety tag is scanned.

    Runs as a background job so the latency-sensitive, publicly rate-limited
    scan endpoint never blocks on the (network-bound) FCM call.
    """
    import uuid

    from pawguard.db.session import AsyncSessionLocal
    from pawguard.modules.notifications.repository import NotificationRepository
    from pawguard.modules.notifications.service import NotificationService

    # Handle both (ctx, user_id, title, body, action_url) and (user_id, title, body, action_url)
    if isinstance(ctx, (str, uuid.UUID)):
        action_url = body
        body = title
        title = user_id
        user_id = str(ctx)
        ctx = {}
    elif not isinstance(ctx, dict):
        ctx = {}

    target_user_id = user_id or kwargs.get("user_id") or kwargs.get("recipient_user_id")
    target_title = title or kwargs.get("title") or "Your pet's safety tag was scanned!"
    target_body = (
        body
        or kwargs.get("body")
        or kwargs.get("message")
        or "Someone scanned your pet's safety tag. Check the app for details."
    )
    target_action_url = action_url or kwargs.get("action_url") or "/companion-pets"

    if not target_user_id:
        return 0

    pool = ctx.get("redis") if isinstance(ctx, dict) else None
    async with AsyncSessionLocal() as session:
        notification_service = NotificationService(NotificationRepository(session), arq_pool=pool)
        return await notification_service._send_push_to_users(
            [uuid.UUID(str(target_user_id))], target_title, target_body, target_action_url
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
