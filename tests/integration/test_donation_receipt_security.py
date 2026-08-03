"""Regression tests for the receipt IDOR (C-1).

A donor must only be able to download receipts for donations they own.
Previously the ownership check in GET /donations/{donation_id}/receipt
compared `donation.donor_id` (a donor_profiles.id) against
`current_user.user.id` (a users.id) - two UUID namespaces that can never
match - and the public `donor` role held the staff-level `donation:read`
permission, so the fallback let any donor download any donor's receipt.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tests.auth_helpers import register_and_auth

from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.donation.models import Donation, DonationStatus, DonationType, DonorProfile

RECEIPT_KEY = "documents/receipt_test.pdf"


@pytest.mark.asyncio
class TestReceiptAccessControl:
    """Owner can read own receipt; non-owner without donation:read cannot."""

    @pytest_asyncio.fixture
    async def donor_role(self, db_session: AsyncSession) -> Role:
        """A donor-equivalent role WITHOUT the staff-level donation:read
        permission, created inside the rolled-back test transaction."""
        perm_code = f"test_receipt_read_{uuid.uuid4().hex[:8]}"
        test_read = Permission(code=perm_code, description=perm_code)
        db_session.add(test_read)
        await db_session.flush()
        role = Role(
            id=uuid.uuid4(),
            name=f"test_donor_{uuid.uuid4().hex[:8]}",
            description="Synthetic donor role for receipt IDOR regression.",
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
            "full_name": "Receipt Test",
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

    async def _create_owned_donation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_email: str,
    ) -> uuid.UUID:
        """Register a donor profile + a receipt-bearing donation owned by
        owner_email, written straight to the DB (payment flows are mocked at
        the gateway level and out of scope here)."""
        owner = (
            await db_session.execute(
                select(User).options(selectinload(User.roles)).where(User.email == owner_email)
            )
        ).scalar_one()
        donor = DonorProfile(user_id=owner.id, tax_identifier=None, notes="receipt idor test")
        db_session.add(donor)
        await db_session.flush()
        donation = Donation(
            donor_id=donor.id,
            amount=50.0,
            currency="USD",
            donation_type=DonationType.ONE_TIME,
            status=DonationStatus.SUCCESS,
            transaction_id=f"TXN-RECEIPT-{uuid.uuid4().hex[:10].upper()}",
            receipt_file_key=RECEIPT_KEY,
        )
        db_session.add(donation)
        await db_session.commit()
        return donation.id

    async def test_owner_can_download_own_receipt(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        headers = await self._register_and_auth(
            client, db_session, "owner@receipt.test.com", donor_role
        )
        donation_id = await self._create_owned_donation(client, db_session, "owner@receipt.test.com")
        resp = await client.get(f"/api/v1/donations/{donation_id}/receipt", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["object_key"] == RECEIPT_KEY

    async def test_non_owner_donor_cannot_download_receipt(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "owner2@receipt.test.com", donor_role
        )
        donation_id = await self._create_owned_donation(client, db_session, "owner2@receipt.test.com")
        other_headers = await self._register_and_auth(
            client, db_session, "other2@receipt.test.com", donor_role
        )
        resp = await client.get(f"/api/v1/donations/{donation_id}/receipt", headers=other_headers)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    async def test_staff_with_donation_read_can_download_any_receipt(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        await self._register_and_auth(
            client, db_session, "owner3@receipt.test.com", donor_role
        )
        donation_id = await self._create_owned_donation(client, db_session, "owner3@receipt.test.com")

        staff_headers = await register_and_auth(
            client, db_session, email="staff3@receipt.test.com"
        )

        resp = await client.get(f"/api/v1/donations/{donation_id}/receipt", headers=staff_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["object_key"] == RECEIPT_KEY

    async def test_donor_role_definition_has_no_donation_read(
        self, db_session: AsyncSession
    ) -> None:
        """The public donor role must not carry the staff-level donation:read
        permission, or the permission fallback re-opens the IDOR."""
        from scripts.seed_roles_and_permissions import ROLE_DEFINITIONS

        definitions = {name: perms for name, _, _, perms in ROLE_DEFINITIONS}
        assert "donation:read" not in definitions["donor"]

        role = (
            await db_session.execute(select(Role).where(Role.name == "donor"))
        ).scalar_one_or_none()
        if role is not None:
            role = (
                await db_session.execute(
                    select(Role).options(selectinload(Role.permissions)).where(Role.name == "donor")
                )
            ).scalar_one()
            assert "donation:read" not in {p.code for p in role.permissions}
