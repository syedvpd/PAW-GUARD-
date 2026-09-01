"""Seed found-animal ("found roaming companion") reports.

The public Lost & Found directory split into two tabs: Lost Pets and Found
Animals. Lost Pets is populated, but Found Animals was empty in production
(0 rows in ``found_reports``), so the "Found Animals" tab rendered the empty
state even though the listing endpoint works. This seeds a realistic set of
found-animal reports (attributed to reporter accounts) so the tab has
content to display.

Usage:
    .venv\\Scripts\\python.exe scripts/seed_found_reports.py
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.core.security import hash_password
from pawguard.modules.auth.models import Role, User, UserRole
from pawguard.modules.lost_found.models import FoundReport, Species

PASSWORD = "PawGuard@2026"

# Reporter accounts that "found" these animals. Each gets the public role so
# their identity is masked in the public listing (per PRR §6.1).
REPORTERS = [
    {"full_name": "Ravi Teja", "email": "found.reporter.ravi@pawguard.org"},
    {"full_name": "Anjali Nair", "email": "found.reporter.anjali@pawguard.org"},
    {"full_name": "Karthik Reddy", "email": "found.reporter.karthik@pawguard.org"},
]

# (reporter_index, species, breed_observed, color_observed, location, found_days_ago, photo)
FOUND = [
    (
        0,
        Species.DOG,
        "Indian Pariah",
        "Tan / brown with white chest",
        "Near Gachibowli Flyover, Hyderabad",
        4,
        "https://images.unsplash.com/photo-1561037404-61cd46aa615b?auto=format&fit=crop&w=600&q=80",
    ),
    (
        0,
        Species.DOG,
        "Labrador mix",
        "Black",
        "DLF Road, Gachibowli, Hyderabad",
        9,
        "https://images.unsplash.com/photo-1601758228041-f3b2795255f1?auto=format&fit=crop&w=600&q=80",
    ),
    (
        1,
        Species.CAT,
        "Domestic Shorthair",
        "Grey tabby",
        "Banjara Hills Road No. 12, Hyderabad",
        2,
        "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?auto=format&fit=crop&w=600&q=80",
    ),
    (
        1,
        Species.DOG,
        "Indian Pariah",
        "White with black patches",
        "Jubilee Hills Check Post, Hyderabad",
        14,
        "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?auto=format&fit=crop&w=600&q=80",
    ),
    (
        2,
        Species.DOG,
        "Street pup",
        "Golden brown",
        "Kondapur Market, Hyderabad",
        6,
        "https://images.unsplash.com/photo-1543466835-00a7907e9de1?auto=format&fit=crop&w=600&q=80",
    ),
    (
        2,
        Species.CAT,
        "Domestic Shorthair",
        "Calico (white/orange/black)",
        "Madhapur, Hyderabad",
        1,
        "https://images.unsplash.com/photo-1495360010541-f48722b34f7d?auto=format&fit=crop&w=600&q=80",
    ),
    (
        1,
        Species.DOG,
        "Pomeranian",
        "Cream / off-white",
        "Hitech City Metro, Hyderabad",
        21,
        "https://images.unsplash.com/photo-1583511656824-1c6c3ee036f8?auto=format&fit=crop&w=600&q=80",
    ),
    (
        0,
        Species.OTHER,
        "Rabbit (domestic)",
        "White",
        "Kukatpally Housing Board, Hyderabad",
        11,
        "https://images.unsplash.com/photo-1585110396000-c9ffd4e4b308?auto=format&fit=crop&w=600&q=80",
    ),
]


async def main() -> None:
    settings = get_settings()
    print("=========================================================")
    print(" Seeding Found-Animal Reports (Lost & Found directory)")
    print("=========================================================")

    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    hashed_pw = hash_password(PASSWORD)

    async with session_factory() as session:
        public_role = (
            (await session.execute(select(Role).where(Role.name == "general_public")))
            .scalars()
            .first()
        )
        if public_role is None:
            public_role = Role(
                id=uuid.uuid4(), name="general_public", description="Public site user"
            )
            session.add(public_role)
            await session.flush()

        # Ensure reporter accounts exist with the public role.
        reporter_ids: list[uuid.UUID] = []
        for rep in REPORTERS:
            existing = (
                (await session.execute(select(User).where(User.email == rep["email"])))
                .scalars()
                .first()
            )
            if existing:
                reporter_ids.append(existing.id)
                continue
            user = User(
                id=uuid.uuid4(),
                email=rep["email"],
                full_name=rep["full_name"],
                hashed_password=hashed_pw,
                is_active=True,
                is_verified=True,
            )
            session.add(user)
            await session.flush()
            reporter_ids.append(user.id)
            session.add(UserRole(user_id=user.id, role_id=public_role.id))

        # Seed found reports (skip exact duplicates by location + found_at day).
        created = 0
        for idx, species, breed, color, location, days_ago, photo in FOUND:
            found_at = datetime.now(UTC) - timedelta(days=days_ago)
            dup = (
                (
                    await session.execute(
                        select(FoundReport).where(
                            FoundReport.location_address == location,
                            FoundReport.found_at == found_at,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if dup:
                continue
            session.add(
                FoundReport(
                    id=uuid.uuid4(),
                    user_id=reporter_ids[idx],
                    species=species,
                    breed_observed=breed,
                    color_observed=color,
                    location_address=location,
                    found_at=found_at,
                    status="active",
                    photo_url=photo,
                )
            )
            created += 1

        await session.commit()

    await engine.dispose()
    print(f"  Found reports created : {created}")
    print(f"  Password for reporters: {PASSWORD}")
    print("  SUCCESS: Found-animal reports live in the database!")


if __name__ == "__main__":
    asyncio.run(main())
