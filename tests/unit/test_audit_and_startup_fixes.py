"""Unit tests for the audit/seeding/activity-stream findings:

- startup role seeding always reconciles (never short-circuits on a
  non-empty DB) so new permission codes reach already-seeded databases;
- UserRepository.get_default_role resolves the seeded ``general_public``
  role (not a non-existent ``user`` role);
- AuditService.record persists structured before_state/after_state;
- the reusable dog activity-stream helper appends an immutable log row.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pawguard.main import _seed_roles
from pawguard.modules.auth.models import AuthAuditEventType, Role, User
from pawguard.modules.auth.repository import DEFAULT_PUBLIC_ROLE, UserRepository
from pawguard.modules.auth.service import AuthService, RequestContext
from pawguard.modules.dog.models import DogActivityEventType, DogActivityLog
from pawguard.modules.dog.service import record_activity
from pawguard.services.audit_service import AuditService


def _ctx() -> RequestContext:
    return RequestContext(ip_address="203.0.113.9", user_agent="test-agent/1.0")


def _make_auth_service(**overrides: object) -> AuthService:
    kwargs: dict[str, object] = dict(
        user_repo=AsyncMock(),
        session_repo=AsyncMock(),
        refresh_token_repo=AsyncMock(),
        mfa_repo=AsyncMock(),
        password_reset_repo=AsyncMock(),
        email_verification_repo=AsyncMock(),
        oauth_account_repo=AsyncMock(),
        audit_service=AsyncMock(),
    )
    kwargs.update(overrides)
    return AuthService(**kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
class TestStartupRoleReconciliation:
    async def test_seed_roles_always_reconciles_even_when_roles_exist(self) -> None:
        """The old guard returned early once any Role row existed, so new
        permission codes never reached an already-seeded DB. _seed_roles must
        invoke reconcile_roles unconditionally on every startup.

        Simulates the exact bug scenario: roles already exist (reconcile adds
        one missing permission rather than creating anything), and the startup
        still runs reconcile and commits.
        """
        session = AsyncMock()

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=session)
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("pawguard.db.session.AsyncSessionLocal", return_value=async_cm),
            patch(
                "scripts.seed_roles_and_permissions.reconcile_roles",
                new=AsyncMock(return_value=(0, 1)),
            ) as reconcile,
        ):
            await _seed_roles()

        # reconcile_roles is called even though roles already exist, in a
        # quiet mode, on the startup session.
        reconcile.assert_awaited_once()
        assert reconcile.call_args.args[0] is session
        assert reconcile.call_args.kwargs == {"verbose": False}
        session.commit.assert_awaited_once()

    async def test_seed_roles_commits_the_reconcile_transaction(self) -> None:
        """Reconcile is additive-only and idempotent; startup must commit so
        the grants are durable (reconcile_roles never commits itself)."""
        session = AsyncMock()

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=session)
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("pawguard.db.session.AsyncSessionLocal", return_value=async_cm),
            patch(
                "scripts.seed_roles_and_permissions.reconcile_roles",
                new=AsyncMock(return_value=(0, 0)),
            ),
        ):
            await _seed_roles()

        session.commit.assert_awaited_once()


@pytest.mark.asyncio
class TestDefaultRole:
    async def test_get_default_role_returns_general_public(self) -> None:
        """The seeded public role is `general_public`, not `user` - the old
        lookup returned None and new registrations got no role at all."""
        general_public = Role(name=DEFAULT_PUBLIC_ROLE, description="Public", is_system=False)
        session = AsyncMock()
        result = AsyncMock()
        result.scalar_one_or_none.return_value = general_public
        session.execute.return_value = result

        repo = UserRepository(session)
        role = await repo.get_default_role()

        assert role is general_public
        assert role.name == DEFAULT_PUBLIC_ROLE
        stmt = session.execute.call_args.args[0]
        params = list(stmt.compile().params.values())
        assert params == ["general_public"], "lookup must target the seeded public role"

    async def test_register_assigns_default_public_role(self) -> None:
        """New self-service users receive general_public so they can exercise
        PUBLIC_READ/PUBLIC_CREATE immediately instead of holding no role."""
        user_repo = AsyncMock()
        general_public = Role(name="general_public", description="Public", is_system=False)
        user_repo.get_by_email.return_value = None
        user_repo.get_default_role.return_value = general_public
        user = User(
            id=uuid.uuid4(),
            email="new@example.com",
            full_name="New User",
            hashed_password="x",
            is_active=True,
        )
        user_repo.create.return_value = user
        user_repo.get_by_id.return_value = user
        svc = _make_auth_service(user_repo=user_repo)

        await svc.register(
            email="new@example.com",
            password="StrongP@ss99",
            full_name="New User",
            phone=None,
            ctx=_ctx(),
        )

        created = user_repo.create.call_args.args[0]
        assert [r.name for r in created.roles] == ["general_public"]


@pytest.mark.asyncio
class TestAuditBeforeAfterState:
    async def test_record_persists_before_and_after_state(self) -> None:
        session = AsyncMock()
        service = AuditService(session)

        entry = await service.record(
            event_type=AuthAuditEventType.DOG_STATUS_CHANGED,
            actor_id=uuid.uuid4(),
            before_state={"status": "rescued"},
            after_state={"status": "shelter"},
        )

        assert entry.before_state == {"status": "rescued"}
        assert entry.after_state == {"status": "shelter"}
        added = session.add.call_args.args[0]
        assert added.before_state == {"status": "rescued"}
        assert added.after_state == {"status": "shelter"}
        session.flush.assert_awaited_once()

    async def test_record_without_state_keeps_columns_null(self) -> None:
        """Existing callers must not break - the new params are optional and
        default to NULL, so pre-existing audit rows have no state."""
        session = AsyncMock()
        entry = await AuditService(session).record(
            event_type=AuthAuditEventType.LOGIN_SUCCESS, actor_id=None
        )

        assert entry.before_state is None
        assert entry.after_state is None
        assert entry.event_type == "login_success"


@pytest.mark.asyncio
class TestDogActivityHelper:
    async def test_record_activity_appends_stream_row(self) -> None:
        session = AsyncMock()
        dog_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        log = await record_activity(
            session,
            dog_id=dog_id,
            event_type=DogActivityEventType.STATUS_CHANGED,
            actor_id=actor_id,
            message="Status changed.",
            metadata={"old_status": "rescued", "new_status": "shelter"},
        )

        assert isinstance(log, DogActivityLog)
        added = session.add.call_args.args[0]
        assert isinstance(added, DogActivityLog)
        assert added.dog_id == dog_id
        assert added.actor_id == actor_id
        assert added.event_type == DogActivityEventType.STATUS_CHANGED
        assert added.message == "Status changed."
        assert added.event_metadata == {"old_status": "rescued", "new_status": "shelter"}
        session.flush.assert_awaited_once()

    async def test_record_activity_accepts_cross_module_event_string(self) -> None:
        """Other modules (adoption/foster/medical/...) can write to the stream
        with a descriptive snake_case event string without editing this module."""
        session = AsyncMock()
        dog_id = uuid.uuid4()

        log = await record_activity(
            session, dog_id=dog_id, event_type="adoption_completed", actor_id=None
        )

        added = session.add.call_args.args[0]
        assert added.event_type == "adoption_completed"
        assert added.message == "adoption completed."
        assert log.event_type == "adoption_completed"
