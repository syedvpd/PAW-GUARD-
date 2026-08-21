"""E2E tests for REPORTS module (4 endpoints)."""

import pytest
from tests.e2e.helpers import call, uid


@pytest.mark.asyncio
class TestReportEndpoints:
    """All 4 report endpoints."""

    async def test_list_report_types(self, client, setup):
        await call(
            client,
            "reports",
            "GET",
            "/api/v1/reports/types",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_list_report_formats(self, client, setup):
        await call(
            client,
            "reports",
            "GET",
            "/api/v1/reports/formats",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_generate_report(self, client, setup):
        await call(
            client,
            "reports",
            "POST",
            "/api/v1/reports/generate",
            headers=setup.admin_headers,
            json={
                "report_type": "adoption_summary",
                "format": "pdf",
            },
            expected=200,
        )

    async def test_download_report(self, client, setup):
        filename = f"report_{uid()}.pdf"
        await call(
            client,
            "reports",
            "GET",
            f"/api/v1/reports/download/{filename}",
            headers=setup.admin_headers,
            expected=200,
        )
