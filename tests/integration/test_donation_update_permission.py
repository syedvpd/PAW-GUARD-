"""Regression tests for the missing `donation:update` permission (Sprint 0, #2).

Five staff endpoints in the donation router are gated on
`Depends(require_permission("donation:update"))`:
- PUT /donations/donors/{donor_id}
- DELETE /donations/donors/{donor_id}
- PATCH /donations/{donation_id}/status
- POST /donations/bulk/status-update
- POST /donations/donors/bulk/delete

The permission code was never added to permission_codes.py nor granted to any
role in the seed, so every caller - including super_admin - received 403 on all
five endpoints. These tests pin the permission to the roles that already hold
`donation:manage` (super_admin, finance_user) and verify the enforcement works
end-to-end on the status-update endpoint.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from scripts.seed_roles_and_permissions import ROLE_DEFINITIONS, reconcile_roles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.donation.models import (
    Donation,
    DonationStatus,
    DonationType,
    DonorProfile,
)


def _role_definitions() -> dict[str, list[str]]:
    return {name: perms for name, _, _, perms in ROLE_DEFINITIONS}


@pytest.mark.asyncio
class TestDonationUpdatePermission:
    """The permission must exist, be granted to donation-managing roles, and be
    enforced on the endpoints that declare it."""

    async def _reconcile(self, db_session: AsyncSession) -> None:
        """Run the startup reconciliation against the real role definitions.
        Safe: runs inside the rolled-back test transaction, so it cannot leave
        the shared database changed."""
        await reconcile_roles(db_session, ROLE_DEFINITIONS, verbose=False)

    @pytest_asyncio.fixture
    async def staff_role(self, db_session: AsyncSession) -> Role:
        """A synthetic staff role holding ONLY donation:update, so tests isolate
        the update permission without relying on a real role."""
        perm = (
            await db_session.execute(
                select(Permission).where(Permission.code == "donation:update")
            )
        ).scalar_one_or_none()
        if perm is None:
            perm = Permission(code="donation:update", description="donation:update")
            db_session.add(perm)
            await db_session.flush()
        role = Role(
            id=uuid.uuid4(),
            name=f"test_update_{uuid.uuid4().hex[:8]}",
            description="Synthetic staff role holding donation:update.",
            is_system=False,
            permissions=[perm],
        )
        db_session.add(role)
        await db_session.flush()
        return role

    @pytest_asyncio.fixture
    async def donor_role(self, db_session: AsyncSession) -> Role:
        """A synthetic role WITHOUT donation:update (donor-equivalent)."""
        perm_code = f"test_donation_read_{uuid.uuid4().hex[:8]}"
        test_read = Permission(code=perm_code, description=perm_code)
        db_session.add(test_read)
        await db_session.flush()
        role = Role(
            id=uuid.uuid4(),
            name=f"test_donor_{uuid.uuid4().hex[:8]}",
            description="Synthetic role without donation:update.",
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
            "full_name": "Donation Update Test",
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

    async def _create_success_donation(
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
        donor = DonorProfile(user_id=owner.id, tax_identifier=None, notes="donation:update test")
        db_session.add(donor)
        await db_session.flush()
        donation = Donation(
            donor_id=donor.id,
            amount=25.0,
            currency="USD",
            donation_type=DonationType.ONE_TIME,
            status=DonationStatus.PENDING,
            transaction_id=f"TXN-UPDATE-{uuid.uuid4().hex[:10].upper()}",
        )
        db_session.add(donation)
        await db_session.commit()
        return donation.id

    async def test_permission_code_is_defined(
        self, db_session: AsyncSession
    ) -> None:
        """The code the router depends on must exist in the registry AND as a
        permission row after reconciliation, or require_permission 403s
        everyone (there is no superuser bypass)."""
        from pawguard.modules.auth import permission_codes as pc

        assert hasattr(pc, "DONATION_UPDATE")
        assert pc.DONATION_UPDATE == "donation:update"

        definitions = _role_definitions()
        assert "donation:update" in definitions["super_admin"]
        assert "donation:update" in definitions["finance_user"]

        await self._reconcile(db_session)
        perm = (
            await db_session.execute(
                select(Permission).where(Permission.code == "donation:update")
            )
        ).scalar_one_or_none()
        assert perm is not None, (
            "donation:update must exist as a permission row (seed reconciliation "
            "creates it on startup) or require_permission 403s everyone"
        )

    async def test_super_admin_and_finance_user_are_granted_donation_update(
        self, db_session: AsyncSession
    ) -> None:
        """The roles that hold donation:manage must also hold donation:update,
        and the live DB role rows must reflect it after reconciliation."""
        await self._reconcile(db_session)
        for role_name in ("super_admin", "finance_user"):
            role = (
                await db_session.execute(
                    select(Role)
                    .options(selectinload(Role.permissions))
                    .where(Role.name == role_name)
                )
            ).scalar_one_or_none()
            assert role is not None
            assert "donation:update" in {p.code for p in role.permissions}

    async def test_public_donor_role_has_no_donation_update(
        self, db_session: AsyncSession
    ) -> None:
        """The donor must NOT be able to mutate donation records."""
        await self._reconcile(db_session)
        definitions = _role_definitions()
        assert "donation:update" not in definitions["donor"]

        role = (
            await db_session.execute(
                select(Role).options(selectinload(Role.permissions)).where(Role.name == "donor")
            )
        ).scalar_one_or_none()
        if role is not None:
            assert "donation:update" not in {p.code for p in role.permissions}

    async def test_staff_with_donation_update_can_change_status(
        self, client: AsyncClient, db_session: AsyncSession, staff_role: Role
    ) -> None:
        headers = await self._register_and_auth(
            client, db_session, "staff4@donation-update.test.com", staff_role
        )
        donation_id = await self._create_success_donation(
            client, db_session, "staff4@donation-update.test.com"
        )
        resp = await client.patch(
            f"/api/v1/donations/{donation_id}/status",
            json={"status": "success"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "success"

    async def test_donor_without_donation_update_gets_403(
        self, client: AsyncClient, db_session: AsyncSession, donor_role: Role
    ) -> None:
        headers = await self._register_and_auth(
            client, db_session, "donor5@donation-update.test.com", donor_role
        )
        donation_id = await self._create_success_donation(
            client, db_session, "donor5@donation-update.test.com"
        )
        resp = await client.patch(
            f"/api/v1/donations/{donation_id}/status",
            json={"status": "success"},
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
