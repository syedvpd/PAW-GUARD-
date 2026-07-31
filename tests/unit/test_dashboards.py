"""Unit tests for dashboard aggregation functions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.modules.dashboards.service import (
    adoption_dashboard,
    donor_dashboard,
    executive_dashboard,
    finance_dashboard,
    foster_dashboard,
    inventory_dashboard,
    medical_dashboard,
    operations_dashboard,
    public_dashboard,
    rescue_dashboard,
    shelter_dashboard,
    staff_dashboard,
    volunteer_dashboard,
)


def _fake_result(scalar_one_val=None, all_val=None, one_val=None, scalars_all=None):
    r = MagicMock()
    if scalar_one_val is not None:
        r.scalar_one.return_value = scalar_one_val
    if all_val is not None:
        r.all.return_value = all_val
    if one_val is not None:
        r.one.return_value = one_val
    if scalars_all is not None:
        r.scalars.return_value.all.return_value = scalars_all
    return r


@pytest.mark.asyncio
class TestDashboards:
    @pytest.fixture
    def session(self):
        return AsyncMock()

    async def test_rescue_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=10),
            _fake_result(scalar_one_val=3),
            _fake_result(scalar_one_val=2),
            _fake_result(scalar_one_val=5),
            _fake_result(scalars_all=[]),
        ]
        result = await rescue_dashboard(session)
        assert result["total_calls"] == 10
        assert result["pending"] == 3
        assert result["dispatched"] == 2
        assert result["rescued"] == 5
        assert result["recent_calls"] == []

    async def test_shelter_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=2),
            _fake_result(scalar_one_val=50),
            _fake_result(scalar_one_val=20),
            _fake_result(scalar_one_val=60),
        ]
        result = await shelter_dashboard(session)
        assert result["total_facilities"] == 2
        assert result["total_dogs"] == 50
        assert result["adoptable_dogs"] == 20
        assert result["total_kennels"] == 60
        assert result["occupancy_rate"] == pytest.approx(83.3, rel=0.1)

    async def test_shelter_dashboard_no_kennels(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=0),
            _fake_result(scalar_one_val=0),
            _fake_result(scalar_one_val=0),
            _fake_result(scalar_one_val=0),
        ]
        result = await shelter_dashboard(session)
        assert result["occupancy_rate"] == 0

    async def test_medical_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=15),
            _fake_result(scalar_one_val=30),
        ]
        result = await medical_dashboard(session)
        assert result["exams_last_30d"] == 15
        assert result["treatments_last_30d"] == 30

    async def test_adoption_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=100),
            _fake_result(scalar_one_val=20),
            _fake_result(scalar_one_val=15),
            _fake_result(scalar_one_val=60),
        ]
        result = await adoption_dashboard(session)
        assert result["total_applications"] == 100
        assert result["pending"] == 20
        assert result["approved"] == 15
        assert result["completed"] == 60
        assert result["completed"] == 60

    async def test_foster_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=25),
            _fake_result(scalar_one_val=10),
        ]
        result = await foster_dashboard(session)
        assert result["total_placements"] == 25
        assert result["active_placements"] == 10

    async def test_volunteer_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=50),
            _fake_result(scalar_one_val=30),
        ]
        result = await volunteer_dashboard(session)
        assert result["total_volunteers"] == 50
        assert result["available"] == 30

    async def test_inventory_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(all_val=[("pharma", 5, 200.0), ("food", 3, 100.0)]),
            _fake_result(scalars_all=[]),
        ]
        result = await inventory_dashboard(session)
        assert len(result["categories"]) == 2
        assert result["total_low_stock"] == 0

    async def test_inventory_dashboard_with_low_stock(self, session):
        low_item = MagicMock()
        low_item.id = "item-1"
        low_item.name = "Bandages"
        low_item.quantity = 5.0
        low_item.reorder_threshold = 10.0
        session.execute.side_effect = [
            _fake_result(all_val=[]),
            _fake_result(scalars_all=[low_item]),
        ]
        result = await inventory_dashboard(session)
        assert result["total_low_stock"] == 1
        assert result["low_stock_alerts"][0]["name"] == "Bandages"

    async def test_finance_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=50000),
            _fake_result(scalar_one_val=30000),
            _fake_result(scalar_one_val=5),
        ]
        result = await finance_dashboard(session)
        assert result["total_income"] == 50000.0
        assert result["total_expenses"] == 30000.0
        assert result["net_balance"] == 20000.0
        assert result["pending_transactions"] == 5

    async def test_donor_dashboard(self, session):
        recent = MagicMock()
        recent.id = "don-1"
        recent.amount = 100.0
        recent.currency = "USD"
        recent.donation_type = "one_time"
        recent.created_at.date.return_value.isoformat.return_value = "2026-07-01"
        session.execute.side_effect = [
            _fake_result(one_val=(50, 25000.0)),
            _fake_result(scalars_all=[recent]),
        ]
        result = await donor_dashboard(session)
        assert result["total_donations"] == 50
        assert result["total_amount"] == 25000.0
        assert len(result["recent_donations"]) == 1

    async def test_staff_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=30),
            _fake_result(scalar_one_val=2),
        ]
        result = await staff_dashboard(session)
        assert result["total_staff"] == 30
        assert result["open_grievances"] == 2

    async def test_executive_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=100),
            _fake_result(scalar_one_val=10),
            _fake_result(scalar_one_val=5),
            _fake_result(scalar_one_val=80),
            _fake_result(scalars_all=[]),
            _fake_result(scalar_one_val=500000),
            _fake_result(scalar_one_val=300000),
            _fake_result(scalar_one_val=10),
            _fake_result(scalar_one_val=200),
            _fake_result(scalar_one_val=30),
            _fake_result(scalar_one_val=50),
            _fake_result(scalar_one_val=100),
        ]
        result = await executive_dashboard(session)
        assert "rescue_overview" in result
        assert "finance_overview" in result
        assert "adoption_overview" in result

    async def test_public_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=25),
            _fake_result(scalar_one_val=100),
        ]
        result = await public_dashboard(session)
        assert result["adoptable_dogs"] == 25
        assert result["dogs_rescued"] == 100

    async def test_operations_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(scalar_one_val=200),
            _fake_result(scalar_one_val=10),
            _fake_result(scalar_one_val=5),
            _fake_result(scalar_one_val=20),
            _fake_result(scalars_all=[]),
            _fake_result(scalar_one_val=3),
            _fake_result(scalar_one_val=80),
            _fake_result(scalar_one_val=30),
            _fake_result(scalar_one_val=100),
            _fake_result(all_val=[]),
            _fake_result(scalars_all=[]),
        ]
        result = await operations_dashboard(session)
        assert "rescue" in result
        assert "shelter" in result
        assert "inventory" in result
