"""Integration tests for full auth flows against the real Supabase test database.

Every test runs inside a transaction that is rolled back on teardown, so no data
persists between tests. Redis and ARQ are replaced with in-memory fakes.
"""


import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.constants import CLIENT_TYPE_HEADER, ClientType
from pawguard.modules.auth.models import EmailVerificationToken, User

REGISTER_PAYLOAD = {
    "email": "testuser@example.com",
    "password": "StrongP@ss99",
    "full_name": "Test User",
    "phone": "+1234567890",
}

LOGIN_PAYLOAD = {
    "email": "testuser@example.com",
    "password": "StrongP@ss99",
}


@pytest.mark.asyncio
class TestRegistration:
    async def test_register_success(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["email"] == REGISTER_PAYLOAD["email"]
        assert data["full_name"] == REGISTER_PAYLOAD["full_name"]
        assert data["is_verified"] is False

    async def test_register_duplicate_email(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        resp = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"

    async def test_register_weak_password(self, client: AsyncClient) -> None:
        payload = {**REGISTER_PAYLOAD, "password": "weak"}
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 422

    async def test_creates_email_verification_token(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        user = (
            await db_session.execute(
                select(User).where(User.email == REGISTER_PAYLOAD["email"])
            )
        ).scalar_one_or_none()
        assert user is not None

        tokens = (
            await db_session.execute(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.user_id == user.id
                )
            )
        ).scalars().all()
        assert len(tokens) == 1
        assert tokens[0].used_at is None


@pytest.mark.asyncio
class TestLogin:
    async def test_login_success(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]
        assert body["data"]["user"]["email"] == REGISTER_PAYLOAD["email"]

    async def test_login_wrong_password(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER_PAYLOAD["email"], "password": "WrongP@ss123"},
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "SomeP@ss123"},
        )
        assert resp.status_code == 401

    async def test_login_web_client_gets_cookies(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        resp = await client.post(
            "/api/v1/auth/login",
            json=LOGIN_PAYLOAD,
            headers={CLIENT_TYPE_HEADER: ClientType.WEB.value},
        )
        assert resp.status_code == 200
        assert "pg_access_token" in resp.cookies
        assert "pg_refresh_token" in resp.cookies
        body = resp.json()
        # Web clients do not get tokens in the body
        assert body["data"]["refresh_token"] is None

    async def test_web_logout_clears_cookies(self, client: AsyncClient) -> None:
        """L-3: logout must clear the cookies it set.

        Set and clear must use the same cookie domain attribute, otherwise the
        browser would ignore the deletion (host-only cookie vs domain-scoped
        delete) and the session cookie would linger after logout.
        """
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json=LOGIN_PAYLOAD,
            headers={CLIENT_TYPE_HEADER: ClientType.WEB.value},
        )
        assert login_resp.status_code == 200
        assert "pg_access_token" in client.cookies

        logout_resp = await client.post("/api/v1/auth/logout")
        assert logout_resp.status_code == 200

        # The deletion Set-Cookie headers must be present (empty value + expiry).
        set_cookies = logout_resp.headers.get_list("set-cookie")
        assert any("pg_access_token=" in c and "max-age=0" in c.lower() for c in set_cookies)
        assert any("pg_refresh_token=" in c and "max-age=0" in c.lower() for c in set_cookies)
        assert "pg_access_token" not in client.cookies


@pytest.mark.asyncio
class TestRefresh:
    async def test_refresh_success(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        login_resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        refresh_token = login_resp.json()["data"]["refresh_token"]

        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["access_token"] is not None
        assert body["data"]["refresh_token"] is not None

    async def test_refresh_with_revoked_token(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        login_resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        refresh_token = login_resp.json()["data"]["refresh_token"]

        # Use it once (consumes it via rotation)
        await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        # Reuse the same token = breach detection
        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "REFRESH_TOKEN_REUSE_DETECTED"

    async def test_refresh_invalid_token(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "totally-invalid"}
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestAuthenticatedEndpoints:
    async def test_get_me(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        login_resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        access_token = login_resp.json()["data"]["access_token"]

        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["email"] == REGISTER_PAYLOAD["email"]

    async def test_get_me_without_token(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_email_verify_request_is_rate_limited(self, client: AsyncClient) -> None:
        """L-4: /email/verify/request must be throttled like its confirm sibling.

        An authenticated caller can otherwise spam verification emails at will.
        The limiter allows 10 requests per 300s window; the 11th is 429.
        """
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        login_resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        access_token = login_resp.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        for _ in range(10):
            resp = await client.post("/api/v1/auth/email/verify/request", headers=headers)
            assert resp.status_code == 200

        throttled = await client.post("/api/v1/auth/email/verify/request", headers=headers)
        assert throttled.status_code == 429

    async def test_logout(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        login_resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        access_token = login_resp.json()["data"]["access_token"]
        refresh_token = login_resp.json()["data"]["refresh_token"]

        logout_resp = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_resp.status_code == 200

        # Refresh with the old token should now fail (session revoked)
        refresh_resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert refresh_resp.status_code == 401

        # The access token is dead immediately too: get_current_user validates
        # the backing session, so logout revokes access now, not at expiry.
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_resp.status_code == 401

    async def test_list_sessions(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        login_resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        access_token = login_resp.json()["data"]["access_token"]

        resp = await client.get(
            "/api/v1/auth/sessions",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200
        sessions = resp.json()["data"]
        assert len(sessions) >= 1


@pytest.mark.asyncio
class TestPasswordReset:
    async def test_request_password_reset(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        resp = await client.post(
            "/api/v1/auth/password/reset/request",
            json={"email": REGISTER_PAYLOAD["email"]},
        )
        assert resp.status_code == 200

    async def test_request_password_reset_nonexistent_email(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/v1/auth/password/reset/request",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 200  # No enumeration

    async def test_confirm_password_reset(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

        await client.post(
            "/api/v1/auth/password/reset/request",
            json={"email": REGISTER_PAYLOAD["email"]},
        )

        user = (
            await db_session.execute(
                select(User).where(User.email == REGISTER_PAYLOAD["email"])
            )
        ).scalar_one_or_none()
        assert user is not None

        from pawguard.modules.auth.models import PasswordResetToken

        token_record = (
            await db_session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == user.id,
                    PasswordResetToken.used_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        assert token_record is not None

    async def test_change_password(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        login_resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
        access_token = login_resp.json()["data"]["access_token"]

        resp = await client.post(
            "/api/v1/auth/password/change",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "current_password": REGISTER_PAYLOAD["password"],
                "new_password": "NewStrongP@ss99",
            },
        )
        assert resp.status_code == 200

        # Login with new password
        new_login = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER_PAYLOAD["email"], "password": "NewStrongP@ss99"},
        )
        assert new_login.status_code == 200
