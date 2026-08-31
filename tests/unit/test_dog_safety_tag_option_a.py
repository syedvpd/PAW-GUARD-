"""Unit tests verifying Option A Dog Master Safety Tag Architecture (TEST A through TEST J)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ConflictError
from pawguard.modules.auth.models import User
from pawguard.modules.companion_pet.models import CompanionPet, SafetyTag
from pawguard.modules.companion_pet.service import CompanionPetService
from pawguard.modules.dog.models import DogGender, DogProfile, DogStatus
from pawguard.modules.lost_found.models import LostReport, ReportStatus


class TestDogSafetyTagOptionA:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.get_active_lost_report_for_pet = AsyncMock(return_value=None)
        return repo

    @pytest.fixture
    def service(self, mock_repo, mock_session):
        return CompanionPetService(
            repository=mock_repo,
            session=mock_session,
            storage=None,
            audit=None,
        )

    @pytest.fixture
    def admin_user(self):
        user_id = uuid.uuid4()
        user_mock = MagicMock()
        user_mock.id = user_id
        current_user = MagicMock()
        current_user.id = user_id
        current_user.user = user_mock
        return current_user

    @pytest.mark.asyncio
    async def test_a_admitted_dog_safety_tag_provisioning(
        self, service, mock_repo, mock_session, admin_user
    ):
        """TEST A: ADMITTED dog without CompanionPet -> provision Safety Tag -> SUCCESS."""
        dog_id = uuid.uuid4()
        dog = DogProfile(
            id=dog_id,
            name="Barnaby",
            registration_number="DOG-2026-0001",
            status=DogStatus.RESCUED,
            gender=DogGender.MALE,
            breed="Indie Mix",
        )
        db_res = MagicMock()
        db_res.scalar_one_or_none.return_value = dog
        mock_session.execute.return_value = db_res

        mock_repo.get_active_tag_for_dog.return_value = None
        created_tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            pet_id=None,
            token_hash="hashed_token_a",
            token_prefix="rawtok_a",
            is_active=True,
        )
        mock_repo.create_tag.return_value = created_tag

        tag, raw_token = await service.provision_dog_safety_tag(dog_id, admin_user)

        assert tag.dog_id == dog_id
        assert tag.pet_id is None
        assert tag.is_active is True
        assert len(raw_token) > 10
        mock_repo.create_tag.assert_called_once()

    @pytest.mark.asyncio
    async def test_b_qr_scan_resolves_dog_master(self, service, mock_repo, mock_session):
        """TEST B: Same dog -> QR/raw token scan -> correct Dog Master returned."""
        dog_id = uuid.uuid4()
        tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            pet_id=None,
            token_hash="hash_b",
            token_prefix="rawtok_b",
            is_active=True,
            last_scanned_at=None,
            scan_count=0,
        )
        dog = DogProfile(
            id=dog_id,
            name="Barnaby",
            registration_number="DOG-2026-0001",
            status=DogStatus.SHELTER,
            gender=DogGender.MALE,
            breed="Indie Mix",
        )
        tag.dog = dog
        tag.pet = None

        mock_repo.get_tag_by_hash.return_value = tag

        scanned_tag, pet, lost_info = await service.scan_safety_tag("rawtok_b")

        assert scanned_tag.id == tag.id
        assert lost_info["dog_id"] == dog_id
        assert lost_info["name"] == "Barnaby"
        assert lost_info["status"] == "shelter"
        assert lost_info["is_lost"] is False

    @pytest.mark.asyncio
    async def test_c_dog_moves_to_foster_same_qr(self, service, mock_repo):
        """TEST C: Dog moves to Foster -> same QR -> same animal with Foster state."""
        dog_id = uuid.uuid4()
        dog = DogProfile(
            id=dog_id,
            name="Barnaby",
            status=DogStatus.FOSTERED,
            breed="Indie Mix",
        )
        tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            token_hash="hash_c",
            token_prefix="rawtok_c",
            is_active=True,
        )
        tag.dog = dog
        tag.pet = None
        mock_repo.get_tag_by_hash.return_value = tag

        _tag, _pet, lost_info = await service.scan_safety_tag("rawtok_c")

        assert lost_info["dog_id"] == dog_id
        assert lost_info["name"] == "Barnaby"
        assert lost_info["status"] == "fostered"

    @pytest.mark.asyncio
    async def test_d_dog_medical_treatment_same_qr(self, service, mock_repo):
        """TEST D: Dog receives veterinary/medical updates -> same QR -> current state."""
        dog_id = uuid.uuid4()
        dog = DogProfile(
            id=dog_id,
            name="Barnaby",
            status=DogStatus.CLINIC,
            breed="Indie Mix",
        )
        tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            token_hash="hash_d",
            token_prefix="rawtok_d",
            is_active=True,
        )
        tag.dog = dog
        tag.pet = None
        mock_repo.get_tag_by_hash.return_value = tag

        _tag, _pet, lost_info = await service.scan_safety_tag("rawtok_d")

        assert lost_info["dog_id"] == dog_id
        assert lost_info["status"] == "clinic"

    @pytest.mark.asyncio
    async def test_e_dog_adoption_links_companion_pet_same_qr(self, service, mock_repo):
        """TEST E: Dog is adopted -> CompanionPet created/linked -> same QR -> same animal/adoption state."""
        dog_id = uuid.uuid4()
        pet_id = uuid.uuid4()
        owner_id = uuid.uuid4()

        dog = DogProfile(id=dog_id, name="Barnaby", status=DogStatus.ADOPTED)
        owner = User(id=owner_id, full_name="Alice Adopter", phone="+919876543210")
        pet = CompanionPet(
            id=pet_id,
            owner_id=owner_id,
            name="Barnaby",
            original_dog_id=dog_id,
            is_scan_enabled=True,
        )
        pet.owner = owner

        tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            pet_id=pet_id,
            token_hash="hash_e",
            token_prefix="rawtok_e",
            is_active=True,
        )
        tag.dog = dog
        tag.pet = pet

        mock_repo.get_tag_by_hash.return_value = tag

        _tag, scanned_pet, lost_info = await service.scan_safety_tag("rawtok_e")

        assert scanned_pet.id == pet_id
        assert lost_info["dog_id"] == dog_id
        assert lost_info["owner_name"] == "Alice Adopter"
        assert lost_info["owner_phone"] == "+919876543210"
        assert lost_info["status"] == "adopted"

    @pytest.mark.asyncio
    async def test_f_owner_details_update_same_qr(self, service, mock_repo):
        """TEST F: Owner changes/updates -> same QR -> current owner/state."""
        dog_id = uuid.uuid4()
        pet_id = uuid.uuid4()
        new_owner_id = uuid.uuid4()

        dog = DogProfile(id=dog_id, name="Barnaby", status=DogStatus.ADOPTED)
        new_owner = User(id=new_owner_id, full_name="Bob NewOwner", phone="+919123456789")
        pet = CompanionPet(
            id=pet_id,
            owner_id=new_owner_id,
            name="Barnaby",
            original_dog_id=dog_id,
            is_scan_enabled=True,
        )
        pet.owner = new_owner

        tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            pet_id=pet_id,
            token_hash="hash_f",
            token_prefix="rawtok_f",
            is_active=True,
        )
        tag.dog = dog
        tag.pet = pet

        mock_repo.get_tag_by_hash.return_value = tag

        _tag, scanned_pet, lost_info = await service.scan_safety_tag("rawtok_f")

        assert scanned_pet.id == pet_id
        assert lost_info["owner_name"] == "Bob NewOwner"
        assert lost_info["owner_phone"] == "+919123456789"

    @pytest.mark.asyncio
    async def test_g_dog_reported_lost_same_qr(self, service, mock_repo):
        """TEST G: Dog becomes LOST -> same QR -> LOST state banner."""
        dog_id = uuid.uuid4()
        pet_id = uuid.uuid4()
        report_id = uuid.uuid4()

        dog = DogProfile(id=dog_id, name="Barnaby", status=DogStatus.ADOPTED)
        pet = CompanionPet(id=pet_id, name="Barnaby", original_dog_id=dog_id, is_scan_enabled=True)
        tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            pet_id=pet_id,
            token_hash="hash_g",
            token_prefix="rawtok_g",
            is_active=True,
        )
        tag.dog = dog
        tag.pet = pet

        mock_report = LostReport(
            id=report_id,
            pet_name="Barnaby",
            location_address="Central Park, NY",
            lost_at=datetime.now(UTC),
            status=ReportStatus.ACTIVE,
        )
        mock_repo.get_tag_by_hash.return_value = tag
        mock_repo.get_active_lost_report_for_pet.return_value = mock_report

        _tag, _pet, lost_info = await service.scan_safety_tag("rawtok_g")

        assert lost_info["is_lost"] is True
        assert lost_info["status"] == "lost"
        assert lost_info["lost_report_id"] == report_id
        assert lost_info["lost_location"] == "Central Park, NY"

    @pytest.mark.asyncio
    async def test_h_dog_reunited_same_qr(self, service, mock_repo):
        """TEST H: Dog becomes FOUND/REUNITED -> same QR -> updated safe state."""
        dog_id = uuid.uuid4()
        pet_id = uuid.uuid4()

        dog = DogProfile(id=dog_id, name="Barnaby", status=DogStatus.ADOPTED)
        pet = CompanionPet(id=pet_id, name="Barnaby", original_dog_id=dog_id, is_scan_enabled=True)
        tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            pet_id=pet_id,
            token_hash="hash_h",
            token_prefix="rawtok_h",
            is_active=True,
        )
        tag.dog = dog
        tag.pet = pet

        mock_repo.get_tag_by_hash.return_value = tag
        mock_repo.get_active_lost_report_for_pet.return_value = (
            None  # No active lost report after reunion
        )

        _tag, _pet, lost_info = await service.scan_safety_tag("rawtok_h")

        assert lost_info["is_lost"] is False
        assert lost_info["status"] == "adopted"

    @pytest.mark.asyncio
    async def test_i_existing_companion_pet_safety_tag_migration(self, service, mock_repo):
        """TEST I: Existing CompanionPet Safety Tag -> migration/backfill -> existing QR/token still works."""
        dog_id = uuid.uuid4()
        pet_id = uuid.uuid4()

        # Legacy tag originally created on pet_id, now backfilled with dog_id
        legacy_tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            pet_id=pet_id,
            token_hash="legacy_hash_i",
            token_prefix="leg_tok",
            is_active=True,
        )
        dog = DogProfile(id=dog_id, name="Legacy Rover", status=DogStatus.ADOPTED)
        pet = CompanionPet(
            id=pet_id, name="Legacy Rover", original_dog_id=dog_id, is_scan_enabled=True
        )
        legacy_tag.dog = dog
        legacy_tag.pet = pet

        mock_repo.get_tag_by_hash.return_value = legacy_tag

        _tag, _pet, lost_info = await service.scan_safety_tag("leg_tok")

        assert lost_info["dog_id"] == dog_id
        assert lost_info["pet_id"] == pet_id
        assert lost_info["name"] == "Legacy Rover"

    @pytest.mark.asyncio
    async def test_j_explicit_tag_replacement(self, service, mock_repo, mock_session, admin_user):
        """TEST J: Explicit tag replacement -> new token -> old token invalidated according to policy -> new QR works."""
        dog_id = uuid.uuid4()
        dog = DogProfile(id=dog_id, name="Barnaby", status=DogStatus.SHELTER)

        old_tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            token_hash="old_hash_j",
            token_prefix="old_tok",
            is_active=True,
        )

        db_res = MagicMock()
        db_res.scalar_one_or_none.return_value = dog
        mock_session.execute.return_value = db_res

        mock_repo.get_active_tag_for_dog.return_value = old_tag

        # 1. Attempting provision without force_reissue raises ConflictError
        with pytest.raises(ConflictError):
            await service.provision_dog_safety_tag(dog_id, admin_user, force_reissue=False)

        # 2. Provisioning with force_reissue=True revokes old tag and creates new active tag
        new_tag = SafetyTag(
            id=uuid.uuid4(),
            dog_id=dog_id,
            token_hash="new_hash_j",
            token_prefix="new_tok",
            is_active=True,
        )
        mock_repo.create_tag.return_value = new_tag

        replaced_tag, new_raw_token = await service.provision_dog_safety_tag(
            dog_id, admin_user, force_reissue=True
        )

        assert old_tag.is_active is False  # Old tag revoked
        assert replaced_tag.id == new_tag.id
        assert len(new_raw_token) > 10
