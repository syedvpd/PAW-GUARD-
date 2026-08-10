"""Smoke tests: fast health checks for post-deploy validation."""

import pytest
from httpx import AsyncClient


@pytest.mark.smoke
class TestSmokeHealth:
    async def test_health_check(self, async_client: AsyncClient):
        resp = await async_client.get("/health")
        assert resp.status_code == 200

    async def test_db_connectivity(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/dogs?page=1&size=1")
        assert resp.status_code == 200

    async def test_auth_login_works(self, async_client: AsyncClient):
        resp = await async_client.post("/api/v1/auth/login", json={"email": "test@pawguard.org", "password": "TestPass123!"})
        assert resp.status_code in (200, 401)

    async def test_portal_endpoints_load(self, async_client: AsyncClient):
        for endpoint in ["/api/v1/portal/landing-stats", "/api/v1/portal/faq", "/api/v1/portal/contact"]:
            resp = await async_client.get(endpoint)
            assert resp.status_code == 200

    async def test_public_dogs_list(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/dogs")
        assert resp.status_code == 200


@pytest.mark.smoke
class TestSmokeModules:
    async def test_rescue_list(self, async_client: AsyncClient, admin_token):
        resp = await async_client.get("/api/v1/rescue/requests", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    async def test_shelter_list(self, async_client: AsyncClient, admin_token):
        resp = await async_client.get("/api/v1/shelter/facilities", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    async def test_inventory_list(self, async_client: AsyncClient, admin_token):
        resp = await async_client.get("/api/v1/inventory/items", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    async def test_donation_list(self, async_client: AsyncClient, admin_token):
        resp = await async_client.get("/api/v1/donations", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
