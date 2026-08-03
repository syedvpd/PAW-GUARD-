"""Scheduled background jobs for proactive alerts and reminders.

These run periodically via ARQ's scheduled_jobs feature and are kept off
the request path per TRANSACTION RULES.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.payments import PaymentGatewayError, get_payment_gateway
from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.auth import permission_codes as pc
from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.donation.models import (
    Donation,
    DonationStatus,
    DonationType,
)
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.grievance.models import ServiceFeedback
from pawguard.modules.inventory.models import InventoryItem
from pawguard.modules.medical.models import VaccinationRecord
from pawguard.modules.notifications.models import Notification
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.schemas import NotificationCreate
from pawguard.modules.notifications.service import NotificationService


async def _staff_user_ids(
    session: AsyncSession, *permission_codes: str
) -> list[uuid.UUID]:
    """Ids of active, non-deleted users holding any of the given permissions.

    Notifications require a concrete recipient (Notification.user_id is NOT
    NULL), so staff-facing system alerts target the users who can act on
    them instead of a nonexistent "system" recipient.
    """
    stmt = (
        select(User.id)
        .join(User.roles)
        .join(Role.permissions)
        .where(
            Permission.code.in_(permission_codes),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .distinct()
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def check_inventory_low_stock(ctx: dict[str, object]) -> None:
    """Alert staff when inventory items fall below reorder threshold."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(InventoryItem).where(
                and_(
                    InventoryItem.deleted_at.is_(None),
                    InventoryItem.quantity <= InventoryItem.reorder_threshold,
                )
            )
        )
        low_stock_items = result.scalars().all()

        if not low_stock_items:
            return

        staff_user_ids = await _staff_user_ids(session, pc.INVENTORY_READ)
        if not staff_user_ids:
            return

        notification_svc = NotificationService(repository=NotificationRepository(session))
        for item in low_stock_items:
            for user_id in staff_user_ids:
                await notification_svc.create_notification(
                    payload=NotificationCreate(
                        user_id=user_id,
                        title="Inventory Low Stock Alert",
                        body=(
                            f"{item.name} is low on stock: "
                            f"{item.quantity} {item.unit} remaining "
                            f"(threshold: {item.reorder_threshold})."
                        ),
                        notification_type="inventory_alert",
                    )
                )
        await session.commit()


async def check_inventory_expiry(ctx: dict[str, object]) -> None:
    """Alert staff when inventory items expire within 60 days (PRR 3.12)."""
    cutoff = date.today() + timedelta(days=60)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(InventoryItem).where(
                and_(
                    InventoryItem.deleted_at.is_(None),
                    InventoryItem.expiry_date.isnot(None),
                    InventoryItem.expiry_date <= cutoff,
                )
            )
        )
        expiring_items = result.scalars().all()

        if not expiring_items:
            return

        staff_user_ids = await _staff_user_ids(session, pc.INVENTORY_READ)
        if not staff_user_ids:
            return

        notification_svc = NotificationService(repository=NotificationRepository(session))
        for item in expiring_items:
            days_left = (item.expiry_date - date.today()).days
            for user_id in staff_user_ids:
                await notification_svc.create_notification(
                    payload=NotificationCreate(
                        user_id=user_id,
                        title="Inventory Expiry Warning",
                        body=(
                            f"{item.name} expires in {days_left} day(s) "
                            f"(on {item.expiry_date})."
                        ),
                        notification_type="expiry_alert",
                    )
                )
        await session.commit()


async def check_vaccination_renewals(ctx: dict[str, object]) -> None:
    """Remind staff when vaccinations expire within 14 days."""
    cutoff = datetime.now(UTC) + timedelta(days=14)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VaccinationRecord).where(
                and_(
                    VaccinationRecord.deleted_at.is_(None),
                    VaccinationRecord.next_due_at.isnot(None),
                    VaccinationRecord.next_due_at <= cutoff,
                )
            )
        )
        due_vaccinations = result.scalars().all()

        if not due_vaccinations:
            return

        staff_user_ids = await _staff_user_ids(session, pc.MEDICAL_READ)
        if not staff_user_ids:
            return

        notification_svc = NotificationService(repository=NotificationRepository(session))
        for vax in due_vaccinations:
            for user_id in staff_user_ids:
                await notification_svc.create_notification(
                    payload=NotificationCreate(
                        user_id=user_id,
                        title="Vaccination Renewal Reminder",
                        body=(
                            f"Vaccination '{vax.vaccine_name}' for dog "
                            f"{vax.dog_id} is due on {vax.next_due_at.date()}."
                        ),
                        notification_type="medical_reminder",
                    )
                )
        await session.commit()


async def post_adoption_followups(ctx: dict[str, object]) -> None:
    """Send follow-up prompts at 30, 90, and 180 days post-adoption."""
    now = datetime.now(UTC)
    intervals = [30, 90, 180]

    async with AsyncSessionLocal() as session:
        notification_svc = NotificationService(repository=NotificationRepository(session))
        for days in intervals:
            target = now - timedelta(days=days)
            start = target.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)

            result = await session.execute(
                select(AdoptionApplication).where(
                    and_(
                        AdoptionApplication.deleted_at.is_(None),
                        AdoptionApplication.status == "completed",
                        AdoptionApplication.completed_at >= start,
                        AdoptionApplication.completed_at < end,
                    )
                )
            )
            adoptions = result.scalars().all()

            if not adoptions:
                continue

            for adoption in adoptions:
                await notification_svc.create_notification(
                    payload=NotificationCreate(
                        user_id=adoption.adopter_id,
                        title=f"{days}-Day Post-Adoption Follow-Up",
                        body=(
                            f"Your adoption of dog {adoption.dog_id} "
                            f"was completed {days} days ago. "
                            f"Please submit a photo or video update of your dog "
                            f"to complete your required follow-up report."
                        ),
                        notification_type="follow_up",
                        action_url=f"/api/v1/storage/upload?folder=documents&entity_type=adoption_application&entity_id={adoption.id}",
                    )
                )
        await session.commit()


