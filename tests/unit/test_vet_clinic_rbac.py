"""Unit tests for veterinary clinic RBAC authorization and public directory synchronization."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from pawguard.core.exceptions import ForbiddenError
from pawguard.core.pagination import PageParams
from pawguard.core.search import SortParams
from pawguard.modules.companion_pet.models import VetClinic
from pawguard.modules.companion_pet.repository import CompanionPetRepository
from pawguard.modules.companion_pet.schemas import VetClinicCreate, VetClinicUpdate
from pawguard.modules.companion_pet.service import CompanionPetService


def _user_with_role(user_id: uuid.UUID, *roles: str) -> Any:
    return SimpleNamespace(
        id=user_id,
        user=SimpleNamespace(id=user_id),
        claims=SimpleNamespace(roles=list(roles)),
    )


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock(spec=CompanionPetRepository)


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_repo: AsyncMock, mock_session: AsyncMock) -> CompanionPetService:
    return CompanionPetService(mock_repo, mock_session)


@pytest.mark.asyncio
async def test_super_admin_can_create_clinic(
    service: CompanionPetService, mock_repo: AsyncMock
) -> None:
    admin = _user_with_role(uuid.uuid4(), "super_admin")
    payload = VetClinicCreate(
        name="Medicover Animal Hospital",
        address="D.No: 51/1E2, 51/1E3, 51/1E4, near RTC Bus Stand, Kurnool",
        phone="7865560987",
        email="medicover@gmail.com",
        services="24/7 Emergency Care",
        latitude=None,
        longitude=None,
        is_emergency=True,
        is_active=True,
    )

    created_clinic = VetClinic(
        id=uuid.uuid4(),
        name=payload.name,
        address=payload.address,
        phone=payload.phone,
        email=payload.email,
        services=payload.services,
        is_emergency=payload.is_emergency,
        is_active=payload.is_active,
    )
    mock_repo.create_clinic.return_value = created_clinic

    result = await service.create_clinic(payload, admin)
    assert result.name == "Medicover Animal Hospital"
    assert result.phone == "7865560987"
    assert result.is_emergency is True
    assert result.is_active is True
    mock_repo.create_clinic.assert_awaited_once()


@pytest.mark.asyncio
async def test_rescue_centre_admin_can_create_clinic(
    service: CompanionPetService, mock_repo: AsyncMock
) -> None:
    rc_admin = _user_with_role(uuid.uuid4(), "rescue_centre_admin")
    payload = VetClinicCreate(
        name="Rescue Centre Partner Clinic",
        address="Road 1, City",
        phone="9876543210",
        email="clinic@pawguard.com",
        services="General Checkup",
        is_emergency=False,
        is_active=True,
    )
    mock_repo.create_clinic.return_value = VetClinic(id=uuid.uuid4(), **payload.model_dump())

    result = await service.create_clinic(payload, rc_admin)
    assert result.name == "Rescue Centre Partner Clinic"
    mock_repo.create_clinic.assert_awaited_once()


@pytest.mark.asyncio
async def test_unauthorized_roles_cannot_create_clinic(service: CompanionPetService) -> None:
    payload = VetClinicCreate(
        name="Unauthorized Clinic",
        address="Road 2, City",
        phone="9876543211",
    )

    # 1. Veterinarian
    vet = _user_with_role(uuid.uuid4(), "veterinarian")
    with pytest.raises(ForbiddenError, match="administrator"):
        await service.create_clinic(payload, vet)

    # 2. Shelter Manager
    shelter_mgr = _user_with_role(uuid.uuid4(), "shelter_manager")
    with pytest.raises(ForbiddenError, match="administrator"):
        await service.create_clinic(payload, shelter_mgr)

    # 3. General Public
    public_user = _user_with_role(uuid.uuid4(), "general_public")
    with pytest.raises(ForbiddenError, match="administrator"):
        await service.create_clinic(payload, public_user)


@pytest.mark.asyncio
async def test_admin_can_update_and_deactivate_and_reactivate_clinic(
    service: CompanionPetService, mock_repo: AsyncMock
) -> None:
    admin = _user_with_role(uuid.uuid4(), "super_admin")
    clinic_id = uuid.uuid4()
    clinic = VetClinic(
        id=clinic_id,
        name="Medicover Animal Hospital",
        address="Old Address",
        phone="7865560987",
        services="Emergency Care",
        is_emergency=True,
        is_active=True,
    )
    mock_repo.get_clinic.return_value = clinic

    # Edit fields
    update_payload = VetClinicUpdate(
        name="Medicover Super Specialty Animal Hospital",
        phone="9988776655",
        services="24/7 Advanced Surgery & Critical Care",
    )
    updated = await service.update_clinic(clinic_id, update_payload, admin)
    assert updated.name == "Medicover Super Specialty Animal Hospital"
    assert updated.phone == "9988776655"
    assert updated.services == "24/7 Advanced Surgery & Critical Care"

    # Deactivate
    deactivate_payload = VetClinicUpdate(is_active=False)
    deactivated = await service.update_clinic(clinic_id, deactivate_payload, admin)
    assert deactivated.is_active is False

    # Reactivate
    reactivate_payload = VetClinicUpdate(is_active=True)
    reactivated = await service.update_clinic(clinic_id, reactivate_payload, admin)
    assert reactivated.is_active is True


@pytest.mark.asyncio
async def test_admin_can_delete_clinic(service: CompanionPetService, mock_repo: AsyncMock) -> None:
    admin = _user_with_role(uuid.uuid4(), "super_admin")
    clinic_id = uuid.uuid4()
    clinic = VetClinic(
        id=clinic_id,
        name="Clinic To Delete",
        address="Road 9",
        phone="1234567890",
        is_active=True,
    )
    mock_repo.get_clinic.return_value = clinic

    await service.delete_clinic(clinic_id, admin)
    assert clinic.is_active is False
    assert clinic.deleted_at is not None


@pytest.mark.asyncio
async def test_unauthorized_roles_cannot_update_or_delete_clinic(
    service: CompanionPetService, mock_repo: AsyncMock
) -> None:
    clinic_id = uuid.uuid4()
    clinic = VetClinic(
        id=clinic_id,
        name="Target Clinic",
        address="Road 9",
        phone="1234567890",
        is_active=True,
    )
    mock_repo.get_clinic.return_value = clinic

    vet = _user_with_role(uuid.uuid4(), "veterinarian")
    with pytest.raises(ForbiddenError, match="administrator"):
        await service.update_clinic(clinic_id, VetClinicUpdate(name="Hacked Name"), vet)

    with pytest.raises(ForbiddenError, match="administrator"):
        await service.delete_clinic(clinic_id, vet)


@pytest.mark.asyncio
async def test_list_clinics_forwards_filter_options(
    service: CompanionPetService, mock_repo: AsyncMock
) -> None:
    now = datetime.now(UTC)
    clinic_1 = VetClinic(
        id=uuid.uuid4(),
        name="Active Clinic",
        address="Road 1",
        phone="123",
        is_emergency=False,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    mock_repo.list_clinics.return_value = ([clinic_1], 1)

    page = PageParams(page=1, page_size=20)
    sort = SortParams(sort_by="name", sort_order="asc")

    # Default public listing (active only)
    res = await service.list_clinics(page, sort, search=None)
    assert len(res.data) == 1
    assert res.data[0].name == "Active Clinic"
    mock_repo.list_clinics.assert_awaited_with(
        page, sort, None, is_active=None, include_inactive=False
    )
