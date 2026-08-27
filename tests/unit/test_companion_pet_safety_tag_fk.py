"""Unit test verifying companion pet safety tag provisioning sets dog_id=None for non-shelter pets."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.modules.companion_pet.models import CompanionPet, SafetyTag
from pawguard.modules.companion_pet.service import CompanionPetService


class TestCompanionPetSafetyTagFK:
    @pytest.mark.asyncio
    async def test_provision_safety_tag_for_personal_pet_sets_dog_id_none(self):
        """Verify provisioning a safety tag for a personal companion pet sets dog_id=None, preventing FK violation."""
        pet_id = uuid.uuid4()
        user_id = uuid.uuid4()

        pet = CompanionPet(
            id=pet_id,
            owner_id=user_id,
            name="Milo",
            species="dog",
            breed="Beagle",
            original_dog_id=None,  # Pure companion pet
        )

        mock_repo = MagicMock()
        mock_repo.get_pet = AsyncMock(return_value=pet)
        mock_repo.get_active_tag_for_pet = AsyncMock(return_value=None)

        created_tag_captures = []

        async def capture_create_tag(tag: SafetyTag):
            created_tag_captures.append(tag)
            tag.id = uuid.uuid4()
            return tag

        mock_repo.create_tag = AsyncMock(side_effect=capture_create_tag)

        mock_session = MagicMock()
        mock_session.flush = AsyncMock()

        current_user = SimpleNamespace(
            id=user_id,
            user=SimpleNamespace(id=user_id),
            claims=SimpleNamespace(roles=["general_public"]),
        )

        service = CompanionPetService(mock_repo, session=mock_session)
        tag, raw_token = await service.provision_safety_tag(pet_id, current_user)

        assert len(created_tag_captures) == 1
        created_tag = created_tag_captures[0]
        assert created_tag.pet_id == pet_id
        assert (
            created_tag.dog_id is None
        )  # CRITICAL FIX: dog_id must be None to prevent foreign_key_violation
        assert created_tag.is_active is True
        assert len(raw_token) > 0
