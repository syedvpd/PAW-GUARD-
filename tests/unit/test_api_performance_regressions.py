"""Performance and Query-Count Regression Tests.

Guarantees that database queries, dashboard aggregations, and list endpoints
do not regress into N+1 queries or multi-statement cascades.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.dashboards.service import (
    adoption_dashboard,
    foster_dashboard,
    rescue_operations_dashboard,
    shelter_dashboard,
)


@pytest.mark.asyncio
async def test_rescue_operations_dashboard_query_count() -> None:
    """Ensure rescue_operations_dashboard executes no more than 3 queries per cache miss
    (status distribution, severity distribution, and consolidated scalar metrics).
    """
    mock_session = AsyncMock(spec=AsyncSession)

    # Status result mock
    mock_status_res = MagicMock()
    mock_status_res.all.return_value = [("reported", 5), ("dispatched", 2)]

    # Severity result mock
    mock_severity_res = MagicMock()
    mock_severity_res.all.return_value = [("critical", 3), ("moderate", 4)]

    # Consolidated metrics result mock
    mock_metrics_res = MagicMock()
    mock_metrics_row = MagicMock()
    mock_metrics_row.active_dispatches = 2
    mock_metrics_row.agents_busy = 3
    mock_metrics_row.agents_total = 10
    mock_metrics_row.vehicles_assigned = 2
    mock_metrics_row.vehicles_total = 5
    mock_metrics_res.one.return_value = mock_metrics_row

    mock_session.execute.side_effect = [
        mock_status_res,
        mock_severity_res,
        mock_metrics_res,
    ]

    result = await rescue_operations_dashboard(mock_session, redis=None)

    # Exactly 3 database statements executed instead of 7
    assert mock_session.execute.call_count == 3
    assert result["active_dispatches"] == 2
    assert result["agents_available"] == 7
    assert result["vehicles_available"] == 3


@pytest.mark.asyncio
async def test_adoption_dashboard_single_query_execution() -> None:
    """Ensure adoption_dashboard executes exactly 1 consolidated SQL statement per cache miss."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_row = MagicMock()
    mock_row.total = 10
    mock_row.pending = 2
    mock_row.approved = 3
    mock_row.completed = 3
    mock_row.screening = 1
    mock_row.interview = 0
    mock_row.home_check = 0
    mock_row.rejected = 1
    mock_row.withdrawn = 0
    mock_row.scheduled_home_visits = 0
    mock_row.adoptable_dogs = 5
    mock_row.overdue_follow_ups = 0
    mock_res.one.return_value = mock_row
    mock_session.execute.return_value = mock_res

    result = await adoption_dashboard(mock_session, redis=None)

    assert mock_session.execute.call_count == 1
    assert result["total_applications"] == 10
    assert result["pending"] == 2


@pytest.mark.asyncio
async def test_foster_dashboard_single_query_execution() -> None:
    """Ensure foster_dashboard executes exactly 1 consolidated SQL statement per cache miss."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_row = MagicMock()
    mock_row.total = 8
    mock_row.active = 5
    mock_row.returned = 2
    mock_row.converted = 1
    mock_row.total_fosters = 12
    mock_row.approved_fosters = 10
    mock_row.available_fosters = 4
    mock_row.pending_applications = 2
    mock_row.rejected_fosters = 0
    mock_row.inactive_fosters = 0
    mock_row.total_capacity = 20
    mock_row.total_homes = 12
    mock_res.one.return_value = mock_row
    mock_session.execute.return_value = mock_res

    result = await foster_dashboard(mock_session, redis=None)

    assert mock_session.execute.call_count == 1
    assert result["total_placements"] == 8
    assert result["available_fosters"] == 4


@pytest.mark.asyncio
async def test_shelter_dashboard_query_count() -> None:
    """Ensure shelter_dashboard executes exactly 2 queries per cache miss (summary + facility breakdown)."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_summary_res = MagicMock()
    mock_summary_row = MagicMock()
    mock_summary_row.total_facilities = 2
    mock_summary_row.total_capacity = 100
    mock_summary_row.total_dogs = 45
    mock_summary_row.adoptable_dogs = 30
    mock_summary_row.total_kennels = 50
    mock_summary_row.occupied_kennels = 45
    mock_summary_row.pending_transfers = 1
    mock_summary_row.isolation_count = 2
    mock_summary_row.quarantine_count = 3
    mock_summary_row.pending_cleaning = 4
    mock_summary_row.daily_intake_today = 5
    mock_summary_row.daily_exits_today = 3
    mock_summary_res.one.return_value = mock_summary_row

    mock_facility_res = MagicMock()
    mock_facility_res.all.return_value = []

    mock_session.execute.side_effect = [mock_summary_res, mock_facility_res]

    result = await shelter_dashboard(mock_session, redis=None)

    assert mock_session.execute.call_count == 2
    assert result["total_facilities"] == 2
    assert result["occupied_kennels"] == 45
