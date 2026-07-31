"""Scheduled background jobs for proactive alerts and reminders.

These run periodically via ARQ's scheduled_jobs feature and are kept off
the request path per TRANSACTION RULES.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select

from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.adoption.models import AdoptionApplication
from pawguard.modules.donation.models import (
    Donation,
    DonationStatus,
    DonationType,
)
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.inventory.models import InventoryItem
from pawguard.modules.medical.models import VaccinationRecord
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.schemas import NotificationCreate
from pawguard.modules.notifications.service import NotificationService


async def check_inventory_low_stock(ctx: dict[str, object]) -> None:
    """Alert when inventory items fall below reorder threshold."""
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

        notification_svc = NotificationService(session)
        for item in low_stock_items:
            await notification_svc.create_notification(
                user_id=None,
                title="Inventory Low Stock Alert",
                message=(
                    f"{item.name} is low on stock: "
                    f"{item.quantity} {item.unit} remaining "
                    f"(threshold: {item.reorder_threshold})."
                ),
                notification_type="inventory_alert",
            )
        await session.commit()


async def check_inventory_expiry(ctx: dict[str, object]) -> None:
    """Alert when inventory items expire within 60 days (PRR 3.12)."""
    from datetime import date as date_type

    cutoff = date_type.today() + timedelta(days=60)

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

        notification_svc = NotificationService(session)
        for item in expiring_items:
            from datetime import date as date_type

            days_left = (item.expiry_date - date_type.today()).days
            await notification_svc.create_notification(
                user_id=None,
                title="Inventory Expiry Warning",
                message=(
                    f"{item.name} expires in {days_left} day(s) "
                    f"(on {item.expiry_date})."
                ),
                notification_type="expiry_alert",
            )
        await session.commit()


async def check_vaccination_renewals(ctx: dict[str, object]) -> None:
    """Remind when vaccinations expire within 14 days."""
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

        notification_svc = NotificationService(session)
        for vax in due_vaccinations:
            await notification_svc.create_notification(
                user_id=None,
                title="Vaccination Renewal Reminder",
                message=(
                    f"Vaccination '{vax.vaccine_name}' for dog "
                    f"{vax.dog_id} is due on {vax.next_due_at.date()}."
                ),
                notification_type="medical_reminder",
            )
        await session.commit()


async def post_adoption_followups(ctx: dict[str, object]) -> None:
    """Send follow-up prompts at 30, 90, and 180 days post-adoption."""
    now = datetime.now(UTC)
    intervals = [30, 90, 180]

    async with AsyncSessionLocal() as session:
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

            notification_svc = NotificationService(session)
            for adoption in adoptions:
                await notification_svc.create_notification(
                    user_id=adoption.adopter_id,
                    title=f"{days}-Day Post-Adoption Follow-Up",
                    message=(
                        f"Your adoption of dog {adoption.dog_id} "
                        f"was completed {days} days ago. "
                        f"How is everything going? We'd love to hear "
                        f"from you!"
                    ),
                    notification_type="follow_up",
                )
        await session.commit()


async def process_sponsorship_charges(ctx: dict[str, object]) -> None:
    """Charge monthly sponsorships whose next_charge_date has arrived."""
    from datetime import date as date_type

    today = date_type.today()

    async with AsyncSessionLocal() as session:
        donation_repo = DonationRepository(session)
        notification_repo = NotificationRepository(session)
        notification_svc = NotificationService(repository=notification_repo)

        sponsorships = await donation_repo.get_due_sponsorships(today)
        if not sponsorships:
            return

        for sp in sponsorships:
            tx_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
            donation = Donation(
                donor_id=sp.donor_id,
                dog_id=sp.dog_id,
                amount=sp.monthly_amount,
                currency=sp.currency,
                donation_type=DonationType.SPONSORSHIP,
                status=DonationStatus.SUCCESS,
                transaction_id=tx_id,
                sponsorship_id=sp.id,
            )
            await donation_repo.create_donation(donation)

            month = sp.next_charge_date.month + 1
            year = sp.next_charge_date.year
            if month > 12:
                month = 1
                year += 1
            next_date = sp.next_charge_date.replace(year=year, month=month)
            await donation_repo.advance_charge_date(sp.id, next_date)

            if sp.donor and sp.donor.user_id:
                n_payload = NotificationCreate(
                    user_id=sp.donor.user_id,
                    title="Monthly Sponsorship Charge",
                    body=(
                        f"Your monthly sponsorship of {sp.monthly_amount} {sp.currency} "
                        f"for dog {sp.dog_id} has been processed successfully."
                    ),
                    notification_type="sponsorship_charge",
                )
                await notification_svc.create_notification(payload=n_payload)

        await session.commit()
