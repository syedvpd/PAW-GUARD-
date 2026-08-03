"""Regression tests for sponsorship IDOR / missing-auth findings (Cycle 1, S1/S2).

Previously:
- PATCH /donations/sponsorships/{id}/status had NO permission gate and NO
  ownership check: any authenticated user could pause/cancel another donor's
  sponsorship.
- GET /donations/sponsorships/{id} was completely unauthenticated, exposing
  donor ids, dog ids, monthly amounts and charge dates.

Both endpoints now enforce owner-or-permission:
- PATCH  -> owner, or `donation:manage`
- GET    -> authenticated, owner, or `donation:read`
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.dog.models import DogProfile
from pawguard.modules.donation.models import (
    DogSponsorship,
    DonorProfile,
    SponsorshipStatus,
)


@pytest.mark.asyncio
class TestSponsorshipAccessControl:
    """Owners can manage their own sponsorships; others are blocked."""

    @pytest_asyncio.fixture
    async def donor_role(self, db_session: AsyncSession) -> Role:
        """A donor-equivalent role WITHOUT staff-level donation:read/manage."""
        perm_code = f"test_sponsor_read_{uuid.uuid4().hex[:8]}"
        test_read = Permission(code=perm_code, description=perm_code)
        db_session.add(test_read)
        await db_session.flush()
        role = Role(
            id=uuid.uuid4(),
            name=f"test_donor_{uuid.uuid4().hex[:8]}",
            description="Synthetic donor role for sponsorship IDOR regression.",
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
            "full_name": "Sponsor Test",
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

    async def _create_owned_sponsorship(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_email: str,
    ) -> uuid.UUID:
        """Create a donor profile + dog + ACTIVE sponsorship owned by owner_email."""
        owner = (
            await db_session.execute(
                select(User).options(selectinload(User.roles)).where(User.email == owner_email)
            )
        ).scalar_one()
        donor = DonorProfile(user_id=owner.id, tax_identifier=None, notes="sponsor idor test")
        db_session.add(donor)
        await db_session.flush()

        dog = DogProfile(
            registration_number=f"SPR-{uuid.uuid4().hex[:8].upper()}",
            name="Test Pup",
            breed="indie_mix",
            gender="male",
        )
        db_session.add(dog)
        await db_session.flush()

        sponsorship = DogSponsorship(
            donor_id=donor.id,
            dog_id=dog.id,
            monthly_amount=25.0,
            currency="USD",
            status=SponsorshipStatus.ACTIVE,
            next_charge_date=date.today() + timedelta(days=30),
            started_at=datetime.now(UTC),
        )
        db_session.add(sponsorship)
        await db_session.commit()
        return sponsorship.id

    async def test_get_sponsorship_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "anonsponsor@sponsor.test.com", donor_role
        )
        sponsorship_id = await self._create_owned_sponsorship(
            client, db_session, "anonsponsor@sponsor.test.com"
        )
        resp = await client.get(f"/api/v1/donations/sponsorships/{sponsorship_id}")
        assert resp.status_code == 401

    async def test_owner_can_read_own_sponsorship(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        headers = await self._register_and_auth(
            client, db_session, "ownersponsor@sponsor.test.com", donor_role
        )
        sponsorship_id = await self._create_owned_sponsorship(
            client, db_session, "ownersponsor@sponsor.test.com"
        )
        resp = await client.get(
            f"/api/v1/donations/sponsorships/{sponsorship_id}", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == str(sponsorship_id)

    async def test_non_owner_cannot_read_sponsorship(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "ownersponsor2@sponsor.test.com", donor_role
        )
        sponsorship_id = await self._create_owned_sponsorship(
            client, db_session, "ownersponsor2@sponsor.test.com"
        )
        other_headers = await self._register_and_auth(
            client, db_session, "othersponsor2@sponsor.test.com", donor_role
        )
        resp = await client.get(
            f"/api/v1/donations/sponsorships/{sponsorship_id}", headers=other_headers
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    async def test_owner_can_pause_own_sponsorship(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        headers = await self._register_and_auth(
            client, db_session, "ownersponsor3@sponsor.test.com", donor_role
        )
        sponsorship_id = await self._create_owned_sponsorship(
            client, db_session, "ownersponsor3@sponsor.test.com"
        )
        resp = await client.patch(
            f"/api/v1/donations/sponsorships/{sponsorship_id}/status",
            json={"status": "paused"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "paused"

    async def test_non_owner_cannot_pause_sponsorship(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "ownersponsor4@sponsor.test.com", donor_role
        )
        sponsorship_id = await self._create_owned_sponsorship(
            client, db_session, "ownersponsor4@sponsor.test.com"
        )
        other_headers = await self._register_and_auth(
            client, db_session, "othersponsor4@sponsor.test.com", donor_role
        )
        resp = await client.patch(
            f"/api/v1/donations/sponsorships/{sponsorship_id}/status",
            json={"status": "paused"},
            headers=other_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    async def test_staff_with_donation_manage_can_manage_any_sponsorship(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "ownersponsor5@sponsor.test.com", donor_role
        )
        sponsorship_id = await self._create_owned_sponsorship(
            client, db_session, "ownersponsor5@sponsor.test.com"
        )

        staff_payload = {
            "email": "staffsponsor5@sponsor.test.com",
            "password": "StrongP@ss99",
            "full_name": "Staff",
            "phone": "+1234567890",
        }
        await client.post("/api/v1/auth/register", json=staff_payload)
        staff = (
            await db_session.execute(
                select(User)
                .options(selectinload(User.roles))
                .where(User.email == staff_payload["email"])
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
            json={"email": staff_payload["email"], "password": staff_payload["password"]},
        )
        staff_headers = {
            "Authorization": f"Bearer {login_resp.json()['data']['access_token']}"
        }

        get_resp = await client.get(
            f"/api/v1/donations/sponsorships/{sponsorship_id}", headers=staff_headers
        )
        assert get_resp.status_code == 200
        patch_resp = await client.patch(
            f"/api/v1/donations/sponsorships/{sponsorship_id}/status",
            json={"status": "paused"},
            headers=staff_headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["data"]["status"] == "paused"
