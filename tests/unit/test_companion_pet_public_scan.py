import uuid
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import NotFoundError
from pawguard.modules.auth.models import User
from pawguard.modules.companion_pet.models import CompanionPet, SafetyTag
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.service import CompanionPetService, _hash_tag_token


@pytest.mark.asyncio
async def test_companion_pet_public_scan_resolves_real_owner():
    """Verify that public_scan_companion_pet resolves real owner_name and owner_phone from User."""
    owner_id = uuid.uuid4()
    pet_id = uuid.uuid4()
    tag_id = uuid.uuid4()

    real_owner = User(
        id=owner_id,
        full_name="Priya Sharma",
        phone="+91 98765 43210",
        email="priya.sharma@example.com",
    )
    pet = CompanionPet(
        id=pet_id,
        owner_id=owner_id,
        name="Bella",
        species="dog",
        breed="Golden Retriever",
        sex="female",
        color="Golden",
        emergency_notes="Allergic to penicillin. Friendly.",
        is_scan_enabled=True,
    )
    pet.owner = real_owner

    tag = SafetyTag(
        id=tag_id,
        pet_id=pet_id,
        token_hash=_hash_tag_token("raw_safety_token_bella"),
        token_prefix="raw_saf",
        is_active=True,
        scan_count=3,
    )
    tag.pet = pet

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_pet.return_value = pet
    repo.get_active_tag_for_pet.return_value = tag
    repo.get_active_lost_report_for_pet.return_value = None

    session = AsyncMock()
    service = CompanionPetService(repo, session)

    scanned_tag, scanned_pet, lost_info = await service.public_scan_companion_pet(pet_id)

    assert scanned_pet.id == pet_id
    assert scanned_pet.name == "Bella"
    assert lost_info["owner_name"] == "Priya Sharma"
    assert lost_info["owner_phone"] == "+91 98765 43210"
    assert lost_info["breed"] == "Golden Retriever"
    assert lost_info["color"] == "Golden"
    assert lost_info["gender"] == "female"
    assert lost_info["emergency_notes"] == "Allergic to penicillin. Friendly."
    assert lost_info["status"] == "safe"
    assert lost_info["is_lost"] is False
    assert lost_info["safety_tag_id"] == tag_id


@pytest.mark.asyncio
async def test_scan_safety_tag_with_pet_id_canonical_identifier():
    """Verify that POST /safety-tag/scan resolves when token is the canonical pet_id UUID."""
    owner_id = uuid.uuid4()
    pet_id = uuid.uuid4()
    tag_id = uuid.uuid4()

    real_owner = User(
        id=owner_id,
        full_name="Vikram Patel",
        phone="+91 91234 56780",
        email="vikram.patel@example.com",
    )
    pet = CompanionPet(
        id=pet_id,
        owner_id=owner_id,
        name="Max",
        species="dog",
        breed="German Shepherd",
        sex="male",
        color="Black & Tan",
        emergency_notes="Epileptic - needs medication daily",
        is_scan_enabled=True,
    )
    pet.owner = real_owner

    tag = SafetyTag(
        id=tag_id,
        pet_id=pet_id,
        token_hash=_hash_tag_token("raw_max_token_12345"),
        token_prefix="raw_max",
        is_active=True,
        scan_count=0,
    )
    tag.pet = pet

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_tag_by_hash.return_value = None  # Token is pet_id, not raw token
    repo.get_active_tag_for_pet.return_value = tag
    repo.get_pet.return_value = pet
    repo.get_active_lost_report_for_pet.return_value = None

    session = AsyncMock()
    service = CompanionPetService(repo, session)

    # Calling with pet_id string
    scanned_tag, scanned_pet, lost_info = await service.scan_safety_tag(str(pet_id))

    assert scanned_pet.id == pet_id
    assert scanned_pet.name == "Max"
    assert lost_info["owner_name"] == "Vikram Patel"
    assert lost_info["owner_phone"] == "+91 91234 56780"
    assert lost_info["breed"] == "German Shepherd"
    assert lost_info["color"] == "Black & Tan"
    assert lost_info["gender"] == "male"
    assert lost_info["emergency_notes"] == "Epileptic - needs medication daily"
    assert lost_info["status"] == "safe"
    assert lost_info["is_lost"] is False


