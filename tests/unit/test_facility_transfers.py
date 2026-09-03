"""Unit tests for facility-scoped confirmation on inter-facility transfers."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from pawguard.core.exceptions import ConflictError, ForbiddenError
from pawguard.modules.auth.models import Role, User
from pawguard.modules.auth.service import AdminService
from pawguard.modules.shelter.models import FacilityTransfer, TransferStatus
from pawguard.modules.shelter.service import ShelterService


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo._session = AsyncMock()
    return repo


@pytest.fixture
def mock_dog_repo():
    repo = AsyncMock()
    repo._session = AsyncMock()
    return repo


@pytest.fixture
def mock_audit():
    return AsyncMock()


@pytest.fixture
def service(mock_repo, mock_dog_repo, mock_audit):
    return ShelterService(mock_repo, mock_dog_repo, mock_audit)


@pytest.mark.asyncio
class TestUserFacilityAssociation:
    async def test_user_managed_facility_id_default_none(self):
        user = User(
            email="manager@shelter.com",
            full_name="Shelter Manager",
            hashed_password="hash",
        )
        assert user.managed_facility_id is None

    async def test_admin_update_user_managed_facility_id(self):
        user_id = uuid.uuid4()
        facility_id = uuid.uuid4()
        user = User(
            id=user_id,
            email="mgr@shelter.com",
            full_name="Facility Manager",
            hashed_password="hash",
            managed_facility_id=None,
        )
        mock_user_repo = AsyncMock()
        mock_user_repo.get_by_id.return_value = user
        mock_user_repo._session = AsyncMock()
        mock_role_repo = AsyncMock()
        mock_perm_repo = AsyncMock()
        mock_user_role_repo = AsyncMock()
        mock_audit = AsyncMock()

        admin_service = AdminService(
            user_repo=mock_user_repo,
            role_repo=mock_role_repo,
            permission_repo=mock_perm_repo,
            user_role_repo=mock_user_role_repo,
            audit_service=mock_audit,
        )

        updated = await admin_service.update_user(user_id, managed_facility_id=facility_id)
        assert updated.managed_facility_id == facility_id


@pytest.mark.asyncio
class TestFacilityTransferConfirmation:
    @pytest.fixture
    def facilities_and_users(self):
        facility_a = uuid.uuid4()
        facility_b = uuid.uuid4()

        role_shelter_mgr = Role(name="shelter_manager", description="Shelter Manager")
        role_super_admin = Role(name="super_admin", description="Super Admin")

        manager_a = User(
            id=uuid.uuid4(),
            email="manager_a@pawguard.com",
            full_name="Manager A",
            hashed_password="hash",
            managed_facility_id=facility_a,
            roles=[role_shelter_mgr],
        )
        manager_b = User(
            id=uuid.uuid4(),
            email="manager_b@pawguard.com",
            full_name="Manager B",
            hashed_password="hash",
            managed_facility_id=facility_b,
            roles=[role_shelter_mgr],
        )
        admin1 = User(
            id=uuid.uuid4(),
            email="admin1@pawguard.com",
            full_name="Admin One",
            hashed_password="hash",
            managed_facility_id=None,
            roles=[role_super_admin],
        )
        admin2 = User(
            id=uuid.uuid4(),
            email="admin2@pawguard.com",
            full_name="Admin Two",
            hashed_password="hash",
            managed_facility_id=None,
            roles=[role_super_admin],
        )

        return {
            "facility_a": facility_a,
            "facility_b": facility_b,
            "manager_a": manager_a,
            "manager_b": manager_b,
            "admin1": admin1,
            "admin2": admin2,
        }

    def _setup_session_mock(self, mock_repo, users_dict):
        async def mock_execute(stmt):
            result = MagicMock()
            # Match user by id
            for u in users_dict.values():
                if isinstance(u, User) and str(u.id) in str(stmt):
                    result.scalar_one_or_none.return_value = u
                    return result
            # Default fallback: check if any user id matches params
            result.scalar_one_or_none.return_value = None
            return result

        mock_repo._session.execute = AsyncMock(side_effect=mock_execute)

    async def test_sender_facility_manager_can_confirm_sender(
        self, service, mock_repo, facilities_and_users
    ):
        f = facilities_and_users
        transfer_id = uuid.uuid4()
        transfer = FacilityTransfer(
            id=transfer_id,
            dog_id=uuid.uuid4(),
            from_facility_id=f["facility_a"],
            to_facility_id=f["facility_b"],
            status=TransferStatus.PENDING,
            transferred_by=uuid.uuid4(),
        )
        mock_repo.get_transfer.return_value = transfer

        # Mock execute returning manager_a
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = f["manager_a"]
        mock_repo._session.execute.return_value = result_mock

        res = await service.confirm_transfer_sender(transfer_id, actor_id=f["manager_a"].id)
        assert res.sender_confirmed_at is not None
        assert res.sender_confirmed_by == f["manager_a"].id

    async def test_wrong_facility_manager_cannot_confirm_sender(
        self, service, mock_repo, facilities_and_users
    ):
        f = facilities_and_users
        transfer_id = uuid.uuid4()
        transfer = FacilityTransfer(
            id=transfer_id,
            dog_id=uuid.uuid4(),
            from_facility_id=f["facility_a"],
            to_facility_id=f["facility_b"],
            status=TransferStatus.PENDING,
            transferred_by=uuid.uuid4(),
        )
        mock_repo.get_transfer.return_value = transfer

        # Manager B (who manages Facility B) tries to confirm sender (Facility A)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = f["manager_b"]
        mock_repo._session.execute.return_value = result_mock

        with pytest.raises(ForbiddenError, match="not authorized to confirm sender"):
            await service.confirm_transfer_sender(transfer_id, actor_id=f["manager_b"].id)

    async def test_wrong_facility_manager_cannot_confirm_receiver(
        self, service, mock_repo, facilities_and_users
    ):
        f = facilities_and_users
        transfer_id = uuid.uuid4()
        transfer = FacilityTransfer(
            id=transfer_id,
            dog_id=uuid.uuid4(),
            from_facility_id=f["facility_a"],
            to_facility_id=f["facility_b"],
            status=TransferStatus.PENDING,
            transferred_by=uuid.uuid4(),
        )
        mock_repo.get_transfer.return_value = transfer

        # Manager A (who manages Facility A) tries to confirm receiver (Facility B)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = f["manager_a"]
        mock_repo._session.execute.return_value = result_mock

        with pytest.raises(ForbiddenError, match="not authorized to confirm receiver"):
            await service.confirm_transfer_receiver(transfer_id, actor_id=f["manager_a"].id)

    async def test_receiver_facility_manager_can_confirm_receiver_and_complete(
        self, service, mock_repo, mock_dog_repo, facilities_and_users
    ):
        f = facilities_and_users
        transfer_id = uuid.uuid4()
        dog_id = uuid.uuid4()
        dog = MagicMock()
        mock_dog_repo.get_by_id.return_value = dog

        transfer = FacilityTransfer(
            id=transfer_id,
            dog_id=dog_id,
            from_facility_id=f["facility_a"],
            to_facility_id=f["facility_b"],
            status=TransferStatus.PENDING,
            transferred_by=uuid.uuid4(),
            sender_confirmed_by=f["manager_a"].id,
        )
        # Pretend sender already confirmed
        transfer.sender_confirmed_at = MagicMock()
        mock_repo.get_transfer.return_value = transfer

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = f["manager_b"]
        mock_repo._session.execute.return_value = result_mock

        res = await service.confirm_transfer_receiver(transfer_id, actor_id=f["manager_b"].id)
        assert res.receiver_confirmed_at is not None
        assert res.receiver_confirmed_by == f["manager_b"].id
        assert res.status == TransferStatus.COMPLETED

    async def test_defense_in_depth_same_actor_blocked_from_both_sides(
        self, service, mock_repo, facilities_and_users
    ):
        f = facilities_and_users
        transfer_id = uuid.uuid4()
        same_admin_id = f["admin1"].id

        transfer = FacilityTransfer(
            id=transfer_id,
            dog_id=uuid.uuid4(),
            from_facility_id=f["facility_a"],
            to_facility_id=f["facility_b"],
            status=TransferStatus.PENDING,
            transferred_by=uuid.uuid4(),
            sender_confirmed_by=same_admin_id,
        )
        transfer.sender_confirmed_at = MagicMock()
        mock_repo.get_transfer.return_value = transfer

        # Even though admin1 has super_admin role, confirming both sides is forbidden
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = f["admin1"]
        mock_repo._session.execute.return_value = result_mock

        with pytest.raises(ConflictError, match="same user cannot confirm both"):
            await service.confirm_transfer_receiver(transfer_id, actor_id=same_admin_id)

    async def test_super_admin_bypass_facility_check(
        self, service, mock_repo, facilities_and_users
    ):
        f = facilities_and_users
        transfer_id = uuid.uuid4()
        transfer = FacilityTransfer(
            id=transfer_id,
            dog_id=uuid.uuid4(),
            from_facility_id=f["facility_a"],
            to_facility_id=f["facility_b"],
            status=TransferStatus.PENDING,
            transferred_by=uuid.uuid4(),
        )
        mock_repo.get_transfer.return_value = transfer

        # Admin1 has no managed_facility_id, but super_admin bypasses facility check
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = f["admin1"]
        mock_repo._session.execute.return_value = result_mock

        res = await service.confirm_transfer_sender(transfer_id, actor_id=f["admin1"].id)
        assert res.sender_confirmed_at is not None
        assert res.sender_confirmed_by == f["admin1"].id
