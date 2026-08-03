"""Regression tests for the missing ownership check on GET /adoptions/{app_id}/scores
(Cycle 1, S3).

The endpoint returns internal vetting scores and the adoption recommendation and
was previously open to any authenticated user. It is now owner-or-permission:
the applicant (`adopter_id`) or staff with `adoption:read`.
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tests.auth_helpers import register_and_auth

from pawguard.modules.adoption.models import AdoptionApplication, AdoptionScore
from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.dog.models import DogProfile


@pytest.mark.asyncio
class TestAdoptionScoresAccessControl:
    """Only the applicant or adoption:read staff can read internal scores."""

    @pytest_asyncio.fixture
    async def adopter_role(self, db_session: AsyncSession) -> Role:
        """A public adopter-equivalent role WITHOUT staff-level adoption:read."""
        perm_code = f"test_scores_read_{uuid.uuid4().hex[:8]}"
        test_read = Permission(code=perm_code, description=perm_code)
        db_session.add(test_read)
        await db_session.flush()
        role = Role(
            id=uuid.uuid4(),
            name=f"test_adopter_{uuid.uuid4().hex[:8]}",
            description="Synthetic adopter role for scores IDOR regression.",
            is_system=False,
            permissions=[test_read],
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
            "full_name": "Scores Test",
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

    async def _create_owned_application_with_score(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_email: str,
    ) -> uuid.UUID:
        """Create a dog + adoption application + a vetting score owned by owner_email."""
        owner = (
            await db_session.execute(
                select(User).options(selectinload(User.roles)).where(User.email == owner_email)
            )
        ).scalar_one()

        dog = DogProfile(
            registration_number=f"SCR-{uuid.uuid4().hex[:8].upper()}",
            name="Score Pup",
            breed="indie_mix",
            gender="female",
        )
        db_session.add(dog)
        await db_session.flush()

        app = AdoptionApplication(
            dog_id=dog.id,
            adopter_id=owner.id,
            residential_status="owned",
            has_landlord_approval=True,
            has_yard_fence=True,
            household_members_count=2,
        )
        db_session.add(app)
        await db_session.flush()

        score = AdoptionScore(
            application_id=app.id,
            scored_by_id=owner.id,
            home_environment_score=8,
            pet_care_knowledge_score=9,
            financial_readiness_score=8,
            lifestyle_compatibility_score=9,
            overall_score=8.5,
            recommendation="approve",
            notes="Excellent fit.",
            scored_at=datetime.now(UTC),
        )
        db_session.add(score)
        await db_session.commit()
        return app.id

    async def test_owner_can_read_own_scores(
        self, client: AsyncClient, db_session: AsyncSession, adopter_role: Role
    ) -> None:
        headers = await self._register_and_auth(
            client, db_session, "ownerscores@scores.test.com", adopter_role
        )
        app_id = await self._create_owned_application_with_score(
            client, db_session, "ownerscores@scores.test.com"
        )
        resp = await client.get(f"/api/v1/adoptions/{app_id}/scores", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"][0]["recommendation"] == "approve"

    async def test_non_owner_cannot_read_scores(
        self, client: AsyncClient, db_session: AsyncSession, adopter_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "ownerscores2@scores.test.com", adopter_role
        )
        app_id = await self._create_owned_application_with_score(
            client, db_session, "ownerscores2@scores.test.com"
        )
        other_headers = await self._register_and_auth(
            client, db_session, "otherscores2@scores.test.com", adopter_role
        )
        resp = await client.get(f"/api/v1/adoptions/{app_id}/scores", headers=other_headers)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    async def test_staff_with_adoption_read_can_read_any_scores(
        self, client: AsyncClient, db_session: AsyncSession, adopter_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "ownerscores3@scores.test.com", adopter_role
        )
        app_id = await self._create_owned_application_with_score(
            client, db_session, "ownerscores3@scores.test.com"
        )

        staff_headers = await register_and_auth(
            client, db_session, email="staffscores3@scores.test.com"
        )

        resp = await client.get(f"/api/v1/adoptions/{app_id}/scores", headers=staff_headers)
        assert resp.status_code == 200
        assert resp.json()["data"][0]["recommendation"] == "approve"
