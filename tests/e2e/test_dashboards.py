"""E2E tests for DASHBOARDS module (34 endpoints).

14 dashboards + 16 admin dashboard + 4 admin audit = 34 endpoints.
"""

import uuid

import pytest
from tests.e2e.helpers import call


@pytest.mark.asyncio
class TestDashboardEndpoints:
    """All 14 dashboard endpoints."""

    async def test_adoption_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/adoption",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_donor_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/donor",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_executive_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/executive",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_finance_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/finance",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_foster_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/foster",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_inventory_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/inventory",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_medical_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/medical",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_operations_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/operations",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_public_dashboard(self, client):
        await call(client, "dashboards", "GET", "/api/v1/dashboards/public", expected=200)

    async def test_rescue_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/rescue",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_rescue_stream_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/rescue/stream",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_shelter_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/shelter",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_staff_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/staff",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_volunteer_dashboard(self, client, setup):
        await call(
            client,
            "dashboards",
            "GET",
            "/api/v1/dashboards/volunteer",
            headers=setup.admin_headers,
            expected=200,
        )


@pytest.mark.asyncio
class TestAdminDashboardEndpoints:
    """All 16 admin dashboard endpoints."""

    async def test_admin_adoption_stats(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/adoption-stats",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_charts(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/charts",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_donation_summary(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/donation-summary",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_foster_stats(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/foster-stats",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_grievance_stats(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/grievance-stats",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_inventory_alerts(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/inventory-alerts",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_kpis(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/kpis",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_lost_found_stats(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/lost-found-stats",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_medical_stats(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/medical-stats",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_metrics(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/metrics",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_notification_summary(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/notification-summary",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_recent_activity(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/recent-activity",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_rescue_stats(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/rescue-stats",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_shelter_stats(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/shelter-stats",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_summary(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/summary",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_admin_volunteer_stats(self, client, setup):
        await call(
            client,
            "admin_dashboard",
            "GET",
            "/api/v1/admin/dashboard/volunteer-stats",
            headers=setup.admin_headers,
            expected=200,
        )


@pytest.mark.asyncio
class TestAdminAuditEndpoints:
    """4 admin audit endpoints."""

    async def test_list_audit_logs(self, client, setup):
        await call(
            client,
            "admin_audit",
            "GET",
            "/api/v1/admin/audit-logs",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_get_audit_log(self, client, setup):
        fake_id = str(uuid.uuid4())
        await call(
            client,
            "admin_audit",
            "GET",
            f"/api/v1/admin/audit-logs/{fake_id}",
            headers=setup.admin_headers,
            expected=404,
        )

    async def test_export_audit_logs_post(self, client, setup):
        await call(
            client,
            "admin_audit",
            "POST",
            "/api/v1/admin/audit-logs/export",
            headers=setup.admin_headers,
            json={
                "format": "csv",
            },
            expected=200,
        )

    async def test_export_audit_logs_get(self, client, setup):
        await call(
            client,
            "admin_audit",
            "GET",
            "/api/v1/admin/audit-logs/export",
            headers=setup.admin_headers,
            expected=200,
        )
