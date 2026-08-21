"""Unit tests for system health and API status checks."""

import pytest
from httpx import ASGITransport, AsyncClient

from pawguard.main import create_app


@pytest.mark.asyncio
async def test_health_check_endpoint():
    """Verify that /health returns 200 OK with healthy status."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data.get("data", {}).get("status") == "ok"


@pytest.mark.asyncio
async def test_metrics_prometheus_endpoint_available():
    """Verify metrics endpoint returns Prometheus format output."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "http_" in response.text or "TYPE" in response.text
