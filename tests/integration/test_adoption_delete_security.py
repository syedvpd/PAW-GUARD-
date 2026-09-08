"""Regression tests for the adoption delete endpoints' permission requirement.

Both DELETE /adoptions/{app_id} and POST /adoptions/bulk/delete previously
required only `adoption:process`, which Adoption Coordinator holds — meaning
a Coordinator could delete applications even though the workflow doc's RBAC
matrix (docs/workflow/08-adoption.md §16) reserves delete for Centre Admin
and Super Admin. They now require the already-seeded-but-unused
`adoption:delete` permission, which only those two roles hold.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.auth_helpers import register_and_auth

from pawguard.modules.adoption.models import AdoptionApplication
from pawguard.modules.dog.models import DogProfile


async def _create_application(db_session: AsyncSession, adopter_id: uuid.UUID) -> uuid.UUID:
    """adopter_id must reference a real user row (FK-constrained); who it is
    doesn't matter for these permission-only tests, so callers pass the
    already-registered staff user's own id."""
    dog = DogProfile(
        registration_number=f"DEL-{uuid.uuid4().hex[:8].upper()}",
        name="Delete Test Pup",
        breed="indie_mix",
        gender="male",
    )
    db_session.add(dog)
    await db_session.flush()

    app = AdoptionApplication(
        dog_id=dog.id,
        adopter_id=adopter_id,
        residential_status="owned",
        has_landlord_approval=True,
        has_yard_fence=True,
        household_members_count=2,
    )
    db_session.add(app)
    await db_session.commit()
    return app.id


async def _user_id(db_session: AsyncSession, email: str) -> uuid.UUID:
    from pawguard.modules.auth.models import User

    return (await db_session.execute(select(User.id).where(User.email == email))).scalar_one()


@pytest.mark.asyncio
class TestAdoptionDeletePermission:
    async def test_adoption_coordinator_cannot_delete_single_application(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        email = "coord_del1@adoption.test.com"
        headers = await register_and_auth(
            client, db_session, email=email, role="adoption_coordinator"
        )
        app_id = await _create_application(db_session, await _user_id(db_session, email))

        resp = await client.delete(f"/api/v1/adoptions/{app_id}", headers=headers)
        assert resp.status_code == 403

        check = (
            await db_session.execute(
                select(AdoptionApplication).where(AdoptionApplication.id == app_id)
            )
        ).scalar_one()
        assert check.deleted_at is None

    async def test_adoption_coordinator_cannot_bulk_delete(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        email = "coord_del2@adoption.test.com"
        headers = await register_and_auth(
            client, db_session, email=email, role="adoption_coordinator"
        )
        app_id = await _create_application(db_session, await _user_id(db_session, email))

        resp = await client.post(
            "/api/v1/adoptions/bulk/delete", json={"ids": [str(app_id)]}, headers=headers
        )
        assert resp.status_code == 403

    async def test_rescue_centre_admin_can_delete_single_application(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        email = "rcadmin_del1@adoption.test.com"
        headers = await register_and_auth(
            client, db_session, email=email, role="rescue_centre_admin"
        )
        app_id = await _create_application(db_session, await _user_id(db_session, email))

        resp = await client.delete(f"/api/v1/adoptions/{app_id}", headers=headers)
        assert resp.status_code == 200

        check = (
            await db_session.execute(
                select(AdoptionApplication).where(AdoptionApplication.id == app_id)
            )
        ).scalar_one()
        assert check.deleted_at is not None

    async def test_super_admin_can_bulk_delete(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        email = "superadmin_del1@adoption.test.com"
        headers = await register_and_auth(client, db_session, email=email, role="super_admin")
        app_id = await _create_application(db_session, await _user_id(db_session, email))

        resp = await client.post(
            "/api/v1/adoptions/bulk/delete", json={"ids": [str(app_id)]}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted_count"] == 1
