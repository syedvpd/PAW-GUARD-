"""Unit tests for DonationService with mocked repository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.donation.models import Donation, DonationStatus, DonationType, DonorProfile
from pawguard.modules.donation.repository import DonationRepository
from pawguard.modules.donation.schemas import DonationCreate, DonorProfileCreate
from pawguard.modules.donation.service import DonationService


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
    def service(self, mock_repo, mock_dog_repo):
        return DonationService(mock_repo, mock_dog_repo)

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
        result = await service.make_donation(user_id, payload)
        assert result.amount == 100.0
        assert result.status == DonationStatus.SUCCESS

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
