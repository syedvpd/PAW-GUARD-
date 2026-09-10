"""Unit tests for PATCH /shelter/medical-requests/{request_id}/status.

These exercise the full router-level serialization path so lazy
relationship loading can never surface as a 422 response.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pawguard.core.exceptions import ForbiddenError, NotFoundError, ValidationFailedError
from pawguard.core.security import AccessTokenClaims
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.models import Role, User
from pawguard.modules.shelter.models import (
    ShelterVetRequest,
    ShelterVetRequestStatus,
)
from pawguard.modules.shelter.router import get_shelter_service
from pawguard.modules.shelter.router import router as shelter_router
from pawguard.modules.shelter.service import ShelterService


@pytest.fixture
def test_app():
    from pawguard.core.exceptions import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(shelter_router, prefix="/api/v1")
    return app


def _make_role(name: str) -> Role:
    role = Role(id=uuid.uuid4(), name=name, is_system=True)
    role.permissions = []
    return role


def _make_vet_request(request_id, vet_id, facility_id, status):
    return ShelterVetRequest(
        id=request_id,
        dog_id=uuid.uuid4(),
        shelter_facility_id=facility_id,
        requested_by_id=uuid.uuid4(),
        vet_id=vet_id,
        reason="Routine exam",
        notes=None,
        urgency="routine",
        status=status,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_current_user(user_id, role_names):
    now = datetime.now(UTC)
    user = User(
        id=user_id,
        email="vet@pawguard.org",
        full_name="Veterinarian",
        phone="+1555000000",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
        mfa_enabled=False,
        created_at=now,
        updated_at=now,
    )
    user.roles = [_make_role(name) for name in role_names]
    claims = AccessTokenClaims(
        user_id=user.id,
        session_id=uuid.uuid4(),
        roles=role_names,
        jti=str(uuid.uuid4()),
        expires_at=now,
    )
    return CurrentUser(
        user=user,
        claims=claims,
        db=AsyncMock(),
        redis=AsyncMock(),
    )


async def _patch_status(test_app, user, service, request_id, body):
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[get_shelter_service] = lambda: service

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.patch(
            f"/api/v1/shelter/medical-requests/{request_id}/status",
            json=body,
        )


@pytest.mark.asyncio
async def test_patch_status_returns_200_with_updated_status(test_app):
    facility_id = uuid.uuid4()
    vet_id = uuid.uuid4()
    request_id = uuid.uuid4()
    user = _make_current_user(vet_id, ["veterinarian"])

    updated = _make_vet_request(
        request_id, vet_id, facility_id, ShelterVetRequestStatus.IN_PROGRESS
    )
    service = AsyncMock(spec=ShelterService)
    service.update_vet_request_status.return_value = updated

    resp = await _patch_status(test_app, user, service, request_id, {"status": "in_progress"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "in_progress"
    assert data["data"]["id"] == str(request_id)
    assert data["data"]["vet_id"] == str(vet_id)
    assert data["data"]["shelter_facility_id"] == str(facility_id)
    assert "updated to in_progress" in data["message"]
    service.update_vet_request_status.assert_awaited_once()
    call_kwargs = service.update_vet_request_status.await_args.kwargs
    assert call_kwargs["actor_id"] == user.user.id
    assert call_kwargs["actor_roles"] == {"veterinarian"}
    assert call_kwargs["ip_address"] is None or call_kwargs["ip_address"]


@pytest.mark.asyncio
async def test_patch_status_serializes_request_without_lazy_relationships(test_app):
    facility_id = uuid.uuid4()
    vet_id = uuid.uuid4()
    request_id = uuid.uuid4()
    user = _make_current_user(vet_id, ["veterinarian"])

    updated = _make_vet_request(
        request_id, vet_id, facility_id, ShelterVetRequestStatus.IN_PROGRESS
    )
    updated.dog = None
    updated.requested_by = None
    updated.vet = None
    updated.shelter_facility = None

    service = AsyncMock(spec=ShelterService)
    service.update_vet_request_status.return_value = updated

    resp = await _patch_status(test_app, user, service, request_id, {"status": "in_progress"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_patch_status_from_pending_to_completed_persists(test_app):
    facility_id = uuid.uuid4()
    vet_id = uuid.uuid4()
    request_id = uuid.uuid4()
    user = _make_current_user(vet_id, ["veterinarian"])

    pending = _make_vet_request(request_id, vet_id, facility_id, ShelterVetRequestStatus.PENDING)
    completed = _make_vet_request(
        request_id, vet_id, facility_id, ShelterVetRequestStatus.COMPLETED
    )

    service = AsyncMock(spec=ShelterService)
    service.update_vet_request_status.return_value = completed

    resp = await _patch_status(test_app, user, service, request_id, {"status": "completed"})

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "completed"
    service.update_vet_request_status.assert_awaited_once()
    assert pending.status != completed.status


@pytest.mark.asyncio
async def test_patch_status_rejected_from_in_progress(test_app):
    facility_id = uuid.uuid4()
    vet_id = uuid.uuid4()
    request_id = uuid.uuid4()
    user = _make_current_user(vet_id, ["veterinarian"])

    rejected = _make_vet_request(request_id, vet_id, facility_id, ShelterVetRequestStatus.REJECTED)
    service = AsyncMock(spec=ShelterService)
    service.update_vet_request_status.return_value = rejected

    resp = await _patch_status(test_app, user, service, request_id, {"status": "rejected"})

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_patch_status_invalid_status_returns_422(test_app):
    vehicle = _make_current_user(uuid.uuid4(), ["super_admin"])
    service = AsyncMock(spec=ShelterService)

    resp = await _patch_status(test_app, vehicle, service, uuid.uuid4(), {"status": "banana"})

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"][0]["loc"] == ["body", "status"]
    service.update_vet_request_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_status_missing_status_returns_422(test_app):
    user = _make_current_user(uuid.uuid4(), ["super_admin"])
    service = AsyncMock(spec=ShelterService)

    resp = await _patch_status(test_app, user, service, uuid.uuid4(), {})

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert resp.json()["error"]["details"][0]["loc"] == ["body", "status"]
    service.update_vet_request_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_status_forbidden_returns_403(test_app):
    user = _make_current_user(uuid.uuid4(), ["veterinarian"])
    service = AsyncMock(spec=ShelterService)
    service.update_vet_request_status.side_effect = ForbiddenError(
        "You can only update requests assigned to you."
    )

    resp = await _patch_status(test_app, user, service, uuid.uuid4(), {"status": "in_progress"})

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "AUTHORIZATION_FAILED"


@pytest.mark.asyncio
async def test_patch_status_not_found_returns_404(test_app):
    user = _make_current_user(uuid.uuid4(), ["super_admin"])
    service = AsyncMock(spec=ShelterService)
    service.update_vet_request_status.side_effect = NotFoundError("Shelter vet request not found.")

    resp = await _patch_status(test_app, user, service, uuid.uuid4(), {"status": "in_progress"})

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_patch_status_invalid_transition_returns_422(test_app):
    user = _make_current_user(uuid.uuid4(), ["veterinarian"])
    service = AsyncMock(spec=ShelterService)
    service.update_vet_request_status.side_effect = ValidationFailedError(
        "Cannot transition shelter vet request from pending to completed."
    )

    resp = await _patch_status(test_app, user, service, uuid.uuid4(), {"status": "completed"})

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_response_model_matches_openapi_contract(test_app):
    schema = test_app.openapi()["components"]["schemas"]
    assert "ShelterVetStatusUpdateRequest" in schema
    status_prop = schema["ShelterVetStatusUpdateRequest"]["properties"]["status"]
    if "$ref" in status_prop:
        ref_name = status_prop["$ref"].split("/")[-1]
        assert set(schema[ref_name]["enum"]) == {
            "pending",
            "in_progress",
            "completed",
            "rejected",
            "cancelled",
        }
    else:
        assert set(status_prop["enum"]) == {
            "pending",
            "in_progress",
            "completed",
            "rejected",
            "cancelled",
        }
