"""Data access for the auth module. Repositories never contain business decisions (RULE-002)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pawguard.modules.auth.models import (
    AuthAuditLog,
    EmailVerificationToken,
    MFADevice,
    OAuthAccount,
    PasswordResetToken,
    Permission,
    RefreshToken,
    Role,
    User,
    UserSession,
)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .where(User.id == user_id, User.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .where(User.email == email.lower(), User.deleted_at.is_(None))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_default_role(self) -> Role | None:
        stmt = select(Role).where(Role.name == "user")
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_role_by_name(self, name: str) -> Role | None:
        stmt = select(Role).where(Role.name == name)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> list[User]:
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.deleted_at.is_(None))
            .order_by(User.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_session: UserSession) -> UserSession:
        self._session.add(user_session)
        await self._session.flush()
        return user_session

    async def get_by_id(self, session_id: uuid.UUID) -> UserSession | None:
        stmt = select(UserSession).where(UserSession.id == session_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[UserSession]:
        stmt = (
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.is_active.is_(True))
            .order_by(UserSession.last_used_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def revoke(self, session_id: uuid.UUID, *, reason: str) -> None:
        stmt = (
            update(UserSession)
            .where(UserSession.id == session_id, UserSession.is_active.is_(True))
            .values(is_active=False, revoked_at=datetime.now(UTC), revoked_reason=reason)
        )
        await self._session.execute(stmt)

    async def revoke_all_for_user(
        self, user_id: uuid.UUID, *, reason: str, except_session_id: uuid.UUID | None = None
    ) -> None:
        stmt = update(UserSession).where(
            UserSession.user_id == user_id, UserSession.is_active.is_(True)
        )
        if except_session_id is not None:
            stmt = stmt.where(UserSession.id != except_session_id)
        stmt = stmt.values(is_active=False, revoked_at=datetime.now(UTC), revoked_reason=reason)
        await self._session.execute(stmt)

    async def touch_last_used(self, session_id: uuid.UUID) -> None:
        stmt = (
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(last_used_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, token: RefreshToken) -> RefreshToken:
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def revoke(
        self, token_id: uuid.UUID, *, reason: str, rotated_to_id: uuid.UUID | None = None
    ) -> None:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.id == token_id)
            .values(
                revoked_at=datetime.now(UTC), revoked_reason=reason, rotated_to_id=rotated_to_id
            )
        )
        await self._session.execute(stmt)

    async def revoke_all_for_session(self, session_id: uuid.UUID, *, reason: str) -> None:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.session_id == session_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
        )
        await self._session.execute(stmt)


class MFARepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user(self, user_id: uuid.UUID) -> MFADevice | None:
        stmt = select(MFADevice).where(MFADevice.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(self, device: MFADevice) -> MFADevice:
        self._session.add(device)
        await self._session.flush()
        return device


class PasswordResetTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, token: PasswordResetToken) -> PasswordResetToken:
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def mark_used(self, token_id: uuid.UUID) -> None:
        stmt = (
            update(PasswordResetToken)
            .where(PasswordResetToken.id == token_id)
            .values(used_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)


class EmailVerificationTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, token: EmailVerificationToken) -> EmailVerificationToken:
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> EmailVerificationToken | None:
        stmt = select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def mark_used(self, token_id: uuid.UUID) -> None:
        stmt = (
            update(EmailVerificationToken)
            .where(EmailVerificationToken.id == token_id)
            .values(used_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, role_id: uuid.UUID) -> Role | None:
        # Eager-load permissions: RoleResponse always reads role.permissions
        # to build permission_codes, and accessing an unloaded relationship
        # outside an explicit awaited context raises MissingGreenlet on an
        # AsyncSession instead of a lazy DB round-trip.
        stmt = select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_name(self, name: str) -> Role | None:
        stmt = select(Role).where(Role.name == name)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> list[Role]:
        stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
        return list((await self._session.execute(stmt)).scalars().all())

    async def create(self, role: Role) -> Role:
        self._session.add(role)
        await self._session.flush()
        return role

    async def delete(self, role_id: uuid.UUID) -> None:
        stmt = select(Role).where(Role.id == role_id)
        role = (await self._session.execute(stmt)).scalar_one_or_none()
        if role is not None:
            await self._session.delete(role)
            await self._session.flush()

    async def get_permission_codes(self, role_id: uuid.UUID) -> set[str]:
        from pawguard.modules.auth.models import Permission, RolePermission
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return {row[0] for row in (await self._session.execute(stmt)).all()}

    async def set_permissions(self, role_id: uuid.UUID, permission_ids: list[uuid.UUID]) -> None:
        from sqlalchemy import delete

        from pawguard.modules.auth.models import RolePermission
        await self._session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for pid in permission_ids:
            self._session.add(RolePermission(role_id=role_id, permission_id=pid))
        await self._session.flush()


class PermissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_code(self, code: str) -> Permission | None:
        stmt = select(Permission).where(Permission.code == code)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_or_create(self, code: str, description: str | None = None) -> Permission:
        existing = await self.get_by_code(code)
        if existing is not None:
            return existing
        perm = Permission(code=code, description=description or code)
        self._session.add(perm)
        await self._session.flush()
        return perm

    async def list_all(self) -> list[Permission]:
        stmt = select(Permission).order_by(Permission.code)
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_by_codes(self, codes: list[str]) -> list[Permission]:
        stmt = select(Permission).where(Permission.code.in_(codes))
        return list((await self._session.execute(stmt)).scalars().all())


class UserRoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_roles(self, user_id: uuid.UUID, role_ids: list[uuid.UUID]) -> None:
        from sqlalchemy import delete

        from pawguard.modules.auth.models import UserRole
        await self._session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        for rid in role_ids:
            self._session.add(UserRole(user_id=user_id, role_id=rid))
        await self._session.flush()

    async def grant_role(self, user_id: uuid.UUID, role_id: uuid.UUID) -> None:
        """Additively grants a role, leaving the user's existing roles intact.

        Used when a staff approval (volunteer/foster onboarding, etc.) should
        unlock that module's self-service permissions without touching
        whatever other roles the user already holds. Idempotent.
        """
        from pawguard.modules.auth.models import UserRole

        existing = await self._session.execute(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == role_id
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        self._session.add(UserRole(user_id=user_id, role_id=role_id))
        await self._session.flush()


class OAuthAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_provider(
        self, provider: str, provider_user_id: str
    ) -> OAuthAccount | None:
        stmt = select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_for_user(self, user_id: uuid.UUID) -> list[OAuthAccount]:
        stmt = (
            select(OAuthAccount)
            .where(OAuthAccount.user_id == user_id)
            .order_by(OAuthAccount.provider)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def create(self, account: OAuthAccount) -> OAuthAccount:
        self._session.add(account)
        await self._session.flush()
        return account

    async def delete(self, account_id: uuid.UUID) -> None:
        stmt = select(OAuthAccount).where(OAuthAccount.id == account_id)
        account = (await self._session.execute(stmt)).scalar_one_or_none()
        if account is not None:
            await self._session.delete(account)
            await self._session.flush()


class AuthAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, entry: AuthAuditLog) -> AuthAuditLog:
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        event_type: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[AuthAuditLog]:
        stmt = select(AuthAuditLog)
        if event_type:
            stmt = stmt.where(AuthAuditLog.event_type == event_type)
        if user_id:
            stmt = stmt.where(AuthAuditLog.user_id == user_id)
        stmt = stmt.order_by(AuthAuditLog.created_at.desc()).offset(skip).limit(limit)
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_by_id(self, entry_id: uuid.UUID) -> AuthAuditLog | None:
        stmt = select(AuthAuditLog).where(AuthAuditLog.id == entry_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()
