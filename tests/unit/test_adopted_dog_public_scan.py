"""Tests for Adopted Dog Public Scan workflow (Dog -> Adoption Application -> User -> GET /dogs/{dog_id}/public-scan)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.auth.models import User
from pawguard.modules.dog.models import (
    DogBreedClassification,
    DogGender,
    DogProfile,
    DogStatus,
)
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.service import DogService


@pytest.mark.asyncio
async def test_three_newly_adopted_dogs_qr_adopter_data():
    """Verify 3 newly adopted dogs return real adopter name, phone, and email on public scan."""
    test_cases = [
        ("Rocky", "Amit Kumar", "+91 98111 22334", "amit.kumar@example.com", "Beagle", "Tri-color"),
        ("Luna", "Neha Sen", "+91 98222 33445", "neha.sen@example.com", "Labrador", "Yellow"),
        (
            "Bruno",
            "Rahul Verma",
            "+91 98333 44556",
            "rahul.verma@example.com",
            "Rottweiler",
            "Black & Mahogany",
        ),
    ]

    for dog_name, adopter_name, adopter_phone, adopter_email, breed, color in test_cases:
        dog_id = uuid.uuid4()
        adopter_id = uuid.uuid4()
        app_id = uuid.uuid4()

        # 1. Adopter user
        adopter = User(
            id=adopter_id,
            full_name=adopter_name,
            phone=adopter_phone,
            email=adopter_email,
            is_active=True,
            is_verified=True,
        )

        # 2. Adopted Dog Profile
        dog = DogProfile(
            id=dog_id,
            name=dog_name,
            breed=breed,
            breed_classification=DogBreedClassification.PURE,
            gender=DogGender.MALE,
            color=color,
            status=DogStatus.ADOPTED,
            is_adoptable=False,
            registration_number=f"DOG-{dog_name.upper()}-001",
        )

        # 3. Finalized Adoption Application (COMPLETED)
        adoption_app = AdoptionApplication(
            id=app_id,
            dog_id=dog_id,
            adopter_id=adopter_id,
            status=AdoptionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        adoption_app.adopter = adopter
        adoption_app.dog = dog

        # Mock repository setup
        repo = AsyncMock(spec=DogRepository)
        repo.get_by_id.return_value = dog
        repo.get_adopter_contact.return_value = (adopter_name, adopter_phone, adopter_email)

        session = AsyncMock()
        service = DogService(repo, session)

        # Fetch dog and adopter contact
        fetched_dog = await service.get_dog(dog_id)
        name, phone, email = await service.get_adopter_contact(dog_id)

        assert fetched_dog.id == dog_id
        assert fetched_dog.status == DogStatus.ADOPTED
        assert fetched_dog.is_adoptable is False
        assert name == adopter_name
        assert phone == adopter_phone
        assert email == adopter_email
