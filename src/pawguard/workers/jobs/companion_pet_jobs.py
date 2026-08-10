"""ARQ jobs for companion-pet vaccination and medication reminders."""

from datetime import UTC, datetime, timedelta
from typing import Any

from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.service import deliver_reminder_once
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService


async def send_companion_pet_reminders(ctx: dict[str, Any]) -> int:
    """Deliver due reminders through the in-app notification service + email.

    Each delivery has a unique reminder/user/scheduled-for key. Re-running an
    ARQ job after a timeout therefore creates no duplicate notification.
    """
    until = datetime.now(UTC) + timedelta(days=14)
    delivered = 0
    async with AsyncSessionLocal() as session:
        repository = CompanionPetRepository(session)
        pool = ctx.get("redis")
        notification_service = NotificationService(
            NotificationRepository(session), arq_pool=pool
        )
        reminders = await repository.list_due_reminders(until)
        for reminder in reminders:
            if await deliver_reminder_once(repository, notification_service, reminder):
                delivered += 1
            await session.commit()
    return delivered
