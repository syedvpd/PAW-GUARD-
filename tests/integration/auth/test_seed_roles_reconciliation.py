"""Integration tests for scripts/seed_roles_and_permissions.py's reconciliation
logic against the real database, inside a rolled-back transaction.

Context: the seeding function used to check "does any Role row exist at all?"
and skip everything if so. That meant editing a role's permission list in
code and shipping it never reached an already-seeded environment - which is
exactly how every role (including super_admin) ended up missing every
dashboard:* permission, and later grievance:*/notification:*, in production.
reconcile_roles() replaces that skip-all check with a per-role, per-permission
diff that grants whatever's missing, every time it runs (including on every
app startup).
"""

import uuid

import pytest
from scripts.seed_roles_and_permissions import reconcile_roles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import Permission, Role

# A synthetic role name that will never collide with a real seeded role, so
# these tests can't interact with production-shaped data even though they
# run against the real database (safe only because the transaction is
# rolled back by the db_session fixture after each test).
TEST_ROLE = "test_reconciliation_role"
TEST_PERM_A = "test_module:read"
TEST_PERM_B = "test_module:write"
TEST_PERM_C = "test_module:delete"


async def _get_role_with_permissions(session: AsyncSession, name: str) -> Role | None:
    result = await session.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.name == name)
    )
    return result.scalar_one_or_none()


@pytest.mark.asyncio
class TestRoleReconciliation:
    async def test_new_role_is_created_with_all_permissions(self, db_session: AsyncSession) -> None:
        definitions = [
            (TEST_ROLE, "Test role", False, [TEST_PERM_A, TEST_PERM_B]),
        ]
        created, granted = await reconcile_roles(db_session, definitions, verbose=False)
        assert created == 1
        assert granted == 2

        role = await _get_role_with_permissions(db_session, TEST_ROLE)
        assert role is not None
        assert {p.code for p in role.permissions} == {TEST_PERM_A, TEST_PERM_B}

    async def test_existing_role_missing_a_permission_gets_it_granted(
        self, db_session: AsyncSession
    ) -> None:
        """This is the exact bug scenario: a role already exists (so the old
        "skip if any role exists" check would never touch it) but is missing
        a permission that's since been added to its definition in code."""
        perm_a = Permission(code=TEST_PERM_A, description=TEST_PERM_A)
        db_session.add(perm_a)
        await db_session.flush()

        role = Role(
            id=uuid.uuid4(),
            name=TEST_ROLE,
            description="Pre-existing",
            is_system=False,
            permissions=[perm_a],
        )
        db_session.add(role)
        await db_session.flush()

        # Definition now requires PERM_A (already granted) and PERM_B (missing).
        definitions = [
            (TEST_ROLE, "Test role", False, [TEST_PERM_A, TEST_PERM_B]),
        ]
        created, granted = await reconcile_roles(db_session, definitions, verbose=False)
        assert created == 0, "role already existed, must not be recreated"
        assert granted == 1, "only the missing permission should be granted"

        refreshed = await _get_role_with_permissions(db_session, TEST_ROLE)
        assert refreshed is not None
        assert {p.code for p in refreshed.permissions} == {TEST_PERM_A, TEST_PERM_B}

    async def test_reconciliation_is_additive_never_revokes(self, db_session: AsyncSession) -> None:
        """A permission granted out-of-band (or since removed from the code
        definition) must survive reconciliation - only additions, no
        revocations, so this can never silently strip access."""
        perm_a = Permission(code=TEST_PERM_A, description=TEST_PERM_A)
        perm_c = Permission(code=TEST_PERM_C, description=TEST_PERM_C)
        db_session.add_all([perm_a, perm_c])
        await db_session.flush()

        role = Role(
            id=uuid.uuid4(),
            name=TEST_ROLE,
            description="Pre-existing",
            is_system=False,
            permissions=[perm_a, perm_c],
        )
        db_session.add(role)
        await db_session.flush()

        # Code definition no longer mentions PERM_C at all.
        definitions = [
            (TEST_ROLE, "Test role", False, [TEST_PERM_A]),
        ]
        created, granted = await reconcile_roles(db_session, definitions, verbose=False)
        assert created == 0
        assert granted == 0

        refreshed = await _get_role_with_permissions(db_session, TEST_ROLE)
        assert refreshed is not None
        assert {p.code for p in refreshed.permissions} == {TEST_PERM_A, TEST_PERM_C}, (
            "PERM_C must still be present - reconciliation must never revoke"
        )

    async def test_reconciliation_is_idempotent(self, db_session: AsyncSession) -> None:
        definitions = [
            (TEST_ROLE, "Test role", False, [TEST_PERM_A, TEST_PERM_B]),
        ]
        created1, granted1 = await reconcile_roles(db_session, definitions, verbose=False)
        assert (created1, granted1) == (1, 2)

        created2, granted2 = await reconcile_roles(db_session, definitions, verbose=False)
        assert (created2, granted2) == (0, 0), "second run must be a no-op"

        role = await _get_role_with_permissions(db_session, TEST_ROLE)
        assert role is not None
        assert len(role.permissions) == 2, "no duplicate grants"
