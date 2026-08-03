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
