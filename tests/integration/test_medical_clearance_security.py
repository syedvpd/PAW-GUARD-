"""Security regression tests for medical clearance authorization enforcement.

Ensures that non-veterinarian roles (such as shelter_manager, foster_family,
or general users) calling POST /api/v1/medical/clearance/{dog_id} are strictly
rejected by the backend with 403 Forbidden.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.dog.models import DogProfile


@pytest.mark.asyncio
class TestMedicalClearanceAccessControl:
    """Only veterinarians (or super admins) may issue medical clearances."""

    @pytest_asyncio.fixture
    async def shelter_role(self, db_session: AsyncSession) -> Role:
        """A role with medical:clearance permission granted directly, but NOT veterinarian role."""
        perm_stmt = select(Permission).where(Permission.code == "medical:clearance")
        perm = (await db_session.execute(perm_stmt)).scalar_one_or_none()
        if perm is None:
            perm = Permission(code="medical:clearance", description="Medical clearance permission")
            db_session.add(perm)
            await db_session.flush()

        role = Role(
            id=uuid.uuid4(),
            name=f"non_vet_role_{uuid.uuid4().hex[:8]}",
            description="Non-vet role holding permission for security test",
            is_system=False,
            permissions=[perm],
        )
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
            "full_name": "Security Test User",
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

    async def test_non_veterinarian_is_rejected_by_backend(
        self, client: AsyncClient, db_session: AsyncSession, shelter_role: Role
    ) -> None:
        """Calling medical clearance with a non-veterinarian role MUST be rejected by the backend."""
        email = f"nonvet_{uuid.uuid4().hex[:8]}@test.com"
        headers = await self._register_and_auth(client, db_session, email, shelter_role)

        dog = DogProfile(
            registration_number=f"REG-{uuid.uuid4().hex[:8].upper()}",
            name=f"TestDog_{uuid.uuid4().hex[:6]}",
            breed="Mixed",
            gender="male",
            estimated_age="2 years",
            weight=12.5,
            color="Brown",
            temperament="Friendly",
        )
        db_session.add(dog)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/medical/clearance/{dog.id}",
            json={"clearance_type": "quarantine", "notes": "Unauthorized attempt"},
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] in ("INSUFFICIENT_PERMISSIONS", "FORBIDDEN")
