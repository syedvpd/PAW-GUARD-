"""Unit test verifying /api/v1/dogs/{dog_id}/public-scan returns active adopter name and phone number."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.service import DogService


class TestPublicScanAdopter:
    @pytest.mark.asyncio
    async def test_get_adopter_contact_returns_real_adopter_info_for_adopted_dog(self):
        """Verify get_adopter_contact retrieves active adopter full_name and phone."""
        dog_id = uuid.uuid4()
        mock_repo = MagicMock(spec=DogRepository)
        mock_repo.get_adopter_contact = AsyncMock(
            return_value=("Syed Mohammed Zubair Khadri", "+91 98765 43210")
        )

        service = DogService(mock_repo)
        name, phone = await service.get_adopter_contact(dog_id)

        assert name == "Syed Mohammed Zubair Khadri"
        assert phone == "+91 98765 43210"
        mock_repo.get_adopter_contact.assert_awaited_once_with(dog_id)

    @pytest.mark.asyncio
    async def test_get_adopter_contact_returns_none_for_unadopted_dog(self):
        """Verify get_adopter_contact returns None when dog has no active adoption."""
        dog_id = uuid.uuid4()
        mock_repo = MagicMock(spec=DogRepository)
        mock_repo.get_adopter_contact = AsyncMock(return_value=(None, None))

        service = DogService(mock_repo)
        name, phone = await service.get_adopter_contact(dog_id)

        assert name is None
        assert phone is None
