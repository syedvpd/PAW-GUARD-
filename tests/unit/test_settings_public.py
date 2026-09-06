"""Unit tests for public settings content anonymous access."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from pawguard.main import app
from pawguard.modules.settings.router import get_public_content_service
from pawguard.modules.settings.schemas import PublicContentResponse
from pawguard.modules.settings.service import PublicContentService


@pytest.fixture
def mock_public_content_service():
    service = AsyncMock(spec=PublicContentService)
    service.get_content.return_value = PublicContentResponse(
        about_us="PawGuard rescues and rehabilitates stray animals.",
        mission="A world where every animal is safe and protected.",
        updated_at=datetime.now(UTC),
    )
    return service


@pytest.mark.asyncio
async def test_get_public_content_anonymous_success(mock_public_content_service):
    app.dependency_overrides[get_public_content_service] = lambda: mock_public_content_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
            # Anonymous call: No Authorization header
            response = await client.get("/api/v1/settings/public-content")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "about_us" in data["data"]
            assert "mission" in data["data"]
            assert "updated_at" in data["data"]
            # Verify private settings are NOT in response
            assert "smtp_password" not in data["data"]
            assert "s3_secret_key" not in data["data"]
            assert "jwt_secret_key" not in data["data"]
    finally:
        app.dependency_overrides.pop(get_public_content_service, None)


@pytest.mark.asyncio
async def test_get_public_content_authenticated_still_works(mock_public_content_service):
    app.dependency_overrides[get_public_content_service] = lambda: mock_public_content_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
            response = await client.get(
                "/api/v1/settings/public-content",
                headers={"Authorization": "Bearer dummy_token"},
            )
            # Even with auth header, endpoint returns 200 without blocking
            assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_public_content_service, None)


@pytest.mark.asyncio
async def test_put_public_content_requires_admin():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
        # Anonymous PUT must be rejected
        response = await client.put(
            "/api/v1/settings/public-content",
            json={"about_us": "New text", "mission": "New mission"},
        )
        assert response.status_code in (401, 403)
