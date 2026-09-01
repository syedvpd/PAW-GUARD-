"""Restore soft-deleted vet and foster.family accounts directly in the database.

Bypasses the admin API to avoid the 500 error. Directly sets deleted_at=None,
is_active=True, and hashed_password for both accounts.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.core.security import hash_password
from pawguard.modules.auth import models as auth_models  # noqa: F401
from pawguard.modules.dog import models as dog_models  # noqa: F401
from pawguard.modules.companion_pet import models as companion_pet_models  # noqa: F401
from pawguard.modules.foster import models as foster_models  # noqa: F401
from pawguard.modules.rescue import models as rescue_models  # noqa: F401
from pawguard.modules.shelter import models as shelter_models  # noqa: F401
from pawguard.modules.auth.models import User

TARGET_EMAILS = [
    "vet@pawguard.com",
    "foster.family@pawguard.com",
]
PASSWORD = "PawGuard@2026"


async def fix_accounts() -> None:
    settings = get_settings()
    hashed = hash_password(PASSWORD)
    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        for email in TARGET_EMAILS:
            result = await session.execute(select(User).where(User.email == email.lower()))
            user = result.scalars().first()
            if user is None:
                print(f"  {email}: NOT FOUND — creating new user")
                from pawguard.modules.auth.models import Role, UserRole

                user = User(
                    email=email.lower(),
                    full_name=email.split("@")[0].replace(".", " ").title(),
                    phone=None,
                    hashed_password=hashed,
                    is_active=True,
                    is_verified=True,
                )
                session.add(user)
                await session.flush()
                # Assign the right role
                role_name = "veterinarian" if "vet@" in email else "foster_family"
                role_result = await session.execute(select(Role).where(Role.name == role_name))
                role = role_result.scalars().first()
                if role is not None:
                    session.add(UserRole(user_id=user.id, role_id=role.id))
                    print(f"  {email}: created + assigned role '{role_name}'")
                else:
                    print(f"  {email}: created but role '{role_name}' not found")
            else:
                was_soft_deleted = user.deleted_at is not None
                user.deleted_at = None
                user.is_active = True
                user.hashed_password = hashed
                print(f"  {email}: restored (was_soft_deleted={was_soft_deleted}, id={user.id})")

        await session.commit()
    await engine.dispose()
    print("\nDone. Both accounts now accept password: PawGuard@2026")


if __name__ == "__main__":
    asyncio.run(fix_accounts())
