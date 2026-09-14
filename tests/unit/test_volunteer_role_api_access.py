"""Unit tests verifying volunteer role permissions and access across volunteer and grievance endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from scripts.seed_roles_and_permissions import ROLE_DEFINITIONS

from pawguard.core.exceptions import register_exception_handlers
from pawguard.core.security import AccessTokenClaims
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.models import Permission, Role, User
from pawguard.modules.grievance.models import ServiceFeedback
from pawguard.modules.grievance.router import get_grievance_service
from pawguard.modules.grievance.router import router as grievance_router
from pawguard.modules.volunteer.models import (
    AttendanceStatus,
    ShiftAttendance,
    VolunteerProfile,
    VolunteerShift,
    VolunteerStatus,
)
from pawguard.modules.volunteer.router import get_volunteer_service
from pawguard.modules.volunteer.router import router as volunteer_router


class TestVolunteerRoleDefinitions:
    def test_volunteer_role_has_exact_required_permissions(self):
        definitions = {name: set(perms) for name, _, _, perms in ROLE_DEFINITIONS}
        volunteer_perms = definitions["volunteer"]

        # Required permissions granted
        assert "volunteer:read" in volunteer_perms
        assert "grievance:read" in volunteer_perms
        assert "grievance:create" in volunteer_perms
        assert "public:read" in volunteer_perms
        assert "dashboard:volunteer" in volunteer_perms

        # Privileged coordinator/admin permissions MUST NOT be granted
        assert "volunteer:update" not in volunteer_perms
        assert "volunteer:delete" not in volunteer_perms
        assert "volunteer:schedule" not in volunteer_perms
        assert "grievance:update" not in volunteer_perms
        assert "grievance:assign" not in volunteer_perms
        assert "system:admin" not in volunteer_perms


class TestVolunteerEndpointPermissions:
    @pytest.fixture
    def test_app(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(volunteer_router, prefix="/api/v1")
        app.include_router(grievance_router, prefix="/api/v1")
        return app

    @pytest.fixture
    def volunteer_user(self) -> User:
        perms = [
            Permission(id=uuid.uuid4(), code="volunteer:read"),
            Permission(id=uuid.uuid4(), code="grievance:read"),
            Permission(id=uuid.uuid4(), code="grievance:create"),
            Permission(id=uuid.uuid4(), code="public:read"),
            Permission(id=uuid.uuid4(), code="dashboard:volunteer"),
        ]
        role = Role(id=uuid.uuid4(), name="volunteer", is_system=False, permissions=perms)
        user = User(
            id=uuid.uuid4(),
            email="volunteer@example.com",
            full_name="Volunteer User",
            is_active=True,
            is_verified=True,
            roles=[role],
        )
        return user

    @pytest.fixture
    def current_volunteer(self, volunteer_user: User) -> CurrentUser:
        claims = AccessTokenClaims(
            user_id=volunteer_user.id,
            session_id=uuid.uuid4(),
            roles=["volunteer"],
            jti=str(uuid.uuid4()),
            expires_at=datetime.now(UTC),
        )
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        return CurrentUser(
            user=volunteer_user,
            claims=claims,
            db=AsyncMock(),
            redis=mock_redis,
        )

    @pytest.mark.asyncio
    async def test_get_volunteers_directory_authorized_with_volunteer_read(
        self, test_app: FastAPI, current_volunteer: CurrentUser
    ):
        from pawguard.core.responses import PaginationMeta

        mock_svc = AsyncMock()
        mock_svc.list_profiles.return_value = (
            [],
            PaginationMeta(page=1, page_size=20, total=0, total_pages=1),
        )

        test_app.dependency_overrides[get_current_user] = lambda: current_volunteer
        test_app.dependency_overrides[get_volunteer_service] = lambda: mock_svc

        with (
            patch(
                "pawguard.modules.auth.rbac.get_role_permission_codes",
                AsyncMock(
                    return_value={
                        "volunteer:read",
                        "grievance:read",
                        "public:read",
                        "dashboard:volunteer",
                    }
                ),
            ),
            patch(
                "pawguard.modules.auth.rbac.get_user_permission_codes",
                AsyncMock(return_value=set()),
            ),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/volunteers")
                assert resp.status_code == 200
                assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_get_grievance_feedback_authorized_with_volunteer_read(
        self, test_app: FastAPI, current_volunteer: CurrentUser
    ):
        from pawguard.core.responses import PaginationMeta

        mock_svc = AsyncMock()
        mock_svc.list_feedback.return_value = (
            [],
            PaginationMeta(page=1, page_size=20, total=0, total_pages=1),
        )

        test_app.dependency_overrides[get_current_user] = lambda: current_volunteer
        test_app.dependency_overrides[get_grievance_service] = lambda: mock_svc

        with (
            patch(
                "pawguard.modules.auth.rbac.get_role_permission_codes",
                AsyncMock(
                    return_value={
                        "volunteer:read",
                        "grievance:read",
                        "public:read",
                        "dashboard:volunteer",
                    }
                ),
            ),
            patch(
                "pawguard.modules.auth.rbac.get_user_permission_codes",
                AsyncMock(return_value=set()),
            ),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/grievance/feedback")
                assert resp.status_code == 200
                assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_post_grievance_feedback_authorized(
        self, test_app: FastAPI, current_volunteer: CurrentUser
    ):
        mock_svc = AsyncMock()
        fb_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_fb = ServiceFeedback(
            id=fb_id,
            rating=5,
            comments="Great shelter experience",
            created_at=now,
            updated_at=now,
        )
        mock_svc.submit_feedback.return_value = mock_fb

        test_app.dependency_overrides[get_current_user] = lambda: current_volunteer
        test_app.dependency_overrides[get_grievance_service] = lambda: mock_svc

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/grievance/feedback",
                json={
                    "rating": 5,
                    "comments": "Great shelter experience",
                },
            )
            assert resp.status_code == 201
            assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_volunteer_attendance_endpoints_authorized(
        self, test_app: FastAPI, current_volunteer: CurrentUser, volunteer_user: User
    ):
        mock_svc = AsyncMock()
        profile_id = uuid.uuid4()
        shift_id = uuid.uuid4()
        att_id = uuid.uuid4()
        now = datetime.now(UTC)

        mock_profile = VolunteerProfile(
            id=profile_id,
            user_id=volunteer_user.id,
            status=VolunteerStatus.ACTIVE,
            emergency_contact_name="Contact",
            emergency_contact_phone="+123",
            created_at=now,
            updated_at=now,
        )
        mock_shift = VolunteerShift(
            id=shift_id,
            role_name="Dog Walking",
            start_at=now,
            end_at=now,
            capacity=5,
            created_at=now,
            updated_at=now,
        )
        mock_attendance = ShiftAttendance(
            id=att_id,
            shift_id=shift_id,
            volunteer_id=profile_id,
            status=AttendanceStatus.CLAIMED,
            created_at=now,
            updated_at=now,
        )
        mock_attendance.shift = mock_shift

        mock_svc.get_profile_by_user.return_value = mock_profile
        mock_svc.list_all_attendance_for_volunteer.return_value = [mock_attendance]
        mock_svc.check_in.return_value = mock_attendance
        mock_svc.check_out.return_value = mock_attendance

        test_app.dependency_overrides[get_current_user] = lambda: current_volunteer
        test_app.dependency_overrides[get_volunteer_service] = lambda: mock_svc

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. GET /api/v1/volunteers/attendance
            get_resp = await client.get("/api/v1/volunteers/attendance")
            assert get_resp.status_code == 200
            assert len(get_resp.json()["data"]) == 1

            # 2. POST /api/v1/volunteers/attendance (check-in)
            post_resp = await client.post(
                "/api/v1/volunteers/attendance",
                json={"attendance_id": str(att_id), "action": "check_in"},
            )
            assert post_resp.status_code == 200
            mock_svc.check_in.assert_awaited()

            # 3. POST /api/v1/volunteers/attendance (check-out)
            post_out_resp = await client.post(
                "/api/v1/volunteers/attendance",
                json={"attendance_id": str(att_id), "action": "check_out"},
            )
            assert post_out_resp.status_code == 200
            mock_svc.check_out.assert_awaited()
