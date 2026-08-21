"""Background jobs for donation processing (audit 3.11).

These are invoked by the ARQ worker pool and must not be wired into
scheduled_jobs.py or arq_worker.py directly.
"""

import logging

from pawguard.core.payments import PaymentGatewayError, get_payment_gateway
from pawguard.db.session import AsyncSessionLocal
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.service import DonationService
from pawguard.modules.notifications.repository import NotificationRepository
from pawguard.modules.notifications.service import NotificationService

logger = logging.getLogger(__name__)


async def process_recurring_donation_charges(ctx: dict[str, object]) -> None:
    """Charge all due recurring subscriptions and create PENDING donations.

    Mirrors the process_sponsorship_charges pattern from scheduled_jobs.py.
    Each charge creates a PENDING Donation linked to the subscription;
    the existing order/verify/webhook flow confirms payment. On success
    the subscription's next_charge_date is advanced by one month.
    """
    try:
        gateway = get_payment_gateway()
    except PaymentGatewayError:
        gateway = None

    async with AsyncSessionLocal() as session:
        donation_repo = DonationRepository(session)
        notification_repo = NotificationRepository(session)
        notification_svc = NotificationService(repository=notification_repo)
        service = DonationService(donation_repo, payment_gateway=gateway)

        donations = await service.charge_due_recurring_subscriptions(session)

        for donation in donations:
            sub = donation.recurring_subscription
            if sub is None or sub.donor is None:
                continue
            user_id = sub.donor.user_id
            if user_id is None:
                continue
            try:
                from pawguard.modules.notifications.schemas import (
                    NotificationCreate,
                )

                await notification_svc.create_notification(
                    payload=NotificationCreate(
                        user_id=user_id,
                        title="Monthly Recurring Donation Charge",
                        body=(
                            f"Your recurring donation of {sub.amount} "
                            f"{sub.currency} is now due. We'll let you "
                            f"know once your payment has been received."
                        ),
                        notification_type="recurring_donation_charge",
                        action_url=f"/api/v1/donations/{donation.id}",
                    )
                )
            except Exception as notif_exc:
                logger.warning(
                    "Failed to send notification for recurring charge %s: %s",
                    sub.id,
                    notif_exc,
                    exc_info=True,
                )

        await session.commit()
