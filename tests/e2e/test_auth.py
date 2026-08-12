"""E2E tests for AUTH module (22 endpoints)."""
import uuid
import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth, _DEFAULT_PASSWORD
from tests.e2e.helpers import call, uid
from tests.e2e.factories import TEST


@pytest.mark.asyncio
class TestAuthEndpoints:
    """All 22 auth endpoints."""

    async def test_register(self, client):
        r = await call(client, "auth", "POST", "/api/v1/auth/register", json={
            "email": f"reg_{uid()}@test.com", "password": _DEFAULT_PASSWORD,
            "full_name": "Test User", "phone": "+1234567890",
        }, expected=201)

    async def test_login(self, client):
        email = f"login_{uid()}@test.com"
        await client.post("/api/v1/auth/register", json={
            "email": email, "password": _DEFAULT_PASSWORD,
            "full_name": "Login Test", "phone": "+1234567890",
        })
        r = await call(client, "auth", "POST", "/api/v1/auth/login", json={
            "email": email, "password": _DEFAULT_PASSWORD,
        }, expected=200)

    async def test_mfa_verify_invalid(self, client):
        r = await call(client, "auth", "POST", "/api/v1/auth/mfa/verify", json={
            "pre_auth_token": "invalid", "code": "000000",
        }, expected=401)

    async def test_refresh_invalid(self, client):
        r = await call(client, "auth", "POST", "/api/v1/auth/refresh", json={
            "refresh_token": "invalid_token",
        }, expected=401)

    async def test_logout(self, client, setup):
        r = await call(client, "auth", "POST", "/api/v1/auth/logout",
                      headers=setup.admin_headers, expected=200)

    async def test_logout_all(self, client, setup):
        r = await call(client, "auth", "POST", "/api/v1/auth/logout-all",
                      headers=setup.admin_headers, expected=200)

    async def test_get_me(self, client, setup):
        r = await call(client, "auth", "GET", "/api/v1/auth/me",
                      headers=setup.admin_headers, expected=200)

    async def test_update_me(self, client, setup):
        r = await call(client, "auth", "PUT", "/api/v1/auth/me",
                      headers=setup.admin_headers, json={
                          "full_name": "Updated Name",
                      }, expected=200)

    async def test_list_sessions(self, client, setup):
        r = await call(client, "auth", "GET", "/api/v1/auth/sessions",
                      headers=setup.admin_headers, expected=200)

    async def test_revoke_session_not_found(self, client, setup):
        fake_sid = str(uuid.uuid4())
        r = await call(client, "auth", "DELETE", f"/api/v1/auth/sessions/{fake_sid}",
                      headers=setup.admin_headers, expected=404)

    async def test_change_password_wrong(self, client, setup):
        r = await call(client, "auth", "POST", "/api/v1/auth/password/change",
                      headers=setup.admin_headers, json={
                          "current_password": "wrong",
                          "new_password": "NewP@ss123!",
                      }, expected=401)

    async def test_password_reset_request(self, client):
        r = await call(client, "auth", "POST", "/api/v1/auth/password/reset/request",
                      json={"email": "nobody@test.com"}, expected=200)

    async def test_password_reset_confirm_invalid(self, client):
        r = await call(client, "auth", "POST", "/api/v1/auth/password/reset/confirm",
                      json={"token": "invalid", "new_password": "NewP@ss123!"}, expected=400)

    async def test_email_verify_confirm_invalid(self, client):
        r = await call(client, "auth", "POST", "/api/v1/auth/email/verify/confirm",
                      json={"token": "invalid"}, expected=400)

    async def test_email_verify_request(self, client, setup):
        r = await call(client, "auth", "POST", "/api/v1/auth/email/verify/request",
                      headers=setup.admin_headers, expected=200)

    async def test_mfa_enroll(self, client, setup):
        r = await call(client, "auth", "POST", "/api/v1/auth/mfa/enroll",
                      headers=setup.admin_headers, expected=200)

    async def test_mfa_enroll_confirm(self, client, setup):
        r = await client.post("/api/v1/auth/mfa/enroll", headers=setup.admin_headers)
        if r.status_code == 200:
            secret = r.json()["data"]["secret"]
            code = pyotp.TOTP(secret).now()
            r2 = await call(client, "auth", "POST", "/api/v1/auth/mfa/enroll/confirm",
                           headers=setup.admin_headers, json={"code": code}, expected=200)

    async def test_mfa_disable(self, client, setup):
        r = await call(client, "auth", "POST", "/api/v1/auth/mfa/disable",
                      headers=setup.admin_headers, json={
                          "password": _DEFAULT_PASSWORD,
                      }, expected=200)

    async def test_oauth_login_invalid(self, client):
        r = await call(client, "auth", "POST", "/api/v1/auth/oauth/login", json={
            "provider": "google", "provider_token": "fake",
        }, expected=401)

    async def test_oauth_accounts(self, client, setup):
        r = await call(client, "auth", "GET", "/api/v1/auth/oauth/accounts",
                      headers=setup.admin_headers, expected=200)

    async def test_oauth_link_invalid(self, client, setup):
        r = await call(client, "auth", "POST", "/api/v1/auth/oauth/link",
                      headers=setup.admin_headers, json={
                          "provider": "google", "provider_token": "fake",
                      }, expected=400)

    async def test_oauth_unlink_not_found(self, client, setup):
        fake_id = str(uuid.uuid4())
        r = await call(client, "auth", "DELETE", f"/api/v1/auth/oauth/accounts/{fake_id}",
                      headers=setup.admin_headers, expected=404)
