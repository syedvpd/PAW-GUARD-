"""Seed script for default adoptable dogs in the adoption catalog."""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.dog.models import (
    DogBreedClassification,
    DogGender,
    DogProfile,
    DogStatus,
    DogTemperament,
)

TEST_DOGS = [
    {
        "registration_number": "DOG-2026-0001",
        "name": "Bruno",
        "breed": "Indie Mix",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.MALE,
        "estimated_age": "2 years",
        "age_months": 24,
        "weight": 18.5,
        "color": "Tan and White",
        "temperament": DogTemperament.FRIENDLY,
        "status": DogStatus.SHELTER,
        "is_adoptable": True,
        "is_spayed_neutered": True,
        "is_quarantine_passed": True,
    },
    {
        "registration_number": "DOG-2026-0002",
        "name": "Bella",
        "breed": "Labrador Retriever",
        "breed_classification": DogBreedClassification.PURE,
        "gender": DogGender.FEMALE,
        "estimated_age": "1 year",
        "age_months": 12,
        "weight": 22.0,
        "color": "Golden",
        "temperament": DogTemperament.FRIENDLY,
        "status": DogStatus.SHELTER,
        "is_adoptable": True,
        "is_spayed_neutered": True,
        "is_quarantine_passed": True,
    },
    {
        "registration_number": "DOG-2026-0003",
        "name": "Rocky",
        "breed": "German Shepherd Mix",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.MALE,
        "estimated_age": "3 years",
        "age_months": 36,
        "weight": 28.0,
        "color": "Black and Tan",
        "temperament": DogTemperament.PACK_COMPATIBLE,
        "status": DogStatus.FOSTERED,
        "is_adoptable": True,
        "is_spayed_neutered": True,
        "is_quarantine_passed": True,
    },
    {
        "registration_number": "DOG-2026-0004",
        "name": "Luna",
        "breed": "Indie Pariah",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.FEMALE,
        "estimated_age": "8 months",
        "age_months": 8,
        "weight": 12.0,
        "color": "Fawn",
        "temperament": DogTemperament.CAT_CHILD_SAFE,
        "status": DogStatus.SHELTER,
        "is_adoptable": True,
        "is_spayed_neutered": True,
        "is_quarantine_passed": True,
    },
]


async def seed_dogs() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        for dog_data in TEST_DOGS:
            existing = (
                await session.execute(
                    select(DogProfile).where(
                        DogProfile.registration_number == dog_data["registration_number"]
                    )
                )
            ).scalars().first()
            if not existing:
                dog = DogProfile(
                    id=uuid.uuid4(),
                    **dog_data,
                )
                session.add(dog)
        await session.commit()
    await engine.dispose()
    print("Seed adoptable dogs completed.")


if __name__ == "__main__":
    asyncio.run(seed_dogs())
