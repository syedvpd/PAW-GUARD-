"""Regression tests for Cycle-1 S4 (volunteer/foster PII scoping).

Previously:
- GET /volunteers (full roster w/ emergency contacts + medical conditions) was
  gated only by `volunteer:read`, which the self-service `volunteer` role held.
- GET /fosters (full roster) was gated only by `foster:read`, which the
  self-service `foster_family` role held.
- GET /fosters/placements/{id}/progress and /supplies had no ownership check,
  so any foster family could read any other family's progress logs.

Now:
- Roster endpoints require `volunteer:update` / `foster:update` (staff only).
- Placement progress/supplies are owner-or-`foster:update`.
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.dog.models import DogProfile
from pawguard.modules.foster.models import FosterPlacement, FosterProfile, FosterProgressLog


def _make_role(db_session: AsyncSession, name_prefix: str, perm_code_suffix: str) -> Role:
    perm = Permission(
        code=f"test_{perm_code_suffix}_{uuid.uuid4().hex[:8]}",
        description=f"test {perm_code_suffix}",
    )
    db_session.add(perm)
    return Role(
        id=uuid.uuid4(),
        name=f"{name_prefix}_{uuid.uuid4().hex[:8]}",
        description="Synthetic self-service role for scoping regression.",
        is_system=False,
        permissions=[perm],
    )


@pytest.mark.asyncio
class TestVolunteerFosterScoping:
    @pytest_asyncio.fixture
    async def volunteer_role(self, db_session: AsyncSession) -> Role:
        """A volunteer-equivalent role WITHOUT staff-level volunteer:update."""
        role = _make_role(db_session, "test_volunteer", "vol")
        db_session.add(role)
        await db_session.flush()
        return role

    @pytest_asyncio.fixture
    async def foster_role(self, db_session: AsyncSession) -> Role:
        """A foster-family-equivalent role WITHOUT staff-level foster:update."""
        role = _make_role(db_session, "test_foster", "fos")
        db_session.add(role)
        await db_session.flush()
        return role

    async def _register_and_auth(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        email: str,
        role: Role,
    ) -> dict:
        payload = {
            "email": email,
            "password": "StrongP@ss99",
            "full_name": "Scoping Test",
            "phone": "+1234567890",
        }
        await client.post("/api/v1/auth/register", json=payload)
        user = (
            await db_session.execute(
                select(User).options(selectinload(User.roles)).where(User.email == email)
            )
        ).scalar_one()
        user.roles.append(role)
        user.is_verified = True
        await db_session.commit()
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "StrongP@ss99"},
        )
        token = resp.json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    async def _make_staff_headers(
        self, client: AsyncClient, db_session: AsyncSession, email: str
    ) -> dict:
        payload = {
            "email": email,
            "password": "StrongP@ss99",
            "full_name": "Staff",
            "phone": "+1234567890",
        }
        await client.post("/api/v1/auth/register", json=payload)
        staff = (
            await db_session.execute(
                select(User)
                .options(selectinload(User.roles))
                .where(User.email == payload["email"])
            )
        ).scalar_one()
        admin_role = (
            await db_session.execute(select(Role).where(Role.name == "super_admin"))
        ).scalar_one()
        staff.roles.append(admin_role)
        staff.is_verified = True
        await db_session.commit()
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        return {"Authorization": f"Bearer {login_resp.json()['data']['access_token']}"}

    async def _create_owned_placement_with_log(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_email: str,
    ) -> uuid.UUID:
        owner = (
            await db_session.execute(
                select(User).options(selectinload(User.roles)).where(User.email == owner_email)
            )
        ).scalar_one()
        profile = FosterProfile(user_id=owner.id, preferences="Puppies", max_capacity=1)
        db_session.add(profile)
        await db_session.flush()
        dog = DogProfile(
            registration_number=f"FST-{uuid.uuid4().hex[:8].upper()}",
            name="Foster Pup",
            breed="indie_mix",
            gender="male",
        )
        db_session.add(dog)
        await db_session.flush()
        placement = FosterPlacement(
            foster_id=profile.id,
            dog_id=dog.id,
            placed_at=datetime.now(UTC),
            is_active=True,
        )
        db_session.add(placement)
        await db_session.flush()
        log = FosterProgressLog(
            placement_id=placement.id,
            tracked_by_id=owner.id,
            behavior_notes="Very playful today.",
            logged_at=datetime.now(UTC),
        )
        db_session.add(log)
        await db_session.commit()
        return placement.id

    async def test_self_service_volunteer_cannot_list_roster(
        self, client: AsyncClient, db_session: AsyncSession, volunteer_role: Role
    ) -> None:
        headers = await self._register_and_auth(
            client, db_session, "volroster@scoping.test.com", volunteer_role
        )
        resp = await client.get("/api/v1/volunteers", headers=headers)
        assert resp.status_code == 403

    async def test_staff_can_list_volunteer_roster(
        self, client: AsyncClient, db_session: AsyncSession, volunteer_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "volroster2@scoping.test.com", volunteer_role
        )
        headers = await self._make_staff_headers(
            client, db_session, "staffvolroster2@scoping.test.com"
        )
        resp = await client.get("/api/v1/volunteers", headers=headers)
        assert resp.status_code == 200

    async def test_self_service_foster_cannot_list_roster(
        self, client: AsyncClient, db_session: AsyncSession, foster_role: Role
    ) -> None:
        headers = await self._register_and_auth(
            client, db_session, "fosroster@scoping.test.com", foster_role
        )
        resp = await client.get("/api/v1/fosters", headers=headers)
        assert resp.status_code == 403

    async def test_non_owner_foster_cannot_read_placement_progress(
        self, client: AsyncClient, db_session: AsyncSession, foster_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "ownerfos@scoping.test.com", foster_role
        )
        placement_id = await self._create_owned_placement_with_log(
            client, db_session, "ownerfos@scoping.test.com"
        )
        other_headers = await self._register_and_auth(
            client, db_session, "otherfos@scoping.test.com", foster_role
        )
        resp = await client.get(
            f"/api/v1/fosters/placements/{placement_id}/progress", headers=other_headers
        )
        assert resp.status_code == 403

    async def test_owner_can_read_own_placement_progress(
        self, client: AsyncClient, db_session: AsyncSession, foster_role: Role
    ) -> None:
        headers = await self._register_and_auth(
            client, db_session, "ownerfos2@scoping.test.com", foster_role
        )
        placement_id = await self._create_owned_placement_with_log(
            client, db_session, "ownerfos2@scoping.test.com"
        )
        resp = await client.get(
            f"/api/v1/fosters/placements/{placement_id}/progress", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"][0]["behavior_notes"] == "Very playful today."

    async def test_staff_can_read_any_placement_progress(
        self, client: AsyncClient, db_session: AsyncSession, foster_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "ownerfos3@scoping.test.com", foster_role
        )
        placement_id = await self._create_owned_placement_with_log(
            client, db_session, "ownerfos3@scoping.test.com"
        )
        headers = await self._make_staff_headers(
            client, db_session, "stafffos3@scoping.test.com"
        )
        resp = await client.get(
            f"/api/v1/fosters/placements/{placement_id}/progress", headers=headers
        )
        assert resp.status_code == 200

    async def test_non_owner_foster_cannot_read_supplies(
        self, client: AsyncClient, db_session: AsyncSession, foster_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "ownersup@scoping.test.com", foster_role
        )
        placement_id = await self._create_owned_placement_with_log(
            client, db_session, "ownersup@scoping.test.com"
        )
        other_headers = await self._register_and_auth(
            client, db_session, "othersup@scoping.test.com", foster_role
        )
        resp = await client.get(
            f"/api/v1/fosters/placements/{placement_id}/supplies", headers=other_headers
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestVolunteerRosterSeedNoSelfServiceAccess:
    """The self-service volunteer/foster roles must not hold the roster
    permissions, so a seed drift cannot silently re-open the roster."""

    async def test_volunteer_role_has_no_update_permission(self, db_session: AsyncSession) -> None:
        from scripts.seed_roles_and_permissions import ROLE_DEFINITIONS

        definitions = {name: perms for name, _, _, perms in ROLE_DEFINITIONS}
        assert "volunteer:update" not in definitions["volunteer"]

    async def test_foster_family_role_has_no_update_permission(
        self, db_session: AsyncSession
    ) -> None:
        from scripts.seed_roles_and_permissions import ROLE_DEFINITIONS

        definitions = {name: perms for name, _, _, perms in ROLE_DEFINITIONS}
        assert "foster:update" not in definitions["foster_family"]

    async def test_seeded_volunteer_role_holds_roster_read_only(
        self, db_session: AsyncSession
    ) -> None:
        role = (
            await db_session.execute(
                select(Role)
                .options(selectinload(Role.permissions))
                .where(Role.name == "volunteer")
            )
        ).scalar_one_or_none()
        if role is not None:
            assert "volunteer:update" not in {p.code for p in role.permissions}
            assert "volunteer:read" in {p.code for p in role.permissions}

    async def test_seeded_foster_family_role_lacks_update(
        self, db_session: AsyncSession
    ) -> None:
        role = (
            await db_session.execute(
                select(Role)
                .options(selectinload(Role.permissions))
                .where(Role.name == "foster_family")
            )
        ).scalar_one_or_none()
        if role is not None:
            assert "foster:update" not in {p.code for p in role.permissions}