async def send_post_service_feedback_surveys(ctx: dict[str, object]) -> None:
    """Auto-prompt adopters for post-adoption feedback (PRR 3.14).

    Adoptions completed 7-14 days ago that have neither submitted feedback nor
    already received a survey prompt get an in-app notification linking to the
    feedback form. Rescue-case feedback stays manual: rescue reporters have no
    user account to target (reporting is public/anonymous), so an in-app
    auto-prompt is impossible for them.
    """
    now = datetime.now(UTC)
    earliest = now - timedelta(days=14)
    latest = now - timedelta(days=7)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AdoptionApplication).where(
                and_(
                    AdoptionApplication.deleted_at.is_(None),
                    AdoptionApplication.status == AdoptionStatus.COMPLETED,
                    AdoptionApplication.completed_at.isnot(None),
                    AdoptionApplication.completed_at >= earliest,
                    AdoptionApplication.completed_at < latest,
                )
            )
        )
        adoptions = result.scalars().all()

        if not adoptions:
            return

        adoption_ids = [adoption.id for adoption in adoptions]

        submitted_result = await session.execute(
            select(ServiceFeedback.adoption_application_id).where(
                ServiceFeedback.adoption_application_id.in_(adoption_ids),
                ServiceFeedback.deleted_at.is_(None),
            )
        )
        submitted_ids = set(submitted_result.scalars().all())

        pending = [a for a in adoptions if a.id not in submitted_ids]
        if not pending:
            return

        prior_result = await session.execute(
            select(Notification.action_url).where(
                Notification.notification_type == "feedback_survey",
                Notification.deleted_at.is_(None),
            )
        )
        prior_urls = {url for url in prior_result.scalars().all() if url is not None}

        notification_svc = NotificationService(repository=NotificationRepository(session))
        for adoption in pending:
            action_url = f"/api/v1/grievance/feedback?adoption_application_id={adoption.id}"
            if action_url in prior_urls:
                continue
            await notification_svc.create_notification(
                payload=NotificationCreate(
                    user_id=adoption.adopter_id,
                    title="How was your adoption experience?",
                    body=(
                        f"It's been a couple of weeks since your adoption of dog "
                        f"{adoption.dog_id}. Please take a minute to rate your "
                        f"experience so we can keep improving our services."
                    ),
                    notification_type="feedback_survey",
                    action_url=action_url,
                )
            )
        await session.commit()


async def process_sponsorship_charges(ctx: dict[str, object]) -> None:
    """Process monthly sponsorships whose next_charge_date has arrived.

    Each charge is routed through the configured PaymentGateway - a PENDING
    donation linked back to the sponsorship is recorded and the donor completes
    checkout via the existing order/verify/webhook flow. When no gateway is
    configured (or an order cannot be created), a PENDING donation is recorded
    for manual collection. A charge is never recorded as SUCCESS without a real
    payment being captured.
    """
    from datetime import date as date_type

    today = date_type.today()

    try:
        gateway = get_payment_gateway()
    except PaymentGatewayError:
        gateway = None

    async with AsyncSessionLocal() as session:
        donation_repo = DonationRepository(session)
        notification_repo = NotificationRepository(session)
        notification_svc = NotificationService(repository=notification_repo)

        sponsorships = await donation_repo.get_due_sponsorships(today)
        if not sponsorships:
            return

        for sp in sponsorships:
            # Check if there is already an active PENDING donation for this sponsorship (PRD 3.11)
            if await donation_repo.has_pending_donation_for_sponsorship(sp.id):
                continue

            donation = Donation(
                donor_id=sp.donor_id,
                dog_id=sp.dog_id,
                amount=sp.monthly_amount,
                currency=sp.currency,
                donation_type=DonationType.SPONSORSHIP,
                status=DonationStatus.PENDING,
                sponsorship_id=sp.id,
                notes="Monthly sponsorship charge requires manual collection.",
            )

            if gateway is not None:
                try:
                    order = await gateway.create_order(
                        amount=sp.monthly_amount,
                        currency=sp.currency,
                        receipt=str(uuid.uuid4()),
                        notes={
                            "sponsorship_id": str(sp.id),
                            "donor_id": str(sp.donor_id),
                        },
                    )
                except PaymentGatewayError:
                    order = None

                if order is not None:
                    donation.payment_provider = order.provider
                    donation.gateway_order_id = order.order_id
                    donation.notes = (
                        "Monthly sponsorship charge initiated; awaiting payment."
                    )

            await donation_repo.create_donation(donation)

            if sp.donor and sp.donor.user_id:
                n_payload = NotificationCreate(
                    user_id=sp.donor.user_id,
                    title="Monthly Sponsorship Charge",
                    body=(
                        f"Your monthly sponsorship of {sp.monthly_amount} {sp.currency} "
                        f"for dog {sp.dog_id} is now due. We'll let you know once "
                        f"your payment has been received."
                    ),
                    notification_type="sponsorship_charge",
                )
                await notification_svc.create_notification(payload=n_payload)

        await session.commit()
