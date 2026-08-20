"""Regression tests for the missing ownership check on POST /donations/verify
(Cycle 1, S6).

The endpoint finalizes a donation as SUCCESS after the client returns from the
payment gateway. It was authenticated and rate-limited but had no ownership
check, so any authenticated user holding another donor's order/payment/signature
values could finalize a donation they did not initiate. Now only the donating
user (or staff with `donation:read`) may call it.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.donation.models import Donation, DonationStatus, DonationType, DonorProfile


@pytest.mark.asyncio
class TestDonationVerifyAccessControl:
    """Only the donor (or staff) may verify a donation payment."""

    @pytest_asyncio.fixture
    async def donor_role(self, db_session: AsyncSession) -> Role:
        """A donor-equivalent role WITHOUT staff-level donation:read."""
        perm_code = f"test_verify_read_{uuid.uuid4().hex[:8]}"
        test_read = Permission(code=perm_code, description=perm_code)
        db_session.add(test_read)
        await db_session.flush()
        role = Role(
            id=uuid.uuid4(),
            name=f"test_donor_{uuid.uuid4().hex[:8]}",
            description="Synthetic donor role for verify IDOR regression.",
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
            "full_name": "Verify Test",
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

    async def _create_pending_donation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_email: str,
    ) -> uuid.UUID:
        """Create a PENDING donation owned by owner_email."""
        owner = (
            await db_session.execute(
                select(User).options(selectinload(User.roles)).where(User.email == owner_email)
            )
        ).scalar_one()
        donor = DonorProfile(user_id=owner.id, tax_identifier=None, notes="verify idor test")
        db_session.add(donor)
        await db_session.flush()
        donation = Donation(
            donor_id=donor.id,
            amount=50.0,
            currency="USD",
            donation_type=DonationType.ONE_TIME,
            status=DonationStatus.PENDING,
            gateway_order_id="ORDER-X",
        )
        db_session.add(donation)
        await db_session.commit()
        return donation.id

    async def test_owner_is_not_blocked_by_ownership_check(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        """The owner passes the guard; the (unconfigured) gateway then rejects,
        proving the check does not lock out the legitimate donor."""
        headers = await self._register_and_auth(
            client, db_session, "ownerverify@verify.test.com", donor_role
        )
        donation_id = await self._create_pending_donation(
            client, db_session, "ownerverify@verify.test.com"
        )
        resp = await client.post(
            "/api/v1/donations/verify",
            json={
                "donation_id": str(donation_id),
                "gateway_order_id": "ORDER-X",
                "gateway_payment_id": "PAY-X",
                "gateway_signature": "sig-x",
            },
            headers=headers,
        )
        assert resp.status_code == 422
        assert any(msg in resp.json()["error"]["message"] for msg in ("not configured", "Signature Verification Failed", "verification failed"))

    async def test_non_owner_is_blocked(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "ownerverify2@verify.test.com", donor_role
        )
        donation_id = await self._create_pending_donation(
            client, db_session, "ownerverify2@verify.test.com"
        )
        other_headers = await self._register_and_auth(
            client, db_session, "otherverify2@verify.test.com", donor_role
        )
        resp = await client.post(
            "/api/v1/donations/verify",
            json={
                "donation_id": str(donation_id),
                "gateway_order_id": "ORDER-X",
                "gateway_payment_id": "PAY-X",
                "gateway_signature": "sig-x",
            },
            headers=other_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    async def test_unauthenticated_is_rejected(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "ownerverify3@verify.test.com", donor_role
        )
        donation_id = await self._create_pending_donation(
            client, db_session, "ownerverify3@verify.test.com"
        )
        resp = await client.post(
            "/api/v1/donations/verify",
            json={
                "donation_id": str(donation_id),
                "gateway_order_id": "ORDER-X",
                "gateway_payment_id": "PAY-X",
                "gateway_signature": "sig-x",
            },
        )
        assert resp.status_code == 401
