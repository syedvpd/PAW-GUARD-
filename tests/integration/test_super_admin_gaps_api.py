"""Super Administrator PRR 2.1 / 6.1 gaps: account security actions, super-admin
guards, paged user search, audit filters, backups, governance summary, MFA bootstrap."""

import uuid

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth

from pawguard.core.config import get_settings
from pawguard.modules.admin.backup import read_backup

pytestmark = pytest.mark.asyncio


def _email(tag: str) -> str:
    return f"sa_{tag}_{uuid.uuid4().hex[:8]}@example.com"


async def _admin(client: AsyncClient, db_session: AsyncSession, role: str = "super_admin") -> dict:
    return await register_and_auth(client, db_session, email=_email(role[:6]), role=role)


async def _me(client: AsyncClient, headers: dict) -> dict:
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _staff(client: AsyncClient, headers: dict, role: str = "shelter_manager") -> dict:
    email = _email("staff")
    resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": email,
            "password": "StrongP@ss99",
            "full_name": "Staff Member",
            "role_names": [role],
            "can_drive": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_user_list_pages_only_with_per_page(client: AsyncClient, db_session: AsyncSession):
    headers = await _admin(client, db_session)
    await _staff(client, headers)
    await _staff(client, headers)

    everyone = await client.get(
        "/api/v1/admin/users", params={"page": 1, "page_size": 1}, headers=headers
    )
    assert everyone.status_code == 200, everyone.text
    assert len(everyone.json()["data"]) >= 3

    paged = await client.get(
        "/api/v1/admin/users", params={"page": 1, "per_page": 1}, headers=headers
    )
    assert len(paged.json()["data"]) == 1
    assert int(paged.headers["X-Total-Count"]) >= 3

    by_role = await client.get(
        "/api/v1/admin/users", params={"role": "shelter_manager"}, headers=headers
    )
    assert all("shelter_manager" in u["roles"] for u in by_role.json()["data"])


async def test_deactivating_user_revokes_their_sessions(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _admin(client, db_session)
    target = await _admin(client, db_session, role="shelter_manager")
    target_id = (await _me(client, target))["id"]

    sessions = await client.get(f"/api/v1/admin/users/{target_id}/sessions", headers=admin)
    assert sessions.status_code == 200, sessions.text
    assert sessions.json()["data"]

    resp = await client.put(
        f"/api/v1/admin/users/{target_id}", json={"is_active": False}, headers=admin
    )
    assert resp.status_code == 200, resp.text
    assert (await client.get("/api/v1/auth/me", headers=target)).status_code in (401, 403)

    after = await client.get(f"/api/v1/admin/users/{target_id}/sessions", headers=admin)
    assert after.json()["data"] == []


async def test_revoke_sessions_signs_user_out(client: AsyncClient, db_session: AsyncSession):
    admin = await _admin(client, db_session)
    target = await _admin(client, db_session, role="shelter_manager")
    target_id = (await _me(client, target))["id"]

    resp = await client.delete(f"/api/v1/admin/users/{target_id}/sessions", headers=admin)
    assert resp.status_code == 200, resp.text
    assert (await client.get("/api/v1/auth/me", headers=target)).status_code == 401


async def test_super_admin_cannot_remove_own_access(client: AsyncClient, db_session: AsyncSession):
    admin = await _admin(client, db_session)
    me = await _me(client, admin)

    for payload in ({"is_active": False}, {"role_names": ["shelter_manager"]}):
        resp = await client.put(f"/api/v1/admin/users/{me['id']}", json=payload, headers=admin)
        assert resp.status_code == 403, resp.text
    resp = await client.delete(f"/api/v1/admin/users/{me['id']}", headers=admin)
    assert resp.status_code == 403, resp.text


async def test_rescue_centre_admin_cannot_touch_super_admins(
    client: AsyncClient, db_session: AsyncSession
):
    super_admin = await _admin(client, db_session)
    rca = await _admin(client, db_session, role="rescue_centre_admin")
    sa_id = (await _me(client, super_admin))["id"]

    resp = await client.put(f"/api/v1/admin/users/{sa_id}", json={"is_active": False}, headers=rca)
    assert resp.status_code == 403, resp.text
    resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": _email("x"),
            "password": "StrongP@ss99",
            "full_name": "Escalation",
            "role_names": ["super_admin"],
        },
        headers=rca,
    )
    assert resp.status_code == 403, resp.text
    for method, path in (
        ("post", f"/api/v1/admin/users/{sa_id}/mfa/reset"),
        ("delete", f"/api/v1/admin/users/{sa_id}/sessions"),
        ("post", "/api/v1/admin/backups"),
        ("get", "/api/v1/admin/dashboard/governance"),
    ):
        resp = await getattr(client, method)(path, headers=rca)
        assert resp.status_code == 403, f"{method} {path}: {resp.status_code}"


