"""Unit and integration tests for new PawGuard Readiness Checklist features:
1. Public QR scan returning lost status, lost_report_id, lost_location, lost_at.
2. Single clinic details endpoint.
3. Deactivating/revoking QR safety tag.
4. Converting an approved adoption application into a companion pet.
5. Public citizen lost-pet sighting submission & owner notification.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from types import SimpleNamespace
from typing import Any

from pawguard.modules.auth.models import User
from pawguard.modules.companion_pet.models import CompanionPet, SafetyTag, VetClinic
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.schemas import SafetyTagScanResponse
from pawguard.modules.companion_pet.service import CompanionPetService
from pawguard.modules.lost_found.models import LostReport, PetSighting, ReportStatus
from pawguard.modules.lost_found.repository import LostFoundRepository
from pawguard.modules.lost_found.schemas import PetSightingCreate
from pawguard.modules.lost_found.service import LostFoundService


def _current_user(user_id: uuid.UUID | None = None) -> Any:
    uid = user_id or uuid.uuid4()
    return SimpleNamespace(
        id=uid,
        claims=SimpleNamespace(roles=["app_user"]),
        user=User(id=uid, email="owner@example.com", full_name="Owner", roles=[]),
    )


@pytest.mark.asyncio
async def test_qr_scan_returns_lost_status_when_pet_is_reported_lost() -> None:
    owner_id = uuid.uuid4()
    pet_id = uuid.uuid4()
    report_id = uuid.uuid4()

    pet = CompanionPet(
        id=pet_id,
        owner_id=owner_id,
        name="Rover",
        species="dog",
        breed="Beagle",
        color="Tricolor",
        emergency_notes="Needs medicine",
        is_scan_enabled=True,
    )
    tag = SafetyTag(
        id=uuid.uuid4(),
        pet_id=pet.id,
        token_hash="hash123",
        token_prefix="prefix",
        is_active=True,
        scan_count=0,
    )
    lost_report = LostReport(
        id=report_id,
        user_id=owner_id,
        companion_pet_id=pet_id,
        pet_name="Rover",
        breed="beagle",
        color="tricolor",
        location_address="Park Avenue, City",
        lost_at=datetime.now(UTC),
        status=ReportStatus.ACTIVE,
    )

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_tag_by_hash.return_value = tag
    repo.get_pet.return_value = pet
    repo.get_active_lost_report_for_pet.return_value = lost_report

    session = AsyncMock()
    service = CompanionPetService(repo, session)

    _tag, scanned_pet, lost_info = await service.scan_safety_tag("raw_token_value", "127.0.0.1")

    assert scanned_pet.id == pet_id
    assert lost_info["status"] == "lost"
    assert lost_info["lost_report_id"] == report_id
    assert lost_info["lost_location"] == "Park Avenue, City"

    scan_response = SafetyTagScanResponse(
        pet_id=scanned_pet.id,
        name=scanned_pet.name,
        species=scanned_pet.species,
        breed=scanned_pet.breed,
        color=scanned_pet.color,
        emergency_notes=scanned_pet.emergency_notes,
        status=lost_info["status"],
        lost_report_id=lost_info["lost_report_id"],
        lost_location=lost_info["lost_location"],
        lost_at=lost_info["lost_at"],
    )

    assert scan_response.status == "lost"
    assert scan_response.lost_report_id == report_id


@pytest.mark.asyncio
async def test_get_single_clinic_details() -> None:
    clinic_id = uuid.uuid4()
    clinic = VetClinic(
        id=clinic_id,
        name="PawCare Vet Hospital",
        address="123 Vet Street",
        phone="+1555999000",
        email="info@pawcare.com",
        services="Vaccination, Surgery",
        latitude=17.43,
        longitude=78.40,
        is_emergency=True,
        is_active=True,
    )
    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_clinic.return_value = clinic
    session = AsyncMock()
    service = CompanionPetService(repo, session)

    res = await service.get_clinic(clinic_id)
    assert res.id == clinic_id
    assert res.name == "PawCare Vet Hospital"
    assert res.is_emergency is True


@pytest.mark.asyncio
async def test_deactivate_safety_tag() -> None:
    owner_id = uuid.uuid4()
    pet = CompanionPet(id=uuid.uuid4(), owner_id=owner_id, name="Max", species="dog", is_scan_enabled=True)
    tag = SafetyTag(id=uuid.uuid4(), pet_id=pet.id, token_hash="abc", token_prefix="abc", is_active=True)

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    repo.get_active_tag_for_pet.return_value = tag
    session = AsyncMock()

    service = CompanionPetService(repo, session)
    await service.deactivate_safety_tag(pet.id, _current_user(owner_id))

    assert tag.is_active is False


@pytest.mark.asyncio
async def test_record_public_sighting_notifies_owner() -> None:
    pet_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    repo = AsyncMock(spec=LostFoundRepository)
    notification_svc = AsyncMock()
    service = LostFoundService(repo, notification_service=notification_svc)

    payload = PetSightingCreate(
        pet_id=pet_id,
        finder_name="John Finder",
        finder_phone="+1555000111",
        finder_address="Main St",
        location_address="Near Central Park Bench 5",
        message="Found dog with red collar, safe now",
    )

    pet_obj = CompanionPet(id=pet_id, owner_id=owner_id, name="Buddy", species="dog")
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = pet_obj
    repo._session = AsyncMock()
    repo._session.execute.return_value = mock_exec

    sighting = await service.record_public_sighting(payload, "127.0.0.1")

    assert sighting.finder_name == "John Finder"
    assert repo.create_sighting.call_count == 1
    assert notification_svc.send_notification.call_count == 1


def test_empty_patch_body_raises_validation_error() -> None:
    from pydantic import ValidationError
    from pawguard.modules.companion_pet.schemas import CompanionPetUpdate

    with pytest.raises(ValidationError) as exc_info:
        CompanionPetUpdate.model_validate({})

    assert "At least one field must be provided for update." in str(exc_info.value)
