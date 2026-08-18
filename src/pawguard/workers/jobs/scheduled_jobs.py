"""Scheduled background jobs for proactive alerts and reminders.

These run periodically via ARQ's scheduled_jobs feature and are kept off
the request path per TRANSACTION RULES.
"""

import calendar
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from arq import Retry
from sqlalchemy import and_, select
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.logging import get_logger
from pawguard.core.payments import PaymentGatewayError, get_payment_gateway
from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.auth.repository import UserRepository
from pawguard.modules.donation.models import (
    Donation,
    DonationStatus,
    DonationType,
)
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.grievance.models import GrievanceStatus, GrievanceTicket, ServiceFeedback
from pawguard.modules.inventory.models import InventoryItem
from pawguard.modules.medical.models import VaccinationRecord
from pawguard.modules.notifications.models import Notification
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.schemas import NotificationCreate, NotificationSend
from pawguard.modules.notifications.service import NotificationService
from pawguard.workers.jobs.retry import retry_defer

logger = get_logger(__name__)


def _notification_service(
    session: AsyncSession, ctx: dict[str, object]
) -> NotificationService:
    """NotificationService wired to the worker's ARQ pool so `send_email=True`
    notifications actually enqueue email jobs. The ARQ worker puts its Redis
    pool on ctx['redis']; absent (e.g. in tests) it degrades to in-app only."""
    pool = ctx.get("redis")
    return NotificationService(repository=NotificationRepository(session), arq_pool=pool)


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
        # Push notifications for low stock
        for item in low_stock_items:
            await notification_svc._send_push_to_users(
                recipients,
                "Inventory Low Stock",
                f"{item.name} is low on stock: {item.quantity} {item.unit} remaining.",
                "/inventory",
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
        # Push notifications for expiring items
        for item in expiring_items:
            if item.expiry_date is None:
                continue
            days_left = (item.expiry_date - date.today()).days
            await notification_svc._send_push_to_users(
                recipients,
                "Inventory Expiring Soon",
                f"{item.name} expires in {days_left} day(s).",
                "/inventory",
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
        # Push notifications for vaccination renewals
        for vax in due_vaccinations:
            if vax.next_due_at is None:
                continue
            await notification_svc._send_push_to_users(
                recipients,
                "Vaccination Due",
                f"Vaccination '{vax.vaccine_name}' for dog {vax.dog_id} is due on {vax.next_due_at.date()}.",
                "/medical",
            )
        await session.commit()


async def post_adoption_followups(ctx: dict[str, object]) -> None:
    """Send follow-up prompts at 30, 90, and 180 days post-adoption."""
    now = datetime.now(UTC)
    intervals = [30, 90, 180]

    async with AsyncSessionLocal() as session:
        notification_svc = _notification_service(session, ctx)
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
                payload = NotificationSend(
                    user_id=adoption.adopter_id,
                    title=f"{days}-Day Post-Adoption Follow-Up",
                    body=(
                        f"Your adoption of dog {adoption.dog_id} "
                        f"was completed {days} days ago. "
                        f"How is everything going? We'd love to hear "
                        f"from you!"
                    ),
                    notification_type="follow_up",
                    send_email=True,
                    send_push=True,
                )
                await notification_svc.send_notification(
                    payload=payload,
                    user_email=adoption.adopter.email if adoption.adopter else None,
                )
        await session.commit()


async def process_sponsorship_charges(ctx: dict[str, object]) -> None:
    """Charge monthly sponsorships whose next_charge_date has arrived."""
    today = date.today()

    try:
        await _run_sponsorship_charges(today, ctx)
    except (OperationalError, InterfaceError) as exc:
        # Transient DB connectivity blips: nothing has committed (the whole
        # batch commits once at the end), so a scheduled retry is idempotent.
        raise Retry(defer=retry_defer(ctx)) from exc


def _next_month_clamped(current: date) -> date:
    """Return the same day next month, clamped to the shorter month's last day.

    A sponsorship charged on Jan 31 advances to Feb 28 (not Mar 3).
    """
    year = current.year
    month = current.month
    next_year = year if month < 12 else year + 1
    next_month = month % 12 + 1
    last_day = calendar.monthrange(next_year, next_month)[1]
    day = min(current.day, last_day)
    return date(next_year, next_month, day)


async def _run_sponsorship_charges(today: date, ctx: dict[str, object]) -> None:
    # 1. Fetch due sponsorships in a quick read-only query
    async with AsyncSessionLocal() as session:
        donation_repo = DonationRepository(session)
        sponsorships = await donation_repo.get_due_sponsorships(today)

    if not sponsorships:
        return

    # 2. Process each due sponsorship in an independent, short atomic transaction
    for sp in sponsorships:
        await _process_single_sponsorship(sp, ctx)


async def _process_single_sponsorship(sp: Any, ctx: dict[str, object]) -> None:
    async with AsyncSessionLocal() as session:
        donation_repo = DonationRepository(session)
        notification_svc = _notification_service(session, ctx)

        # Idempotency guard: Skip if there is already an active PENDING donation (PRD 3.11)
        if await donation_repo.has_pending_donation_for_sponsorship(sp.id):
            return

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

        try:
            gateway = get_payment_gateway()
        except PaymentGatewayError:
            gateway = None

        if gateway is not None:
            receipt_id = f"spons_{sp.id}_{sp.next_charge_date.strftime('%Y%m')}"
            try:
                order = await gateway.create_order(
                    amount=sp.monthly_amount,
                    currency=sp.currency,
                    receipt=receipt_id,
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
        next_date = _next_month_clamped(sp.next_charge_date)
        await donation_repo.advance_charge_date(sp.id, next_date)
        await session.commit()

        if sp.donor and sp.donor.user_id:
            n_payload = NotificationSend(
                user_id=sp.donor.user_id,
                title="Monthly Sponsorship Charge",
                body=(
                    f"Your monthly sponsorship of {sp.monthly_amount} {sp.currency} "
                    f"for dog {sp.dog_id} is now due. We'll let you know once "
                    f"your payment has been received."
                ),
                notification_type="sponsorship_charge",
                send_email=True,
                send_push=True,
            )
            try:
                await notification_svc.send_notification(
                    payload=n_payload,
                    user_email=sp.donor.user.email if sp.donor.user else None,
                )
                await session.commit()
            except Exception as exc:
                logger.warning("sponsorship_notification_failed", sponsorship_id=str(sp.id), error=str(exc))


async def check_grievance_sla_escalation(ctx: dict[str, object]) -> None:
    """Escalate unresolved grievances that have exceeded their SLA resolution time."""
    now = datetime.now(UTC)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GrievanceTicket).where(
                and_(
                    GrievanceTicket.deleted_at.is_(None),
                    GrievanceTicket.sla_due_at.isnot(None),
                    GrievanceTicket.sla_due_at < now,
                    GrievanceTicket.status.in_(
                        [
                            GrievanceStatus.OPEN,
                            GrievanceStatus.AWAITING_RESPONSE,
                            GrievanceStatus.INVESTIGATING,
                        ]
                    ),
                    GrievanceTicket.escalated_at.is_(None),
                )
            )
        )
        overdue = result.scalars().all()
        if not overdue:
            return

        notification_repo = NotificationRepository(session)
        notification_svc = NotificationService(repository=notification_repo)

        for ticket in overdue:
            ticket.escalation_level += 1
            ticket.escalated_at = now

            if ticket.assigned_to_admin_id:
                n_payload = NotificationCreate(
                    user_id=ticket.assigned_to_admin_id,
                    title="Grievance SLA Breach",
                    body=(
                        f"Grievance ticket {ticket.id} has exceeded its SLA "
                        f"resolution time and was escalated to level "
                        f"{ticket.escalation_level}."
                    ),
                    notification_type="grievance_escalation",
                    action_url=f"/api/v1/grievance/tickets/{ticket.id}",
                )
                await notification_svc.create_notification(payload=n_payload)
                # Push notification for SLA breach
                await notification_svc._send_push_to_users(
                    [ticket.assigned_to_admin_id],
                    "Grievance SLA Breach",
                    f"Ticket {ticket.id} has exceeded its SLA and was escalated.",
                    f"/api/v1/grievance/tickets/{ticket.id}",
                )

        await session.commit()


async def process_recurring_donation_charges(ctx: dict[str, object]) -> None:
    """Process recurring monthly donation subscriptions whose charge date has arrived."""
    today = date.today()

    try:
        await _run_recurring_charges(today, ctx)
    except (OperationalError, InterfaceError) as exc:
        # Transient DB connectivity blips: nothing has committed (the whole
        # batch commits once at the end), so a scheduled retry is idempotent.
        raise Retry(defer=retry_defer(ctx)) from exc


async def _run_recurring_charges(today: date, ctx: dict[str, object]) -> None:
    async with AsyncSessionLocal() as session:
        donation_repo = DonationRepository(session)
        notification_svc = _notification_service(session, ctx)

        subscriptions = await donation_repo.get_due_recurring_subscriptions(today)
        if not subscriptions:
            return

        try:
            gateway = get_payment_gateway()
        except PaymentGatewayError:
            gateway = None

        for sub in subscriptions:
            # Skip if a PENDING charge for this subscription is already in flight.
            if await donation_repo.has_pending_donation_for_subscription(sub.id):
                continue

            donation = Donation(
                donor_id=sub.donor_id,
                amount=sub.amount,
                currency=sub.currency,
                donation_type=DonationType.RECURRING,
                status=DonationStatus.PENDING,
                recurring_subscription_id=sub.id,
                notes="Monthly recurring donation charge requires manual collection.",
            )

            if gateway is not None:
                try:
                    order = await gateway.create_order(
                        amount=sub.amount,
                        currency=sub.currency,
                        receipt=str(uuid.uuid4()),
                        notes={
                            "subscription_id": str(sub.id),
                            "donor_id": str(sub.donor_id),
                        },
                    )
                except PaymentGatewayError:
                    order = None

                if order is not None:
                    donation.payment_provider = order.provider
                    donation.gateway_order_id = order.order_id
                    donation.notes = (
                        "Monthly recurring donation charge initiated; awaiting payment."
                    )

            await donation_repo.create_donation(donation)

            next_date = _next_month_clamped(sub.next_charge_date)
            await donation_repo.advance_recurring_charge_date(sub.id, next_date)

            if sub.donor and sub.donor.user_id:
                n_payload = NotificationSend(
                    user_id=sub.donor.user_id,
                    title="Monthly Recurring Donation",
                    body=(
                        f"Your recurring donation of {sub.amount} {sub.currency} "
                        f"is now due. We'll let you know once your payment "
                        f"has been received."
                    ),
                    notification_type="recurring_charge",
                    send_email=True,
                )
                await notification_svc.send_notification(
                    payload=n_payload,
                    user_email=sub.donor.user.email if sub.donor.user else None,
                )

        await session.commit()


async def send_post_service_feedback_surveys(ctx: dict[str, object]) -> None:
    """Send automated post-service feedback survey notifications to adopters.

    Completed adoptions 7-14 days old whose adopters have neither submitted
    feedback nor already received a survey prompt are notified once.
    """
    now = datetime.now(UTC)
    window_end = now - timedelta(days=7)
    window_start = window_end - timedelta(days=7)

    async with AsyncSessionLocal() as session:
        notification_svc = _notification_service(session, ctx)

        result = await session.execute(
            select(AdoptionApplication).where(
                and_(
                    AdoptionApplication.deleted_at.is_(None),
                    AdoptionApplication.status == AdoptionStatus.COMPLETED,
                    AdoptionApplication.completed_at >= window_start,
                    AdoptionApplication.completed_at < window_end,
                )
            )
        )
        adoptions = result.scalars().all()
        if not adoptions:
            return

        adoption_ids = [a.id for a in adoptions]

        feedback_ids = set(
            (
                await session.execute(
                    select(ServiceFeedback.adoption_application_id).where(
                        ServiceFeedback.adoption_application_id.in_(adoption_ids)
                    )
                )
            ).scalars().all()
        )

        prior_urls = list(
            (
                await session.execute(
                    select(Notification.action_url).where(
                        and_(
                            Notification.notification_type == "feedback_survey",
                            Notification.action_url.isnot(None),
                        )
                    )
                )
            ).scalars().all()
        )
        surveyed_ids = {
            prior_id
            for url in prior_urls
            if (prior_id := _extract_adoption_id_from_action_url(url)) is not None
        }

        for adoption in adoptions:
            if adoption.id in feedback_ids or adoption.id in surveyed_ids:
                continue
            payload = NotificationSend(
                user_id=adoption.adopter_id,
                title="We'd Love Your Feedback",
                body=(
                    f"Your adoption of dog {adoption.dog_id} has been completed. "
                    f"Please take a moment to rate your experience."
                ),
                notification_type="feedback_survey",
                action_url=(
                    f"/api/v1/grievance/feedback?"
                    f"adoption_application_id={adoption.id}"
                ),
                send_email=True,
            )
            await notification_svc.send_notification(
                payload=payload,
                user_email=adoption.adopter.email if adoption.adopter else None,
            )

        await session.commit()


def _extract_adoption_id_from_action_url(url: str) -> uuid.UUID | None:
    prefix = "adoption_application_id="
    if not url or prefix not in url:
        return None
    raw = url.split(prefix, 1)[1].split("&", 1)[0]
    try:
        return uuid.UUID(raw)
    except (ValueError, TypeError):
        return None