async def test_system_admin_cannot_be_granted_directly(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _admin(client, db_session)
    staff = await _staff(client, admin)
    resp = await client.post(
        f"/api/v1/admin/users/{staff['id']}/permissions",
        json={"permission_codes": ["system:admin"]},
        headers=admin,
    )
    assert resp.status_code == 403, resp.text


async def test_mfa_reset_then_bootstrap_enrollment_logs_in(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "mfa_mandatory_for_admins", True)
    monkeypatch.setattr(settings, "mfa_bypass_for_dev", False)
    admin = await _admin(client, db_session)
    other_email = _email("other")
    other = await register_and_auth(client, db_session, email=other_email, role="super_admin")
    other_id = (await _me(client, other))["id"]

    resp = await client.post(f"/api/v1/admin/users/{other_id}/mfa/reset", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["mfa_enabled"] is False

    login = await client.post(
        "/api/v1/auth/login", json={"email": other_email, "password": "StrongP@ss99"}
    )
    pre_auth = login.json()["data"]["pre_auth_token"]
    enroll = await client.post(
        "/api/v1/auth/mfa/enroll/bootstrap", json={"pre_auth_token": pre_auth}
    )
    assert enroll.status_code == 200, enroll.text
    code = pyotp.TOTP(enroll.json()["data"]["secret"]).now()

    confirm = await client.post(
        "/api/v1/auth/mfa/enroll/bootstrap/confirm",
        json={"pre_auth_token": pre_auth, "code": code},
    )
    assert confirm.status_code == 200, confirm.text
    verify = await client.post(
        "/api/v1/auth/mfa/verify", json={"pre_auth_token": pre_auth, "code": code}
    )
    assert verify.status_code == 200, verify.text
    token = verify.json()["data"]["access_token"]
    me = await _me(client, {"Authorization": f"Bearer {token}"})
    assert me["mfa_enabled"] is True

    again = await client.post(
        "/api/v1/auth/mfa/enroll/bootstrap", json={"pre_auth_token": pre_auth}
    )
    assert again.status_code >= 400


async def test_audit_module_and_date_filters(client: AsyncClient, db_session: AsyncSession):
    admin = await _admin(client, db_session)
    await _staff(client, admin)

    resp = await client.get("/api/v1/admin/audit-logs", params={"module": "admin"}, headers=admin)
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    assert rows and all(r["event_type"].startswith("admin_") for r in rows)
    created = next(r for r in rows if r["event_type"] == "admin_user_created")
    assert created["ip_address"] is not None

    future = await client.get(
        "/api/v1/admin/audit-logs", params={"date_from": "2999-01-01T00:00:00Z"}, headers=admin
    )
    assert future.json()["data"] == []


async def test_user_update_audits_before_and_after(client: AsyncClient, db_session: AsyncSession):
    admin = await _admin(client, db_session)
    staff = await _staff(client, admin)
    resp = await client.put(
        f"/api/v1/admin/users/{staff['id']}", json={"can_drive": False}, headers=admin
    )
    assert resp.status_code == 200, resp.text

    logs = await client.get(
        "/api/v1/admin/audit-logs", params={"event_type": "admin_user_updated"}, headers=admin
    )
    entry = next(
        r for r in logs.json()["data"] if (r["event_metadata"] or {}).get("user_id") == staff["id"]
    )
    assert entry["before_state"]["can_drive"] is True
    assert entry["after_state"]["can_drive"] is False


async def test_backup_download_history_and_governance(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _admin(client, db_session)

    resp = await client.post("/api/v1/admin/backups", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/gzip"
    document = read_backup(resp.content)
    assert document["tables"]["users"]
    assert "refresh_tokens" not in document["tables"]
    assert all("hashed_password" in u for u in document["tables"]["users"])

    history = await client.get("/api/v1/admin/backups", headers=admin)
    assert history.status_code == 200, history.text
    assert history.json()["data"][0]["size_bytes"] == len(resp.content)

    governance = await client.get("/api/v1/admin/dashboard/governance", headers=admin)
    assert governance.status_code == 200, governance.text
    data = governance.json()["data"]
    assert data["last_backup_at"] is not None
    assert data["users_by_role"].get("super_admin", 0) >= 1


async def test_session_policy_readable_by_any_staff(client: AsyncClient, db_session: AsyncSession):
    staff = await _admin(client, db_session, role="shelter_manager")
    resp = await client.get("/api/v1/settings/session-policy", headers=staff)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["idle_timeout_minutes"] == 15
