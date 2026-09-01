"""Seed script for default adoptable dogs in the adoption catalog.

Populates the dog_profiles table with adoptable dogs that have external
gallery image URLs so the public adoption directory listing renders
images out-of-the-box. Re-running this script is idempotent: existing
dogs (matched by registration_number) are skipped.

Usage:
    .venv\\Scripts\\python.exe scripts/seed_dogs.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.auth import models as auth_models  # noqa: F401  registers User for AuditMixin FKs
from pawguard.modules.companion_pet import models as companion_pet_models  # noqa: F401  registers SafetyTag
from pawguard.modules.foster import models as foster_models  # noqa: F401  registers foster_profiles
from pawguard.modules.rescue import models as rescue_models  # noqa: F401  registers rescue_requests
from pawguard.modules.shelter import models as shelter_models  # noqa: F401  registers shelter_sections
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
        "image_urls": [
            "https://images.dog.ceo/breeds/retriever-indian/n02110185_10369.jpg",
            "https://images.dog.ceo/breeds/retriever-indian/n02110185_11716.jpg",
            "https://images.dog.ceo/breeds/retriever-indian/n02110185_13978.jpg",
        ],
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
        "image_urls": [
            "https://images.dog.ceo/breeds/labrador/n02099712_4497.jpg",
            "https://images.dog.ceo/breeds/labrador/n02099712_5633.jpg",
        ],
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
        "image_urls": [
            "https://images.dog.ceo/breeds/germanshepherd/n02106625_22496.jpg",
            "https://images.dog.ceo/breeds/germanshepherd/n02106625_25931.jpg",
        ],
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
        "image_urls": [
            "https://images.dog.ceo/breeds/beagle/n02088364_12628.jpg",
            "https://images.dog.ceo/breeds/beagle/n02088364_15940.jpg",
        ],
    },
    {
        "registration_number": "DOG-2026-0005",
        "name": "Max",
        "breed": "Golden Retriever",
        "breed_classification": DogBreedClassification.PURE,
        "gender": DogGender.MALE,
        "estimated_age": "4 years",
        "age_months": 48,
        "weight": 30.0,
        "color": "Golden",
        "temperament": DogTemperament.FRIENDLY,
        "status": DogStatus.SHELTER,
        "is_adoptable": True,
        "is_spayed_neutered": True,
        "is_quarantine_passed": True,
        "image_urls": [
            "https://images.dog.ceo/breeds/retriever-golden/n02099601_3787.jpg",
            "https://images.dog.ceo/breeds/retriever-golden/n02099601_4922.jpg",
        ],
    },
    {
        "registration_number": "DOG-2026-0006",
        "name": "Daisy",
        "breed": "Indie Mix",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.FEMALE,
        "estimated_age": "6 months",
        "age_months": 6,
        "weight": 8.5,
        "color": "Brown and White",
        "temperament": DogTemperament.CAT_CHILD_SAFE,
        "status": DogStatus.SHELTER,
        "is_adoptable": True,
        "is_spayed_neutered": False,
        "is_quarantine_passed": True,
        "image_urls": [
            "https://images.dog.ceo/breeds/cavalier-king-charles-spaniel/n02085711_3676.jpg",
            "https://images.dog.ceo/breeds/cavalier-king-charles-spaniel/n02085711_4051.jpg",
        ],
    },
    {
        "registration_number": "DOG-2026-0007",
        "name": "Shadow",
        "breed": "Indie Mix",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.MALE,
        "estimated_age": "5 years",
        "age_months": 60,
        "weight": 22.0,
        "color": "Black",
        "temperament": DogTemperament.PACK_COMPATIBLE,
        "status": DogStatus.SHELTER,
        "is_adoptable": True,
        "is_spayed_neutered": True,
        "is_quarantine_passed": True,
        "image_urls": [
            "https://images.dog.ceo/breeds/labrador/n02099712_7229.jpg",
            "https://images.dog.ceo/breeds/labrador/n02099712_7414.jpg",
        ],
    },
    {
        "registration_number": "DOG-2026-0008",
        "name": "Maya",
        "breed": "Indie Pariah",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.FEMALE,
        "estimated_age": "1.5 years",
        "age_months": 18,
        "weight": 15.0,
        "color": "White and Brown",
        "temperament": DogTemperament.FRIENDLY,
        "status": DogStatus.SHELTER,
        "is_adoptable": True,
        "is_spayed_neutered": True,
        "is_quarantine_passed": True,
        "image_urls": [
            "https://images.dog.ceo/breeds/poodle-standard/n02113799_4693.jpg",
            "https://images.dog.ceo/breeds/poodle-standard/n02113799_4854.jpg",
        ],
    },
    {
        "registration_number": "DOG-2026-0009",
        "name": "Tiger",
        "breed": "Indie Mix",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.MALE,
        "estimated_age": "2 years",
        "age_months": 24,
        "weight": 20.0,
        "color": "Brindle",
        "temperament": DogTemperament.AGGRESSIVE,
        "status": DogStatus.SHELTER,
        "is_adoptable": True,
        "is_spayed_neutered": True,
        "is_quarantine_passed": True,
        "image_urls": [
            "https://images.dog.ceo/breeds/boxer/n02108089_6165.jpg",
            "https://images.dog.ceo/breeds/boxer/n02108089_6724.jpg",
        ],
    },
    {
        "registration_number": "DOG-2026-0010",
        "name": "Coco",
        "breed": "Pomeranian",
        "breed_classification": DogBreedClassification.PURE,
        "gender": DogGender.FEMALE,
        "estimated_age": "3 years",
        "age_months": 36,
        "weight": 4.5,
        "color": "Cream",
        "temperament": DogTemperament.FRIENDLY,
        "status": DogStatus.FOSTERED,
        "is_adoptable": True,
        "is_spayed_neutered": True,
        "is_quarantine_passed": True,
        "image_urls": [
            "https://images.dog.ceo/breeds/pomeranian/n02112018_6584.jpg",
            "https://images.dog.ceo/breeds/pomeranian/n02112018_7113.jpg",
        ],
    },
]

ADOPTED_SEED_DOGS = [
    {
        "registration_number": "DOG-2026-0011",
        "name": "Oscar",
        "breed": "Golden Retriever Mix",
        "breed_classification": DogBreedClassification.MIX,
        "gender": DogGender.MALE,
        "estimated_age": "2 years",
        "age_months": 24,
        "weight": 24.0,
        "color": "Golden Tan",
        "temperament": DogTemperament.FRIENDLY,
        "status": DogStatus.ADOPTED,
        "is_adoptable": False,
        "is_spayed_neutered": True,
        "is_quarantine_passed": True,
        "image_urls": [
            "https://images.dog.ceo/breeds/retriever-golden/n02099601_1028.jpg",
        ],
    },
]


async def seed_dogs() -> None:
    from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
    from pawguard.modules.auth.models import User

    settings = get_settings()
    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        # 1. Ensure test adopter user exists
        adopter_user = (
            (await session.execute(select(User).where(User.email == "adopter@pawguard.org")))
            .scalars()
            .first()
        )

        if not adopter_user:
            adopter_user = User(
                id=uuid.uuid4(),
                email="adopter@pawguard.org",
                full_name="Syed Mohammed Zubair Khadri",
                phone="+91 98765 43210",
                hashed_password="pbkdf2_sha256$test$hashedpassword",
                is_active=True,
                is_verified=True,
            )
            session.add(adopter_user)
            await session.flush()
        else:
            adopter_user.full_name = "Syed Mohammed Zubair Khadri"
            adopter_user.phone = "+91 98765 43210"

        # 2. Seed dogs
        all_seed = TEST_DOGS + ADOPTED_SEED_DOGS
        adopted_dog_obj = None
        for dog_data in all_seed:
            existing = (
                (
                    await session.execute(
                        select(DogProfile).where(
                            DogProfile.registration_number == dog_data["registration_number"]
                        )
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                existing.image_urls = dog_data.get("image_urls")
                existing.status = dog_data.get("status", existing.status)
                if dog_data["registration_number"] == "DOG-2026-0011":
                    adopted_dog_obj = existing
                continue
            dog = DogProfile(
                id=uuid.uuid4(),
                **dog_data,
            )
            session.add(dog)
            if dog_data["registration_number"] == "DOG-2026-0011":
                adopted_dog_obj = dog

        await session.flush()

        # 3. Ensure active COMPLETED adoption record exists for DOG-2026-0011 (Oscar)
        if adopted_dog_obj:
            existing_app = (
                (
                    await session.execute(
                        select(AdoptionApplication).where(
                            AdoptionApplication.dog_id == adopted_dog_obj.id,
                            AdoptionApplication.adopter_id == adopter_user.id,
                        )
                    )
                )
                .scalars()
                .first()
            )

            if not existing_app:
                adoption_app = AdoptionApplication(
                    id=uuid.uuid4(),
                    dog_id=adopted_dog_obj.id,
                    adopter_id=adopter_user.id,
                    residential_status="owned",
                    has_landlord_approval=True,
                    has_yard_fence=True,
                    household_members_count=3,
                    status=AdoptionStatus.COMPLETED,
                )
                session.add(adoption_app)
            else:
                existing_app.status = AdoptionStatus.COMPLETED

        await session.commit()
    await engine.dispose()
    print(f"Seed adoptable & adopted dogs completed ({len(TEST_DOGS)} dogs).")


if __name__ == "__main__":
    asyncio.run(seed_dogs())
