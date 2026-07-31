"""Seed one verified, active test login per PRR role for frontend integration testing.

Safe to re-run — skips users that already exist. Requires
`seed_roles_and_permissions.py` to have run first (roles must already exist).

Usage:
    uv run python scripts/seed_test_users.py

All accounts share the password below. These are TEST credentials only —
never reuse this password scheme in a real production dataset.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import or_ as sa_or
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.core.security import hash_password
from pawguard.modules.auth.models import Role, User

TEST_PASSWORD = "PawGuard@2026"

# (role_name, login email, display name) — role_name must match
# scripts/seed_roles_and_permissions.py ROLE_DEFINITIONS.
#
# NOTE: the domain must NOT be a reserved TLD (.test, .example, .invalid,
# .localhost per RFC 2606) — pydantic's EmailStr/email-validator rejects
# those at the schema layer, so accounts on those domains can never log in
# through the API even though they exist in the database.
TEST_ACCOUNTS: list[tuple[str, str, str]] = [
    ("super_admin", "super.admin@pawguard.com", "Super Administrator"),
    ("rescue_centre_admin", "rescue.admin@pawguard.com", "Rescue Centre Admin"),
    ("rescue_coordinator", "rescue.coordinator@pawguard.com", "Rescue Coordinator"),
    ("rescue_agent", "rescue.agent@pawguard.com", "Rescue Agent"),
    ("veterinarian", "vet@pawguard.com", "Dr. Veterinarian"),
    ("shelter_manager", "shelter.manager@pawguard.com", "Shelter Manager"),
    ("adoption_coordinator", "adoption.coordinator@pawguard.com", "Adoption Coordinator"),
    ("foster_coordinator", "foster.coordinator@pawguard.com", "Foster Coordinator"),
    ("volunteer_coordinator", "volunteer.coordinator@pawguard.com", "Volunteer Coordinator"),
    ("inventory_manager", "inventory.manager@pawguard.com", "Inventory Manager"),
    ("finance_user", "finance.user@pawguard.com", "Finance User"),
    ("volunteer", "volunteer@pawguard.com", "Test Volunteer"),
    ("foster_family", "foster.family@pawguard.com", "Test Foster Family"),
    ("donor", "donor@pawguard.com", "Test Donor"),
    ("general_public", "public.user@pawguard.com", "Test Public User"),
]

LEGACY_EMAIL_DOMAINS = ("@pawguard.test", "@pawguard-qa.com")


async def seed_db(label: str, database_url: str) -> None:
    if not database_url:
        print(f"SKIP [{label}]: No database URL configured.")
        return

    print(f"SEED [{label}]: Seeding test login accounts...")
    engine = create_async_engine(
        database_url, echo=False, connect_args={"statement_cache_size": 0}
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    hashed = hash_password(TEST_PASSWORD)

    async with session_factory() as session:
        legacy_filter = sa_or(*(User.email.like(f"%{d}") for d in LEGACY_EMAIL_DOMAINS))
        legacy = (await session.execute(select(User).where(legacy_filter))).scalars().all()
        for user in legacy:
            print(f"  [CLEANUP] removing legacy account {user.email}")
            await session.delete(user)
        if legacy:
            await session.commit()

        roles_by_name: dict[str, Role] = {}
        for role_name, _, _ in TEST_ACCOUNTS:
            if role_name in roles_by_name:
                continue
            role = (
                await session.execute(select(Role).where(Role.name == role_name))
            ).scalar_one_or_none()
            if role is None:
                print(f"  [SKIP] role '{role_name}' not found — run seed_roles first.")
                continue
            roles_by_name[role_name] = role

        for role_name, email, full_name in TEST_ACCOUNTS:
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing is not None:
                print(f"  [SKIP] {email} already exists.")
                continue

            role = roles_by_name.get(role_name)
            if role is None:
                continue

            user = User(
                email=email,
                full_name=full_name,
                hashed_password=hashed,
                is_active=True,
                is_verified=True,
                mfa_enabled=False,
                roles=[role],
            )
            session.add(user)
            print(f"  [OK] {email}  ({role_name})")

        await session.commit()
        print(f"DONE [{label}]: Test accounts seeded.\n")

    await engine.dispose()


async def main() -> None:
    settings = get_settings()
    await seed_db("Backend DB", settings.database_url)
    await seed_db("Frontend DB", settings.database_url_frontend)

    print("=" * 70)
    print(f"Shared test password for every account below: {TEST_PASSWORD}")
    print("=" * 70)
    for role_name, email, full_name in TEST_ACCOUNTS:
        print(f"  {role_name:24s}  {email:38s}  {full_name}")


if __name__ == "__main__":
    asyncio.run(main())
