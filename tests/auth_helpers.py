"""Shared auth helpers for integration tests.

Since T6, admin accounts always hit the MFA challenge on login, and an admin
without an enrolled MFA device can never complete login. The helpers below
register a user, enroll + confirm MFA *before* promoting them to the requested
role, then log in again and pass the MFA challenge, returning Bearer headers
backed by a real access token.
"""

import pyotp
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Role, User

_DEFAULT_PASSWORD = "StrongP@ss99"


async def _fetch_user(db_session: AsyncSession, email: str) -> User:
    stmt = select(User).options(selectinload(User.roles)).where(User.email == email)
    return (await db_session.execute(stmt)).scalar_one()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def promote_and_auth(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    email: str,
    password: str = _DEFAULT_PASSWORD,
    role: str = "super_admin",
) -> dict:
    """Finish the T6 MFA flow for an already-registered user.

    Assumes the user was created via /api/v1/auth/register. Steps:
      1. log in as the pre-promotion (non-admin, no-MFA) user to get a token,
      2. enroll + confirm MFA so the account holds a valid device secret,
      3. promote the user to ``role``,
      4. log in again (now the MFA challenge applies) and verify the code.

    Returns Bearer headers issued after promotion, so role/permission claims
    in the token match the requested ``role``.
    """
    user = await _fetch_user(db_session, email)
    user.is_verified = True
    await db_session.commit()

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    body = login.json()["data"]
    if "access_token" not in body:
        raise AssertionError(
            f"Pre-promotion login should not require MFA: {login.status_code} {login.text}"
        )
    enroll_headers = _bearer(body["access_token"])
    enroll = await client.post("/api/v1/auth/mfa/enroll", headers=enroll_headers)
    if enroll.status_code != 200:
        raise AssertionError(f"MFA enroll failed: {enroll.status_code} {enroll.text}")
    secret = enroll.json()["data"]["secret"]

    confirm = await client.post(
        "/api/v1/auth/mfa/enroll/confirm",
        json={"code": pyotp.TOTP(secret).now()},
        headers=enroll_headers,
    )
    if confirm.status_code != 200:
        raise AssertionError(f"MFA confirm failed: {confirm.status_code} {confirm.text}")

    user = await _fetch_user(db_session, email)
    role_row = (await db_session.execute(select(Role).where(Role.name == role))).scalar_one()
    if role_row not in user.roles:
        user.roles.append(role_row)
    await db_session.commit()

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    body = login.json()["data"]
    if "access_token" in body:
        return _bearer(body["access_token"])

    verify = await client.post(
        "/api/v1/auth/mfa/verify",
        json={
            "pre_auth_token": body["pre_auth_token"],
            "code": pyotp.TOTP(secret).now(),
        },
    )
    if verify.status_code != 200:
        raise AssertionError(f"MFA verify failed: {verify.status_code} {verify.text}")
    return _bearer(verify.json()["data"]["access_token"])


async def register_and_auth(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    email: str,
    password: str = _DEFAULT_PASSWORD,
    full_name: str = "Integration Tester",
    phone: str = "+1234567890",
    role: str = "super_admin",
) -> dict:
    """Register a fresh user and return admin-grade Bearer headers.

    Equivalent to the per-file ``_auth`` helpers: register, promote to
    ``role``, and log in — completing the T6 mandatory-MFA flow.
    """
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "phone": phone,
        },
    )
    if resp.status_code != 201:
        raise AssertionError(f"Register failed: {resp.status_code} {resp.text}")
    return await promote_and_auth(client, db_session, email=email, password=password, role=role)
