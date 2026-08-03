"""Unit tests for DonationService with mocked repository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.auth.models import User
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.donation.models import (
    DogSponsorship,
    Donation,
    DonationStatus,
    DonationType,
    DonorProfile,
    SponsorshipStatus,
)
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.schemas import DonationCreate, DonorProfileCreate, SponsorshipCreate
from pawguard.modules.donation.service import DonationService
from pawguard.modules.notifications.service import NotificationService
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService


def _make_donation(**kw):
    now = datetime.now(UTC)
    vals = dict(
        amount=0, currency="USD", donation_type=DonationType.ONE_TIME,
        status=DonationStatus.PENDING, created_at=now, updated_at=now,
    )
    vals.update(kw)
    return Donation(**vals)


class TestDonationService:
    @pytest.fixture
    def mock_repo(self):
        return AsyncMock(spec=DonationRepository)

    @pytest.fixture
    def mock_dog_repo(self):
        return AsyncMock(spec=DogRepository)

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_audit):
        return DonationService(mock_repo, mock_dog_repo, audit_service=mock_audit)

    @pytest.mark.asyncio
    async def test_register_donor(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.get_donor_by_user_id.return_value = None
        donor_id = uuid.uuid4()
        mock_repo.create_donor_profile.return_value = DonorProfile(
            id=donor_id, user_id=user_id,
        )
        payload = DonorProfileCreate(tax_identifier="TAX-123")
        result = await service.register_donor(user_id, payload)
        assert result.user_id == user_id

    @pytest.mark.asyncio
    async def test_register_donor_records_audit(self, service, mock_repo, mock_audit):
        """Self-service donor registration is a public mutation - it must be
        audited with the acting user and IP (PRR §6.1)."""
        user_id = uuid.uuid4()
        mock_repo.get_donor_by_user_id.return_value = None
        donor_id = uuid.uuid4()
        mock_repo.create_donor_profile.return_value = DonorProfile(
            id=donor_id, user_id=user_id,
        )
        payload = DonorProfileCreate(tax_identifier="TAX-123")
        await service.register_donor(
            user_id, payload, actor_id=user_id, ip_address="203.0.113.9",
        )
        mock_audit.record.assert_awaited_once()
        kwargs = mock_audit.record.call_args.kwargs
        assert kwargs["event_type"].value == "donor_registered"
        assert kwargs["actor_id"] == user_id
        assert kwargs["ip_address"] == "203.0.113.9"

    @pytest.mark.asyncio
    async def test_register_donor_already_exists(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.get_donor_by_user_id.return_value = DonorProfile(id=uuid.uuid4(), user_id=user_id)
        with pytest.raises(ConflictError, match="already registered"):
            await service.register_donor(user_id, DonorProfileCreate())

    @pytest.mark.asyncio
    async def test_get_or_create_donor_existing(self, service, mock_repo):
        user_id = uuid.uuid4()
        donor = DonorProfile(id=uuid.uuid4(), user_id=user_id)
        mock_repo.get_donor_by_user_id.return_value = donor
        result = await service.get_or_create_donor(user_id)
        assert result == donor

    @pytest.mark.asyncio
    async def test_get_or_create_donor_new(self, service, mock_repo):
        user_id = uuid.uuid4()
        mock_repo.get_donor_by_user_id.return_value = None
        new_donor = DonorProfile(id=uuid.uuid4(), user_id=user_id)
        mock_repo.create_donor_profile.return_value = new_donor
        result = await service.get_or_create_donor(user_id)
        assert result.user_id == user_id

    @pytest.mark.asyncio
    async def test_make_donation(self, service, mock_repo, mock_dog_repo):
        user_id = uuid.uuid4()
        donor_id = uuid.uuid4()
        mock_repo.get_donor_by_user_id.return_value = DonorProfile(id=donor_id, user_id=user_id)
        donation_id = uuid.uuid4()
        mock_repo.create_donation.return_value = None
        mock_repo.get_donation_by_id.return_value = Donation(
            id=donation_id, donor_id=donor_id, amount=100.0, currency="USD",
            donation_type=DonationType.ONE_TIME, status=DonationStatus.SUCCESS,
            transaction_id="TXN-ABC123",
        )
        payload = DonationCreate(amount=100.0, currency="USD", donation_type=DonationType.ONE_TIME)
        result = await service.make_donation(user_id, payload, actor_id=uuid.uuid4())
        assert result.amount == 100.0
        assert result.status == DonationStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_initiate_online_donation_records_audit(
        self, mock_repo, mock_dog_repo, mock_audit
    ):
        """Creating a checkout order is a public mutation - it must be audited
        (the payment itself is audited separately as DONATION_RECEIVED)."""
        from pawguard.core.payments import PaymentOrder

        user_id = uuid.uuid4()
        donor_id = uuid.uuid4()
        mock_repo.get_donor_by_user_id.return_value = DonorProfile(
            id=donor_id, user_id=user_id,
        )
        donation_id = uuid.uuid4()
        # The real repo assigns the id on flush; the mock must do the same or
        # DonationOrderResponse(donation_id=donation.id) receives None.
        mock_repo.create_donation.side_effect = lambda d: setattr(d, "id", donation_id)
        mock_repo.update_gateway_fields.return_value = None

        mock_gateway = AsyncMock()
        mock_gateway.provider_name = "razorpay"
        mock_gateway.create_order.return_value = PaymentOrder(
            provider="razorpay",
            order_id="order_abc123",
            amount=100.0,
            currency="INR",
            checkout_key="key",
            receipt="receipt-1",
        )

        svc = DonationService(
            mock_repo, mock_dog_repo, payment_gateway=mock_gateway,
            audit_service=mock_audit,
        )
        payload = DonationCreate(
            amount=100.0, currency="INR", donation_type=DonationType.ONE_TIME,
        )
        await svc.initiate_online_donation(
            user_id, payload, actor_id=user_id, ip_address="203.0.113.9",
        )
        mock_audit.record.assert_awaited_once()
        kwargs = mock_audit.record.call_args.kwargs
        assert kwargs["event_type"].value == "donation_order_created"
        assert kwargs["actor_id"] == user_id
        assert kwargs["metadata"]["gateway_order_id"] == "order_abc123"

    @pytest.mark.asyncio
    async def test_make_donation_records_audit(self, service, mock_repo, mock_dog_repo, mock_audit):
        user_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        donor_id = uuid.uuid4()
        mock_repo.get_donor_by_user_id.return_value = DonorProfile(id=donor_id, user_id=user_id)
        donation_id = uuid.uuid4()
        mock_repo.get_donation_by_id.return_value = Donation(
            id=donation_id, donor_id=donor_id, amount=100.0, currency="USD",
            donation_type=DonationType.ONE_TIME, status=DonationStatus.SUCCESS,
            transaction_id="TXN-ABC123",
        )
        payload = DonationCreate(amount=100.0, currency="USD", donation_type=DonationType.ONE_TIME)
        await service.make_donation(user_id, payload, actor_id=actor_id)
        mock_audit.record.assert_awaited_once()
        assert mock_audit.record.call_args.kwargs["actor_id"] == actor_id

    @pytest.mark.asyncio
    async def test_update_donation_status_records_audit(self, service, mock_repo, mock_audit):
        donation_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        mock_repo.get_donation_by_id.return_value = _make_donation(
            id=donation_id, status=DonationStatus.PENDING,
        )
        mock_repo.update_donation_status.return_value = _make_donation(
            id=donation_id, status=DonationStatus.FAILED,
        )
        await service.update_donation_status(donation_id, DonationStatus.FAILED, actor_id=actor_id)
        mock_audit.record.assert_awaited_once()
        assert mock_audit.record.call_args.kwargs["metadata"]["new_status"] == "failed"

    @pytest.mark.asyncio
    async def test_soft_delete_donor_records_audit(self, service, mock_repo, mock_audit):
        donor_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        mock_repo.get_donor_by_id.return_value = DonorProfile(id=donor_id, user_id=uuid.uuid4())
        await service.soft_delete_donor(donor_id, actor_id=actor_id)
        mock_audit.record.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_make_donation_with_dog(self, service, mock_repo, mock_dog_repo):
        user_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="B", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        donor_id = uuid.uuid4()
        mock_repo.get_donor_by_user_id.return_value = DonorProfile(id=donor_id, user_id=user_id)
        donation_id = uuid.uuid4()
        mock_repo.get_donation_by_id.return_value = Donation(
            id=donation_id, donor_id=donor_id, dog_id=dog_id, amount=50.0,
            currency="USD", donation_type=DonationType.SPONSORSHIP,
            status=DonationStatus.SUCCESS, transaction_id="TXN-DEF456",
        )
        payload = DonationCreate(amount=50.0, currency="USD", dog_id=dog_id, donation_type=DonationType.SPONSORSHIP)
        result = await service.make_donation(user_id, payload)
        assert result.dog_id == dog_id

    @pytest.mark.asyncio
    async def test_make_donation_dog_not_found(self, service, mock_repo, mock_dog_repo):
        user_id = uuid.uuid4()
        mock_repo.get_donor_by_user_id.return_value = DonorProfile(id=uuid.uuid4(), user_id=user_id)
        mock_dog_repo.get_by_id.return_value = None
        payload = DonationCreate(amount=10.0, dog_id=uuid.uuid4())
        with pytest.raises(NotFoundError, match="Dog profile not found"):
            await service.make_donation(user_id, payload)

    @pytest.mark.asyncio
    async def test_list_donations_paginated(self, service, mock_repo):
        donation = _make_donation(
            id=uuid.uuid4(), donor_id=uuid.uuid4(), amount=25.0,
            donation_type=DonationType.ONE_TIME, status=DonationStatus.SUCCESS,
        )
        mock_repo.paginate_donations.return_value = ([donation], 1)
        page = PageParams(page=1, page_size=20)
        sort = SortParams()
        result = await service.list_donations_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_soft_delete_donor(self, service, mock_repo):
        donor_id = uuid.uuid4()
        mock_repo.get_donor_by_id.return_value = DonorProfile(id=donor_id, user_id=uuid.uuid4())
        mock_repo.soft_delete_donor.return_value = None
        await service.soft_delete_donor(donor_id)
        mock_repo.soft_delete_donor.assert_called_once_with(donor_id)

    @pytest.mark.asyncio
    async def test_soft_delete_donor_not_found(self, service, mock_repo):
        mock_repo.get_donor_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_donor(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_donation(self, service, mock_repo):
        donation_id = uuid.uuid4()
        mock_repo.get_donation_by_id.return_value = Donation(
            id=donation_id, donor_id=uuid.uuid4(), amount=100.0, currency="USD",
            donation_type=DonationType.ONE_TIME, status=DonationStatus.SUCCESS,
        )
        result = await service.get_donation(donation_id)
        assert result.id == donation_id

    @pytest.mark.asyncio
    async def test_get_donation_not_found(self, service, mock_repo):
        mock_repo.get_donation_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_donation(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_make_donation_generates_receipt(self, mock_repo, mock_dog_repo, mock_audit):
        user_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        donor_id = uuid.uuid4()
        user = User(id=user_id, full_name="John Doe", email="john@example.com")
        donor = DonorProfile(id=donor_id, user_id=user_id, user=user)
        mock_repo.get_donor_by_user_id.return_value = donor
        donation_id = uuid.uuid4()
        now = datetime.now(UTC)
        donation = Donation(
            id=donation_id, donor_id=donor_id, donor=donor, amount=100.0,
            currency="USD", donation_type=DonationType.ONE_TIME,
            status=DonationStatus.SUCCESS, transaction_id="TXN-ABC123",
            created_at=now,
        )
        mock_repo.create_donation.return_value = None
        mock_repo.get_donation_by_id.return_value = donation
        mock_repo._session = AsyncMock()

        mock_storage = AsyncMock(spec=StorageService)
        mock_storage.build_object_key.return_value = "documents/receipt_test.pdf"

        svc = DonationService(
            mock_repo, mock_dog_repo, audit_service=mock_audit,
            storage_service=mock_storage,
        )
        payload = DonationCreate(amount=100.0, currency="USD", donation_type=DonationType.ONE_TIME)
        result = await svc.make_donation(user_id, payload, actor_id=actor_id)
        assert result.receipt_file_key == "documents/receipt_test.pdf"
        mock_storage.put_object.assert_called_once()
        call_kwargs = mock_storage.put_object.call_args.kwargs
        assert call_kwargs["content_type"] == "application/pdf"
        assert len(call_kwargs["content"]) > 0


class TestSponsorshipService:
    @pytest.fixture
    def mock_repo(self):
        return AsyncMock(spec=DonationRepository)

    @pytest.fixture
    def mock_dog_repo(self):
        return AsyncMock(spec=DogRepository)

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def mock_notification_svc(self):
        return AsyncMock(spec=NotificationService)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_audit, mock_notification_svc):
        return DonationService(
            mock_repo, mock_dog_repo,
            audit_service=mock_audit,
            notification_service=mock_notification_svc,
        )

    @pytest.mark.asyncio
    async def test_create_sponsorship_success(
        self, service, mock_repo, mock_dog_repo, mock_audit
    ):
        user_id = uuid.uuid4()
        donor_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        mock_repo.get_donor_by_user_id.return_value = DonorProfile(
            id=donor_id, user_id=user_id,
        )
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Bella",
            breed="Mix", gender="female", status=DogStatus.SHELTER,
            is_adoptable=True,
        )

        sponsorship_id = uuid.uuid4()
        mock_repo.create_sponsorship.return_value = DogSponsorship(
            id=sponsorship_id, donor_id=donor_id, dog_id=dog_id,
            monthly_amount=25.0, currency="USD",
            status=SponsorshipStatus.ACTIVE,
        )

        payload = SponsorshipCreate(dog_id=dog_id, monthly_amount=25.0)
        result = await service.create_sponsorship(
            user_id, payload, actor_id=actor_id,
        )

        assert result.donor_id == donor_id
        assert result.dog_id == dog_id
        assert result.monthly_amount == 25.0
        mock_repo.create_sponsorship.assert_awaited_once()
        mock_audit.record.assert_awaited_once()
        assert mock_audit.record.call_args.kwargs["event_type"].value == "sponsorship_created"

    @pytest.mark.asyncio
    async def test_cancel_sponsorship(self, service, mock_repo, mock_audit):
        sponsorship_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        mock_repo.get_sponsorship_by_id.return_value = DogSponsorship(
            id=sponsorship_id, donor_id=uuid.uuid4(), dog_id=uuid.uuid4(),
            monthly_amount=25.0, currency="USD",
            status=SponsorshipStatus.ACTIVE,
        )
        mock_repo.cancel_sponsorship.return_value = DogSponsorship(
            id=sponsorship_id, donor_id=uuid.uuid4(), dog_id=uuid.uuid4(),
            monthly_amount=25.0, currency="USD",
            status=SponsorshipStatus.CANCELLED,
        )

        result = await service.cancel_sponsorship(
            sponsorship_id, actor_id=actor_id,
        )

        assert result.status == SponsorshipStatus.CANCELLED
        mock_repo.cancel_sponsorship.assert_awaited_once()
        mock_audit.record.assert_awaited_once()
        assert mock_audit.record.call_args.kwargs["event_type"].value == "sponsorship_cancelled"

    @pytest.mark.asyncio
    async def test_pause_sponsorship(self, service, mock_repo, mock_audit):
        sponsorship_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        mock_repo.get_sponsorship_by_id.return_value = DogSponsorship(
            id=sponsorship_id, donor_id=uuid.uuid4(), dog_id=uuid.uuid4(),
            monthly_amount=25.0, currency="USD",
            status=SponsorshipStatus.ACTIVE,
        )
        mock_repo.update_sponsorship_status.return_value = DogSponsorship(
            id=sponsorship_id, donor_id=uuid.uuid4(), dog_id=uuid.uuid4(),
            monthly_amount=25.0, currency="USD",
            status=SponsorshipStatus.PAUSED,
        )

        result = await service.pause_sponsorship(
            sponsorship_id, actor_id=actor_id,
        )

        assert result.status == SponsorshipStatus.PAUSED
        mock_repo.update_sponsorship_status.assert_awaited_once_with(
            sponsorship_id, SponsorshipStatus.PAUSED,
        )
        mock_audit.record.assert_awaited_once()
        assert mock_audit.record.call_args.kwargs["event_type"].value == "sponsorship_paused"
