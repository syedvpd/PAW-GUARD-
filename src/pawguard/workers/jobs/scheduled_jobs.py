"""Scheduled background jobs for proactive alerts and reminders.

These run periodically via ARQ's scheduled_jobs feature and are kept off
the request path per TRANSACTION RULES.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from arq import Retry
from sqlalchemy import and_, select
from sqlalchemy.exc import InterfaceError, OperationalError

from pawguard.core.payments import PaymentGatewayError, get_payment_gateway
from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.adoption.models import AdoptionApplication
from pawguard.modules.auth.repository import UserRepository
from pawguard.modules.donation.models import (
    Donation,
    DonationStatus,
    DonationType,
    RecurringStatus,
    RecurringSubscription,
)
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.grievance.models import ServiceFeedback
from pawguard.modules.inventory.models import InventoryItem
from pawguard.modules.medical.models import VaccinationRecord
from pawguard.modules.notifications.models import Notification
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.schemas import NotificationCreate
from pawguard.modules.notifications.service import NotificationService
from pawguard.workers.jobs.retry import retry_defer


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

        recipients = await UserRepository(session).list_staff_user_ids()
        if not recipients:
            return

        notification_svc = NotificationService(repository=NotificationRepository(session))
        for item in low_stock_items:
            for user_id in recipients:
                payload = NotificationCreate(
                    user_id=user_id,
                    title="Inventory Low Stock Alert",
                    body=(
                        f"{item.name} is low on stock: "
                        f"{item.quantity} {item.unit} remaining "
                        f"(threshold: {item.reorder_threshold})."
                    ),
                    notification_type="inventory_alert",
                )
                await notification_svc.create_notification(payload=payload)
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

        recipients = await UserRepository(session).list_staff_user_ids()
        if not recipients:
            return

        notification_svc = NotificationService(repository=NotificationRepository(session))
        for item in expiring_items:
            if item.expiry_date is None:
                continue
            days_left = (item.expiry_date - date.today()).days
            for user_id in recipients:
                payload = NotificationCreate(
                    user_id=user_id,
                    title="Inventory Expiry Warning",
                    body=(
                        f"{item.name} expires in {days_left} day(s) "
                        f"(on {item.expiry_date})."
                    ),
                    notification_type="expiry_alert",
                )
                await notification_svc.create_notification(payload=payload)
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

        recipients = await UserRepository(session).list_staff_user_ids()
        if not recipients:
            return

        notification_svc = NotificationService(repository=NotificationRepository(session))
        for vax in due_vaccinations:
            if vax.next_due_at is None:
                continue
            for user_id in recipients:
                payload = NotificationCreate(
                    user_id=user_id,
                    title="Vaccination Renewal Reminder",
                    body=(
                        f"Vaccination '{vax.vaccine_name}' for dog "
                        f"{vax.dog_id} is due on {vax.next_due_at.date()}."
                    ),
                    notification_type="medical_reminder",
                )
                await notification_svc.create_notification(payload=payload)
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

            for adoption in adoptions:
                payload = NotificationCreate(
                    user_id=adoption.adopter_id,
                    title=f"{days}-Day Post-Adoption Follow-Up",
                    body=(
                        f"Your adoption of dog {adoption.dog_id} "
                        f"was completed {days} days ago. "
                        f"How is everything going? We'd love to hear "
                        f"from you!"
                    ),
                    notification_type="follow_up",
                )
                await notification_svc.create_notification(payload=payload)
        await session.commit()


async def process_sponsorship_charges(ctx: dict[str, object]) -> None:
    """Charge monthly sponsorships whose next_charge_date has arrived."""
    today = date.today()

    try:
        await _run_sponsorship_charges(today)
    except (OperationalError, InterfaceError) as exc:
        # Transient DB connectivity blips: nothing has committed (the whole
        # batch commits once at the end), so a scheduled retry is idempotent.
        raise Retry(defer=retry_defer(ctx)) from exc


async def _run_sponsorship_charges(today: date) -> None:
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
