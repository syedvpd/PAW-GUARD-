"""Unit tests for rescue dispatch aggregate counts endpoint (PRR 3.3).

Validates the RescueDispatchCountsResponse schema and the service delegation.
Database-level query logic is covered by integration tests.
"""

import pytest

from pawguard.modules.rescue.schemas import RescueDispatchCountsResponse


class TestRescueDispatchCountsResponse:
    """Schema validation for the counts response."""

    def test_valid_counts_response(self):
        """All four count fields must be present and non-negative."""
        resp = RescueDispatchCountsResponse(
            total_dispatches=100,
            active_dispatches=20,
            escalated_dispatches=5,
            failed_dispatches=3,
        )
        assert resp.total_dispatches == 100
        assert resp.active_dispatches == 20
        assert resp.escalated_dispatches == 5
        assert resp.failed_dispatches == 3

    def test_zero_counts_valid(self):
        """Zero counts are valid (empty system)."""
        resp = RescueDispatchCountsResponse(
            total_dispatches=0,
            active_dispatches=0,
            escalated_dispatches=0,
            failed_dispatches=0,
        )
        assert resp.total_dispatches == 0

    def test_schema_field_names(self):
        """Field names must exactly match the Flutter API contract."""
        resp = RescueDispatchCountsResponse(
            total_dispatches=1,
            active_dispatches=1,
            escalated_dispatches=0,
            failed_dispatches=0,
        )
        data = resp.model_dump()
        assert "total_dispatches" in data
        assert "active_dispatches" in data
        assert "escalated_dispatches" in data
        assert "failed_dispatches" in data

    def test_escalated_is_subset_of_total(self):
        """Sanity: escalated_dispatches should never exceed total_dispatches."""
        resp = RescueDispatchCountsResponse(
            total_dispatches=10,
            active_dispatches=8,
            escalated_dispatches=3,
            failed_dispatches=2,
        )
        assert resp.escalated_dispatches <= resp.total_dispatches
        assert resp.failed_dispatches <= resp.total_dispatches


class TestDispatchCountsServiceDelegation:
    """Service-level unit tests using a mocked repository."""

    @pytest.mark.asyncio
    async def test_get_dispatch_counts_delegates_to_repo(self):
        """get_dispatch_counts() must call repo.get_dispatch_counts() and wrap result."""
        from unittest.mock import AsyncMock

        from pawguard.modules.dog.repository import DogRepository
        from pawguard.modules.rescue.repository import RescueRepository
        from pawguard.modules.rescue.service import RescueService

        mock_repo = AsyncMock(spec=RescueRepository)
        mock_repo._session = AsyncMock()
        mock_repo.get_request_by_ticket.return_value = None
        mock_repo.get_dispatch_counts.return_value = {
            "total_dispatches": 50,
            "active_dispatches": 10,
            "escalated_dispatches": 4,
            "failed_dispatches": 6,
        }

        service = RescueService(
            mock_repo,
            audit_service=None,
            dog_repo=AsyncMock(spec=DogRepository),
            redis_client=None,
            arq_pool=None,
        )

        result = await service.get_dispatch_counts()

        mock_repo.get_dispatch_counts.assert_called_once()
        assert isinstance(result, RescueDispatchCountsResponse)
        assert result.total_dispatches == 50
        assert result.escalated_dispatches == 4
        assert result.failed_dispatches == 6

    @pytest.mark.asyncio
    async def test_get_dispatch_counts_zero_when_no_dispatches(self):
        """Zero result from repo produces valid zero-counts response."""
        from unittest.mock import AsyncMock

        from pawguard.modules.dog.repository import DogRepository
        from pawguard.modules.rescue.repository import RescueRepository
        from pawguard.modules.rescue.service import RescueService

        mock_repo = AsyncMock(spec=RescueRepository)
        mock_repo._session = AsyncMock()
        mock_repo.get_request_by_ticket.return_value = None
        mock_repo.get_dispatch_counts.return_value = {
            "total_dispatches": 0,
            "active_dispatches": 0,
            "escalated_dispatches": 0,
            "failed_dispatches": 0,
        }

        service = RescueService(
            mock_repo,
            audit_service=None,
            dog_repo=AsyncMock(spec=DogRepository),
            redis_client=None,
            arq_pool=None,
        )

        result = await service.get_dispatch_counts()
        assert result.total_dispatches == 0
        assert result.escalated_dispatches == 0
