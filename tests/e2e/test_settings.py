"""E2E tests for SETTINGS module (17 endpoints)."""

import pytest
from tests.e2e.helpers import call, uid


@pytest.mark.asyncio
class TestSettingsEndpoints:
    """All 17 settings endpoints."""

    # ── General ──────────────────────────────────────────────────────────

    async def test_get_general_settings(self, client, setup):
        await call(
            client,
            "settings",
            "GET",
            "/api/v1/settings/general",
            headers=setup.admin_headers,
            expected=200,
        )

    # ── Email ────────────────────────────────────────────────────────────

    async def test_get_email_settings(self, client, setup):
        await call(
            client,
            "settings",
            "GET",
            "/api/v1/settings/email",
            headers=setup.admin_headers,
            expected=200,
        )

    # ── Password Policy ──────────────────────────────────────────────────

    async def test_get_password_policy(self, client, setup):
        await call(
            client,
            "settings",
            "GET",
            "/api/v1/settings/password-policy",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_password_policy(self, client, setup):
        await call(
            client,
            "settings",
            "PUT",
            "/api/v1/settings/password-policy",
            headers=setup.admin_headers,
            json={
                "min_length": 10,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_digit": True,
                "require_special": True,
            },
            expected=200,
        )

    # ── Storage ──────────────────────────────────────────────────────────

    async def test_get_storage_settings(self, client, setup):
        await call(
            client,
            "settings",
            "GET",
            "/api/v1/settings/storage",
            headers=setup.admin_headers,
            expected=200,
        )

    # ── Public Content ───────────────────────────────────────────────────

    async def test_get_public_content(self, client):
        await call(client, "settings", "GET", "/api/v1/settings/public-content", expected=200)

    async def test_update_public_content(self, client, setup):
        await call(
            client,
            "settings",
            "PUT",
            "/api/v1/settings/public-content",
            headers=setup.admin_headers,
            json={
                "site_name": "PawGuard",
                "tagline": "Saving Paws Together",
            },
            expected=200,
        )

    # ── System Settings ──────────────────────────────────────────────────

    async def test_get_system_settings(self, client, setup):
        await call(
            client,
            "settings",
            "GET",
            "/api/v1/settings/system",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_create_system_setting(self, client, setup):
        await call(
            client,
            "settings",
            "POST",
            "/api/v1/settings/system",
            headers=setup.admin_headers,
            json={
                "key": f"test_setting_{uid()}",
                "value": "test_value",
                "description": "Test setting",
            },
            expected=201,
        )

    async def test_get_system_setting_by_key(self, client, setup):
        create_r = await client.post(
            "/api/v1/settings/system",
            json={
                "key": f"get_setting_{uid()}",
                "value": "get_value",
                "description": "Get setting",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            key = create_r.json()["data"]["key"]
            await call(
                client,
                "settings",
                "GET",
                f"/api/v1/settings/system/{key}",
                headers=setup.admin_headers,
                expected=200,
            )

    async def test_update_system_setting_by_key(self, client, setup):
        create_r = await client.post(
            "/api/v1/settings/system",
            json={
                "key": f"upd_setting_{uid()}",
                "value": "original",
                "description": "Update setting",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            key = create_r.json()["data"]["key"]
            await call(
                client,
                "settings",
                "PUT",
                f"/api/v1/settings/system/{key}",
                headers=setup.admin_headers,
                json={
                    "value": "updated",
                },
                expected=200,
            )

    async def test_delete_system_setting(self, client, setup):
        create_r = await client.post(
            "/api/v1/settings/system",
            json={
                "key": f"del_setting_{uid()}",
                "value": "to_delete",
                "description": "Delete setting",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            setting_id = create_r.json()["data"]["id"]
            await call(
                client,
                "settings",
                "DELETE",
                f"/api/v1/settings/system/{setting_id}",
                headers=setup.admin_headers,
                expected=200,
            )

    # ── Business Rules ───────────────────────────────────────────────────

    async def test_list_business_rules(self, client, setup):
        await call(
            client,
            "settings",
            "GET",
            "/api/v1/settings/business-rules",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_create_business_rule(self, client, setup):
        await call(
            client,
            "settings",
            "POST",
            "/api/v1/settings/business-rules",
            headers=setup.admin_headers,
            json={
                "rule_key": f"rule_{uid()}",
                "rule_value": "true",
                "description": "Test rule",
            },
            expected=201,
        )

    async def test_get_business_rule(self, client, setup):
        create_r = await client.post(
            "/api/v1/settings/business-rules",
            json={
                "rule_key": f"get_rule_{uid()}",
                "rule_value": "100",
                "description": "Get rule",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            rule_key = create_r.json()["data"]["rule_key"]
            await call(
                client,
                "settings",
                "GET",
                f"/api/v1/settings/business-rules/{rule_key}",
                headers=setup.admin_headers,
                expected=200,
            )

    async def test_update_business_rule(self, client, setup):
        create_r = await client.post(
            "/api/v1/settings/business-rules",
            json={
                "rule_key": f"upd_rule_{uid()}",
                "rule_value": "original",
                "description": "Update rule",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            rule_key = create_r.json()["data"]["rule_key"]
            await call(
                client,
                "settings",
                "PUT",
                f"/api/v1/settings/business-rules/{rule_key}",
                headers=setup.admin_headers,
                json={
                    "rule_value": "updated",
                },
                expected=200,
            )

    async def test_delete_business_rule(self, client, setup):
        create_r = await client.post(
            "/api/v1/settings/business-rules",
            json={
                "rule_key": f"del_rule_{uid()}",
                "rule_value": "to_delete",
                "description": "Delete rule",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            rule_id = create_r.json()["data"]["id"]
            await call(
                client,
                "settings",
                "DELETE",
                f"/api/v1/settings/business-rules/{rule_id}",
                headers=setup.admin_headers,
                expected=200,
            )
