import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from pawguard.core.config import get_settings


async def trace_pets():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.connect() as conn:
        print("=== 1. ALL DOG PROFILES (Dog Master) ===")
        dogs = await conn.execute(
            text("""
            SELECT id, name, breed, status, gender, is_adoptable, deleted_at, created_at, updated_at
            FROM dog_profiles
            ORDER BY created_at ASC
        """)
        )
        all_dogs = [dict(r._mapping) for r in dogs.fetchall()]
        for d in all_dogs:
            print(d)
        print(f"Total dogs in master: {len(all_dogs)}")

        print("\n=== 2. ALL COMPANION PETS ===")
        cpets = await conn.execute(
            text("""
            SELECT id, owner_id, original_dog_id, name, breed, sex, is_scan_enabled, deleted_at, created_at, updated_at
            FROM companion_pets
            ORDER BY created_at ASC
        """)
        )
        all_cpets = [dict(r._mapping) for r in cpets.fetchall()]
        for c in all_cpets:
            if "julie" in c["name"].lower() or "zeus" in c["name"].lower():
                print("MATCH CPET:", c)
        print(f"Total companion pets: {len(all_cpets)}")

        print("\n=== 3. ALL SAFETY TAGS (pet_safety_tags) ===")
        tags = await conn.execute(
            text("""
            SELECT id, dog_id, pet_id, token_prefix, token_hash, is_active, scan_count, last_scanned_at, deleted_at, created_at
            FROM pet_safety_tags
            ORDER BY created_at ASC
        """)
        )
        all_tags = [dict(r._mapping) for r in tags.fetchall()]
        for t in all_tags:
            print(t)
        print(f"Total safety tags: {len(all_tags)}")

        print("\n=== 4. USERS ===")
        users = await conn.execute(
            text("""
            SELECT id, email, full_name FROM users
        """)
        )
        all_users = [dict(r._mapping) for r in users.fetchall()]
        for u in all_users:
            print(u)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(trace_pets())
