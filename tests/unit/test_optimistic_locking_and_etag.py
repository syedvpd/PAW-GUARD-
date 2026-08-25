"""Unit tests for Optimistic Version Locking (version_id) and ETag HTTP 304 Caching."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from pawguard.core.cache_utils import etag_cache_response
from pawguard.core.exceptions import ConflictError
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.adoption.schemas import AdoptionApplicationUpdate
from pawguard.modules.adoption.service import AdoptionService
from pawguard.modules.dog.models import DogProfile, DogStatus


class TestOptimisticLocking:
    """Test suite for version_id optimistic locking behavior."""

    @pytest.mark.asyncio
    async def test_adoption_application_version_id_field_exists(self):
        """Verify version_id attribute exists on models."""
        app = AdoptionApplication(
            id=uuid.uuid4(),
            dog_id=uuid.uuid4(),
            adopter_id=uuid.uuid4(),
            residential_status="owned",
            has_landlord_approval=True,
            has_yard_fence=True,
            household_members_count=2,
            status=AdoptionStatus.SUBMITTED,
            version_id=1,
        )
        assert app.version_id == 1

        dog = DogProfile(
            id=uuid.uuid4(),
            registration_number="DOG-2026-TEST",
            name="Barnaby",
            breed="Indie Mix",
            status=DogStatus.SHELTER,
            version_id=1,
        )
        assert dog.version_id == 1

    @pytest.mark.asyncio
    async def test_update_application_version_mismatch_raises_conflict(self):
        """Verify version_id mismatch triggers a ConflictError (HTTP 409)."""
        app_id = uuid.uuid4()
        existing_app = AdoptionApplication(
            id=app_id,
            dog_id=uuid.uuid4(),
            adopter_id=uuid.uuid4(),
            residential_status="owned",
            has_landlord_approval=True,
            has_yard_fence=True,
            household_members_count=2,
            status=AdoptionStatus.SUBMITTED,
            version_id=2,  # Current DB version is 2
        )

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing_app)
        mock_repo._session = MagicMock()
        mock_repo._session.flush = AsyncMock()

        mock_dog_repo = MagicMock()

        service = AdoptionService(mock_repo, mock_dog_repo)

        # Payload supplies stale expected version_id = 1
        stale_payload = AdoptionApplicationUpdate(
            vetting_officer_notes="Stale update attempt", version_id=1
        )

        with pytest.raises(ConflictError) as exc_info:
            await service.update_application(app_id, stale_payload)

        assert "concurrently" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_update_application_matching_version_increments_version_id(self):
        """Verify matching expected version_id increments version_id on update."""
        app_id = uuid.uuid4()
        existing_app = AdoptionApplication(
            id=app_id,
            dog_id=uuid.uuid4(),
            adopter_id=uuid.uuid4(),
            residential_status="owned",
            has_landlord_approval=True,
            has_yard_fence=True,
            household_members_count=2,
            status=AdoptionStatus.SUBMITTED,
            version_id=2,
        )

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=existing_app)
        mock_repo._session = MagicMock()
        mock_repo._session.flush = AsyncMock()

        mock_dog_repo = MagicMock()

        service = AdoptionService(mock_repo, mock_dog_repo)

        valid_payload = AdoptionApplicationUpdate(
            vetting_officer_notes="Valid update", version_id=2
        )

        res = await service.update_application(app_id, valid_payload)
        assert res.version_id == 3  # Incremented to 3


class TestETag304Caching:
    """Test suite for ETag HTTP 304 caching handling."""

    @pytest.mark.asyncio
    async def test_etag_cache_response_returns_304_on_matching_header(self):
        """Verify etag_cache_response returns HTTP 304 when If-None-Match matches."""
        payload_data = {"dogs": [{"id": "dog-1", "name": "Barnaby"}]}

        mock_req_1 = MagicMock(spec=Request)
        mock_req_1.headers = {}

        # 1. First request generates response with ETag header
        first_resp = etag_cache_response(mock_req_1, payload_data)
        assert first_resp.status_code == 200
        assert "ETag" in first_resp.headers
        generated_etag = first_resp.headers["ETag"]

        # 2. Subsequent request with matching If-None-Match returns 304 Not Modified
        mock_req_2 = MagicMock(spec=Request)
        mock_req_2.headers = {"if-none-match": generated_etag}

        second_resp = etag_cache_response(mock_req_2, payload_data)
        assert second_resp.status_code == 304
        assert len(second_resp.body) == 0  # Zero byte payload
