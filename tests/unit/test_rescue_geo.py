import uuid
from unittest.mock import AsyncMock, MagicMock
from datetime import UTC, datetime
import pytest
from pawguard.modules.rescue.models import RescueDispatch, RescueRequest, RescueStatus
from pawguard.modules.rescue.schemas import RescueDispatchResponse, NearbyAgentResponse
from pawguard.modules.rescue.service import RescueService
from pawguard.modules.auth.models import User, Role


class TestRescueGeo:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo._session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        return redis

    @pytest.fixture
    def service(self, mock_repo, mock_redis):
        return RescueService(
            mock_repo,
            audit_service=None,
            dog_repo=None,
            redis_client=mock_redis,
        )

    @pytest.mark.asyncio
    async def test_update_agent_location(self, service, mock_redis):
        agent_id = uuid.uuid4()
        await service.update_agent_location(agent_id, 17.4482, 78.3741)

        mock_redis.geoadd.assert_called_once_with(
            "rescue:agent_locations", (78.3741, 17.4482, str(agent_id))
        )
        mock_redis.set.assert_called_once_with(
            f"rescue:agent_active:{agent_id}", "1", ex=300
        )

    @pytest.mark.asyncio
    async def test_get_nearest_agents_redis_hit(self, service, mock_repo, mock_redis):
        agent_id = uuid.uuid4()
        mock_redis.geosearch.return_value = [[str(agent_id), 12.3, (78.3741, 17.4482)]]
        mock_redis.get.return_value = "1"  # active heartbeat

        # Mock DB user
        fake_user = User(
            id=agent_id,
            email="agent@pawguard.com",
            phone="123456",
            full_name="Rescue Agent 1",
            is_active=True,
        )
        db_result = MagicMock()
        db_result.scalars().all.return_value = [fake_user]
        mock_repo._session.execute = AsyncMock(return_value=db_result)

        results = await service.get_nearest_agents(17.4480, 78.3740, radius_km=50.0)

        assert len(results) == 1
        assert results[0]["agent_id"] == agent_id
        assert results[0]["name"] == "Rescue Agent 1"
        assert results[0]["distance_km"] == 12.3
        assert results[0]["latitude"] == 17.4482
        assert results[0]["longitude"] == 78.3741

    @pytest.mark.asyncio
    async def test_get_nearest_agents_fallback_to_db(self, service, mock_repo, mock_redis):
        mock_redis.geosearch.return_value = []

        # Mock DB users for fallback (super_admin / rescue_agent)
        agent_id = uuid.uuid4()
        fake_user = User(
            id=agent_id,
            email="fallback@pawguard.com",
            phone="987654",
            full_name="Fallback Agent",
            is_active=True,
        )
        db_result = MagicMock()
        db_result.scalars().all.return_value = [fake_user]
        mock_repo._session.execute = AsyncMock(return_value=db_result)

        results = await service.get_nearest_agents(17.4480, 78.3740, radius_km=50.0)

        # Should fall back to database query and return fallback list (distance_km is None)
        assert len(results) == 1
        assert results[0]["agent_id"] == agent_id
        assert results[0]["name"] == "Fallback Agent"
        assert results[0]["distance_km"] is None

    def test_rescue_dispatch_response_properties(self):
        request_id = uuid.uuid4()
        dispatch_id = uuid.uuid4()
        driver_id = uuid.uuid4()

        # Mock parent request
        request = RescueRequest(
            id=request_id,
            ticket_number="RES-20260814-1234",
            status=RescueStatus.DISPATCHED,
        )

        dispatch = RescueDispatch(
            id=dispatch_id,
            rescue_request_id=request_id,
            assigned_driver_id=driver_id,
            vehicle_id="VEH-001",
            dispatched_at=datetime.now(UTC),
        )
        dispatch.rescue_request = request

        # Validate that model properties work
        assert dispatch.status == RescueStatus.DISPATCHED
        assert dispatch.ticket_number == "RES-20260814-1234"

        # Validate Pydantic schema serialization
        response = RescueDispatchResponse.model_validate(dispatch)
        assert response.status == RescueStatus.DISPATCHED
        assert response.ticket_number == "RES-20260814-1234"
