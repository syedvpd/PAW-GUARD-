"""Unit tests for DogService with mocked DogRepository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from pawguard.core.pagination import PageParams
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams
from pawguard.modules.dog.models import (
    DogActivityEventType,
    DogActivityLog,
    DogBreedClassification,
    DogEarShape,
    DogProfile,
    DogStatus,
    DogTailType,
    DogWeightLog,
)
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.dog.schemas import (
    DogProfileCreate,
    DogProfileUpdate,
    DogWeightLogCreate,
)
from pawguard.modules.dog.service import DogService, _parse_age_months
from pawguard.services.audit_service import AuditService


def _make_dog(**kw):
    now = datetime.now(UTC)
    vals = dict(
        is_spayed_neutered=False, is_quarantine_passed=False,
        breed_classification=DogBreedClassification.UNKNOWN,
        created_at=now, updated_at=now,
    )
    vals.update(kw)
    return DogProfile(**vals)


class TestDogService:
    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock(spec=DogRepository)
        repo._session = AsyncMock()
        # register_dog pre-checks both uniqueness fast paths; default to "free"
        # so existing tests don't trip the collision branches.
        repo.get_by_registration.return_value = None
        repo.get_by_microchip.return_value = None
        return repo

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock(spec=AuditService)

    @pytest.fixture
    def service(self, mock_repo, mock_audit):
        return DogService(mock_repo, mock_audit)

    @pytest.mark.asyncio
    async def test_register_dog(self, service, mock_repo, mock_audit):
        dog_id = uuid.uuid4()
        mock_repo.create.return_value = DogProfile(
            id=dog_id, registration_number="DOG-2026-1234", name="Buddy", breed="Labrador",
            gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        payload = DogProfileCreate(name="Buddy", breed="Labrador", gender="male")
        result = await service.register_dog(payload, actor_id=uuid.uuid4())
        assert result.name == "Buddy"
        assert result.registration_number.startswith("DOG-")

    @pytest.mark.asyncio
    async def test_get_dog_found(self, service, mock_repo):
        dog_id = uuid.uuid4()
        mock_repo.get_by_id.return_value = _make_dog(
            id=dog_id, registration_number="DOG-2026-0001", name="Max", breed="Beagle",
            gender="male", status=DogStatus.SHELTER, is_adoptable=True,
        )
        result = await service.get_dog(dog_id)
        assert result.name == "Max"

    @pytest.mark.asyncio
    async def test_get_dog_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError, match="Dog profile not found"):
            await service.get_dog(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_dog(self, service, mock_repo):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0002", name="Old", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_by_id.return_value = dog
        payload = DogProfileUpdate(name="Updated")
        result = await service.update_dog(dog_id, payload, actor_id=uuid.uuid4())
        assert result.name == "Updated"

    @pytest.mark.asyncio
    async def test_update_dog_cannot_grant_is_adoptable(self, service, mock_repo):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0002", name="Old", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_by_id.return_value = dog
        payload = DogProfileUpdate(is_adoptable=True)
        with pytest.raises(ForbiddenError, match="medical clearance"):
            await service.update_dog(dog_id, payload, actor_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_register_dog_ignores_is_adoptable_payload(self, service, mock_repo, mock_audit):
        dog_id = uuid.uuid4()
        mock_repo.create.return_value = DogProfile(
            id=dog_id, registration_number="DOG-2026-1234", name="Buddy", breed="Labrador",
            gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        payload = DogProfileCreate(name="Buddy", breed="Labrador", gender="male", is_adoptable=True)
        await service.register_dog(payload, actor_id=uuid.uuid4())
        created_dog = mock_repo.create.call_args[0][0]
        assert created_dog.is_adoptable is False

    @pytest.mark.asyncio
    async def test_update_dog_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.update_dog(uuid.uuid4(), DogProfileUpdate(name="x"))

    @pytest.mark.asyncio
    async def test_update_dog_status(self, service, mock_repo):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0003", name="Rex", breed="Mix",
            gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        mock_repo.get_by_id.return_value = dog
        result = await service.update_dog_status(dog_id, DogStatus.SHELTER, actor_id=uuid.uuid4())
        assert result.status == DogStatus.SHELTER

    @pytest.mark.asyncio
    async def test_soft_delete_dog(self, service, mock_repo):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0004", name="Rocky", breed="Mix",
            gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_by_id.return_value = dog
        await service.soft_delete_dog(dog_id, actor_id=uuid.uuid4())
        assert dog.deleted_at is not None

    @pytest.mark.asyncio
    async def test_soft_delete_dog_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.soft_delete_dog(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_list_dogs_paginated(self, service, mock_repo):
        dog = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-0005", name="Oscar",
            breed="Poodle", gender="male", status=DogStatus.SHELTER, is_adoptable=True,
        )
        mock_repo.list_paginated.return_value = ([dog], 1)
        page = PageParams(page=1, page_size=20)
        sort = SortParams(sort_by="name", sort_order="asc")
        result = await service.list_dogs_paginated(page, sort)
        assert isinstance(result, PaginatedResponse)
        assert len(result.data) == 1
        assert result.meta.total == 1

    @pytest.mark.asyncio
    async def test_bulk_update_status(self, service, mock_repo):
        ids = [uuid.uuid4(), uuid.uuid4()]
        mock_repo.bulk_update_status.return_value = 2
        mock_repo.list_by_ids.return_value = [
            _make_dog(id=ids[0], registration_number="DOG-2026-0001", name="A",
                      breed="Mix", gender="male", status=DogStatus.SHELTER, is_adoptable=False),
            _make_dog(id=ids[1], registration_number="DOG-2026-0002", name="B",
                      breed="Mix", gender="female", status=DogStatus.SHELTER, is_adoptable=False),
        ]
        count = await service.bulk_update_status(ids, DogStatus.ADOPTED, actor_id=uuid.uuid4())
        assert count == 2
        # One timeline entry per updated dog, keyed on their real ids.
        logged_ids = [c[0][0].dog_id for c in mock_repo.create_activity.call_args_list]
        assert sorted(str(i) for i in logged_ids) == sorted(str(i) for i in ids)

    @pytest.mark.asyncio
    async def test_bulk_update_status_skips_unknown_ids(self, service, mock_repo):
        """Bulk timeline entries must not be recorded for ids that don't exist
        (dangling dog_id FK would raise IntegrityError 500)."""
        known = uuid.uuid4()
        unknown = uuid.uuid4()
        mock_repo.bulk_update_status.return_value = 1
        mock_repo.list_by_ids.return_value = [
            _make_dog(id=known, registration_number="DOG-2026-0001", name="A",
                      breed="Mix", gender="male", status=DogStatus.SHELTER, is_adoptable=False),
        ]
        await service.bulk_update_status(
            [known, unknown], DogStatus.ADOPTED, actor_id=uuid.uuid4()
        )
        assert mock_repo.create_activity.await_count == 1
        logged = mock_repo.create_activity.call_args[0][0]
        assert logged.dog_id == known

    @pytest.mark.asyncio
    async def test_bulk_soft_delete(self, service, mock_repo):
        ids = [uuid.uuid4(), uuid.uuid4()]
        mock_repo.bulk_soft_delete.return_value = 2
        mock_repo.list_by_ids.return_value = [
            _make_dog(id=ids[0], registration_number="DOG-2026-0001", name="A",
                      breed="Mix", gender="male", status=DogStatus.SHELTER, is_adoptable=False),
            _make_dog(id=ids[1], registration_number="DOG-2026-0002", name="B",
                      breed="Mix", gender="female", status=DogStatus.SHELTER, is_adoptable=False),
        ]
        count = await service.bulk_soft_delete(ids, actor_id=uuid.uuid4())
        assert count == 2
        assert mock_repo.create_activity.await_count == 2

    @pytest.mark.asyncio
    async def test_bulk_soft_delete_captures_dogs_before_delete(
        self, service, mock_repo
    ):
        """list_by_ids must run BEFORE the soft-delete, otherwise the
        deleted_at.is_(None) filter returns nothing and no timeline entries
        are written for the just-deleted dogs."""
        ids = [uuid.uuid4()]
        mock_repo.bulk_soft_delete.return_value = 1
        mock_repo.list_by_ids.return_value = [
            _make_dog(id=ids[0], registration_number="DOG-2026-0001", name="A",
                      breed="Mix", gender="male", status=DogStatus.SHELTER, is_adoptable=False),
        ]

        await service.bulk_soft_delete(ids, actor_id=uuid.uuid4())

        # Cross-mock call ordering: the parent AsyncMock records child calls
        # in method_calls, so we can prove list_by_ids ran before the delete.
        call_names = [c[0] for c in mock_repo.method_calls]
        assert call_names.index("list_by_ids") < call_names.index("bulk_soft_delete")
        assert mock_repo.create_activity.await_count == 1

    @pytest.mark.asyncio
    async def test_bulk_soft_delete_skips_unknown_ids(self, service, mock_repo):
        known = uuid.uuid4()
        unknown = uuid.uuid4()
        mock_repo.bulk_soft_delete.return_value = 1
        mock_repo.list_by_ids.return_value = [
            _make_dog(id=known, registration_number="DOG-2026-0001", name="A",
                      breed="Mix", gender="male", status=DogStatus.SHELTER, is_adoptable=False),
        ]
        await service.bulk_soft_delete([known, unknown], actor_id=uuid.uuid4())
        assert mock_repo.create_activity.await_count == 1
        assert mock_repo.create_activity.call_args[0][0].dog_id == known

    # ── H-1: registration-number collision retry ──────────────────────────────

    @pytest.mark.asyncio
    async def test_register_dog_retries_on_number_collision(
        self, service, mock_repo, mock_audit
    ):
        taken = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-9999", name="Taken",
            breed="Mix", gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_by_registration.side_effect = [taken, None]
        mock_repo.create.return_value = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-7777", name="Buddy",
            breed="Labrador", gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        payload = DogProfileCreate(name="Buddy", breed="Labrador", gender="male")

        result = await service.register_dog(payload, actor_id=uuid.uuid4())

        assert result.registration_number == "DOG-2026-7777"
        # First attempt hit the taken number, second found a free one.
        assert mock_repo.get_by_registration.await_count == 2
        assert mock_repo.create.await_count == 1

    # ── H-2: duplicate microchip → clean 409 ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_register_dog_duplicate_microchip_conflict(
        self, service, mock_repo
    ):
        existing = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-0001", name="Chip Dog",
            breed="Mix", gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_by_microchip.return_value = existing
        payload = DogProfileCreate(
            name="Buddy", breed="Labrador", gender="male",
            microchip_id="985141002345678",
        )

        with pytest.raises(ConflictError, match="microchip"):
            await service.register_dog(payload, actor_id=uuid.uuid4())
        # No row is created when the chip is already taken.
        mock_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_dog_duplicate_microchip_conflict(
        self, service, mock_repo
    ):
        dog = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-0002", name="Old",
            breed="Mix", gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )
        mock_repo.get_by_id.return_value = dog
        mock_repo.get_by_microchip.return_value = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-0003", name="Other",
            breed="Mix", gender="male", status=DogStatus.SHELTER, is_adoptable=False,
        )

        with pytest.raises(ConflictError, match="microchip"):
            await service.update_dog(
                dog.id,
                DogProfileUpdate(microchip_id="985141002399999"),
                actor_id=uuid.uuid4(),
            )

    # ── H-3: lifecycle activity stream ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_register_dog_records_activity(self, service, mock_repo, mock_audit):
        dog = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-1234", name="Buddy",
            breed="Labrador", gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        mock_repo.create.return_value = dog
        payload = DogProfileCreate(name="Buddy", breed="Labrador", gender="male")

        await service.register_dog(payload, actor_id=uuid.uuid4())

        mock_repo.create_activity.assert_awaited_once()
        log = mock_repo.create_activity.call_args[0][0]
        assert log.event_type == DogActivityEventType.REGISTERED
        assert log.dog_id == dog.id

    @pytest.mark.asyncio
    async def test_status_change_records_activity(self, service, mock_repo):
        dog = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-0003", name="Rex",
            breed="Mix", gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        mock_repo.get_by_id.return_value = dog

        await service.update_dog_status(dog.id, DogStatus.SHELTER, actor_id=uuid.uuid4())

        log = mock_repo.create_activity.call_args[0][0]
        assert log.event_type == DogActivityEventType.STATUS_CHANGED
        assert log.event_metadata == {"old_status": "rescued", "new_status": "shelter"}

    @pytest.mark.asyncio
    async def test_get_dog_timeline_returns_chronological_stream(
        self, service, mock_repo
    ):
        dog_id = uuid.uuid4()
        mock_repo.get_any_by_id.return_value = _make_dog(
            id=dog_id, registration_number="DOG-2026-0001", name="Max",
            breed="Beagle", gender="male", status=DogStatus.SHELTER, is_adoptable=True,
        )
        mock_repo.list_activity_by_dog.return_value = [
            DogActivityLog(
                dog_id=dog_id, event_type=DogActivityEventType.REGISTERED,
                message="Dog registered.",
            ),
            DogActivityLog(
                dog_id=dog_id, event_type=DogActivityEventType.STATUS_CHANGED,
                message="Status changed.",
            ),
        ]

        timeline = await service.get_dog_timeline(dog_id)

        assert len(timeline) == 2
        assert timeline[0].event_type == DogActivityEventType.REGISTERED
        mock_repo.list_activity_by_dog.assert_awaited_once_with(dog_id)

    @pytest.mark.asyncio
    async def test_get_dog_timeline_readable_after_soft_delete(
        self, service, mock_repo
    ):
        """PRR 3.4: the trail stays readable after soft-deletion."""
        dog_id = uuid.uuid4()
        deleted_dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0001", name="Max",
            breed="Beagle", gender="male", status=DogStatus.ADOPTED, is_adoptable=False,
        )
        deleted_dog.deleted_at = datetime.now(UTC)
        mock_repo.get_any_by_id.return_value = deleted_dog
        mock_repo.list_activity_by_dog.return_value = [
            DogActivityLog(
                dog_id=dog_id, event_type=DogActivityEventType.DELETED,
                message="Dog soft-deleted.",
            ),
        ]

        timeline = await service.get_dog_timeline(dog_id)

        assert len(timeline) == 1
        assert timeline[0].event_type == DogActivityEventType.DELETED

    @pytest.mark.asyncio
    async def test_get_dog_timeline_not_found(self, service, mock_repo):
        mock_repo.get_any_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_dog_timeline(uuid.uuid4())

    # ── M-3: breed classification (Pure/Mix/Unknown) ────────────────────────

    @pytest.mark.asyncio
    async def test_register_dog_infers_breed_classification(
        self, service, mock_repo, mock_audit
    ):
        dog = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-1234", name="Buddy",
            breed="Labrador Mix", gender="male", status=DogStatus.RESCUED,
            is_adoptable=False,
        )
        mock_repo.create.return_value = dog
        payload = DogProfileCreate(name="Buddy", breed="Labrador Mix", gender="male")

        await service.register_dog(payload, actor_id=uuid.uuid4())

        created_dog = mock_repo.create.call_args[0][0]
        assert created_dog.breed_classification == DogBreedClassification.MIX

    @pytest.mark.asyncio
    async def test_register_dog_explicit_classification_wins(
        self, service, mock_repo, mock_audit
    ):
        dog = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-1234", name="Buddy",
            breed="Labrador Mix", gender="male", status=DogStatus.RESCUED,
            is_adoptable=False,
        )
        mock_repo.create.return_value = dog
        payload = DogProfileCreate(
            name="Buddy", breed="Labrador Mix", gender="male",
            breed_classification=DogBreedClassification.PURE,
        )

        await service.register_dog(payload, actor_id=uuid.uuid4())

        created_dog = mock_repo.create.call_args[0][0]
        assert created_dog.breed_classification == DogBreedClassification.PURE

    @pytest.mark.asyncio
    async def test_update_dog_reinfers_classification_on_breed_change(
        self, service, mock_repo
    ):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0002", name="Old",
            breed="Labrador", gender="male", status=DogStatus.SHELTER,
            is_adoptable=False, breed_classification=DogBreedClassification.UNKNOWN,
        )
        mock_repo.get_by_id.return_value = dog

        await service.update_dog(
            dog_id, DogProfileUpdate(breed="Labrador Mix"), actor_id=uuid.uuid4()
        )

        assert dog.breed_classification == DogBreedClassification.MIX

    @pytest.mark.asyncio
    async def test_update_dog_explicit_null_reinfers_classification(
        self, service, mock_repo
    ):
        """An explicit null breed_classification means auto-infer (the column
        is NOT NULL, so a bare None would be a constraint violation)."""
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0002", name="Old",
            breed="Labrador Mix", gender="male", status=DogStatus.SHELTER,
            is_adoptable=False, breed_classification=DogBreedClassification.UNKNOWN,
        )
        mock_repo.get_by_id.return_value = dog

        await service.update_dog(
            dog_id, DogProfileUpdate(breed_classification=None), actor_id=uuid.uuid4()
        )

        assert dog.breed_classification == DogBreedClassification.MIX

    # ── M-2: weight history ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_record_weight_updates_profile_and_logs_activity(
        self, service, mock_repo, mock_audit
    ):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0005", name="Rex",
            breed="Mix", gender="male", status=DogStatus.SHELTER,
            is_adoptable=False, weight=15.0,
        )
        mock_repo.get_by_id.return_value = dog
        mock_repo.create_weight_log.return_value = DogWeightLog(
            dog_id=dog_id, weight=16.4
        )

        result = await service.record_weight(
            dog_id,
            DogWeightLogCreate(weight=16.4, notes="Post-surgery"),
            actor_id=uuid.uuid4(),
        )

        # Current profile weight follows the latest measurement.
        assert dog.weight == 16.4
        # A WEIGHT_RECORDED event is appended to the lifecycle stream.
        log = mock_repo.create_activity.call_args[0][0]
        assert log.event_type == DogActivityEventType.WEIGHT_RECORDED
        assert log.dog_id == dog_id
        # Audit is recorded for the actor.
        mock_audit.record.assert_awaited_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_weight_history_returns_chronological(
        self, service, mock_repo
    ):
        dog_id = uuid.uuid4()
        mock_repo.get_by_id.return_value = _make_dog(
            id=dog_id, registration_number="DOG-2026-0006", name="Scale",
            breed="Mix", gender="female", status=DogStatus.SHELTER,
            is_adoptable=False,
        )
        mock_repo.list_weight_logs.return_value = [
            DogWeightLog(dog_id=dog_id, weight=15.0),
            DogWeightLog(dog_id=dog_id, weight=16.4),
        ]

        history = await service.get_weight_history(dog_id)

        assert len(history) == 2
        mock_repo.list_weight_logs.assert_awaited_once_with(dog_id)

    @pytest.mark.asyncio
    async def test_record_weight_dog_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.record_weight(
                uuid.uuid4(), DogWeightLogCreate(weight=10.0), actor_id=uuid.uuid4()
            )

    # ── L-2: age_months derivation (PRR 3.1.4 age filter) ───────────────────

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("2 years", 24),
            ("2 year", 24),
            ("6 months", 6),
            ("1 month", 1),
            ("3 yrs", 36),
            ("2-year-old", 24),
            # Decimal/range strings must be rejected as unparseable rather
            # than silently extracting "5 years" (60 months) or "18 months":
            # the regex is anchored so unparseable rows stay NULL and are
            # excluded from filters, matching the migration's backfill.
            ("2.5 years", None),
            ("12-18 months", None),
            ("Puppy", None),
            (None, None),
            ("", None),
        ],
    )
    def test_parse_age_months(self, text, expected):
        assert _parse_age_months(text) == expected

    @pytest.mark.asyncio
    async def test_register_dog_derives_age_months(
        self, service, mock_repo, mock_audit
    ):
        dog = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-1234", name="Pup",
            breed="Mix", gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        mock_repo.create.return_value = dog

        await service.register_dog(
            DogProfileCreate(name="Pup", breed="Mix", gender="male", estimated_age="2 years"),
            actor_id=uuid.uuid4(),
        )

        created = mock_repo.create.call_args[0][0]
        assert created.age_months == 24

    @pytest.mark.asyncio
    async def test_register_dog_explicit_age_months_wins(
        self, service, mock_repo, mock_audit
    ):
        dog = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-1234", name="Pup",
            breed="Mix", gender="male", status=DogStatus.RESCUED, is_adoptable=False,
        )
        mock_repo.create.return_value = dog

        await service.register_dog(
            DogProfileCreate(
                name="Pup", breed="Mix", gender="male",
                estimated_age="2 years", age_months=18,
            ),
            actor_id=uuid.uuid4(),
        )

        created = mock_repo.create.call_args[0][0]
        assert created.age_months == 18

    @pytest.mark.asyncio
    async def test_update_dog_reinfers_age_months_on_age_edit(
        self, service, mock_repo
    ):
        dog_id = uuid.uuid4()
        dog = _make_dog(
            id=dog_id, registration_number="DOG-2026-0002", name="Old",
            breed="Mix", gender="male", status=DogStatus.SHELTER,
            is_adoptable=False, estimated_age="1 year", age_months=12,
        )
        mock_repo.get_by_id.return_value = dog

        await service.update_dog(
            dog_id, DogProfileUpdate(estimated_age="2 years"), actor_id=uuid.uuid4()
        )

        assert dog.age_months == 24

    # ── L-1: visual attributes ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_register_dog_stores_visual_attributes(
        self, service, mock_repo, mock_audit
    ):
        dog = _make_dog(
            id=uuid.uuid4(), registration_number="DOG-2026-1234", name="Spot",
            breed="Mix", gender="female", status=DogStatus.RESCUED, is_adoptable=False,
        )
        mock_repo.create.return_value = dog

        await service.register_dog(
            DogProfileCreate(
                name="Spot", breed="Mix", gender="female",
                ear_shape=DogEarShape.FLOPPY,
                tail_type=DogTailType.CURLED,
                distinctive_markers="White patch on chest",
            ),
            actor_id=uuid.uuid4(),
        )

        created = mock_repo.create.call_args[0][0]
        assert created.ear_shape == DogEarShape.FLOPPY
        assert created.tail_type == DogTailType.CURLED
        assert created.distinctive_markers == "White patch on chest"
