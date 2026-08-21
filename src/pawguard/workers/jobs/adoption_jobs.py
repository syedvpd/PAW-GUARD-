"""Background jobs for adoption follow-up management."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.adoption.models import (
    AdoptionApplication,
    AdoptionFollowUp,
    AdoptionStatus,
    FollowUpStatus,
)
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.schemas import NotificationCreate
from pawguard.modules.notifications.service import NotificationService

FOLLOW_UP_INTERVALS = (30, 90, 180)


async def post_adoption_followups(ctx: dict[str, object]) -> None:
    """Create follow-up milestones for completed adoptions and notify
    adopters when follow-ups are due."""
    now = datetime.now(UTC)

    async with AsyncSessionLocal() as session:
        notification_repo = NotificationRepository(session)
        notification_svc = NotificationService(repository=notification_repo)

        completed = await session.execute(
            select(AdoptionApplication).where(
                AdoptionApplication.status == AdoptionStatus.COMPLETED,
                AdoptionApplication.deleted_at.is_(None),
                AdoptionApplication.completed_at.isnot(None),
            )
        )
        apps = completed.scalars().all()

        for app in apps:
            if app.completed_at is None:
                continue

            for days in FOLLOW_UP_INTERVALS:
                existing = await session.execute(
                    select(AdoptionFollowUp).where(
                        AdoptionFollowUp.adoption_application_id == app.id,
                        AdoptionFollowUp.due_day == days,
                    )
                )
                if existing.scalar_one_or_none() is None:
                    follow_up = AdoptionFollowUp(
                        adoption_application_id=app.id,
                        due_day=days,
                        due_at=app.completed_at + timedelta(days=days),
                        status=FollowUpStatus.PENDING,
                    )
                    session.add(follow_up)

            await session.flush()

            for days in FOLLOW_UP_INTERVALS:
                due_at = app.completed_at + timedelta(days=days)
                if due_at <= now:
                    await notification_svc.create_notification(
                        payload=NotificationCreate(
                            user_id=app.adopter_id,
                            title=f"{days}-Day Post-Adoption Follow-Up",
                            body=(
                                f"Your adoption of dog {app.dog_id} "
                                f"was completed {days} days ago. "
                                f"Please submit a photo or video update "
                                f"of your dog to complete your required "
                                f"follow-up report."
                            ),
                            notification_type="follow_up",
                            action_url=(f"/api/v1/adoptions/{app.id}/follow-ups"),
                        )
                    )

        await session.commit()
