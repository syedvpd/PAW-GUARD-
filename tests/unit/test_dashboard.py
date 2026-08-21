"""Unit tests for DashboardRepository aggregation queries."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.modules.admin.dashboard_repository import DashboardRepository


class TestDashboardRepository:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        return DashboardRepository(mock_session)

    async def test_get_total_users_count(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42
        mock_session.execute.return_value = mock_result
        count = await repo.get_total_users_count()
        assert count == 42

    async def test_get_active_users_count(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 30
        mock_session.execute.return_value = mock_result
        count = await repo.get_active_users_count()
        assert count == 30

    async def test_get_shelter_occupancy(self, repo, mock_session):
        mock_capacity = MagicMock()
        mock_capacity.scalar_one.return_value = 100
        mock_occupied = MagicMock()
        mock_occupied.scalar_one.return_value = 60

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_capacity
            return mock_occupied

        mock_session.execute = AsyncMock(side_effect=side_effect)
        result = await repo.get_shelter_occupancy()
        assert result["capacity"] == 100
        assert result["occupied"] == 60
        assert result["occupancy_pct"] == 60.0

    async def test_get_inventory_alerts_no_alerts(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        alerts = await repo.get_inventory_alerts()
        assert alerts == []

    async def test_count_expiring_inventory(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_session.execute.return_value = mock_result
        count = await repo.count_expiring_inventory(days=30)
        assert count == 5

    async def test_get_system_metrics(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_result
        metrics = await repo.get_system_metrics()
        assert metrics["total_users"] == 0
        assert "total_rescues" in metrics

    async def test_get_summary_returns_nested_dict(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_result.scalar_one_or_none.return_value = None
        mock_result.one.side_effect = [(0,) * 11] + [(0, 0)] * 10
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        summary = await repo.get_summary()
        assert "users" in summary and "dogs" in summary
        assert "rescues" in summary and "donations" in summary

    async def test_get_kpis_returns_expected_keys(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_result.scalar_one_or_none.return_value = None
        mock_result.one.return_value = (0, 0)
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        kpis = await repo.get_kpis()
        assert "adoption_rate_pct" in kpis
        assert "shelter_occupancy_pct" in kpis

    async def test_get_charts_returns_trend_keys(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_result.scalar_one_or_none.return_value = None
        mock_result.one.return_value = (0, 0)
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        charts = await repo.get_charts()
        assert "adoption_trend" in charts
        assert "rescue_trend" in charts
        assert "donation_trend" in charts
        assert "breed_distribution" in charts

    async def test_rescue_donation_adoption_volunteer_stats(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_result.scalar_one_or_none.return_value = None
        mock_result.one.return_value = (0, 0)
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        rescue = await repo.get_rescue_stats()
        assert "by_status" in rescue and "total_rescues" in rescue
        donation = await repo.get_donation_summary()
        assert "total_raised" in donation and "monthly_trend" in donation
        adoption = await repo.get_adoption_stats()
        assert "by_status" in adoption and "adoption_rate_pct" in adoption
        volunteer = await repo.get_volunteer_stats()
        assert "total_volunteers" in volunteer and "hours_logged" in volunteer

    async def test_notification_shelter_lost_found_grievance_stats(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_result.scalar_one_or_none.return_value = None
        mock_result.one.return_value = (0, 0)
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        notif = await repo.get_notification_summary()
        assert "total" in notif and "unread" in notif and "read" in notif
        shelter = await repo.get_shelter_stats()
        assert "total_facilities" in shelter and "occupancy_pct" in shelter
        lf = await repo.get_lost_found_stats()
        assert "active_lost" in lf and "total_lost" in lf
        grievance = await repo.get_grievance_stats()
        assert "open" in grievance and "feedback" in grievance
