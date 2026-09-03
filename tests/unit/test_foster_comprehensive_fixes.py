"""Unit tests verifying all 8 foster fixes end-to-end (RULE-008)."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

from pawguard.core.exceptions import ValidationFailedError
from pawguard.modules.adoption.models import AdoptionApplication, AdoptionStatus
from pawguard.modules.adoption.repository import AdoptionRepository
from pawguard.modules.auth.dependencies import _extract_access_token
from pawguard.modules.auth.exceptions import InvalidSessionError
from pawguard.modules.auth.repository import RoleRepository, UserRoleRepository
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.repository import DogRepository
from pawguard.modules.foster.models import (
    FosterPlacement,
    FosterPlacementStatus,
    FosterProfile,
    FosterStatus,
)
from pawguard.modules.foster.repository import FosterRepository
from pawguard.modules.foster.schemas import (
    FosterBackgroundCheckInitiate,
    FosterBackgroundCheckOutcome,
    FosterBehaviorLogCreate,
    FosterHomeInspectionLog,
    FosterHomeInspectionOutcome,
    FosterHomeInspectionSchedule,
    FosterMediaLogCreate,
    FosterMedicationLogCreate,
    FosterPlacementCreate,
    FosterProfileResponse,
    FosterProfileUpdate,
    FosterVetCheckRequest,
    FosterWeightLogCreate,
)
from pawguard.modules.foster.service import FosterService
from pawguard.services.audit_service import AuditService


@pytest.fixture
def mock_repo():
    repo = AsyncMock(spec=FosterRepository)
    repo._session = AsyncMock()
    return repo


@pytest.fixture
def mock_dog_repo():
    return AsyncMock(spec=DogRepository)


@pytest.fixture
def mock_adoption_repo():
    return AsyncMock(spec=AdoptionRepository)


@pytest.fixture
def mock_audit():
    return AsyncMock(spec=AuditService)


@pytest.fixture
def mock_roles():
    return AsyncMock(spec=RoleRepository)


@pytest.fixture
def mock_user_roles():
    return AsyncMock(spec=UserRoleRepository)


@pytest.fixture
def service(mock_repo, mock_dog_repo, mock_adoption_repo, mock_audit):
    return FosterService(
        mock_repo,
        mock_dog_repo,
        mock_adoption_repo,
        mock_audit,
    )


# ---------------------------------------------------------------------------
# BUG-FOSTER-001: Convert to Adopt converts directly to permanent adoption
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bug_foster_001_convert_to_adopt_permanent(
    service, mock_repo, mock_dog_repo, mock_adoption_repo
):
    placement_id = uuid.uuid4()
    foster_id = uuid.uuid4()
    dog_id = uuid.uuid4()
    user_id = uuid.uuid4()

    dog = DogProfile(
        id=dog_id,
        registration_number="DOG-TEST-01",
        name="Charlie",
        breed="Labrador",
        status=DogStatus.FOSTERED,
        is_adoptable=True,
    )
    placement = FosterPlacement(
        id=placement_id,
        foster_id=foster_id,
        dog_id=dog_id,
        is_active=True,
        placed_at=datetime.now(UTC),
    )
    foster = FosterProfile(
        id=foster_id,
        user_id=user_id,
        status=FosterStatus.APPROVED,
        max_capacity=2,
        active_count=1,
        is_available=False,
    )

    mock_repo.get_placement_by_id.return_value = placement
    mock_repo.get_profile_by_id.return_value = foster
    mock_dog_repo.get_by_id_for_update.return_value = dog
    mock_adoption_repo.get_approved_application_for_dog.return_value = None

    app_id = uuid.uuid4()
    mock_adoption_repo.create.return_value = None
    mock_adoption_repo.get_by_id.return_value = AdoptionApplication(
        id=app_id,
        dog_id=dog_id,
        adopter_id=user_id,
        residential_status="foster",
        status=AdoptionStatus.APPROVED,
    )

    with (
        patch(
            "pawguard.modules.foster.service.MedicalRepository.get_latest_approved_clearance",
            AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        ),
        patch.object(service, "_generate_adoption_lease", AsyncMock()) as mock_lease,
    ):
        result = await service.convert_to_adoption(placement_id, actor_id=uuid.uuid4())

    assert result.status == AdoptionStatus.APPROVED
    assert placement.is_active is False
    assert placement.status == FosterPlacementStatus.CONVERTED_TO_ADOPT
    assert dog.status == DogStatus.ADOPTED
    assert dog.is_adoptable is False
    assert mock_lease.await_count == 1


# ---------------------------------------------------------------------------
# BUG-FOSTER-002: Request Vet Check supports default empty payload & notifies
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bug_foster_002_request_vet_check_defaults(service, mock_repo, mock_dog_repo):
    placement_id = uuid.uuid4()
    foster_id = uuid.uuid4()
    dog_id = uuid.uuid4()
    user_id = uuid.uuid4()

    placement = FosterPlacement(
        id=placement_id,
        foster_id=foster_id,
        dog_id=dog_id,
        is_active=True,
    )
    foster = FosterProfile(id=foster_id, user_id=user_id)
    dog = DogProfile(id=dog_id, name="Bella")

    mock_repo.get_placement_by_id.return_value = placement
    mock_repo.get_profile_by_id.return_value = foster
    mock_dog_repo.get_by_id.return_value = dog

    # Empty default request
    with patch(
        "pawguard.modules.notifications.governance_service.dispatch_governed_notification",
        AsyncMock(),
    ) as mock_dispatch:
        response = await service.request_vet_check(placement_id, FosterVetCheckRequest())

    assert response.placement_id == placement_id
    assert response.status == "requested"
    assert mock_repo.create_progress_log.await_count == 1
    assert mock_dispatch.await_count == 1


# ---------------------------------------------------------------------------
# BUG-FOSTER-003: Return to Shelter cleanly closes placement & returns dog
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bug_foster_003_return_to_shelter(service, mock_repo, mock_dog_repo):
    placement_id = uuid.uuid4()
    foster_id = uuid.uuid4()
    dog_id = uuid.uuid4()

    placement = FosterPlacement(
        id=placement_id,
        foster_id=foster_id,
        dog_id=dog_id,
        is_active=True,
    )
    foster = FosterProfile(
        id=foster_id,
        active_count=1,
        max_capacity=1,
        is_available=False,
    )
    dog = DogProfile(id=dog_id, status=DogStatus.FOSTERED)

    mock_repo.get_placement_by_id.side_effect = [placement, placement]
    mock_repo.get_profile_by_id.return_value = foster
    mock_dog_repo.get_by_id.return_value = dog

    res = await service.return_dog(placement_id, notes="Care period concluded")
    assert res.is_active is False
    assert res.status == FosterPlacementStatus.RETURNED
    assert dog.status == DogStatus.SHELTER
    assert foster.active_count == 0
    assert foster.is_available is True


# ---------------------------------------------------------------------------
# BUG-FOSTER-004: Approval handles string statuses without 422 errors
# ---------------------------------------------------------------------------
def test_bug_foster_004_schema_normalizes_string_statuses():
    # Frontend modal submits "pending" strings for boolean checks
    update = FosterProfileUpdate(
        status="approved",
        background_check_passed="pending",
        home_inspection_passed="pending",
    )
    assert update.background_check_passed is None
    assert update.home_inspection_passed is None
    assert update.status == FosterStatus.APPROVED

    # Frontend modal submits "cleared" or "approved"
    update2 = FosterProfileUpdate(
        background_check_passed="cleared",
        home_inspection_passed="approved",
    )
    assert update2.background_check_passed is True
    assert update2.home_inspection_passed is True


@pytest.mark.asyncio
async def test_bug_foster_004_service_approves_pending_profile(service, mock_repo):
    profile_id = uuid.uuid4()
    profile = FosterProfile(
        id=profile_id,
        user_id=uuid.uuid4(),
        status=FosterStatus.APPLIED,
        background_check_passed=None,
        home_inspection_passed=None,
        references_checked=None,
    )
    mock_repo.get_profile_by_id.return_value = profile

    payload = FosterProfileUpdate(
        status=FosterStatus.APPROVED,
        background_check_passed=None,
        home_inspection_passed=None,
    )
    with (
        patch.object(service._roles, "get_by_name", AsyncMock(return_value=None)),
        patch.object(service, "_send_push", AsyncMock()),
    ):
        updated = await service.update_profile(profile_id, payload)
    assert updated.status == FosterStatus.APPROVED
    assert updated.background_check_passed is True
    assert updated.home_inspection_passed is True


# ---------------------------------------------------------------------------
# FOSTER-005: Daily Foster Progress Portal separate reporting functions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_foster_005_daily_progress_separate_reporting(service, mock_repo, mock_dog_repo):
    placement_id = uuid.uuid4()
    dog_id = uuid.uuid4()
    placement = FosterPlacement(
        id=placement_id,
        dog_id=dog_id,
        is_active=True,
    )
    dog = DogProfile(id=dog_id, weight=20.0)
    mock_repo.get_placement_by_id.return_value = placement
    mock_dog_repo.get_by_id.return_value = dog

    # 1. Weight log: syncs to dog profile & DogWeightLog
    weight_log = await service.log_weight(
        placement_id, FosterWeightLogCreate(weight_kg=21.5, notes="Digital scale")
    )
    assert weight_log.weight_kg == 21.5
    assert dog.weight == 21.5
    assert mock_dog_repo.create_weight_log.await_count == 1

    # 2. Behavior log
    behavior_log = await service.log_behavior(
        placement_id,
        FosterBehaviorLogCreate(
            behavior_notes="Calm and playful", mood_rating=5, exercise_minutes=40
        ),
    )
    assert behavior_log.behavior_notes == "Calm and playful"
    assert behavior_log.mood_rating == 5
    assert behavior_log.exercise_minutes == 40

    # 3. Medication log
    med_log = await service.log_medication(
        placement_id,
        FosterMedicationLogCreate(medication_notes="Heartgard chewable", verified=True),
    )
    assert "Heartgard chewable" in (med_log.medication_notes or "")
    assert "[VERIFIED=True]" in (med_log.medication_notes or "")

    # 4. Media log
    media_log = await service.log_media(
        placement_id,
        FosterMediaLogCreate(photo_urls=["https://img.com/dog1.jpg"], caption="Sunny day"),
    )
    assert media_log.photo_urls == ["https://img.com/dog1.jpg"]


# ---------------------------------------------------------------------------
# BUG-FOSTER-006: Flexible token extraction (raw token, X-Access-Token, query)
# ---------------------------------------------------------------------------
def test_bug_foster_006_extract_access_token():
    dummy_jwt = "header.payload.signature"

    # Standard Bearer
    req = MagicMock(spec=Request)
    assert _extract_access_token(req, authorization=f"Bearer {dummy_jwt}") == dummy_jwt

    # Raw JWT without Bearer prefix
    assert _extract_access_token(req, authorization=dummy_jwt) == dummy_jwt

    # X-Access-Token header
    assert _extract_access_token(req, x_access_token=dummy_jwt) == dummy_jwt

    # Query param token
    req_query = MagicMock(spec=Request)
    req_query.query_params = {"token": dummy_jwt}
    assert _extract_access_token(req_query) == dummy_jwt

    # Missing credentials raises InvalidSessionError
    req_empty = MagicMock(spec=Request)
    req_empty.query_params = {}
    with pytest.raises(InvalidSessionError):
        _extract_access_token(req_empty)


# ---------------------------------------------------------------------------
# PAW-FC-007: Background check workflow and placement gate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paw_fc_007_background_check_workflow_and_gate(service, mock_repo, mock_dog_repo):
    profile_id = uuid.uuid4()
    profile = FosterProfile(
        id=profile_id,
        user_id=uuid.uuid4(),
        status=FosterStatus.APPROVED,
        background_check_passed=None,
        home_inspection_passed=True,
        is_available=True,
        max_capacity=2,
        active_count=0,
    )
    mock_repo.get_profile_by_id.return_value = profile
    mock_repo.get_profile_by_id_for_update.return_value = profile

    # 1. Initiate background check
    await service.initiate_background_check(
        profile_id, FosterBackgroundCheckInitiate(provider="Checkr")
    )
    resp = FosterProfileResponse.model_validate(profile)
    assert resp.background_check_status == "initiated"

    # 2. Placement blocked while not cleared
    with pytest.raises(ValidationFailedError, match="background check has not been cleared"):
        await service.place_dog(profile_id, FosterPlacementCreate(dog_id=uuid.uuid4()))

    # 3. Complete outcome: cleared
    await service.record_background_check_outcome(
        profile_id,
        FosterBackgroundCheckOutcome(
            outcome="cleared",
            notes="No criminal records found.",
            references_checked=True,
        ),
    )
    resp_cleared = FosterProfileResponse.model_validate(profile)
    assert resp_cleared.background_check_status == "cleared"
    assert profile.background_check_passed is True


# ---------------------------------------------------------------------------
# PAW-FC-008: Home inspection workflow and placement gate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paw_fc_008_home_inspection_workflow_and_gate(service, mock_repo, mock_dog_repo):
    profile_id = uuid.uuid4()
    profile = FosterProfile(
        id=profile_id,
        user_id=uuid.uuid4(),
        status=FosterStatus.APPROVED,
        background_check_passed=True,
        home_inspection_passed=None,
        is_available=True,
        max_capacity=2,
        active_count=0,
    )
    mock_repo.get_profile_by_id.return_value = profile
    mock_repo.get_profile_by_id_for_update.return_value = profile

    # 1. Schedule inspection
    await service.schedule_home_inspection(
        profile_id,
        FosterHomeInspectionSchedule(
            scheduled_at=datetime.now(UTC),
            inspector_name="Officer Jane",
            inspection_type="physical",
            address="123 Oak Lane",
        ),
    )
    resp = FosterProfileResponse.model_validate(profile)
    assert resp.home_inspection_status == "scheduled"

    # 2. Placement blocked while home inspection not approved
    with pytest.raises(ValidationFailedError, match="home inspection has not been approved"):
        await service.place_dog(profile_id, FosterPlacementCreate(dog_id=uuid.uuid4()))

    # 3. Log audit details
    await service.log_home_inspection_audit(
        profile_id,
        FosterHomeInspectionLog(
            yard_condition="Enclosed yard",
            fencing_condition="6ft fence",
            rating=5,
        ),
    )
    resp_inspected = FosterProfileResponse.model_validate(profile)
    assert resp_inspected.home_inspection_status == "inspected"

    # 4. Approve inspection
    await service.record_home_inspection_outcome(
        profile_id,
        FosterHomeInspectionOutcome(outcome="approved", notes="Secure home"),
    )
    resp_approved = FosterProfileResponse.model_validate(profile)
    assert resp_approved.home_inspection_status == "approved"
    assert profile.home_inspection_passed is True
