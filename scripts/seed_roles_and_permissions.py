"""Seed the 15 PRR-defined roles with their module-level permissions.

Safe to re-run — skips roles that already exist.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.auth import permission_codes as pc
from pawguard.modules.auth.models import Permission, Role

# ── Role definitions ─────────────────────────────────────────────────────────
# Each entry: (role_name, description, is_system, [permission_code, …])

ROLE_DEFINITIONS: list[tuple[str, str, bool, list[str]]] = [
    (
        "super_admin",
        "System governance, RBAC management, global configuration, audit review.",
        True,
        [
            pc.SYSTEM_READ, pc.SYSTEM_WRITE, pc.SYSTEM_ADMIN,
            pc.USER_READ, pc.USER_CREATE, pc.USER_UPDATE, pc.USER_DELETE, pc.USER_ASSIGN_ROLE,
            pc.RESCUE_CREATE, pc.RESCUE_READ, pc.RESCUE_UPDATE, pc.RESCUE_DELETE,
            pc.RESCUE_VERIFY, pc.RESCUE_DISPATCH, pc.RESCUE_EXECUTE,
            pc.VEHICLE_READ, pc.VEHICLE_ASSIGN, pc.VEHICLE_UPDATE,
            pc.SHELTER_READ, pc.SHELTER_UPDATE, pc.SHELTER_MANAGE_KENNELS, pc.SHELTER_TRANSFER,
            pc.MEDICAL_CREATE, pc.MEDICAL_READ, pc.MEDICAL_UPDATE, pc.MEDICAL_CLEARANCE, pc.MEDICAL_DELETE,
            pc.ADOPTION_READ, pc.ADOPTION_PROCESS, pc.ADOPTION_APPROVE, pc.ADOPTION_LOCK,
            pc.FOSTER_CREATE, pc.FOSTER_READ, pc.FOSTER_UPDATE, pc.FOSTER_APPROVE,
            pc.VOLUNTEER_CREATE, pc.VOLUNTEER_READ, pc.VOLUNTEER_UPDATE, pc.VOLUNTEER_SCHEDULE,
            pc.INVENTORY_CREATE, pc.INVENTORY_READ, pc.INVENTORY_UPDATE, pc.INVENTORY_DELETE,
            pc.FINANCE_READ, pc.FINANCE_CREATE, pc.FINANCE_RECONCILE,
            pc.DONATION_READ, pc.DONATION_MANAGE,
            pc.PUBLIC_READ, pc.PUBLIC_CREATE,
            pc.AUDIT_READ,
            pc.GRIEVANCE_CREATE, pc.GRIEVANCE_READ,
            pc.GRIEVANCE_UPDATE, pc.GRIEVANCE_ASSIGN, pc.GRIEVANCE_COMMENT,
            pc.NOTIFICATION_READ, pc.NOTIFICATION_MANAGE,
        ],
    ),
    (
        "rescue_centre_admin",
        "Operational strategy, facility oversight, compliance, approvals.",
        True,
        [
            pc.USER_READ, pc.USER_CREATE, pc.USER_UPDATE, pc.USER_ASSIGN_ROLE,
            pc.RESCUE_CREATE, pc.RESCUE_READ, pc.RESCUE_UPDATE, pc.RESCUE_VERIFY, pc.RESCUE_DISPATCH, pc.RESCUE_EXECUTE,
            pc.VEHICLE_READ, pc.VEHICLE_ASSIGN, pc.VEHICLE_UPDATE,
            pc.SHELTER_READ, pc.SHELTER_UPDATE, pc.SHELTER_MANAGE_KENNELS, pc.SHELTER_TRANSFER,
            pc.MEDICAL_READ, pc.MEDICAL_CLEARANCE,
            pc.ADOPTION_READ, pc.ADOPTION_PROCESS, pc.ADOPTION_APPROVE, pc.ADOPTION_LOCK,
            pc.FOSTER_CREATE, pc.FOSTER_READ, pc.FOSTER_UPDATE, pc.FOSTER_APPROVE,
            pc.VOLUNTEER_CREATE, pc.VOLUNTEER_READ, pc.VOLUNTEER_UPDATE, pc.VOLUNTEER_SCHEDULE,
            pc.INVENTORY_READ, pc.INVENTORY_UPDATE,
            pc.FINANCE_READ,
            pc.DONATION_READ,
            pc.PUBLIC_READ, pc.PUBLIC_CREATE,
            pc.AUDIT_READ,
            pc.GRIEVANCE_READ, pc.GRIEVANCE_UPDATE,
            pc.GRIEVANCE_ASSIGN, pc.GRIEVANCE_COMMENT,
            pc.NOTIFICATION_READ,
        ],
    ),
    (
        "rescue_coordinator",
        "Verification of public reports, severity prioritization, field dispatching.",
        True,
        [
            pc.RESCUE_CREATE, pc.RESCUE_READ, pc.RESCUE_UPDATE, pc.RESCUE_VERIFY, pc.RESCUE_DISPATCH,
            pc.VEHICLE_READ, pc.VEHICLE_ASSIGN,
            pc.PUBLIC_READ,
        ],
    ),
    (
        "rescue_agent",
        "Field location, rescue execution, transport log.",
        True,
        [
            pc.RESCUE_READ, pc.RESCUE_EXECUTE,
            pc.VEHICLE_READ,
            pc.PUBLIC_READ,
        ],
    ),
    (
        "veterinarian",
        "Clinical examinations, surgeries, prescriptions, medical clearances.",
        True,
        [
            pc.MEDICAL_CREATE, pc.MEDICAL_READ, pc.MEDICAL_UPDATE, pc.MEDICAL_CLEARANCE,
            pc.SHELTER_READ,
            pc.ADOPTION_READ,
            pc.INVENTORY_READ,
            pc.PUBLIC_READ,
        ],
    ),
    (
        "shelter_manager",
        "Daily care tracking, intake logs, kennel allocation, transfers.",
        True,
        [
            pc.SHELTER_READ, pc.SHELTER_UPDATE, pc.SHELTER_MANAGE_KENNELS, pc.SHELTER_TRANSFER,
            pc.RESCUE_READ,
            pc.MEDICAL_READ,
            pc.ADOPTION_READ,
            pc.INVENTORY_READ,
            pc.PUBLIC_READ,
        ],
    ),
    (
        "adoption_coordinator",
        "Application processing, applicant vetting, interviews, post-adoption audits.",
        True,
        [
            pc.ADOPTION_READ, pc.ADOPTION_PROCESS, pc.ADOPTION_APPROVE, pc.ADOPTION_LOCK,
            pc.PUBLIC_READ,
        ],
    ),
    (
        "foster_coordinator",
        "Foster parent onboarding, home inspection, placement tracking, supply provision.",
        True,
        [
            pc.FOSTER_CREATE, pc.FOSTER_READ, pc.FOSTER_UPDATE, pc.FOSTER_APPROVE,
            pc.INVENTORY_READ,
            pc.PUBLIC_READ,
        ],
    ),
    (
        "volunteer_coordinator",
        "Volunteer registration vetting, activity schedules, shift attendance.",
        True,
        [
            pc.VOLUNTEER_CREATE, pc.VOLUNTEER_READ, pc.VOLUNTEER_UPDATE, pc.VOLUNTEER_SCHEDULE,
            pc.PUBLIC_READ,
        ],
    ),
    (
        "inventory_manager",
        "Stock tracking, orders, expiry enforcement, vendor records.",
        True,
        [
            pc.INVENTORY_CREATE, pc.INVENTORY_READ, pc.INVENTORY_UPDATE, pc.INVENTORY_DELETE,
            pc.PUBLIC_READ,
        ],
    ),
    (
        "finance_user",
        "Expense recording, income reconciliation, donor receipting.",
        True,
        [
            pc.FINANCE_READ, pc.FINANCE_CREATE, pc.FINANCE_RECONCILE,
            pc.DONATION_READ, pc.DONATION_MANAGE,
            pc.PUBLIC_READ,
        ],
    ),
    (
        "volunteer",
        "Duty acceptance, shift check-in/out, activity logging.",
        False,
        [
            pc.VOLUNTEER_READ,
        ],
    ),
    (
        "foster_family",
        "Daily progress reporting, medical symptom uploads, supply requests.",
        False,
        [
            pc.FOSTER_READ,
        ],
    ),
    (
        "donor",
        "Direct contributions, dog sponsorship, tax receipt downloads.",
        False,
        [
            pc.DONATION_READ,
            pc.PUBLIC_READ,
        ],
    ),
    (
        "general_public",
        "Emergency reporting, adoption applications, lost/found postings.",
        False,
        [
            pc.PUBLIC_READ, pc.PUBLIC_CREATE,
        ],
    ),
]


async def seed_db(label: str, database_url: str) -> None:
    if not database_url:
        print(f"SKIP [{label}]: No database URL configured.")
        return

    print(f"SEED [{label}]: Seeding roles and permissions in database...")
    engine = create_async_engine(
        database_url,
        echo=False,
        connect_args={"statement_cache_size": 0}
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        existing_count = (await session.execute(select(Role).limit(1))).scalar_one_or_none()
        if existing_count is not None:
            print(f"Roles already seeded in [{label}] — skipping.")
            await engine.dispose()
            return

        permissions_cache: dict[str, Permission] = {}

        for role_name, description, is_system, permission_codes in ROLE_DEFINITIONS:
            role_perms = []
            for code in permission_codes:
                if code in permissions_cache:
                    perm = permissions_cache[code]
                else:
                    perm_result = await session.execute(
                        select(Permission).where(Permission.code == code)
                    )
                    perm_db = perm_result.scalar_one_or_none()
                    if perm_db is None:
                        perm = Permission(code=code, description=code)
                        session.add(perm)
                        await session.flush()
                    else:
                        perm = perm_db
                    permissions_cache[code] = perm
                role_perms.append(perm)

            role = Role(
                name=role_name,
                description=description,
                is_system=is_system,
                permissions=role_perms
            )
            session.add(role)
            await session.flush()

            print(f"  [OK] {role_name} ({len(permission_codes)} permissions)")

        await session.commit()
        print(f"DONE [{label}]: Roles seeded successfully.\n")

    await engine.dispose()


async def main() -> None:
    settings = get_settings()
    await seed_db("Backend DB", settings.database_url)
    await seed_db("Frontend DB", settings.database_url_frontend)


if __name__ == "__main__":
    asyncio.run(main())