@pytest.mark.asyncio
async def test_scan_three_pets_contract_verification():
    """Verify 3 distinct companion pets: Bella, Max, Charlie."""
    test_cases = [
        ("Bella", "Priya Sharma", "+91 98765 43210", "Golden Retriever", "Golden", "female"),
        ("Max", "Vikram Patel", "+91 91234 56780", "German Shepherd", "Black & Tan", "male"),
        ("Charlie", "Ananya Roy", "+91 99887 76655", "Labrador", "Chocolate", "male"),
    ]

    for name, owner_name, owner_phone, breed, color, sex in test_cases:
        owner_id = uuid.uuid4()
        pet_id = uuid.uuid4()
        tag_id = uuid.uuid4()

        owner = User(id=owner_id, full_name=owner_name, phone=owner_phone)
        pet = CompanionPet(
            id=pet_id,
            owner_id=owner_id,
            name=name,
            species="dog",
            breed=breed,
            sex=sex,
            color=color,
            emergency_notes=f"Contact {owner_name} immediately if found.",
            is_scan_enabled=True,
        )
        pet.owner = owner

        tag = SafetyTag(
            id=tag_id,
            pet_id=pet_id,
            token_hash=_hash_tag_token(f"raw_token_{name}"),
            token_prefix="raw_tok",
            is_active=True,
        )
        tag.pet = pet

        repo = AsyncMock(spec=CompanionPetRepository)
        repo.get_pet.return_value = pet
        repo.get_active_tag_for_pet.return_value = tag
        repo.get_active_lost_report_for_pet.return_value = None

        session = AsyncMock()
        service = CompanionPetService(repo, session)

        _tag, p, info = await service.public_scan_companion_pet(pet_id)

        assert p.name == name
        assert info["owner_name"] == owner_name
        assert info["owner_phone"] == owner_phone
        assert info["breed"] == breed
        assert info["color"] == color
        assert info["gender"] == sex
        assert info["emergency_notes"] == f"Contact {owner_name} immediately if found."


@pytest.mark.asyncio
async def test_invalid_qr_returns_not_found():
    """Verify that an invalid token or nonexistent pet_id raises NotFoundError."""
    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_tag_by_hash.return_value = None
    repo.get_tag_by_prefix.return_value = None
    repo.get_active_tag_for_pet.return_value = None
    repo.get_active_tag_for_dog.return_value = None
    repo.get_pet.return_value = None

    session = AsyncMock()
    service = CompanionPetService(repo, session)

    with pytest.raises(NotFoundError):
        await service.scan_safety_tag("completely_invalid_token_99999")

    with pytest.raises(NotFoundError):
        await service.public_scan_companion_pet(uuid.uuid4())


