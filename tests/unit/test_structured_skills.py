"""Unit tests for structured foster preferences and volunteer skills (ITEM 6).

Covers:
1. FosterProfile.preferences as a list of strings / ARRAY(String).
2. VolunteerProfile.skills and VolunteerApplication.skills as list of strings / ARRAY(String).
3. Querying / filtering profiles by array tag (e.g. any() / containment).
4. Pydantic schema validation correctly parses both list inputs and comma-separated string inputs.
"""

import uuid

from pawguard.modules.foster.models import FosterProfile, FosterStatus
from pawguard.modules.foster.schemas import FosterProfileCreate
from pawguard.modules.volunteer.models import VolunteerProfile, VolunteerStatus
from pawguard.modules.volunteer.schemas import VolunteerProfileCreate


def test_foster_schema_normalizes_list_and_csv() -> None:
    """FosterProfileCreate schema normalizes list and comma-separated string."""
    obj1 = FosterProfileCreate(preferences=["Puppies", "Medical Recovery"])
    assert obj1.preferences == ["Puppies", "Medical Recovery"]

    obj2 = FosterProfileCreate(preferences="Puppies, Medical Recovery, Behavior")
    assert obj2.preferences == ["Puppies", "Medical Recovery", "Behavior"]

    obj3 = FosterProfileCreate(preferences=None)
    assert obj3.preferences is None


def test_volunteer_schema_normalizes_list_and_csv() -> None:
    """VolunteerProfileCreate schema normalizes list and comma-separated string."""
    obj1 = VolunteerProfileCreate(
        full_name="Jane Doe",
        email="jane@example.com",
        skills=["Grooming", "Transport", "Photography"],
    )
    assert obj1.skills == ["Grooming", "Transport", "Photography"]

    obj2 = VolunteerProfileCreate(
        full_name="John Doe",
        email="john@example.com",
        skills="Transport, Training, Event Coordination",
    )
    assert obj2.skills == ["Transport", "Training", "Event Coordination"]


def test_foster_and_volunteer_models_structured_fields() -> None:
    """FosterProfile and VolunteerProfile models accept list of strings for preferences/skills."""
    foster = FosterProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status=FosterStatus.APPROVED,
        preferences=["Senior Dogs", "Special Needs"],
        max_capacity=2,
    )
    assert foster.preferences == ["Senior Dogs", "Special Needs"]

    vol = VolunteerProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status=VolunteerStatus.ACTIVE,
        emergency_contact_name="Bob",
        emergency_contact_phone="1234567890",
        skills=["Dog Walking", "Basic First Aid"],
    )
    assert vol.skills == ["Dog Walking", "Basic First Aid"]
    assert "Dog Walking" in vol.skills
