"""Seed adoptable test dog profiles for frontend integration testing.

Usage:
    uv run python scripts/seed_dogs.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.dog.models import DogProfile, DogStatus, DogGender, DogBreedClassification, DogTemperament

# Import other models to ensure SQLAlchemy resolves foreign key constraints
from pawguard.modules.auth.models import User, Role, Permission
from pawguard.modules.rescue.models import RescueRequest
from pawguard.modules.shelter.models import ShelterFacility, ShelterSection, Kennel
from pawguard.modules.foster.models import FosterProfile

TEST_DOGS = [
    {
        "registration_number": "DOG-2026-0001",
        "name": "Buddy",
        "breed": "Indie Mix",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.MALE,
        "is_spayed_neutered": True,
        "estimated_age": "2 years",
        "age_months": 24,
        "weight": 18.5,
        "color": "Tan/Brown",
        "temperament": DogTemperament.FRIENDLY,
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "status": DogStatus.SHELTER,
    },
    {
        "registration_number": "DOG-2026-0002",
        "name": "Bella",
        "breed": "Labrador Retriever",
        "breed_classification": DogBreedClassification.PURE,
        "gender": DogGender.FEMALE,
        "is_spayed_neutered": True,
        "estimated_age": "1 year 6 months",
        "age_months": 18,
        "weight": 24.2,
        "color": "Golden",
        "temperament": DogTemperament.HIGH_ENERGY,
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "status": DogStatus.SHELTER,
    },
    {
        "registration_number": "DOG-2026-0003",
        "name": "Rocky",
        "breed": "German Shepherd Mix",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.MALE,
        "is_spayed_neutered": False,
        "estimated_age": "3 years",
        "age_months": 36,
        "weight": 28.0,
        "color": "Black & Tan",
        "temperament": DogTemperament.PACK_COMPATIBLE,
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "status": DogStatus.SHELTER,
    },
    {
        "registration_number": "DOG-2026-0004",
        "name": "Luna",
        "breed": "Beagle",
        "breed_classification": DogBreedClassification.PURE,
        "gender": DogGender.FEMALE,
        "is_spayed_neutered": True,
        "estimated_age": "10 months",
        "age_months": 10,
        "weight": 11.3,
        "color": "Tricolor",
        "temperament": DogTemperament.CAT_CHILD_SAFE,
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "status": DogStatus.FOSTERED,
    },
    {
        "registration_number": "DOG-2026-0005",
        "name": "Charlie",
        "breed": "Indie Mix",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.MALE,
        "is_spayed_neutered": True,
        "estimated_age": "4 years",
        "age_months": 48,
        "weight": 16.0,
        "color": "White & Brown",
        "temperament": DogTemperament.TIMID_FEARFUL,
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "status": DogStatus.SHELTER,
    },
]

async def seed_db(label: str, database_url: str) -> None:
    if not database_url:
        print(f"SKIP [{label}]: No database URL configured.")
        return

    print(f"SEEDING [{label}] via URL: {database_url.split('@')[-1] if '@' in database_url else 'sqlite/local'}")
    # Disable prepared statements cache for pgBouncer pooling compat
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        for dog_data in TEST_DOGS:
            stmt = select(DogProfile).where(DogProfile.registration_number == dog_data["registration_number"])
            existing = (await session.execute(stmt)).scalars().first()
            if existing:
                print(f"  [SKIP] Dog {dog_data['registration_number']} ('{dog_data['name']}') already exists.")
                continue

            dog = DogProfile(**dog_data)
            session.add(dog)
            print(f"  [ADD] Dog {dog_data['registration_number']} ('{dog_data['name']}') created.")

        await session.commit()
    await engine.dispose()
    print(f"DONE [{label}]: Test dogs seeded.\n")

async def main() -> None:
    settings = get_settings()
    await seed_db("Backend DB", settings.database_url)

if __name__ == "__main__":
    asyncio.run(main())
