"""Seed and reconcile the 15 PRR-defined roles with their module-level
permissions.

Safe to re-run, and runs on every app startup (see main.py). Reconciles
rather than skips: creates any role/permission that doesn't exist yet, and
grants any permission in ROLE_DEFINITIONS that an existing role is missing.

This matters because it used to short-circuit entirely once any role
existed - so adding a new permission to a role's list here, and shipping
that as a code change, silently never reached an already-seeded database.
That's exactly how every role (including super_admin) ended up missing
every dashboard:* permission, and later grievance:*/notification:*, until
someone happened to notice the 403s in production. Reconciliation is
additive-only (grants missing permissions, never revokes) so it can't
strip an out-of-band manual grant.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from pawguard.core.config import get_settings
from pawguard.modules.auth import permission_codes as pc
from pawguard.modules.auth.models import Permission, Role, RolePermission

# ── Role definitions ─────────────────────────────────────────────────────────
# Each entry: (role_name, description, is_system, [permission_code, …])

ROLE_DEFINITIONS: list[tuple[str, str, bool, list[str]]] = [
    (
        "super_admin",
        "System governance, RBAC management, global configuration, audit review.",
        True,
        [
            pc.SYSTEM_READ,
            pc.SYSTEM_WRITE,
            pc.SYSTEM_ADMIN,
            pc.USER_READ,
            pc.USER_CREATE,
            pc.USER_UPDATE,
            pc.USER_DELETE,
            pc.USER_ASSIGN_ROLE,
            pc.RESCUE_CREATE,
            pc.RESCUE_READ,
            pc.RESCUE_UPDATE,
            pc.RESCUE_DELETE,
            pc.RESCUE_VERIFY,
            pc.RESCUE_DISPATCH,
            pc.RESCUE_EXECUTE,
            pc.VEHICLE_READ,
            pc.VEHICLE_ASSIGN,
            pc.VEHICLE_UPDATE,
            pc.SHELTER_READ,
            pc.SHELTER_UPDATE,
            pc.SHELTER_MANAGE_KENNELS,
            pc.SHELTER_TRANSFER,
            pc.MEDICAL_CREATE,
            pc.MEDICAL_READ,
            pc.MEDICAL_UPDATE,
            pc.MEDICAL_DELETE,
            pc.DOG_MEDICAL_UPDATE,
            pc.ADOPTION_READ,
            pc.ADOPTION_PROCESS,
            pc.ADOPTION_APPROVE,
            pc.ADOPTION_LOCK,
            pc.FOSTER_CREATE,
            pc.FOSTER_READ,
            pc.FOSTER_UPDATE,
            pc.FOSTER_APPROVE,
            pc.VOLUNTEER_CREATE,
            pc.VOLUNTEER_READ,
            pc.VOLUNTEER_UPDATE,
            pc.VOLUNTEER_SCHEDULE,
            pc.INVENTORY_CREATE,
            pc.INVENTORY_READ,
            pc.INVENTORY_UPDATE,
            pc.INVENTORY_DELETE,
            pc.REQUISITION_CREATE,
            pc.FINANCE_READ,
            pc.FINANCE_CREATE,
            pc.FINANCE_RECONCILE,
            pc.DONATION_READ,
            pc.DONATION_MANAGE,
            pc.DONATION_UPDATE,
            pc.PUBLIC_READ,
            pc.PUBLIC_CREATE,
            pc.AUDIT_READ,
            pc.GRIEVANCE_CREATE,
            pc.GRIEVANCE_READ,
            pc.GRIEVANCE_UPDATE,
            pc.GRIEVANCE_ASSIGN,
            pc.GRIEVANCE_COMMENT,
            pc.NOTIFICATION_READ,
            pc.NOTIFICATION_MANAGE,
            pc.DASHBOARD_RESCUE,
            pc.DASHBOARD_SHELTER,
            pc.DASHBOARD_MEDICAL,
            pc.DASHBOARD_ADOPTION,
            pc.DASHBOARD_FOSTER,
            pc.DASHBOARD_VOLUNTEER,
            pc.DASHBOARD_INVENTORY,
            pc.DASHBOARD_FINANCE,
            pc.DASHBOARD_DONOR,
            pc.REPORTS_READ,
            pc.REPORTS_CREATE,
            pc.REPORTS_EXPORT_PDF,
            pc.REPORTS_EXPORT_CSV,
            pc.REPORTS_EXPORT_EXCEL,
            pc.FINANCE_UPDATE,
            pc.FINANCE_DELETE,
            pc.FINANCE_EXPORT,
            pc.RESCUE_WRITE,
            pc.DONATIONS_WRITE,
            pc.COMPLAINTS_WRITE,
            pc.NOTIFICATIONS_WRITE,
            pc.COMPANION_PET_CREATE,
            pc.COMPANION_PET_READ,
            pc.COMPANION_PET_UPDATE,
            pc.COMPANION_PET_DELETE,
            pc.COMPANION_PET_MEDICAL_UPLOAD,
            pc.SAFETY_TAG_MANAGE,
            pc.VET_CLINIC_READ,
            pc.VET_CLINIC_MANAGE,
            pc.APPOINTMENT_CREATE,
            pc.APPOINTMENT_READ,
            pc.APPOINTMENT_CANCEL,
            pc.APPOINTMENT_MANAGE,
            pc.LOST_FOUND_BROADCAST,
        ],
    ),
    (
        "rescue_centre_admin",
        "Operational strategy, facility oversight, compliance, approvals.",
        True,
        [
            pc.USER_READ,
            pc.USER_CREATE,
            pc.USER_UPDATE,
            pc.USER_ASSIGN_ROLE,
            pc.RESCUE_CREATE,
            pc.RESCUE_READ,
            pc.RESCUE_UPDATE,
            pc.RESCUE_VERIFY,
            pc.RESCUE_DISPATCH,
            pc.RESCUE_EXECUTE,
            pc.RESCUE_DELETE,
            pc.VEHICLE_READ,
            pc.VEHICLE_ASSIGN,
            pc.VEHICLE_UPDATE,
            pc.SHELTER_READ,
            pc.SHELTER_UPDATE,
            pc.SHELTER_MANAGE_KENNELS,
            pc.SHELTER_TRANSFER,
            pc.DOG_MEDICAL_UPDATE,
            pc.MEDICAL_READ,
            pc.ADOPTION_READ,
            pc.ADOPTION_PROCESS,
            pc.ADOPTION_APPROVE,
            pc.ADOPTION_LOCK,
            pc.ADOPTION_DELETE,
            pc.FOSTER_CREATE,
            pc.FOSTER_READ,
            pc.FOSTER_UPDATE,
            pc.FOSTER_APPROVE,
            pc.FOSTER_DELETE,
            pc.VOLUNTEER_CREATE,
            pc.VOLUNTEER_READ,
            pc.VOLUNTEER_UPDATE,
            pc.VOLUNTEER_SCHEDULE,
            pc.VOLUNTEER_DELETE,
            pc.INVENTORY_READ,
            pc.INVENTORY_UPDATE,
            pc.INVENTORY_DELETE,
            pc.REQUISITION_CREATE,
            pc.FINANCE_READ,
            pc.DONATION_READ,
            pc.PUBLIC_READ,
            pc.PUBLIC_CREATE,
            pc.AUDIT_READ,
            pc.GRIEVANCE_READ,
            pc.GRIEVANCE_UPDATE,
            pc.GRIEVANCE_ASSIGN,
            pc.GRIEVANCE_COMMENT,
            pc.SYSTEM_ADMIN,
            pc.NOTIFICATION_READ,
            pc.DASHBOARD_RESCUE,
            pc.DASHBOARD_SHELTER,
            pc.DASHBOARD_MEDICAL,
            pc.DASHBOARD_ADOPTION,
            pc.DASHBOARD_FOSTER,
            pc.DASHBOARD_VOLUNTEER,
            pc.DASHBOARD_INVENTORY,
            pc.DASHBOARD_FINANCE,
            pc.DASHBOARD_DONOR,
            pc.RESCUE_WRITE,
            pc.COMPLAINTS_WRITE,
            pc.COMPANION_PET_CREATE,
            pc.COMPANION_PET_READ,
            pc.COMPANION_PET_UPDATE,
            pc.COMPANION_PET_DELETE,
            pc.COMPANION_PET_MEDICAL_UPLOAD,
            pc.SAFETY_TAG_MANAGE,
            pc.VET_CLINIC_READ,
            pc.VET_CLINIC_MANAGE,
            pc.APPOINTMENT_CREATE,
            pc.APPOINTMENT_READ,
            pc.APPOINTMENT_CANCEL,
            pc.APPOINTMENT_MANAGE,
            pc.LOST_FOUND_BROADCAST,
        ],
    ),
    (
        "rescue_coordinator",
        "Verification of public reports, severity prioritization, field dispatching.",
        True,
        [
            pc.RESCUE_CREATE,
            pc.RESCUE_READ,
            pc.RESCUE_UPDATE,
            pc.RESCUE_VERIFY,
            pc.RESCUE_DISPATCH,
            pc.RESCUE_EXECUTE,
            pc.VEHICLE_READ,
            pc.VEHICLE_ASSIGN,
            pc.VEHICLE_UPDATE,
            pc.PUBLIC_READ,
            pc.DASHBOARD_RESCUE,
            pc.RESCUE_WRITE,
        ],
    ),
    (
        "rescue_agent",
        "Field location, rescue execution, transport log.",
        True,
        [
            pc.RESCUE_READ,
            pc.RESCUE_EXECUTE,
            pc.VEHICLE_READ,
            pc.PUBLIC_READ,
            pc.DASHBOARD_RESCUE,
        ],
    ),
    (
        "veterinarian",
        "Clinical examinations, surgeries, prescriptions, medical clearances.",
        True,
        [
            pc.MEDICAL_CREATE,
            pc.MEDICAL_READ,
            pc.MEDICAL_UPDATE,
            pc.MEDICAL_CLEARANCE,
            pc.DOG_MEDICAL_UPDATE,
            pc.SHELTER_READ,
            pc.ADOPTION_READ,
            pc.INVENTORY_READ,
            pc.REQUISITION_CREATE,
            pc.PUBLIC_READ,
            pc.DASHBOARD_MEDICAL,
            pc.COMPANION_PET_READ,
            pc.COMPANION_PET_UPDATE,
            pc.COMPANION_PET_MEDICAL_UPLOAD,
            pc.VET_CLINIC_READ,
            pc.APPOINTMENT_READ,
            pc.APPOINTMENT_MANAGE,
        ],
    ),
    (
        "shelter_manager",
        "Daily care tracking, intake logs, kennel allocation, transfers.",
        True,
        [
            pc.SHELTER_READ,
            pc.SHELTER_UPDATE,
            pc.SHELTER_MANAGE_KENNELS,
            pc.SHELTER_TRANSFER,
            pc.RESCUE_READ,
            pc.MEDICAL_READ,
            pc.ADOPTION_READ,
            pc.INVENTORY_READ,
            pc.REQUISITION_CREATE,
            pc.PUBLIC_READ,
            pc.DASHBOARD_SHELTER,
            pc.COMPANION_PET_READ,
        ],
    ),
    (
        "adoption_coordinator",
        "Application processing, applicant vetting, interviews, post-adoption audits.",
        True,
        [
            pc.ADOPTION_READ,
            pc.ADOPTION_PROCESS,
            pc.ADOPTION_APPROVE,
            pc.ADOPTION_LOCK,
            pc.SHELTER_READ,
            pc.MEDICAL_READ,
            pc.PUBLIC_READ,
            pc.DASHBOARD_ADOPTION,
        ],
    ),
    (
        "foster_coordinator",
        "Foster parent onboarding, home inspection, placement tracking, supply provision.",
        True,
        [
            pc.FOSTER_CREATE,
            pc.FOSTER_READ,
            pc.FOSTER_UPDATE,
            pc.FOSTER_APPROVE,
            pc.INVENTORY_READ,
            pc.PUBLIC_READ,
            pc.DASHBOARD_FOSTER,
        ],
    ),
    (
        "volunteer_coordinator",
        "Volunteer registration vetting, activity schedules, shift attendance.",
        True,
        [
            pc.VOLUNTEER_CREATE,
            pc.VOLUNTEER_READ,
            pc.VOLUNTEER_UPDATE,
            pc.VOLUNTEER_SCHEDULE,
            pc.PUBLIC_READ,
            pc.DASHBOARD_VOLUNTEER,
        ],
    ),
    (
        "inventory_manager",
        "Stock tracking, orders, expiry enforcement, vendor records.",
        True,
        [
            pc.INVENTORY_CREATE,
            pc.INVENTORY_READ,
            pc.INVENTORY_UPDATE,
            pc.INVENTORY_DELETE,
            pc.REQUISITION_CREATE,
            pc.PUBLIC_READ,
            pc.DASHBOARD_INVENTORY,
        ],
    ),
    (
        "finance_user",
        "Expense recording, income reconciliation, donor receipting.",
        True,
        [
            pc.FINANCE_READ,
            pc.FINANCE_CREATE,
            pc.FINANCE_RECONCILE,
            pc.DONATION_READ,
            pc.DONATION_MANAGE,
            pc.DONATION_UPDATE,
            pc.PUBLIC_READ,
            pc.DASHBOARD_FINANCE,
            pc.DONATIONS_WRITE,
        ],
    ),
    (
        "volunteer",
        "Duty acceptance, shift check-in/out, activity logging.",
        False,
        [
            pc.VOLUNTEER_READ,
            pc.DASHBOARD_VOLUNTEER,
        ],
    ),
    (
        "foster_family",
        "Daily progress reporting, medical symptom uploads, supply requests.",
        False,
        [
            pc.FOSTER_READ,
            pc.DASHBOARD_FOSTER,
        ],
    ),
    (
        "donor",
        "Direct contributions, dog sponsorship, tax receipt downloads.",
        False,
        [
            pc.PUBLIC_READ,
            pc.DASHBOARD_DONOR,
            pc.COMPANION_PET_CREATE,
            pc.COMPANION_PET_READ,
            pc.COMPANION_PET_UPDATE,
            pc.COMPANION_PET_DELETE,
            pc.COMPANION_PET_MEDICAL_UPLOAD,
            pc.SAFETY_TAG_MANAGE,
            pc.VET_CLINIC_READ,
            pc.APPOINTMENT_CREATE,
            pc.APPOINTMENT_READ,
            pc.APPOINTMENT_CANCEL,
            pc.LOST_FOUND_BROADCAST,
        ],
    ),
    (
        "general_public",
        "Emergency reporting, adoption applications, lost/found postings.",
        False,
        [
            pc.PUBLIC_READ,
            pc.PUBLIC_CREATE,
            pc.COMPANION_PET_CREATE,
            pc.COMPANION_PET_READ,
            pc.COMPANION_PET_UPDATE,
            pc.COMPANION_PET_DELETE,
            pc.COMPANION_PET_MEDICAL_UPLOAD,
            pc.SAFETY_TAG_MANAGE,
            pc.VET_CLINIC_READ,
            pc.APPOINTMENT_CREATE,
            pc.APPOINTMENT_READ,
            pc.APPOINTMENT_CANCEL,
            pc.LOST_FOUND_BROADCAST,
        ],
    ),
    (
        "app_user",
        "Public application user for companion pets, lost & found, and emergency reporting.",
        False,
        [
            pc.PUBLIC_READ,
            pc.PUBLIC_CREATE,
            pc.COMPANION_PET_CREATE,
            pc.COMPANION_PET_READ,
            pc.COMPANION_PET_UPDATE,
            pc.COMPANION_PET_DELETE,
            pc.COMPANION_PET_MEDICAL_UPLOAD,
            pc.SAFETY_TAG_MANAGE,
            pc.VET_CLINIC_READ,
            pc.APPOINTMENT_CREATE,
            pc.APPOINTMENT_READ,
            pc.APPOINTMENT_CANCEL,
            pc.LOST_FOUND_BROADCAST,
        ],
    ),
]


async def _get_or_create_permission(
    session: AsyncSession, permissions_cache: dict[str, Permission], code: str
) -> Permission:
    if code in permissions_cache:
        return permissions_cache[code]
    perm_result = await session.execute(select(Permission).where(Permission.code == code))
    perm = perm_result.scalar_one_or_none()
    if perm is None:
        perm = Permission(code=code, description=code)
        session.add(perm)
        await session.flush()
    permissions_cache[code] = perm
    assert perm is not None
    return perm


async def reconcile_roles(
    session: AsyncSession,
    role_definitions: list[tuple[str, str, bool, list[str]]] = ROLE_DEFINITIONS,
    *,
    verbose: bool = True,
) -> tuple[int, int]:
    """Creates any missing role/permission and grants any permission in
    `role_definitions` that an existing role doesn't already have.

    Additive only - never revokes a permission a role already has, even if
    it's no longer listed (avoids stripping an out-of-band manual grant).
    Does not commit; caller controls the transaction. Returns
    (roles_created, permissions_granted) for callers/tests to assert on.
    """
    permissions_cache: dict[str, Permission] = {}
    created_roles = 0
    granted_total = 0

    for role_name, description, is_system, permission_codes in role_definitions:
        role_result = await session.execute(
            select(Role).options(selectinload(Role.permissions)).where(Role.name == role_name)
        )
        role = role_result.scalar_one_or_none()
        is_new_role = role is None

        if role is None:
            # A brand-new role has no permissions yet by definition - skip
            # reading role.permissions here. On an AsyncSession, accessing an
            # unloaded relationship attribute triggers an implicit lazy load
            # that isn't safe outside an explicit awaited/greenlet context
            # and raises MissingGreenlet.
            role = Role(name=role_name, description=description, is_system=is_system)
            session.add(role)
            await session.flush()
            created_roles += 1
            existing_codes: set[str] = set()
        else:
            existing_codes = {p.code for p in role.permissions}
        granted_here = 0
        for code in permission_codes:
            if code in existing_codes:
                continue
            perm = await _get_or_create_permission(session, permissions_cache, code)
            # Insert the association row directly rather than mutating
            # role.permissions - the same MissingGreenlet risk as reading it
            # applies to appending, since SQLAlchemy needs the collection's
            # current state to reconcile the append.
            session.add(RolePermission(role_id=role.id, permission_id=perm.id))
            granted_here += 1

        await session.flush()
        if granted_here and not is_new_role:
            # role.permissions was loaded (via selectinload above) before we
            # inserted the new RolePermission rows directly, so the ORM's
            # in-memory collection is now stale for anyone re-reading this
            # same identity-mapped Role instance later in the transaction.
            # refresh() is a real awaited call (safe here), unlike an
            # implicit lazy-load triggered by bare attribute access.
            await session.refresh(role, attribute_names=["permissions"])
        granted_total += granted_here

        if not verbose:
            continue
        if is_new_role:
            print(f"  [NEW] {role_name}: created with {granted_here} permission(s)")
        elif granted_here:
            print(
                f"  [SYNC] {role_name}: +{granted_here} permission(s) "
                f"(now {len(permission_codes)} total)"
            )
        else:
            print(f"  [OK] {role_name} (already in sync, {len(permission_codes)} permissions)")

    return created_roles, granted_total


async def backfill_default_role(
    session: AsyncSession,
    *,
    role_name: str = "general_public",
    verbose: bool = True,
) -> int:
    """Assign the default public role to every active user that has no role.

    Some legacy accounts were created before role assignment was enforced at
    registration / OAuth sign-in, leaving them with zero roles. A role-less
    account passes authentication but fails every permission check (e.g.
    ``companion_pet:read``), so the booking screen's "my pets" list returns
    HTTP 403 and the UI renders an empty "No pets yet" state even though the
    user does own pets. Granting the lowest-privilege public role restores
    access without widening any capability. Idempotent: only users with no
    role at all are touched.
    """
    from pawguard.modules.auth.models import Role, User, UserRole

    role = (await session.execute(select(Role).where(Role.name == role_name))).scalars().first()
    if role is None:
        if verbose:
            print(f"  [SKIP] default role '{role_name}' does not exist yet")
        return 0

    orphan_users = (
        (
            await session.execute(
                select(User)
                .where(User.is_active.is_(True), User.deleted_at.is_(None))
                .where(~User.id.in_(select(UserRole.user_id)))
            )
        )
        .scalars()
        .all()
    )

    granted = 0
    for user in orphan_users:
        session.add(UserRole(user_id=user.id, role_id=role.id))
        granted += 1
    await session.flush()

    if verbose:
        if granted:
            print(f"  [FIX] {granted} role-less user(s) granted '{role_name}'")
        else:
            print(f"  [OK] no role-less users need the '{role_name}' role")
    return granted


async def seed_db(label: str, database_url: str) -> None:
    if not database_url:
        print(f"SKIP [{label}]: No database URL configured.")
        return

    print(f"SEED [{label}]: Reconciling roles and permissions in database...")
    engine = create_async_engine(database_url, echo=False, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        created_roles, granted_total = await reconcile_roles(session)
        await session.commit()
        print(
            f"DONE [{label}]: {created_roles} role(s) created, "
            f"{granted_total} permission grant(s) added.\n"
        )

    await engine.dispose()


async def main() -> None:
    settings = get_settings()
    await seed_db("Backend DB", settings.database_url)
    await seed_db("Frontend DB", settings.database_url_frontend)


if __name__ == "__main__":
    asyncio.run(main())