@pytest.mark.asyncio
async def test_scan_safety_tag_with_tag_id_and_audit_service():
    """Verify scanning by tag_id works and correctly invokes AuditService without TypeError."""
    owner_id = uuid.uuid4()
    pet_id = uuid.uuid4()
    tag_id = uuid.uuid4()

    owner = User(id=owner_id, full_name="Julie Owner", phone="+91 98765 43210")
    pet = CompanionPet(
        id=pet_id,
        owner_id=owner_id,
        name="Julie",
        species="dog",
        breed="Golden Retriever",
        is_scan_enabled=True,
    )
    pet.owner = owner

    tag = SafetyTag(
        id=tag_id,
        pet_id=pet_id,
        token_hash=_hash_tag_token("raw_token_julie"),
        token_prefix="raw_juli",
        is_active=True,
        scan_count=0,
    )
    tag.pet = pet

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_tag_by_hash.return_value = None
    repo.get_active_tag_for_pet.return_value = None
    repo.get_active_tag_for_dog.return_value = None
    repo.get_tag_by_id.return_value = tag
    repo.get_pet.return_value = pet
    repo.get_active_lost_report_for_pet.return_value = None

    session = AsyncMock()
    from pawguard.services.audit_service import AuditService

    audit_mock = AsyncMock(spec=AuditService)
    service = CompanionPetService(repo, session, audit=audit_mock)

    scanned_tag, scanned_pet, lost_info = await service.scan_safety_tag(
        str(tag_id), ip_address="127.0.0.1"
    )

    assert scanned_tag.id == tag_id
    assert scanned_pet.name == "Julie"
    assert lost_info["name"] == "Julie"
    assert scanned_tag.scan_count == 1
    # Verify audit.record was called with keyword arguments
    audit_mock.record.assert_called_once()
    kwargs = audit_mock.record.call_args.kwargs
    assert kwargs["event_type"].value == "safety_tag_scanned"
    assert kwargs["ip_address"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_scan_safety_tag_with_8_char_token_prefix():
    """Verify scanning with 8-character token_prefix (e.g. wrFwg2xw) resolves correctly."""
    owner_id = uuid.uuid4()
    pet_id = uuid.uuid4()
    tag_id = uuid.uuid4()

    owner = User(id=owner_id, full_name="Julie Owner", phone="+91 98765 43210")
    pet = CompanionPet(
        id=pet_id,
        owner_id=owner_id,
        name="Julie",
        species="dog",
        breed="Golden Retriever",
        is_scan_enabled=True,
    )
    pet.owner = owner

    tag = SafetyTag(
        id=tag_id,
        pet_id=pet_id,
        token_hash=_hash_tag_token("raw_secret_token_43_characters_long_value"),
        token_prefix="wrFwg2xw",
        is_active=True,
        scan_count=2,
    )
    tag.pet = pet

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_tag_by_hash.return_value = None  # Prefix does not match full token hash
    repo.get_tag_by_prefix.return_value = tag
    repo.get_pet.return_value = pet
    repo.get_active_lost_report_for_pet.return_value = None

    session = AsyncMock()
    service = CompanionPetService(repo, session)

    scanned_tag, scanned_pet, lost_info = await service.scan_safety_tag("wrFwg2xw")

    assert scanned_tag.id == tag_id
    assert scanned_tag.token_prefix == "wrFwg2xw"
    assert scanned_pet.name == "Julie"
    assert lost_info["name"] == "Julie"
    assert scanned_tag.scan_count == 3


@pytest.mark.asyncio
async def test_scan_safety_tag_with_public_web_scan_url():
    """Verify scanning full URL https://pawguard-public-web.vercel.app/scan?token=wrFwg2xw parses prefix."""
    owner_id = uuid.uuid4()
    pet_id = uuid.uuid4()
    tag_id = uuid.uuid4()

    owner = User(id=owner_id, full_name="Julie Owner", phone="+91 98765 43210")
    pet = CompanionPet(
        id=pet_id,
        owner_id=owner_id,
        name="Julie",
        species="dog",
        breed="Golden Retriever",
        is_scan_enabled=True,
    )
    pet.owner = owner

    tag = SafetyTag(
        id=tag_id,
        pet_id=pet_id,
        token_hash=_hash_tag_token("raw_secret_token_43_characters_long_value"),
        token_prefix="wrFwg2xw",
        is_active=True,
        scan_count=2,
    )
    tag.pet = pet

    repo = AsyncMock(spec=CompanionPetRepository)
    repo.get_tag_by_hash.return_value = None
    repo.get_tag_by_prefix.return_value = tag
    repo.get_pet.return_value = pet
    repo.get_active_lost_report_for_pet.return_value = None

    session = AsyncMock()
    service = CompanionPetService(repo, session)

    scanned_tag, scanned_pet, lost_info = await service.scan_safety_tag(
        "https://pawguard-public-web.vercel.app/scan?token=wrFwg2xw"
    )

    assert scanned_tag.id == tag_id
    assert scanned_tag.token_prefix == "wrFwg2xw"
    assert scanned_pet.name == "Julie"
    assert lost_info["name"] == "Julie"
    assert scanned_tag.scan_count == 3
