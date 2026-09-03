"""Unit tests for clinical dog-record permissions, requisition separation, and medical dashboard."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from scripts.seed_roles_and_permissions import ROLE_DEFINITIONS

from pawguard.core.exceptions import ForbiddenError
from pawguard.modules.auth import permission_codes as pc
from pawguard.modules.auth.dependencies import CurrentUser
from pawguard.modules.auth.models import Role, User
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dashboards.service import medical_dashboard
from pawguard.modules.dog.models import DogProfile, DogStatus
from pawguard.modules.dog.schemas import DogProfileCreate, DogProfileUpdate
from pawguard.modules.dog.service import DogService
from pawguard.modules.inventory.router import router as inventory_router
from pawguard.modules.medical.repository import MedicalRepository


@pytest.mark.asyncio
class TestDogInitialWeightLog:
    async def test_register_dog_with_positive_weight_creates_weight_log(self):
        mock_repo = AsyncMock()
        mock_repo._session = AsyncMock()
        mock_repo.get_duplicate_by_details.return_value = None
        mock_repo.get_by_microchip.return_value = None
        mock_repo.get_by_registration.return_value = None

        created_dog = DogProfile(
            id=uuid.uuid4(),
            registration_number="DOG-2026-1234",
            name="Buddy",
            breed="Labrador",
            gender="male",
            weight=15.5,
            status=DogStatus.RESCUED,
        )
        mock_repo.create.return_value = created_dog

        service = DogService(mock_repo)
        payload = DogProfileCreate(
            name="Buddy",
            breed="Labrador",
            gender="male",
            weight=15.5,
        )

        dog = await service.register_dog(payload)
        assert dog.id == created_dog.id

        # Verify initial DogWeightLog was created with weight 15.5
        assert mock_repo.create_weight_log.call_count == 1
        weight_log = mock_repo.create_weight_log.call_args[0][0]
        assert weight_log.dog_id == created_dog.id
        assert weight_log.weight == 15.5
        assert "initial weight" in weight_log.notes.lower()

    async def test_register_dog_with_zero_or_none_weight_skips_weight_log(self):
        mock_repo = AsyncMock()
        mock_repo._session = AsyncMock()
        mock_repo.get_duplicate_by_details.return_value = None
        mock_repo.get_by_microchip.return_value = None
        mock_repo.get_by_registration.return_value = None

        created_dog = DogProfile(
            id=uuid.uuid4(),
            registration_number="DOG-2026-5678",
            name="Pup",
            breed="Mix",
            gender="female",
            weight=None,
            status=DogStatus.RESCUED,
        )
        mock_repo.create.return_value = created_dog

        service = DogService(mock_repo)
        payload = DogProfileCreate(
            name="Pup",
            breed="Mix",
            gender="female",
            weight=None,
        )

        await service.register_dog(payload)
        assert mock_repo.create_weight_log.call_count == 0


class TestRoleAndPermissionDefinitions:
    def test_permission_codes_registered(self):
        assert pc.DOG_MEDICAL_UPDATE == "dog:medical_update"
        assert pc.REQUISITION_CREATE == "requisition:create"

    def test_veterinarian_role_permissions(self):
        role_map = {r[0]: set(r[3]) for r in ROLE_DEFINITIONS}
        vet_perms = role_map["veterinarian"]

        assert pc.DOG_MEDICAL_UPDATE in vet_perms
        assert pc.REQUISITION_CREATE in vet_perms
        assert pc.INVENTORY_CREATE not in vet_perms
        assert pc.SHELTER_UPDATE not in vet_perms

    def test_inventory_manager_role_permissions(self):
        role_map = {r[0]: set(r[3]) for r in ROLE_DEFINITIONS}
        im_perms = role_map["inventory_manager"]

        assert pc.INVENTORY_CREATE in im_perms
        assert pc.REQUISITION_CREATE in im_perms

    def test_shelter_manager_role_permissions(self):
        role_map = {r[0]: set(r[3]) for r in ROLE_DEFINITIONS}
        sm_perms = role_map["shelter_manager"]

        assert pc.REQUISITION_CREATE in sm_perms
        assert pc.SHELTER_UPDATE in sm_perms


@pytest.mark.asyncio
class TestDogMedicalUpdatePermissions:
    async def test_require_permission_allows_any_matching_code(self):
        require_check = require_permission("shelter:update", pc.DOG_MEDICAL_UPDATE)

        vet_claims = MagicMock()
        vet_claims.roles = ["veterinarian"]
        vet_user = User(
            id=uuid.uuid4(),
            email="vet@pawguard.org",
            full_name="Dr. Vet",
            hashed_password="hash",
            roles=[Role(name="veterinarian", description="vet")],
        )
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        current = CurrentUser(claims=vet_claims, user=vet_user, redis=mock_redis, db=AsyncMock())

        from unittest.mock import patch

        with patch(
            "pawguard.modules.auth.rbac.get_role_permission_codes",
            return_value=[pc.DOG_MEDICAL_UPDATE, pc.MEDICAL_READ],
        ):
            res = await require_check(current)
            assert res == current

    async def test_update_dog_rejects_non_medical_fields_for_medical_only_user(self):
        from pawguard.modules.dog.router import update_dog

        vet_user = User(
            id=uuid.uuid4(),
            email="vet@pawguard.org",
            full_name="Dr. Vet",
            hashed_password="hash",
            roles=[Role(name="veterinarian", description="vet")],
        )
        vet_claims = MagicMock()
        vet_claims.roles = ["veterinarian"]
        current = CurrentUser(claims=vet_claims, user=vet_user, redis=AsyncMock(), db=AsyncMock())

        mock_service = AsyncMock()
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        # Attempt to modify dog name (forbidden for vet)
        payload = DogProfileUpdate(name="Hacked Name")
        with pytest.raises(ForbiddenError, match="cannot modify non-medical fields"):
            await update_dog(
                dog_id=uuid.uuid4(),
                payload=payload,
                request=mock_request,
                current_user=current,
                service=mock_service,
            )

    async def test_update_dog_allows_adoptability_and_weight_fields(self):
        from pawguard.modules.dog.models import DogBreedClassification
        from pawguard.modules.dog.router import update_dog

        vet_user = User(
            id=uuid.uuid4(),
            email="vet@pawguard.org",
            full_name="Dr. Vet",
            hashed_password="hash",
            roles=[Role(name="veterinarian", description="vet")],
        )
        vet_claims = MagicMock()
        vet_claims.roles = ["veterinarian"]
        current = CurrentUser(claims=vet_claims, user=vet_user, redis=AsyncMock(), db=AsyncMock())

        now = datetime.now(UTC)
        dog_id = uuid.uuid4()
        returned_dog = DogProfile(
            id=dog_id,
            registration_number="DOG-2026-9999",
            name="Good Dog",
            breed="Retriever",
            breed_classification=DogBreedClassification.PURE,
            gender="male",
            is_spayed_neutered=False,
            is_adoptable=True,
            is_quarantine_passed=True,
            weight=18.0,
            status=DogStatus.SHELTER,
            created_at=now,
            updated_at=now,
        )
        mock_service = AsyncMock()
        mock_service.update_dog.return_value = returned_dog
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        payload = DogProfileUpdate(is_adoptable=True, is_quarantine_passed=True, weight=18.0)
        res = await update_dog(
            dog_id=dog_id,
            payload=payload,
            request=mock_request,
            current_user=current,
            service=mock_service,
        )
        assert res.data.is_adoptable is True


class TestInventoryRequisitionSeparation:
    def test_router_dependencies_separated(self):
        items_posts = [
            r
            for r in inventory_router.routes
            if r.path == "/inventory/items" and "POST" in r.methods
        ]
        assert len(items_posts) == 1
        items_perms = [
            d.dependency.permission_codes
            for d in items_posts[0].dependencies
            if hasattr(d.dependency, "permission_codes")
        ]
        assert ("inventory:create",) in items_perms

        req_posts = [
            r
            for r in inventory_router.routes
            if r.path == "/inventory/requisitions" and "POST" in r.methods
        ]
        assert len(req_posts) == 1
        req_perms = [
            d.dependency.permission_codes
            for d in req_posts[0].dependencies
            if hasattr(d.dependency, "permission_codes")
        ]
        assert ("requisition:create",) in req_perms


@pytest.mark.asyncio
class TestMedicalDashboardPendingVaccinations:
    async def test_medical_dashboard_queries_pending_vaccinations(self):
        mock_session = AsyncMock()

        res_exams = MagicMock()
        res_exams.scalar_one.return_value = 12
        res_treatments = MagicMock()
        res_treatments.scalar_one.return_value = 8
        res_pending = MagicMock()
        res_pending.scalar_one.return_value = 5

        mock_session.execute.side_effect = [res_exams, res_treatments, res_pending]

        data = await medical_dashboard(mock_session, redis=None)

        assert data["exams_last_30d"] == 12
        assert data["treatments_last_30d"] == 8
        assert data["pending_vaccinations"] == 5
        assert data["vaccinations_last_30d"] == 5

    async def test_list_vaccinations_paginated_pending_filter(self):
        from pawguard.core.search import SortParams

        mock_session = AsyncMock()
        count_res = MagicMock()
        count_res.scalar_one.return_value = 3
        scalars_res = MagicMock()
        scalars_res.scalars.return_value.all.return_value = []
        mock_session.execute.side_effect = [count_res, scalars_res]

        repo = MedicalRepository(mock_session)
        page = MagicMock(offset=0, limit=20)
        sort = SortParams(sort_by="vaccine_name", sort_order="asc")

        results, total = await repo.list_vaccinations_paginated(
            page=page,
            sort=sort,
            pending=True,
        )
        assert total == 3
        assert mock_session.execute.call_count == 2
