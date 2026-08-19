"""Unit tests for AdminService audit-actor threading (M-1) and RBAC cache
invalidation (M-2).

Admin actions previously wrote audit rows with ``actor_id=None`` (no trail of
who made the change) and role-permission changes lingered in the 300s RBAC
cache. Both are fixed here and locked in by these tests.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from pawguard.modules.auth.models import AuthAuditEventType, Role, User
from pawguard.modules.auth.service import AdminService


class _FakeRedis:
    """Duck-typed RedisClient stand-in recording keys deleted by cache purge."""

    def __init__(self) -> None:
        self.deleted: list[str] = []
        self._store: dict[str, str] = {
            "rbac:roles:a:b": "1",
            "rbac:roles:c": "1",
        }

    async def scan_iter(self, match: str = "", count: int | None = None):
        import fnmatch
        for key in list(self._store):
            if fnmatch.fnmatch(key, match):
                yield key

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self._store.pop(key, None)


def _make_service(**overrides: object) -> AdminService:
    kwargs = dict(
        user_repo=AsyncMock(),
        role_repo=AsyncMock(),
        permission_repo=AsyncMock(),
        user_role_repo=AsyncMock(),
        audit_service=AsyncMock(),
        redis=None,
    )
    kwargs.update(overrides)
    return AdminService(**kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
class TestAdminAuditActorThreading:
    async def test_create_role_records_actor(self) -> None:
        audit = AsyncMock()
        role_repo = AsyncMock()
        role = Role(id=uuid.uuid4(), name="foster_coordinator", is_system=False)
        role_repo.get_by_name.return_value = None
        role_repo.create.return_value = role
        role_repo.get_by_id.return_value = role
        permission_repo = AsyncMock()
        permission_repo.get_by_codes.return_value = []
        svc = _make_service(
            role_repo=role_repo, permission_repo=permission_repo, audit_service=audit
        )
        actor_id = uuid.uuid4()

        await svc.create_role(
            name="foster_coordinator",
            description="Manages fosters",
            permission_codes=[],
            actor_id=actor_id,
            ip_address="10.0.0.7",
        )

        audit.record.assert_awaited_once()
        kwargs = audit.record.call_args.kwargs
        assert kwargs["event_type"] == AuthAuditEventType.ADMIN_ROLE_CREATED
        assert kwargs["actor_id"] == actor_id
        assert kwargs["ip_address"] == "10.0.0.7"

    async def test_update_user_records_actor(self) -> None:
        audit = AsyncMock()
        user_repo = AsyncMock()
        user = User(
            id=uuid.uuid4(),
            email="target@example.com",
            full_name="Target",
            hashed_password="x",
            is_active=True,
        )
        user_repo.get_by_id.return_value = user
        svc = _make_service(user_repo=user_repo, audit_service=audit)
        actor_id = uuid.uuid4()

        await svc.update_user(
            user.id, is_active=False, actor_id=actor_id, ip_address="10.0.0.7"
        )

        kwargs = audit.record.call_args.kwargs
        assert kwargs["event_type"] == AuthAuditEventType.ADMIN_USER_UPDATED
        assert kwargs["actor_id"] == actor_id

    async def test_delete_user_records_actor(self) -> None:
        audit = AsyncMock()
        user_repo = AsyncMock()
        user = User(
            id=uuid.uuid4(),
            email="gone@example.com",
            full_name="Gone",
            hashed_password="x",
        )
        user_repo.get_by_id.return_value = user
        svc = _make_service(user_repo=user_repo, audit_service=audit)
        actor_id = uuid.uuid4()

        await svc.delete_user(user.id, actor_id=actor_id)

        kwargs = audit.record.call_args.kwargs
        assert kwargs["event_type"] == AuthAuditEventType.ADMIN_USER_DELETED
        assert kwargs["actor_id"] == actor_id


@pytest.mark.asyncio
class TestRbacCacheInvalidation:
    async def test_update_role_invalidates_rbac_cache(self) -> None:
        role_repo = AsyncMock()
        role = Role(id=uuid.uuid4(), name="coordinator", is_system=False)
        role_repo.get_by_id.return_value = role
        permission_repo = AsyncMock()
        perm = AsyncMock()
        perm.code = "rescue:delete"
        permission_repo.get_by_codes.return_value = [perm]
        fake_redis = _FakeRedis()
        svc = _make_service(
            role_repo=role_repo, permission_repo=permission_repo, redis=fake_redis
        )

        await svc.update_role(
            role.id, description=None, permission_codes=["rescue:delete"]
        )

        # Both scanned rbac:roles:* keys were purged.
        assert sorted(fake_redis.deleted) == ["rbac:roles:a:b", "rbac:roles:c"]

    async def test_delete_role_invalidates_rbac_cache(self) -> None:
        role_repo = AsyncMock()
        role = Role(id=uuid.uuid4(), name="coordinator", is_system=False)
        role_repo.get_by_id.return_value = role
        fake_redis = _FakeRedis()
        svc = _make_service(role_repo=role_repo, redis=fake_redis)

        await svc.delete_role(role.id)

        assert fake_redis.deleted, "expected role deletion to purge the RBAC cache"

    async def test_invalidation_is_optional_without_redis(self) -> None:
        """redis=None (tests / legacy wiring) must not raise."""
        role_repo = AsyncMock()
        role = Role(id=uuid.uuid4(), name="coordinator", is_system=False)
        role_repo.get_by_id.return_value = role
        permission_repo = AsyncMock()
        perm = AsyncMock()
        perm.code = "rescue:delete"
        permission_repo.get_by_codes.return_value = [perm]
        svc = _make_service(role_repo=role_repo, permission_repo=permission_repo)

        await svc.update_role(
            role.id, description=None, permission_codes=["rescue:delete"]
        )
