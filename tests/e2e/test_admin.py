"""E2E tests for ADMIN module (11 endpoints)."""
import uuid
import pytest
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestAdminEndpoints:
    """All 11 admin endpoints: roles CRUD, permissions list, users CRUD."""

    # ── Roles ────────────────────────────────────────────────────────────

    async def test_list_roles(self, client, setup):
        r = await call(client, "admin", "GET", "/api/v1/admin/roles",
                       headers=setup.admin_headers, expected=200)

    async def test_create_role(self, client, setup):
        r = await call(client, "admin", "POST", "/api/v1/admin/roles",
                       headers=setup.admin_headers, json={
                           "name": f"role_{uid()}",
                           "description": "Test role",
                       }, expected=201)
        if r.status_code == 201:
            TEST.role_id = uuid.UUID(r.json()["data"]["id"])

    async def test_get_role(self, client, setup):
        await call(client, "admin", "POST", "/api/v1/admin/roles",
                   headers=setup.admin_headers, json={
                       "name": f"role_{uid()}",
                       "description": "Test role",
                   }, expected=201)
        r = await call(client, "admin", "GET",
                       f"/api/v1/admin/roles/{TEST.role_id}",
                       headers=setup.admin_headers, expected=200)

    async def test_get_role_not_found(self, client, setup):
        fake_id = str(uuid.uuid4())
        r = await call(client, "admin", "GET", f"/api/v1/admin/roles/{fake_id}",
                       headers=setup.admin_headers, expected=404)

    async def test_update_role(self, client, setup):
        await call(client, "admin", "POST", "/api/v1/admin/roles",
                   headers=setup.admin_headers, json={
                       "name": f"role_{uid()}",
                       "description": "Original",
                   }, expected=201)
        r = await call(client, "admin", "PUT",
                       f"/api/v1/admin/roles/{TEST.role_id}",
                       headers=setup.admin_headers, json={
                           "description": "Updated",
                       }, expected=200)

    async def test_delete_role(self, client, setup):
        create_r = await client.post("/api/v1/admin/roles", json={
            "name": f"role_{uid()}",
            "description": "To delete",
        }, headers=setup.admin_headers)
        if create_r.status_code == 201:
            role_id = create_r.json()["data"]["id"]
            r = await call(client, "admin", "DELETE",
                           f"/api/v1/admin/roles/{role_id}",
                           headers=setup.admin_headers, expected=200)

    # ── Permissions ──────────────────────────────────────────────────────

    async def test_list_permissions(self, client, setup):
        r = await call(client, "admin", "GET", "/api/v1/admin/permissions",
                       headers=setup.admin_headers, expected=200)

    # ── Users ────────────────────────────────────────────────────────────

    async def test_list_users(self, client, setup):
        r = await call(client, "admin", "GET", "/api/v1/admin/users",
                       headers=setup.admin_headers, expected=200)

    async def test_create_user(self, client, setup):
        r = await call(client, "admin", "POST", "/api/v1/admin/users",
                       headers=setup.admin_headers, json={
                           "email": f"admin_created_{uid()}@test.com",
                           "password": "StrongP@ss99",
                           "full_name": "Admin Created User",
                           "phone": "+1234567890",
                       }, expected=201)

    async def test_get_user(self, client, setup):
        create_r = await client.post("/api/v1/admin/users", json={
            "email": f"admin_user_{uid()}@test.com",
            "password": "StrongP@ss99",
            "full_name": "Fetch User",
            "phone": "+1234567890",
        }, headers=setup.admin_headers)
        if create_r.status_code == 201:
            user_id = create_r.json()["data"]["id"]
            r = await call(client, "admin", "GET",
                           f"/api/v1/admin/users/{user_id}",
                           headers=setup.admin_headers, expected=200)

    async def test_update_user(self, client, setup):
        create_r = await client.post("/api/v1/admin/users", json={
            "email": f"admin_upd_{uid()}@test.com",
            "password": "StrongP@ss99",
            "full_name": "Update Target",
            "phone": "+1234567890",
        }, headers=setup.admin_headers)
        if create_r.status_code == 201:
            user_id = create_r.json()["data"]["id"]
            r = await call(client, "admin", "PUT",
                           f"/api/v1/admin/users/{user_id}",
                           headers=setup.admin_headers, json={
                               "full_name": "Updated Name",
                           }, expected=200)

    async def test_delete_user(self, client, setup):
        create_r = await client.post("/api/v1/admin/users", json={
            "email": f"admin_del_{uid()}@test.com",
            "password": "StrongP@ss99",
            "full_name": "Delete Target",
            "phone": "+1234567890",
        }, headers=setup.admin_headers)
        if create_r.status_code == 201:
            user_id = create_r.json()["data"]["id"]
            r = await call(client, "admin", "DELETE",
                           f"/api/v1/admin/users/{user_id}",
                           headers=setup.admin_headers, expected=200)
