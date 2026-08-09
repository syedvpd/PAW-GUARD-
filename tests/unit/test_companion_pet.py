"""Focused unit coverage for companion-pet authorization and safety workflows."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, ForbiddenError
from pawguard.modules.companion_pet.models import (
    CompanionPet,
    PetAppointment,
    PetReminder,
    SafetyTag,
)
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.schemas import (
    CompanionPetUpdate,
    PetAppointmentCreate,
    SafetyTagScanResponse,
)
from pawguard.modules.companion_pet.service import CompanionPetService, deliver_reminder_once
from pawguard.modules.notifications.service import NotificationService


def _current_user(user_id: uuid.UUID, *roles: str) -> Any:
    return SimpleNamespace(
        id=user_id,
        user=SimpleNamespace(id=user_id),
        claims=SimpleNamespace(roles=list(roles)),
    )


def _pet(owner_id: uuid.UUID) -> CompanionPet:
    return CompanionPet(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name="Milo",
        species="dog",
        is_scan_enabled=True,
    )


@pytest.mark.asyncio
async def test_owner_can_manage_own_pet_but_unrelated_vet_cannot() -> None:
    owner_id = uuid.uuid4()
    pet = _pet(owner_id)
    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    repo.has_pet_clinic_access.return_value = False
    repo.create_pet.return_value = pet
    service = CompanionPetService(repo, AsyncMock())

    result = await service.get_pet(pet.id, _current_user(owner_id))
    assert result.id == pet.id

    with pytest.raises(ForbiddenError):
        await service.get_pet(pet.id, _current_user(uuid.uuid4(), "veterinarian"))


@pytest.mark.asyncio
async def test_admin_can_manage_any_pet() -> None:
    pet = _pet(uuid.uuid4())
    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    service = CompanionPetService(repo, AsyncMock())

    result = await service.update_pet(
        pet.id,
        CompanionPetUpdate(name="Updated"),
        _current_user(uuid.uuid4(), "super_admin"),
    )
    assert result.name == "Updated"


@pytest.mark.asyncio
async def test_qr_token_is_random_hashed_and_scan_has_no_owner_data() -> None:
    owner_id = uuid.uuid4()
    pet = _pet(owner_id)
    tag = SafetyTag(
        id=uuid.uuid4(),
        pet_id=pet.id,
        token_hash="unused",
        token_prefix="unused",
        is_active=True,
        scan_count=0,
    )
    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.side_effect = [pet, pet]
    repo.get_active_tag_for_pet.return_value = None
    repo.create_tag.side_effect = lambda created: created
    repo.get_tag_by_hash.return_value = tag
    session = AsyncMock()
    service = CompanionPetService(repo, session)

    provisioned, raw_token = await service.provision_safety_tag(pet.id, _current_user(owner_id))
    assert provisioned.pet_id == pet.id
    assert raw_token != provisioned.token_hash
    assert len(provisioned.token_hash) == 64
    assert repo.get_tag_by_hash.call_count == 0
    repo.get_tag_by_hash.return_value = provisioned

    _scanned_tag, scanned_pet = await service.scan_safety_tag(raw_token, "203.0.113.5")
    looked_up_hash = repo.get_tag_by_hash.call_args.args[0]
    assert looked_up_hash != raw_token
    assert len(looked_up_hash) == 64
    assert scanned_pet.owner_id == owner_id
    scan_response = SafetyTagScanResponse(
        pet_id=scanned_pet.id,
        name=scanned_pet.name,
        species=scanned_pet.species,
        breed=scanned_pet.breed,
        color=scanned_pet.color,
        emergency_notes=scanned_pet.emergency_notes,
    )
    assert "owner_id" not in scan_response.model_dump()


@pytest.mark.asyncio
async def test_appointment_conflict_is_rejected_before_insert() -> None:
    owner_id = uuid.uuid4()
    pet = _pet(owner_id)
    clinic_id = uuid.uuid4()
    starts_at = datetime.now(UTC) + timedelta(days=1)
    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    repo.get_clinic.return_value = SimpleNamespace(id=clinic_id)
    repo.find_appointment_conflict.return_value = PetAppointment(id=uuid.uuid4())
    service = CompanionPetService(repo, AsyncMock())

    payload = PetAppointmentCreate(
        pet_id=pet.id,
        clinic_id=clinic_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        reason="Annual check-up",
    )
    with pytest.raises(ConflictError):
        await service.create_appointment(payload, _current_user(owner_id))
    repo.create_appointment.assert_not_awaited()


@pytest.mark.asyncio
async def test_reminder_delivery_is_idempotent() -> None:
    reminder = PetReminder(
        id=uuid.uuid4(),
        pet_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        kind="vaccination",
        title="Rabies renewal",
        due_at=datetime.now(UTC),
        source_key="vaccine-1",
    )
    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_delivery.side_effect = [None, SimpleNamespace()]
    repo._session = AsyncMock()
    notification_service = AsyncMock(spec=NotificationService)

    assert await deliver_reminder_once(repo, notification_service, reminder) is True
    assert await deliver_reminder_once(repo, notification_service, reminder) is False
    repo.create_delivery.assert_awaited_once()
    notification_service.create_notification.assert_awaited_once()
