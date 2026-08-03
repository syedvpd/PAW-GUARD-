"""Unit tests for ShelterService with mocked repositories."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.inventory.service import InventoryService
from pawguard.modules.shelter.models import (
    DailyCareLog,
    FacilityStatus,
    FacilityTransfer,
    Kennel,
    KennelSanitationState,
    ShelterFacility,
    ShelterSection,
    TransferStatus,
)
from pawguard.modules.shelter.repository import ShelterRepository
from pawguard.modules.shelter.schemas import (
    DailyCareLogCreate,
    FacilityTransferCreate,
    KennelCreate,
    ShelterFacilityCreate,
    ShelterSectionCreate,
)
from pawguard.modules.shelter.service import ShelterService
from pawguard.services.audit_service import AuditService


class TestShelterService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=ShelterRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_dog_repo(self):
        repo = AsyncMock(spec=DogRepository)
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_dog_repo, mock_audit):
        return ShelterService(mock_repo, mock_dog_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_create_facility(self, service, mock_repo):
        facility_id = uuid.uuid4()
        mock_repo.get_facility_by_name.return_value = None
        mock_repo.create_facility.return_value = ShelterFacility(
            id=facility_id, name="Main Shelter", address="123 Street",
            phone="+1234567890", total_capacity=100,
        )
        payload = ShelterFacilityCreate(
            name="Main Shelter", address="123 Street", phone="+1234567890",
            total_capacity=100,
        )
        result = await service.create_facility(payload, actor_id=uuid.uuid4())
        assert result.name == "Main Shelter"

    @pytest.mark.asyncio
    async def test_create_section(self, service, mock_repo):
        facility_id = uuid.uuid4()
        mock_repo.get_facility.return_value = ShelterFacility(
            id=facility_id, name="Main", address="Addr", phone="+1",
            total_capacity=100,
        )
        section_id = uuid.uuid4()
        mock_repo.create_section.return_value = ShelterSection(
            id=section_id, facility_id=facility_id, name="Quarantine", capacity=10,
        )
        payload = ShelterSectionCreate(name="Quarantine", capacity=10)
        result = await service.create_section(facility_id, payload, actor_id=uuid.uuid4())
        assert result.name == "Quarantine"

    @pytest.mark.asyncio
    async def test_create_section_facility_not_found(self, service, mock_repo):
        mock_repo.get_facility.return_value = None
        with pytest.raises(NotFoundError):
            await service.create_section(uuid.uuid4(), ShelterSectionCreate(name="X", capacity=5))

    @pytest.mark.asyncio
    async def test_create_kennel(self, service, mock_repo):
        section_id = uuid.uuid4()
        mock_repo.get_section.return_value = ShelterSection(
            id=section_id, facility_id=uuid.uuid4(), name="General", capacity=20,
        )
        mock_repo.list_kennels_by_section.return_value = []
        kennel_id = uuid.uuid4()
        mock_repo.create_kennel.return_value = Kennel(
            id=kennel_id, section_id=section_id, identifier="K-01", capacity=2,
            sanitation_state=KennelSanitationState.CLEAN,
        )
        payload = KennelCreate(identifier="K-01", capacity=2)
        result = await service.create_kennel(section_id, payload, actor_id=uuid.uuid4())
        assert result.identifier == "K-01"

    @pytest.mark.asyncio
    async def test_create_kennel_section_full(self, service, mock_repo):
        section_id = uuid.uuid4()
        mock_repo.get_section.return_value = ShelterSection(
            id=section_id, facility_id=uuid.uuid4(), name="Gen", capacity=1,
        )
        mock_repo.list_kennels_by_section.return_value = [Kennel(
            id=uuid.uuid4(), section_id=section_id, identifier="K-01",
            capacity=2, sanitation_state=KennelSanitationState.CLEAN,
        )]
        with pytest.raises(ConflictError, match="capacity limit"):
            await service.create_kennel(section_id, KennelCreate(identifier="K-02", capacity=1))

    @pytest.mark.asyncio
    async def test_assign_dog_to_kennel(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        kennel_id = uuid.uuid4()
        section_id = uuid.uuid4()
        facility_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Rex", breed="Mix",
            gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        mock_repo.get_kennel.return_value = Kennel(
            id=kennel_id, section_id=section_id, identifier="K-01", capacity=2,
            sanitation_state=KennelSanitationState.CLEAN,
        )
        mock_repo.get_section.return_value = ShelterSection(
            id=section_id, facility_id=facility_id, name="Gen", capacity=10,
        )
        mock_dog_repo.count_by_kennel.return_value = 0
        result = await service.assign_dog_to_kennel(dog_id, kennel_id, actor_id=uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_assign_dog_to_kennel_unclean(self, service, mock_repo, mock_dog_repo):
        kennel_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=uuid.uuid4(), registration_number="DOG-001", name="Rex",
            breed="Mix", gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        mock_repo.get_kennel.return_value = Kennel(
            id=kennel_id, section_id=uuid.uuid4(), identifier="K-01", capacity=2,
            sanitation_state=KennelSanitationState.NEEDS_CLEANING,
        )
        with pytest.raises(ConflictError, match="Cannot assign"):
            await service.assign_dog_to_kennel(uuid.uuid4(), kennel_id)

    @pytest.mark.asyncio
    async def test_assign_dog_to_kennel_at_capacity(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        kennel_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Rex", breed="Mix",
            gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        mock_repo.get_kennel.return_value = Kennel(
            id=kennel_id, section_id=uuid.uuid4(), identifier="K-01", capacity=1,
            sanitation_state=KennelSanitationState.CLEAN,
        )
        mock_dog_repo.count_by_kennel.return_value = 1
        with pytest.raises(ConflictError, match="at capacity"):
            await service.assign_dog_to_kennel(dog_id, kennel_id)

    @pytest.mark.asyncio
    async def test_update_kennel_sanitation(self, service, mock_repo):
        kennel_id = uuid.uuid4()
        kennel = Kennel(
            id=kennel_id, section_id=uuid.uuid4(), identifier="K-01", capacity=2,
            sanitation_state=KennelSanitationState.CLEAN,
        )
        mock_repo.get_kennel.return_value = kennel
        result = await service.update_kennel_sanitation(
            kennel_id, KennelSanitationState.NEEDS_CLEANING, actor_id=uuid.uuid4(),
        )
        assert result.sanitation_state == KennelSanitationState.NEEDS_CLEANING

    @pytest.mark.asyncio
    async def test_request_transfer(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        from_fac_id = uuid.uuid4()
        to_fac_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Rex", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_facility.side_effect = [
            ShelterFacility(id=from_fac_id, name="From", address="A", phone="+1", total_capacity=50),
            ShelterFacility(id=to_fac_id, name="To", address="B", phone="+2", total_capacity=50),
        ]
        transfer_id = uuid.uuid4()
        mock_repo.create_transfer.return_value = FacilityTransfer(
            id=transfer_id, dog_id=dog_id, from_facility_id=from_fac_id,
            to_facility_id=to_fac_id, transferred_by=uuid.uuid4(),
            status=TransferStatus.PENDING,
        )
        payload = FacilityTransferCreate(
            dog_id=dog_id, from_facility_id=from_fac_id, to_facility_id=to_fac_id,
        )
        result = await service.request_transfer(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert result.status == TransferStatus.PENDING

    @pytest.mark.asyncio
    async def test_confirm_transfer_requires_both_sides(self, service, mock_repo, mock_dog_repo):
        transfer_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        to_fac_id = uuid.uuid4()
        transfer = FacilityTransfer(
            id=transfer_id, dog_id=dog_id, from_facility_id=uuid.uuid4(),
            to_facility_id=to_fac_id, transferred_by=uuid.uuid4(),
            status=TransferStatus.PENDING,
        )
        mock_repo.get_transfer.return_value = transfer
        dog = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Rex", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_dog_repo.get_by_id.return_value = dog

        sender_id = uuid.uuid4()
        receiver_id = uuid.uuid4()

        # Sender confirms alone: not enough to complete the transfer.
        result = await service.confirm_transfer_sender(transfer_id, actor_id=sender_id)
        assert result.status == TransferStatus.PENDING
        assert result.sender_confirmed_at is not None
        assert dog.shelter_facility_id != to_fac_id

        # Receiver confirms: now both sides are in, transfer completes.
        result = await service.confirm_transfer_receiver(transfer_id, actor_id=receiver_id)
        assert result.status == TransferStatus.COMPLETED
        assert dog.shelter_facility_id == to_fac_id

    @pytest.mark.asyncio
    async def test_confirm_transfer_same_actor_both_sides_rejected(
        self, service, mock_repo, mock_dog_repo
    ):
        transfer_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        transfer = FacilityTransfer(
            id=transfer_id, dog_id=uuid.uuid4(), from_facility_id=uuid.uuid4(),
            to_facility_id=uuid.uuid4(), transferred_by=uuid.uuid4(),
            status=TransferStatus.PENDING,
        )
        mock_repo.get_transfer.return_value = transfer
        await service.confirm_transfer_sender(transfer_id, actor_id=actor_id)
        with pytest.raises(ConflictError, match="cannot confirm both"):
            await service.confirm_transfer_receiver(transfer_id, actor_id=actor_id)

    @pytest.mark.asyncio
    async def test_confirm_transfer_already_processed(self, service, mock_repo):
        transfer = FacilityTransfer(
            id=uuid.uuid4(), dog_id=uuid.uuid4(), from_facility_id=uuid.uuid4(),
            to_facility_id=uuid.uuid4(), transferred_by=uuid.uuid4(),
            status=TransferStatus.COMPLETED,
        )
        mock_repo.get_transfer.return_value = transfer
        with pytest.raises(ConflictError, match="already been processed"):
            await service.confirm_transfer_sender(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_submit_daily_care_log(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Rex", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        log_id = uuid.uuid4()
        mock_repo.create_care_log.return_value = DailyCareLog(
            id=log_id, dog_id=dog_id, logged_by=uuid.uuid4(),
            feed_time=datetime.now(), exercise_hours=1.5,
        )
        payload = DailyCareLogCreate(dog_id=dog_id, exercise_hours=1.5)
        result = await service.submit_daily_care_log(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert result.exercise_hours == 1.5

    @pytest.mark.asyncio
    async def test_submit_daily_care_log_with_inventory_consumption(
        self, mock_repo, mock_dog_repo, mock_audit
    ):
        from unittest.mock import AsyncMock as _AsyncMock

        mock_inventory = _AsyncMock(spec=InventoryService)
        service = ShelterService(
            mock_repo, mock_dog_repo, mock_audit, inventory_service=mock_inventory
        )
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Rex", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        log_id = uuid.uuid4()
        mock_repo.create_care_log.return_value = DailyCareLog(
            id=log_id, dog_id=dog_id, logged_by=uuid.uuid4(),
            feed_time=datetime.now(), exercise_hours=1.5,
        )
        item_id = uuid.uuid4()
        payload = DailyCareLogCreate(
            dog_id=dog_id, exercise_hours=1.5,
            inventory_consumptions=[{"item_id": item_id, "quantity": 1.0}],
        )
        user_id = uuid.uuid4()
        await service.submit_daily_care_log(user_id, payload, actor_id=uuid.uuid4())
        mock_inventory.record_movement.assert_awaited_once()
        _, kwargs = mock_inventory.record_movement.await_args
        assert kwargs["user_id"] == user_id
        assert kwargs["payload"].reference_type == "daily_care_log"
        assert kwargs["payload"].reference_id == log_id
        assert kwargs["payload"].item_id == item_id

    @pytest.mark.asyncio
    async def test_submit_daily_care_log_no_inventory_service(self, service, mock_repo, mock_dog_repo):
        dog_id = uuid.uuid4()
        mock_dog_repo.get_by_id.return_value = DogProfile(
            id=dog_id, registration_number="DOG-001", name="Rex", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.create_care_log.return_value = DailyCareLog(
            id=uuid.uuid4(), dog_id=dog_id, logged_by=uuid.uuid4(),
            feed_time=datetime.now(), exercise_hours=1.5,
        )
        payload = DailyCareLogCreate(
            dog_id=dog_id, exercise_hours=1.5,
            inventory_consumptions=[{"item_id": uuid.uuid4(), "quantity": 1.0}],
        )
        result = await service.submit_daily_care_log(uuid.uuid4(), payload, actor_id=uuid.uuid4())
        assert result.exercise_hours == 1.5

    @pytest.mark.asyncio
    async def test_list_facilities_paginated(self, service, mock_repo):
        fac = ShelterFacility(
            id=uuid.uuid4(), name="Main", address="Addr", phone="+1", total_capacity=100,
        )
        mock_repo.list_facilities_paginated.return_value = ([fac], 1)
        page = PageParams()
        sort = SortParams()
        result = await service.list_facilities_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_soft_delete_facility(self, service, mock_repo):
        facility_id = uuid.uuid4()
        mock_repo.soft_delete_facility.return_value = True
        await service.soft_delete_facility(facility_id)
        mock_repo.soft_delete_facility.assert_called_once_with(facility_id)

    @pytest.mark.asyncio
    async def test_soft_delete_facility_not_found(self, service, mock_repo):
        mock_repo.soft_delete_facility.return_value = False
        with pytest.raises(NotFoundError):
            await service.soft_delete_facility(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_facility_status(self, service, mock_repo):
        facility_id = uuid.uuid4()
        facility = ShelterFacility(
            id=facility_id, name="Main", address="Addr", phone="+1", total_capacity=100,
            status=FacilityStatus.ACTIVE,
        )
        mock_repo.get_facility.return_value = facility
        result = await service.update_facility_status(facility_id, FacilityStatus.INACTIVE)
        assert result.status == FacilityStatus.INACTIVE
