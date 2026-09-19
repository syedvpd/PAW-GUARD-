"""GAP-0 (PRR 2.1): Rescue Centre Admin keeps its admin-tier features without the
system:admin wildcard, and loses Super Administrator and out-of-role writes."""

import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tests.auth_helpers import register_and_auth

from pawguard.modules.auth.models import Role
from pawguard.modules.auth.rbac import is_admin_tier
from pawguard.modules.auth.service import AuthService

pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, db_session: AsyncSession, role: str) -> dict:
    return await register_and_auth(
        client, db_session, email=f"gap0_{uuid.uuid4().hex[:8]}@example.com", role=role
    )


async def test_rescue_centre_admin_role_has_no_system_admin(db_session: AsyncSession):
    role = (
        await db_session.execute(
            select(Role)
            .options(selectinload(Role.permissions))
            .where(Role.name == "rescue_centre_admin")
        )
    ).scalar_one()
    codes = {p.code for p in role.permissions}
    assert "system:admin" not in codes
    assert {"inventory:create", "notification:view", "dog:read", "lost_found:read"} <= codes


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/users",
        "/api/v1/admin/roles",
        "/api/v1/admin/permissions",
        "/api/v1/admin/audit-logs",
        "/api/v1/admin/dashboard/summary",
        "/api/v1/admin/dashboard/kpis",
        "/api/v1/admin/dashboard/lost-found-stats",
        "/api/v1/admin/notifications/approvals",
        "/api/v1/settings/system",
        "/api/v1/settings/business-rules",
        "/api/v1/portal/admin/urgent-alerts",
        "/api/v1/rescue",
        "/api/v1/inventory/items",
    ],
)
async def test_rescue_centre_admin_keeps_admin_tier_reads(
    client: AsyncClient, db_session: AsyncSession, path: str
):
    headers = await _auth(client, db_session, "rescue_centre_admin")
    resp = await client.get(path, headers=headers)
    assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text[:200]}"


async def test_rescue_centre_admin_can_still_provision_staff(
    client: AsyncClient, db_session: AsyncSession
):
    headers = await _auth(client, db_session, "rescue_centre_admin")
    resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": f"gap0_staff_{uuid.uuid4().hex[:8]}@example.com",
            "password": "StrongP@ss99",
            "full_name": "Kennel Hand",
            "role_names": ["shelter_manager"],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    resp = await client.put(
        f"/api/v1/admin/users/{resp.json()['data']['id']}",
        json={"phone": "9876543210"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/v1/admin/roles", {"name": "gap0_custom", "permission_codes": []}),
        ("get", "/api/v1/portal/admin/faq", None),
        ("post", "/api/v1/notifications/broadcast", {"title": "x", "message": "y"}),
        ("post", "/api/v1/medical/exams", {}),
        ("post", "/api/v1/finance/accounts", {}),
    ],
)
async def test_rescue_centre_admin_loses_wildcard_only_access(
    client: AsyncClient, db_session: AsyncSession, method: str, path: str, body: dict | None
):
    headers = await _auth(client, db_session, "rescue_centre_admin")
    kwargs = {"headers": headers}
    if body is not None:
        kwargs["json"] = body
    resp = await getattr(client, method)(path, **kwargs)
    assert resp.status_code == 403, f"{method} {path}: {resp.status_code} {resp.text[:200]}"


async def test_super_admin_unaffected(client: AsyncClient, db_session: AsyncSession):
    headers = await _auth(client, db_session, "super_admin")
    for path in ("/api/v1/portal/admin/faq", "/api/v1/admin/users", "/api/v1/settings/system"):
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200, f"{path}: {resp.status_code}"


async def test_custom_role_cannot_carry_system_admin(client: AsyncClient, db_session: AsyncSession):
    headers = await _auth(client, db_session, "super_admin")
    resp = await client.post(
        "/api/v1/admin/roles",
        json={"name": f"gap0_{uuid.uuid4().hex[:6]}", "permission_codes": ["system:admin"]},
        headers=headers,
    )
    assert resp.status_code == 403, resp.text


def _user(*role_names: str) -> SimpleNamespace:
    return SimpleNamespace(roles=[SimpleNamespace(name=n, permissions=[]) for n in role_names])


def test_admin_tier_and_mandatory_mfa_follow_role_not_wildcard():
    assert is_admin_tier(_user("rescue_centre_admin"))
    assert is_admin_tier(_user("super_admin"))
    assert not is_admin_tier(_user("inventory_manager"))
    assert AuthService._is_admin(_user("rescue_centre_admin"))
    assert not AuthService._is_admin(_user("rescue_coordinator"))


async def test_bulk_delete_is_scoped_to_own_notifications(
    client: AsyncClient, db_session: AsyncSession
):
    from pawguard.modules.notifications.models import Notification

    rca = await _auth(client, db_session, "rescue_centre_admin")
    other = await _auth(client, db_session, "shelter_manager")
    rca_id = uuid.UUID((await client.get("/api/v1/auth/me", headers=rca)).json()["data"]["id"])
    other_id = uuid.UUID((await client.get("/api/v1/auth/me", headers=other)).json()["data"]["id"])
    mine = Notification(user_id=rca_id, title="mine", body="m")
    theirs = Notification(user_id=other_id, title="theirs", body="t")
    db_session.add_all([mine, theirs])
    await db_session.commit()

    resp = await client.post(
        "/api/v1/notifications/bulk/delete",
        json={"ids": [str(mine.id), str(theirs.id)]},
        headers=rca,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["deleted_count"] == 1
