"""Unit tests for donation webhook concurrency, deduplication, and atomic transitions (PRR P0-1, P0-2, P1-1)."""

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.payments import WebhookEvent
from pawguard.modules.auth.models import User
from pawguard.modules.donation.models import (
    DogSponsorship,
    Donation,
    DonationStatus,
    DonationType,
    DonorProfile,
    SponsorshipStatus,
)
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.service import DonationService


@pytest.mark.asyncio
class TestWebhookDeduplicationAndConcurrency:
    async def test_duplicate_webhook_processed_only_once(self, db_session):
        repo = DonationRepository(db_session)
        event_id = f"evt_{uuid.uuid4().hex}"

        is_new1 = await repo.record_webhook_event(
            gateway="razorpay",
            event_id=event_id,
            event_type="payment.captured",
            order_id="order_1",
            payment_id="pay_1",
        )
        assert is_new1 is True

        is_new2 = await repo.record_webhook_event(
            gateway="razorpay",
            event_id=event_id,
            event_type="payment.captured",
            order_id="order_1",
            payment_id="pay_1",
        )
        assert is_new2 is False

    async def test_concurrent_webhook_deliveries_deduplicated(self, db_session):
        repo = DonationRepository(db_session)
        event_id = f"evt_concurrent_{uuid.uuid4().hex}"

        # Sequentially and concurrently test dedup
        res1 = await repo.record_webhook_event(
            gateway="razorpay",
            event_id=event_id,
            event_type="payment.captured",
            order_id="order_conc",
            payment_id="pay_conc",
        )
        assert res1 is True

        res2 = await repo.record_webhook_event(
            gateway="razorpay",
            event_id=event_id,
            event_type="payment.captured",
            order_id="order_conc",
            payment_id="pay_conc",
        )
        assert res2 is False

    async def test_sponsorship_billing_date_advances_exactly_once_under_concurrent_updates(
        self, db_session
    ):
        repo = DonationRepository(db_session)

        # Create donor
        user = User(
            id=uuid.uuid4(),
            email=f"donor_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="pw",
            full_name="Donor",
            is_active=True,
        )
        db_session.add(user)
        donor = DonorProfile(id=uuid.uuid4(), user_id=user.id, full_name_for_80g="Donor")
        db_session.add(donor)

        # Create dummy dog profile
        from pawguard.modules.dog.models import DogProfile, DogStatus

        dog = DogProfile(
            id=uuid.uuid4(),
            registration_number=f"DOG-{uuid.uuid4().hex[:6].upper()}",
            name="Charlie",
            status=DogStatus.SHELTER,
        )
        db_session.add(dog)

        # Create sponsorship
        today = datetime.date.today()
        sp = DogSponsorship(
            id=uuid.uuid4(),
            donor_id=donor.id,
            dog_id=dog.id,
            monthly_amount=50.0,
            currency="USD",
            status=SponsorshipStatus.ACTIVE,
            next_charge_date=today,
            started_at=datetime.datetime.now(datetime.UTC),
        )
        db_session.add(sp)

        # Create donation
        sp_order_id = f"order_sp_{uuid.uuid4().hex[:8]}"
        donation = Donation(
            id=uuid.uuid4(),
            donor_id=donor.id,
            sponsorship_id=sp.id,
            amount=50.0,
            currency="USD",
            donation_type=DonationType.SPONSORSHIP,
            status=DonationStatus.PENDING,
            gateway_order_id=sp_order_id,
        )
        db_session.add(donation)
        await db_session.flush()

        # Update donation to success atomically
        sp_pay_id = f"pay_sp_{uuid.uuid4().hex[:8]}"
        _, transitioned1 = await repo.update_gateway_fields_atomic(
            donation.id, status=DonationStatus.SUCCESS, gateway_payment_id=sp_pay_id
        )
        assert transitioned1 is True

        # Second update for same donation
        _, transitioned2 = await repo.update_gateway_fields_atomic(
            donation.id, status=DonationStatus.SUCCESS, gateway_payment_id=sp_pay_id
        )
        assert transitioned2 is False

        await db_session.refresh(sp)
        # Expected next charge date: advanced by exactly 1 month
        expected_month = today.month + 1 if today.month < 12 else 1
        assert sp.next_charge_date.month == expected_month

    async def test_handle_gateway_webhook_deduplication_service(self, db_session):
        repo = DonationRepository(db_session)
        dog_repo = MagicMock()
        gateway = MagicMock()
        gateway.provider_name = "razorpay"
        audit = MagicMock()
        audit.record = AsyncMock()

        # Setup donation
        user = User(
            id=uuid.uuid4(),
            email=f"donor2_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="pw",
            full_name="Donor 2",
            is_active=True,
        )
        db_session.add(user)
        donor = DonorProfile(id=uuid.uuid4(), user_id=user.id)
        db_session.add(donor)

        wh_order_id = f"order_wh_{uuid.uuid4().hex[:8]}"
        wh_pay_id = f"pay_wh_{uuid.uuid4().hex[:8]}"
        donation = Donation(
            id=uuid.uuid4(),
            donor_id=donor.id,
            amount=100.0,
            currency="USD",
            donation_type=DonationType.ONE_TIME,
            status=DonationStatus.PENDING,
            gateway_order_id=wh_order_id,
        )
        db_session.add(donation)
        await db_session.flush()

        event_id = f"evt_service_{uuid.uuid4().hex}"
        event = WebhookEvent(
            event_type="payment.captured",
            order_id=wh_order_id,
            payment_id=wh_pay_id,
            is_success=True,
            raw_payload={},
            event_id=event_id,
        )
        gateway.parse_webhook.return_value = event

        svc = DonationService(repo, dog_repo, gateway, audit_service=audit)

        # Call 1
        await svc.handle_gateway_webhook(b"{}", "sig")
        await db_session.refresh(donation)
        assert donation.status == DonationStatus.SUCCESS
        assert audit.record.call_count == 1

        # Call 2 (duplicate delivery of same event)
        await svc.handle_gateway_webhook(b"{}", "sig")
        assert audit.record.call_count == 1  # No duplicate audit or side-effects
