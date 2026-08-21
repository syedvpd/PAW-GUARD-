"""Unit tests for system health, API contracts, and PawGuard configuration checks."""

import pytest
from httpx import ASGITransport, AsyncClient

from pawguard.core.config import get_settings
from pawguard.core.responses import ApiResponse
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


def test_pawguard_response_model_contract():
    """Verify standard PawGuard ApiResponse envelope schema."""
    resp = ApiResponse(data={"status": "active"}, message="Operation succeeded")
    assert resp.success is True
    assert resp.data == {"status": "active"}
    assert resp.message == "Operation succeeded"


def test_app_settings_configuration():
    """Verify core PawGuard settings load valid configuration defaults."""
    settings = get_settings()
    assert settings.app_name == "PawGuard"
    assert settings.api_v1_prefix == "/api/v1"
