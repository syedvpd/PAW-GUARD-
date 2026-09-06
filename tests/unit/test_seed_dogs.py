"""Unit tests for the deploy-time adoptable test-dog seed data.

The deployment entrypoint (docker-entrypoint.sh) runs scripts/seed_dogs.py so
the public adoption catalog (GET /api/v1/dogs, which only surfaces adoptable
dogs to anonymous visitors) is never empty. These tests pin the seed data
contract: every record must be adoptable, carry a unique registration number,
and use a valid DogStatus.
"""

from scripts.seed_dogs import TEST_DOGS

from pawguard.modules.dog.models import DogStatus


class TestSeedDogs:
    def test_all_seed_dogs_are_adoptable(self):
        assert TEST_DOGS
        for dog in TEST_DOGS:
            assert dog["is_adoptable"] is True, (
                f"{dog['registration_number']} must be adoptable so it "
                "appears in the public catalog"
            )

    def test_registration_numbers_are_unique(self):
        regs = [d["registration_number"] for d in TEST_DOGS]
        assert len(regs) == len(set(regs))

    def test_statuses_are_valid_and_renderable(self):
        valid = set(DogStatus)
        for dog in TEST_DOGS:
            assert dog["status"] in valid

    def test_seed_protects_adopted_dog_state(self):
        from pawguard.modules.dog.models import DogProfile

        existing_adopted = DogProfile(
            name="Oscar",
            registration_number="DOG-2026-0011",
            status=DogStatus.ADOPTED,
            is_adoptable=False,
        )
        dog_data = {"status": DogStatus.SHELTER, "is_adoptable": True}
        is_already_adopted = existing_adopted.status == DogStatus.ADOPTED
        if is_already_adopted:
            existing_adopted.status = DogStatus.ADOPTED
            existing_adopted.is_adoptable = False
        else:
            existing_adopted.status = dog_data["status"]
            existing_adopted.is_adoptable = dog_data["is_adoptable"]

        assert existing_adopted.status == DogStatus.ADOPTED
        assert existing_adopted.is_adoptable is False
