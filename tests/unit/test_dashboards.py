"""Unit tests for dashboard aggregation functions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.modules.dashboards.router import stream_rescue_dashboard
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


def _fake_result(
    scalar_one_val=None, all_val=None, one_val=None, scalars_all=None, scalar_val=None, **row_attrs
):
    r = MagicMock()
    if row_attrs:
        row = MagicMock()
        for k, v in row_attrs.items():
            setattr(row, k, v)
        r.one.return_value = row
    if scalar_one_val is not None:
        r.scalar_one.return_value = scalar_one_val
    if scalar_val is not None:
        r.scalar.return_value = scalar_val
        r.scalar_one.return_value = scalar_val
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
            _fake_result(total=10, pending=3, dispatched=2, rescued=5),
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
            _fake_result(
                total_facilities=2,
                total_dogs=50,
                adoptable_dogs=20,
                total_kennels=60,
                pending_transfers=0,
                isolation_count=0,
                pending_cleaning=0,
            ),
        ]
        result = await shelter_dashboard(session)
        assert result["total_facilities"] == 2
        assert result["total_dogs"] == 50
        assert result["adoptable_dogs"] == 20
        assert result["total_kennels"] == 60
        assert result["occupancy_rate"] == pytest.approx(83.3, rel=0.1)

    async def test_shelter_dashboard_no_kennels(self, session):
        session.execute.side_effect = [
            _fake_result(
                total_facilities=0,
                total_dogs=0,
                adoptable_dogs=0,
                total_kennels=0,
                pending_transfers=0,
                isolation_count=0,
                pending_cleaning=0,
            ),
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
            _fake_result(
                total=100,
                pending=20,
                approved=15,
                completed=60,
                screening=8,
                interview=5,
                home_check=3,
                overdue_follow_ups=4,
            ),
        ]
        result = await adoption_dashboard(session)
        assert result["total_applications"] == 100
        assert result["pending"] == 20
        assert result["approved"] == 15
        assert result["completed"] == 60
        assert result["screening"] == 8
        assert result["interview"] == 5
        assert result["home_check"] == 3
        assert result["overdue_follow_ups"] == 4

    async def test_foster_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(total=25, active=10),
        ]
        result = await foster_dashboard(session)
        assert result["total_placements"] == 25
        assert result["active_placements"] == 10

    async def test_volunteer_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(total=50, available=35),
        ]
        result = await volunteer_dashboard(session)
        assert result["total_volunteers"] == 50
        assert result["available"] == 35

    async def test_inventory_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(all_val=[("food", 10, 500.0)]),
            _fake_result(scalars_all=[]),
        ]
        result = await inventory_dashboard(session)
        assert len(result["categories"]) == 1
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
            _fake_result(income=30000.0, donation_income=15000.0, expense=20000.0, pending_tx=5),
            _fake_result(amount=5000.0),
        ]
        result = await finance_dashboard(session)
        assert result["total_income"] == 50000.0
        assert result["total_expenses"] == 20000.0
        assert result["net_balance"] == 30000.0
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
            _fake_result(total_staff=25, open_grievances=8),
        ]
        result = await staff_dashboard(session)
        assert result["total_staff"] == 25
        assert result["open_grievances"] == 8

    async def test_executive_dashboard(self, session):
        session.execute.side_effect = [
            # rescue_dashboard (2 queries)
            _fake_result(total=200, pending=10, dispatched=5, rescued=20),
            _fake_result(scalars_all=[]),
            # finance_dashboard (2 queries)
            _fake_result(income=60000.0, donation_income=30000.0, expense=40000.0, pending_tx=2),
            _fake_result(amount=10000.0),
            # adoption_dashboard (1 query)
            _fake_result(
                total=150,
                pending=20,
                approved=15,
                completed=60,
                screening=8,
                interview=5,
                home_check=3,
                overdue_follow_ups=4,
            ),
        ]
        result = await executive_dashboard(session)
        assert "rescue_overview" in result
        assert "finance_overview" in result
        assert "adoption_overview" in result
        assert result["rescue_overview"]["total_calls"] == 200
        assert result["rescue_overview"]["rescued"] == 20
        assert result["finance_overview"]["total_income"] == 100000.0
        assert result["finance_overview"]["total_expenses"] == 40000.0
        assert result["adoption_overview"]["total"] == 150
        assert result["adoption_overview"]["completed"] == 60

    async def test_public_dashboard(self, session):
        session.execute.side_effect = [
            _fake_result(adoptable_dogs=45, dogs_rescued=100),
        ]
        result = await public_dashboard(session)
        assert result["adoptable_dogs"] == 45
        assert result["dogs_rescued"] == 100

    async def test_operations_dashboard(self, session):
        session.execute.side_effect = [
            # rescue_dashboard (2 queries)
            _fake_result(total=200, pending=10, dispatched=5, rescued=20),
            _fake_result(scalars_all=[]),
            # shelter_dashboard (1 query)
            _fake_result(
                total_facilities=3,
                total_dogs=80,
                adoptable_dogs=30,
                total_kennels=100,
                pending_transfers=0,
                isolation_count=0,
                pending_cleaning=0,
            ),
            # inventory_dashboard (2 queries)
            _fake_result(all_val=[]),
            _fake_result(scalars_all=[]),
        ]
        result = await operations_dashboard(session)
        assert "rescue" in result
        assert "shelter" in result
        assert "inventory" in result

    async def test_dashboard_cache_hit(self, session):
        fake_redis = AsyncMock()
        fake_redis.get.return_value = (
            '{"total_calls": 999, "pending": 1, "dispatched": 2, "rescued": 3, "recent_calls": []}'
        )
        result = await rescue_dashboard(session, redis=fake_redis)
        assert result["total_calls"] == 999
        session.execute.assert_not_called()

    async def test_dashboard_cache_miss_stores_value(self, session):
        fake_redis = AsyncMock()
        fake_redis.get.return_value = None
        session.execute.side_effect = [
            _fake_result(total=10, pending=3, dispatched=2, rescued=5),
            _fake_result(scalars_all=[]),
        ]
        result = await rescue_dashboard(session, redis=fake_redis)
        assert result["total_calls"] == 10
        fake_redis.set.assert_called_once()
        assert fake_redis.set.call_args[0][0] == "cache:dashboard:rescue"

    async def test_stream_rescue_dashboard_pubsub(self, session):
        request = AsyncMock()
        request.is_disconnected.side_effect = [False, True]

        fake_redis = MagicMock()
        pubsub_mock = AsyncMock()
        fake_redis.pubsub.return_value = pubsub_mock

        pubsub_mock.get_message.return_value = {"type": "message", "data": "updated"}

        session.execute.side_effect = [
            _fake_result(total=10, pending=3, dispatched=2, rescued=5),
            _fake_result(scalars_all=[]),
            _fake_result(total=10, pending=3, dispatched=2, rescued=5),
            _fake_result(scalars_all=[]),
        ]

        response = await stream_rescue_dashboard(
            request=request,
            interval=10,
            db=session,
            redis=fake_redis,
            current_user=AsyncMock(),
        )

        outputs = []
        async for chunk in response.body_iterator:
            outputs.append(chunk)

        fake_redis.pubsub.assert_called_once()
        pubsub_mock.subscribe.assert_called_with("dispatch:events")
        pubsub_mock.unsubscribe.assert_called_with("dispatch:events")
        pubsub_mock.close.assert_called_once()

        assert len(outputs) == 2
        assert "event: snapshot" in outputs[0]
        assert "event: snapshot" in outputs[1]
