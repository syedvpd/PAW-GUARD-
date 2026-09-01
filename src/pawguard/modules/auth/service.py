"""AuthService: owns all authentication business behaviour (RULE-003).

Routers only authenticate/authorise/validate/call-service/return-response (RULE-004).
Repositories never make business decisions (RULE-002) — locking policy, token rotation
rules, and MFA gating all live here.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import pyotp

from pawguard.core.config import get_settings
from pawguard.core.constants import DeviceType
from pawguard.core.exceptions import NotFoundError
from pawguard.core.logging import get_logger
from pawguard.core.security import (
    TokenError,
    TokenType,
    create_access_token,
    create_pre_auth_token,
    decode_token,
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    is_encrypted_mfa_secret,
    needs_rehash,
    verify_password,
)
from pawguard.modules.auth import permission_codes as pc
from pawguard.modules.auth.exceptions import (
    AccountInactiveError,
    AccountLockedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidMFACodeError,
    InvalidRefreshTokenError,
    InvalidSessionError,
    InvalidTokenError,
    MFAAlreadyEnabledError,
    MFADisableNotAllowedError,
    MFARequiredError,
    RefreshTokenReuseDetectedError,
)
from pawguard.modules.auth.models import (
    AuthAuditEventType,
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
from pawguard.modules.auth.repository import (
    EmailVerificationTokenRepository,
    MFARepository,
    OAuthAccountRepository,
    PasswordResetTokenRepository,
    PermissionRepository,
    RefreshTokenRepository,
    RoleRepository,
    SessionRepository,
    UserPermissionRepository,
    UserRepository,
    UserRoleRepository,
)
from pawguard.modules.auth.schemas import DeviceContext, MFADisableRequest
from pawguard.redis.client import RedisClient
from pawguard.services.audit_service import AuditService
from pawguard.services.cache_service import CacheService

logger = get_logger(__name__)

MAX_FAILED_LOGIN_ATTEMPTS = 5
ACCOUNT_LOCKOUT_MINUTES = 15


class RequestContext:
    """Transport-agnostic metadata about the calling client, set by the router."""

    __slots__ = ("ip_address", "user_agent")

    def __init__(self, *, ip_address: str | None, user_agent: str | None) -> None:
        self.ip_address = ip_address
        self.user_agent = user_agent


class AuthenticatedTokens:
    __slots__ = ("access_token", "refresh_token", "expires_in", "user")

    def __init__(
        self, *, access_token: str, refresh_token: str, expires_in: int, user: User
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = expires_in
        self.user = user


class AuthService:
    def __init__(
        self,
        *,
        user_repo: UserRepository,
        session_repo: SessionRepository,
        refresh_token_repo: RefreshTokenRepository,
        mfa_repo: MFARepository,
        password_reset_repo: PasswordResetTokenRepository,
        email_verification_repo: EmailVerificationTokenRepository,
        oauth_account_repo: OAuthAccountRepository,
        audit_service: AuditService,
    ) -> None:
        self._users = user_repo
        self._sessions = session_repo
        self._refresh_tokens = refresh_token_repo
        self._mfa = mfa_repo
        self._password_resets = password_reset_repo
        self._email_verifications = email_verification_repo
        self._oauth_accounts = oauth_account_repo
        self._audit = audit_service
        self._settings = get_settings()

    # --- Registration ---

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        phone: str | None,
        ctx: RequestContext,
    ) -> User:
        normalized_email = email.lower()
        existing = await self._users.get_by_email(normalized_email)
        if existing is not None:
            raise EmailAlreadyRegisteredError("An account with this email already exists.")

        role = await self._users.get_default_role()
        user = User(
            email=normalized_email,
            full_name=full_name,
            phone=phone,
            hashed_password=await asyncio.to_thread(hash_password, password),
            is_active=True,
            is_verified=False,
        )
        if role is not None:
            user.roles.append(role)

        await self._users.create(user)
        fresh = await self._users.get_by_id(user.id)
        await self._audit.record(
            event_type=AuthAuditEventType.REGISTERED,
            actor_id=fresh.id if fresh else user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return fresh or user

    # --- Login ---

    async def login(
        self,
        *,
        email: str,
        password: str,
        device: DeviceContext,
        ctx: RequestContext,
        client_type: str | None = None,
        origin: str | None = None,
    ) -> AuthenticatedTokens | str:
        """Returns AuthenticatedTokens, or a pre-auth token (str) if MFA is required."""
        user = await self._users.get_by_email(email.lower())

        if user is None or not await asyncio.to_thread(
            verify_password, password, user.hashed_password
        ):
            if user is not None:
                await self._register_failed_attempt(user, ctx)
            await self._audit.record(
                event_type=AuthAuditEventType.LOGIN_FAILED,
                actor_id=user.id if user else None,
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
            )
            raise InvalidCredentialsError("Invalid email or password.")

        if await asyncio.to_thread(needs_rehash, user.hashed_password):
            user.hashed_password = await asyncio.to_thread(hash_password, password)

        if user.locked_until and user.locked_until > datetime.now(UTC):
            raise AccountLockedError("Account is temporarily locked due to failed login attempts.")

        if not user.is_active:
            raise AccountInactiveError("This account has been deactivated.")

        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = datetime.now(UTC)

        session = await self._create_session(user_id=user.id, device=device, ctx=ctx)

        if user.mfa_enabled or (
            self._settings.mfa_mandatory_for_admins
            and self._is_admin(user)
            and not (self._settings.mfa_bypass_for_dev and not self._settings.is_production)
        ):
            return create_pre_auth_token(user_id=user.id, session_id=session.id)

        tokens = await self._issue_tokens(user=user, session=session)
        await self._audit.record(
            event_type=AuthAuditEventType.LOGIN_SUCCESS,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return tokens

    async def verify_mfa_login(
        self, *, pre_auth_token: str, code: str, device: DeviceContext, ctx: RequestContext
    ) -> AuthenticatedTokens:
        try:
            payload = decode_token(pre_auth_token, expected_type=TokenType.PRE_AUTH)
        except TokenError as exc:
            raise InvalidTokenError("Pre-authentication token is invalid or expired.") from exc

        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])

        user = await self._users.get_by_id(user_id)
        session = await self._sessions.get_by_id(session_id)
        if user is None or session is None or not session.is_active:
            raise InvalidSessionError("Session is no longer valid.")

        device_record = await self._mfa.get_for_user(user.id)

        if self._is_admin(user) and not user.mfa_enabled:
            # Mandatory MFA for admins: an admin without an enrolled device
            # cannot complete login - they must enroll first (PRR security).
            # Note: mfa_bypass_for_dev only applies at the login() gate above;
            # if the user reaches verify_mfa_login, bypass is not applicable.
            await self._audit.record(
                event_type=AuthAuditEventType.MFA_FAILED,
                actor_id=user.id,
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
            )
            raise MFARequiredError("Admin accounts must enroll in MFA before completing login.")

        if device_record is None or not self._verify_totp(device_record, code):
            await self._audit.record(
                event_type=AuthAuditEventType.MFA_FAILED,
                actor_id=user.id,
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
            )
            raise InvalidMFACodeError("Invalid MFA code.")

        tokens = await self._issue_tokens(user=user, session=session)
        await self._audit.record(
            event_type=AuthAuditEventType.MFA_VERIFIED,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        await self._audit.record(
            event_type=AuthAuditEventType.LOGIN_SUCCESS,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return tokens

    # --- Refresh (with rotation + reuse detection) ---

    async def refresh(self, *, raw_refresh_token: str, ctx: RequestContext) -> AuthenticatedTokens:
        token_hash = hash_opaque_token(raw_refresh_token)
        existing = await self._refresh_tokens.get_by_hash(token_hash)

        if existing is None:
            raise InvalidRefreshTokenError("Refresh token is invalid.")

        ref_time = datetime.now(UTC)

        if existing.revoked_at is not None:
            revoked_at = existing.revoked_at
            if revoked_at.tzinfo is None:
                revoked_at = revoked_at.replace(tzinfo=UTC)

            if existing.revoked_reason == "rotated" and ref_time - revoked_at < timedelta(
                seconds=30
            ):
                logger.info(f"Rotated refresh token reused within grace period: {existing.id}")
            else:
                # Reuse of a rotated/revoked token — treat as a breach signal and kill the session.
                await self._sessions.revoke(
                    existing.session_id, reason="refresh_token_reuse_detected"
                )
                await self._refresh_tokens.revoke_all_for_session(
                    existing.session_id, reason="refresh_token_reuse_detected"
                )
                session = await self._sessions.get_by_id(existing.session_id)
                await self._audit.record(
                    event_type=AuthAuditEventType.REFRESH_REUSE_DETECTED,
                    actor_id=session.user_id if session else None,
                    ip_address=ctx.ip_address,
                    user_agent=ctx.user_agent,
                )
                raise RefreshTokenReuseDetectedError(
                    "Refresh token reuse detected. Session revoked."
                )

        expires_at = existing.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if expires_at < ref_time:
            raise InvalidRefreshTokenError("Refresh token has expired.")

        session = await self._sessions.get_by_id(existing.session_id)
        if session is None or not session.is_active:
            raise InvalidSessionError("Session is no longer valid.")

        session_expires_at = session.expires_at
        if session_expires_at.tzinfo is None:
            session_expires_at = session_expires_at.replace(tzinfo=UTC)

        if session_expires_at < ref_time:
            raise InvalidSessionError("Session has expired.")

        user = await self._users.get_by_id(session.user_id)
        if user is None or not user.is_active:
            raise AccountInactiveError("This account has been deactivated.")

        new_refresh_raw = generate_opaque_token()
        new_refresh_token = RefreshToken(
            session_id=session.id,
            token_hash=hash_opaque_token(new_refresh_raw),
            expires_at=datetime.now(UTC) + timedelta(days=self._settings.refresh_token_expire_days),
        )
        await self._refresh_tokens.create(new_refresh_token)
        await self._refresh_tokens.revoke(
            existing.id, reason="rotated", rotated_to_id=new_refresh_token.id
        )
        await self._sessions.touch_last_used(session.id)

        access_token = create_access_token(
            user_id=user.id,
            session_id=session.id,
            roles=[role.name for role in user.roles],
        )
        await self._audit.record(
            event_type=AuthAuditEventType.REFRESH,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return AuthenticatedTokens(
            access_token=access_token,
            refresh_token=new_refresh_raw,
            expires_in=self._settings.access_token_expire_minutes * 60,
            user=user,
        )

    # --- Logout ---

    async def logout(
        self, *, session_id: uuid.UUID, user_id: uuid.UUID, ctx: RequestContext
    ) -> None:
        await self._sessions.revoke(session_id, reason="user_logout")
        await self._refresh_tokens.revoke_all_for_session(session_id, reason="user_logout")
        await self._audit.record(
            event_type=AuthAuditEventType.LOGOUT,
            actor_id=user_id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )

    async def logout_all(
        self, *, user_id: uuid.UUID, current_session_id: uuid.UUID | None, ctx: RequestContext
    ) -> None:
        sessions = await self._sessions.list_active_for_user(user_id)
        await self._sessions.revoke_all_for_user(
            user_id, reason="user_logout_all", except_session_id=current_session_id
        )
        for s in sessions:
            if s.id != current_session_id:
                await self._refresh_tokens.revoke_all_for_session(s.id, reason="user_logout_all")
        await self._audit.record(
            event_type=AuthAuditEventType.LOGOUT_ALL,
            actor_id=user_id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )

    # --- Password management ---

    async def change_password(
        self,
        *,
        user: User,
        current_password: str,
        new_password: str,
        current_session_id: uuid.UUID,
        ctx: RequestContext,
    ) -> None:
        if current_password == new_password:
            raise InvalidCredentialsError("New password must be different from current password.")
        if not await asyncio.to_thread(verify_password, current_password, user.hashed_password):
            raise InvalidCredentialsError("Current password is incorrect.")

        user.hashed_password = await asyncio.to_thread(hash_password, new_password)
        await self._sessions.revoke_all_for_user(
            user.id, reason="password_changed", except_session_id=current_session_id
        )
        await self._audit.record(
            event_type=AuthAuditEventType.PASSWORD_CHANGE,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )

    async def create_password(
        self,
        *,
        user: User,
        new_password: str,
        ctx: RequestContext,
    ) -> None:
        """Allow social/OAuth-authenticated users to create their initial PawGuard password."""
        user.hashed_password = await asyncio.to_thread(hash_password, new_password)
        await self._audit.record(
            event_type=AuthAuditEventType.PASSWORD_CHANGE,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            metadata={"action": "password_created"},
        )

    async def request_password_reset(self, *, email: str, ctx: RequestContext) -> str | None:
        """Returns the raw token to be emailed, or None if no account exists (no enumeration)."""
        user = await self._users.get_by_email(email.lower())
        if user is None:
            return None

        raw_token = generate_opaque_token()
        token = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_opaque_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        await self._password_resets.create(token)
        await self._audit.record(
            event_type=AuthAuditEventType.PASSWORD_RESET_REQUESTED,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        # Push notification for password reset request
        try:
            from pawguard.modules.notifications.repository import NotificationRepository
            from pawguard.modules.notifications.service import NotificationService

            session = self._sessions._session
            notification_svc = NotificationService(repository=NotificationRepository(session))
            await notification_svc._send_push_to_users(
                [user.id],
                "Password Reset Requested",
                "A password reset was requested for your account. If you didn't request this, contact support.",
                "/auth/login",
            )
        except Exception:
            logger.debug("push_notification_skipped", action="password_reset_request")
        return raw_token

    async def confirm_password_reset(
        self, *, raw_token: str, new_password: str, ctx: RequestContext
    ) -> None:
        token_hash = hash_opaque_token(raw_token)
        token = await self._password_resets.get_by_hash(token_hash)

        if token is None or token.used_at is not None or token.expires_at < datetime.now(UTC):
            raise InvalidTokenError("Password reset token is invalid or expired.")

        user = await self._users.get_by_id(token.user_id)
        if user is None:
            raise InvalidTokenError("Password reset token is invalid or expired.")

        user.hashed_password = await asyncio.to_thread(hash_password, new_password)
        await self._password_resets.mark_used(token.id)
        await self._sessions.revoke_all_for_user(user.id, reason="password_reset")
        await self._audit.record(
            event_type=AuthAuditEventType.PASSWORD_RESET_COMPLETED,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )

    # --- Email verification ---

    async def request_email_verification(self, *, user: User, ctx: RequestContext) -> str:
        raw_token = generate_opaque_token()
        token = EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_opaque_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        await self._email_verifications.create(token)
        await self._audit.record(
            event_type=AuthAuditEventType.EMAIL_VERIFICATION_REQUESTED,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return raw_token

    async def confirm_email_verification(self, *, raw_token: str, ctx: RequestContext) -> None:
        token_hash = hash_opaque_token(raw_token)
        token = await self._email_verifications.get_by_hash(token_hash)

        if token is None or token.used_at is not None or token.expires_at < datetime.now(UTC):
            raise InvalidTokenError("Email verification token is invalid or expired.")

        user = await self._users.get_by_id(token.user_id)
        if user is None:
            raise InvalidTokenError("Email verification token is invalid or expired.")

        user.is_verified = True
        user.email_verified_at = datetime.now(UTC)
        await self._email_verifications.mark_used(token.id)
        await self._audit.record(
            event_type=AuthAuditEventType.EMAIL_VERIFIED,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )

    # --- MFA enrollment ---

    async def enroll_mfa(self, *, user: User) -> tuple[str, str]:
        if user.mfa_enabled:
            raise MFAAlreadyEnabledError("MFA is already enabled for this account.")

        secret = pyotp.random_base32()
        encrypted_secret = encrypt_mfa_secret(secret)
        existing = await self._mfa.get_for_user(user.id)
        if existing is None:
            await self._mfa.create(
                MFADevice(
                    user_id=user.id,
                    device_type="totp",
                    secret_encrypted=encrypted_secret,
                )
            )
        else:
            existing.secret_encrypted = encrypted_secret
            existing.is_verified = False

        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="PawGuard")
        return secret, uri

    async def confirm_mfa_enrollment(self, *, user: User, code: str, ctx: RequestContext) -> None:
        device = await self._mfa.get_for_user(user.id)
        if device is None or not self._verify_totp(device, code):
            raise InvalidMFACodeError("Invalid MFA code.")

        device.is_verified = True
        user.mfa_enabled = True
        await self._audit.record(
            event_type=AuthAuditEventType.MFA_ENROLLED,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        # Push notification for MFA enrollment
        try:
            from pawguard.modules.notifications.repository import NotificationRepository
            from pawguard.modules.notifications.service import NotificationService

            session = self._sessions._session
            notification_svc = NotificationService(repository=NotificationRepository(session))
            await notification_svc._send_push_to_users(
                [user.id],
                "MFA Enabled",
                "Multi-factor authentication has been enabled on your account.",
                "/auth/settings",
            )
        except Exception:
            logger.debug("push_notification_skipped", action="mfa_enrolled")

    # --- Sessions ---

    async def list_sessions(self, *, user_id: uuid.UUID) -> list[UserSession]:
        return await self._sessions.list_active_for_user(user_id)

    async def revoke_session(
        self, *, user_id: uuid.UUID, session_id: uuid.UUID, ctx: RequestContext
    ) -> None:
        session = await self._sessions.get_by_id(session_id)
        if session is None or session.user_id != user_id:
            raise InvalidSessionError("Session not found.")
        await self._sessions.revoke(session_id, reason="user_revoked")
        await self._refresh_tokens.revoke_all_for_session(session_id, reason="user_revoked")
        await self._audit.record(
            event_type=AuthAuditEventType.SESSION_REVOKED,
            actor_id=user_id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )

    # --- Internal helpers ---

    async def _create_session(
        self, *, user_id: uuid.UUID, device: DeviceContext, ctx: RequestContext
    ) -> UserSession:
        session = UserSession(
            user_id=user_id,
            device_id=device.device_id,
            device_name=device.device_name,
            device_type=device.device_type or DeviceType.UNKNOWN,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            is_active=True,
            expires_at=datetime.now(UTC) + timedelta(days=self._settings.refresh_token_expire_days),
        )
        return await self._sessions.create(session)

    async def _issue_tokens(self, *, user: User, session: UserSession) -> AuthenticatedTokens:
        session.user = user

        access_token = create_access_token(
            user_id=user.id,
            session_id=session.id,
            roles=[role.name for role in user.roles],
        )
        raw_refresh_token = generate_opaque_token()
        refresh_token = RefreshToken(
            session_id=session.id,
            token_hash=hash_opaque_token(raw_refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=self._settings.refresh_token_expire_days),
        )
        await self._refresh_tokens.create(refresh_token)

        return AuthenticatedTokens(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in=self._settings.access_token_expire_minutes * 60,
            user=user,
        )

    async def _register_failed_attempt(self, user: User, ctx: RequestContext) -> None:
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=ACCOUNT_LOCKOUT_MINUTES)
            await self._audit.record(
                event_type=AuthAuditEventType.ACCOUNT_LOCKED,
                actor_id=user.id,
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
            )

    @staticmethod
    def _verify_totp(device: MFADevice, code: str) -> bool:
        stored = device.secret_encrypted
        secret = decrypt_mfa_secret(stored)
        verified = pyotp.totp.TOTP(secret).verify(code, valid_window=1)
        if verified and not is_encrypted_mfa_secret(stored):
            device.secret_encrypted = encrypt_mfa_secret(secret)
        return verified

    @staticmethod
    def _is_admin(user: User) -> bool:
        """True when the user holds the `system:admin` permission via any role.

        Used to enforce mandatory MFA for admin accounts: admins always hit
        the MFA challenge at login and can never disable MFA.
        """
        for role in user.roles:
            for permission in role.permissions:
                if permission.code == pc.SYSTEM_ADMIN:
                    return True
        return False

    # --- MFA disable ---

    async def disable_mfa(
        self, *, user: User, payload: MFADisableRequest, ctx: RequestContext
    ) -> None:
        if self._is_admin(user):
            raise MFADisableNotAllowedError("Admins must keep MFA enabled.")

        confirmed_via: str | None = None

        if payload.password is not None:
            if not await asyncio.to_thread(verify_password, payload.password, user.hashed_password):
                raise InvalidCredentialsError("Incorrect password.")
            confirmed_via = "password"

        if payload.totp_code is not None:
            device = await self._mfa.get_for_user(user.id)
            if device is None or not self._verify_totp(device, payload.totp_code):
                raise InvalidMFACodeError("Invalid MFA code.")
            if confirmed_via is None:
                confirmed_via = "totp"

        if confirmed_via is None:
            raise InvalidCredentialsError(
                "Provide either your current password or a valid TOTP code."
            )

        device = await self._mfa.get_for_user(user.id)
        if device is not None:
            device.is_verified = False
        user.mfa_enabled = False
        await self._audit.record(
            event_type=AuthAuditEventType.MFA_DISABLED,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            metadata={"confirmed_via": confirmed_via},
        )
        # Push notification for MFA disable (security alert)
        try:
            from pawguard.modules.notifications.repository import NotificationRepository
            from pawguard.modules.notifications.service import NotificationService

            session = self._sessions._session
            notification_svc = NotificationService(repository=NotificationRepository(session))
            await notification_svc._send_push_to_users(
                [user.id],
                "MFA Disabled",
                "Multi-factor authentication has been disabled on your account. If you didn't do this, secure your account immediately.",
                "/auth/settings",
            )
        except Exception:
            logger.debug("push_notification_skipped", action="mfa_disabled")

    # --- OAuth / Social Login ---

    async def oauth_login(
        self,
        *,
        provider: str,
        provider_token: str,
        device: DeviceContext,
        ctx: RequestContext,
    ) -> AuthenticatedTokens:
        provider = provider.lower()
        provider_data = await self._verify_oauth_token(provider, provider_token)
        provider_user_id = str(provider_data["sub"])
        provider_email = (provider_data.get("email") or "").strip()

        account = await self._oauth_accounts.get_by_provider(provider, provider_user_id)
        if account is not None:
            user = await self._users.get_by_id(account.user_id)
        else:
            normalized_email = provider_email.lower() if provider_email else ""
            user = await self._users.get_by_email(normalized_email) if normalized_email else None
            if user is None:
                raw_name = (provider_data.get("name") or "").strip()
                display_name = raw_name or normalized_email or f"{provider.capitalize()} User"
                user = User(
                    email=normalized_email or f"{provider_user_id}@{provider}.oauth",
                    full_name=display_name,
                    hashed_password=await asyncio.to_thread(hash_password, generate_opaque_token()),
                    is_active=True,
                    is_verified=bool(provider_email),
                )
                role = await self._users.get_default_role()
                if role is not None:
                    user.roles.append(role)
                await self._users.create(user)
                fetched_user = await self._users.get_by_id(user.id)
                if fetched_user is not None:
                    user = fetched_user
                await self._audit.record(
                    event_type=AuthAuditEventType.REGISTERED,
                    actor_id=user.id,
                    ip_address=ctx.ip_address,
                    user_agent=ctx.user_agent,
                )

            assert user is not None
            # Double-check if account was created concurrently
            existing_account = await self._oauth_accounts.get_by_provider(
                provider, provider_user_id
            )
            if existing_account is None:
                account = OAuthAccount(
                    user_id=user.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    provider_email=provider_email or None,
                    display_name=provider_data.get("name") or None,
                    picture_url=provider_data.get("picture") or None,
                )
                try:
                    await self._oauth_accounts.create(account)
                except Exception as exc:
                    logger.warning("oauth_account_create_skipped", error=str(exc))

        if not user or not user.is_active:
            raise AccountInactiveError("This account has been deactivated.")

        session = await self._create_session(user_id=user.id, device=device, ctx=ctx)
        tokens = await self._issue_tokens(user=user, session=session)
        await self._audit.record(
            event_type=AuthAuditEventType.OAUTH_LOGIN,
            actor_id=user.id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return tokens

    async def link_oauth_account(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        provider_token: str,
        ctx: RequestContext,
    ) -> OAuthAccount:
        provider_data = await self._verify_oauth_token(provider, provider_token)
        provider_user_id = provider_data["sub"]

        existing = await self._oauth_accounts.get_by_provider(provider, provider_user_id)
        if existing is not None:
            from pawguard.core.exceptions import ConflictError

            raise ConflictError(f"This {provider} account is already linked to another user.")

        account = OAuthAccount(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=provider_data.get("email"),
            display_name=provider_data.get("name"),
            picture_url=provider_data.get("picture"),
        )
        await self._oauth_accounts.create(account)
        await self._audit.record(
            event_type=AuthAuditEventType.OAUTH_LINKED,
            actor_id=user_id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return account

    async def unlink_oauth_account(
        self, *, user_id: uuid.UUID, account_id: uuid.UUID, ctx: RequestContext
    ) -> None:
        accounts = await self._oauth_accounts.get_for_user(user_id)
        account = next((a for a in accounts if a.id == account_id), None)
        if account is None:
            raise NotFoundError("OAuth account not found.")
        await self._oauth_accounts.delete(account_id)
        await self._audit.record(
            event_type=AuthAuditEventType.OAUTH_UNLINKED,
            actor_id=user_id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )

    async def list_oauth_accounts(self, *, user_id: uuid.UUID) -> list[OAuthAccount]:
        return await self._oauth_accounts.get_for_user(user_id)

    @staticmethod
    async def _verify_oauth_token(provider: str, token: str) -> dict[str, str]:
        try:
            return await AuthService._verify_oauth_token_unsafe(provider, token)
        except InvalidCredentialsError:
            raise
        except Exception as exc:
            # A malformed/garbage token, a provider outage, a network error,
            # or an unexpected response shape must surface as a clean 401,
            # not an unhandled 500 - narrowing this to specific exception
            # types (httpx.HTTPError, KeyError, ValueError) still let a 500
            # through live, presumably from some other transport/SSL error
            # shape on the hosting environment's network path to the
            # provider. There's no legitimate reason for this helper to ever
            # raise anything other than "the token didn't verify."
            raise InvalidCredentialsError(f"Could not verify {provider} token.") from exc

    @staticmethod
    async def _verify_oauth_token_unsafe(provider: str, token: str) -> dict[str, str]:
        import httpx

        if provider == "google":
            expected_aud = get_settings().google_oauth_client_id
            if not expected_aud:
                raise InvalidCredentialsError("Google OAuth is not configured on this server.")
            valid_auds = [aud.strip() for aud in expected_aud.split(",") if aud.strip()]
            async with httpx.AsyncClient() as client:
                if token.startswith("ya29."):
                    import time

                    from pawguard.core.metrics import track_outbound_request

                    start = time.perf_counter()
                    info_resp = await client.get(
                        f"https://oauth2.googleapis.com/tokeninfo?access_token={token}",
                        timeout=10,
                    )
                    duration_ms = (time.perf_counter() - start) * 1000
                    track_outbound_request(
                        destination="google_oauth",
                        operation="tokeninfo",
                        request_bytes=0,
                        response_bytes=len(info_resp.content),
                        duration_ms=duration_ms,
                        status="success" if info_resp.status_code == 200 else "failed",
                    )
                    if info_resp.status_code != 200:
                        raise InvalidCredentialsError("Invalid Google access token.")
                    info_data = info_resp.json()
                    aud = info_data.get("aud") or info_data.get("azp")
                    if aud not in valid_auds:
                        raise InvalidCredentialsError(
                            "Google token was not issued for this application."
                        )
                    start = time.perf_counter()
                    userinfo_resp = await client.get(
                        "https://www.googleapis.com/oauth2/v3/userinfo",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10,
                    )
                    duration_ms = (time.perf_counter() - start) * 1000
                    track_outbound_request(
                        destination="google_oauth",
                        operation="userinfo",
                        request_bytes=0,
                        response_bytes=len(userinfo_resp.content),
                        duration_ms=duration_ms,
                        status="success" if userinfo_resp.status_code == 200 else "failed",
                    )
                    user_data = userinfo_resp.json() if userinfo_resp.status_code == 200 else {}
                    sub = info_data.get("sub") or user_data.get("sub")
                    email = info_data.get("email") or user_data.get("email", "")
                    if not sub:
                        raise InvalidCredentialsError("Google sub identifier missing.")
                    return {
                        "sub": sub,
                        "email": email,
                        "name": user_data.get("name", ""),
                        "picture": user_data.get("picture", ""),
                    }
                else:
                    import time

                    from pawguard.core.metrics import track_outbound_request

                    start = time.perf_counter()
                    resp = await client.get(
                        f"https://oauth2.googleapis.com/tokeninfo?id_token={token}",
                        timeout=10,
                    )
                    duration_ms = (time.perf_counter() - start) * 1000
                    track_outbound_request(
                        destination="google_oauth",
                        operation="tokeninfo_id",
                        request_bytes=0,
                        response_bytes=len(resp.content),
                        duration_ms=duration_ms,
                        status="success" if resp.status_code == 200 else "failed",
                    )
                    if resp.status_code != 200:
                        raise InvalidCredentialsError("Invalid Google token.")
                    data = resp.json()
                    if data.get("aud") not in valid_auds:
                        raise InvalidCredentialsError(
                            "Google token was not issued for this application."
                        )
                    if not data.get("email_verified") and not data.get("sub"):
                        raise InvalidCredentialsError("Google email not verified.")
                    return {
                        "sub": data["sub"],
                        "email": data.get("email", ""),
                        "name": data.get("name", ""),
                        "picture": data.get("picture", ""),
                    }
        elif provider == "apple":
            import jwt as pyjwt

            expected_aud = get_settings().apple_oauth_client_id
            if not expected_aud:
                raise InvalidCredentialsError("Apple OAuth is not configured on this server.")
            valid_auds = [aud.strip() for aud in expected_aud.split(",") if aud.strip()]
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://appleid.apple.com/auth/keys", timeout=10)
                if resp.status_code != 200:
                    raise InvalidCredentialsError("Failed to fetch Apple public keys.")
                keys = resp.json()["keys"]
                header = pyjwt.get_unverified_header(token)
                kid = header.get("kid")
                matching_key = next((k for k in keys if k["kid"] == kid), None)
                if matching_key is None:
                    raise InvalidCredentialsError("Invalid Apple token (key not found).")
                public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(matching_key)
                payload = pyjwt.decode(
                    token,
                    public_key,
                    algorithms=["RS256"],  # type: ignore[arg-type]
                    options={"verify_aud": False},
                )
                if payload.get("aud") not in valid_auds:
                    raise InvalidCredentialsError(
                        "Apple token was not issued for this application."
                    )
            return {
                "sub": payload["sub"],
                "email": payload.get("email", ""),
                "name": f"{payload.get('given_name', '')} {payload.get('family_name', '')}".strip(),
            }
        else:
            raise InvalidCredentialsError(f"Unsupported OAuth provider: {provider}")

    async def update_profile(
        self,
        user_id: uuid.UUID,
        *,
        full_name: str | None = None,
        phone: str | None = None,
        profile_picture_url: str | None = None,
        date_of_birth: date | str | None = None,
        gender: str | None = None,
        address_line: str | None = None,
        city: str | None = None,
        state: str | None = None,
        country: str | None = None,
        postal_code: str | None = None,
        push_notifications_enabled: bool | None = None,
        fcm_token: str | None = None,
        ctx: RequestContext,
    ) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        if full_name is not None:
            user.full_name = full_name
        if phone is not None:
            user.phone = phone
        if profile_picture_url is not None:
            user.profile_picture_url = profile_picture_url
        if date_of_birth is not None:
            if isinstance(date_of_birth, str) and date_of_birth.strip():
                user.date_of_birth = date.fromisoformat(date_of_birth.strip())
            elif isinstance(date_of_birth, date):
                user.date_of_birth = date_of_birth
            elif date_of_birth == "" or date_of_birth is None:
                user.date_of_birth = None
        if gender is not None:
            user.gender = gender
        if address_line is not None:
            user.address_line = address_line
        if city is not None:
            user.city = city
        if state is not None:
            user.state = state
        if country is not None:
            user.country = country
        if postal_code is not None:
            user.postal_code = postal_code
        if push_notifications_enabled is not None:
            user.push_notifications_enabled = push_notifications_enabled
        if fcm_token is not None:
            user.fcm_token = fcm_token if fcm_token else None

        await self._users._session.flush()
        await self._users._session.refresh(user)
        await self._audit.record(
            event_type=AuthAuditEventType.PROFILE_UPDATED,
            actor_id=user_id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return user

    async def delete_my_account(
        self,
        user_id: uuid.UUID,
        *,
        ctx: RequestContext | None = None,
    ) -> None:
        """Self-service user account deletion."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        user.deleted_at = datetime.now(UTC)
        user.is_active = False

        # Invalidate all active sessions and refresh tokens
        await self._sessions.revoke_all_for_user(user_id, reason="account_deleted")
        await self._refresh_tokens.revoke_all_for_user(user_id, reason="account_deleted")

        await self._users._session.flush()

        await self._audit.record(
            event_type=AuthAuditEventType.USER_ACCOUNT_DELETED,
            actor_id=user_id,
            ip_address=ctx.ip_address if ctx else None,
            user_agent=ctx.user_agent if ctx else None,
            metadata={"user_id": str(user_id), "email": user.email, "self_service": True},
        )


# ── Admin service ────────────────────────────────────────────────────────────


class AdminService:
    """User provisioning and RBAC management for Super Administrator."""

    def __init__(
        self,
        *,
        user_repo: UserRepository,
        role_repo: RoleRepository,
        permission_repo: PermissionRepository,
        user_role_repo: UserRoleRepository,
        user_permission_repo: "UserPermissionRepository | None" = None,
        audit_service: AuditService,
        redis: RedisClient | None = None,
    ) -> None:
        self._users = user_repo
        self._roles = role_repo
        self._permissions = permission_repo
        self._user_roles = user_role_repo
        self._user_permissions = user_permission_repo
        self._audit = audit_service
        self._redis = redis

    async def _invalidate_rbac_cache(self) -> None:
        """Drop cached role->permission sets so RBAC changes apply immediately.

        ``RequirePermission`` caches permission codes per role-name combination
        under namespace ``rbac`` (keys ``roles:<names>``, 300s TTL). Without
        invalidation a permission change would linger for the whole TTL, so
        every role mutation purges the namespace (CACHE CONTRACT: permissions
        are never cached without invalidation).
        """
        if self._redis is None:
            return
        await CacheService(self._redis, namespace="rbac").delete_prefix("roles")
        await CacheService(self._redis, namespace="rbac").delete_prefix("user")

    # ── Role management ──────────────────────────────────────────────────────

    async def list_roles(self) -> list[Role]:
        return await self._roles.list_all()

    async def get_role(self, role_id: uuid.UUID) -> Role:
        role = await self._roles.get_by_id(role_id)
        if role is None:
            raise NotFoundError(f"Role {role_id} not found.")
        return role

    async def create_role(
        self,
        *,
        name: str,
        description: str | None,
        permission_codes: list[str],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Role:
        existing = await self._roles.get_by_name(name)
        if existing is not None:
            from pawguard.core.exceptions import ConflictError

            raise ConflictError(f"Role '{name}' already exists.")

        role = Role(name=name, description=description, is_system=False)
        await self._roles.create(role)
        if permission_codes:
            perms = await self._permissions.get_by_codes(permission_codes)
            found_codes = {p.code for p in perms}
            invalid_codes = set(permission_codes) - found_codes
            if invalid_codes:
                from pawguard.core.exceptions import ValidationFailedError

                raise ValidationFailedError(
                    f"Invalid permission code(s): {', '.join(sorted(invalid_codes))}"
                )
            await self._roles.set_permissions(role.id, [p.id for p in perms])
        await self._audit.record(
            event_type=AuthAuditEventType.ADMIN_ROLE_CREATED,
            actor_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"role_name": name, "permission_codes": permission_codes},
        )
        await self._invalidate_rbac_cache()
        # Re-fetch with permissions eager-loaded: set_permissions() writes
        # the RolePermission association directly rather than through the
        # ORM relationship, and role.permissions was never loaded on this
        # freshly-created object either way - RoleResponse reads it to build
        # permission_codes, and an unloaded/stale relationship read on an
        # AsyncSession raises MissingGreenlet instead of a lazy round-trip.
        refreshed = await self._roles.get_by_id(role.id)
        assert refreshed is not None
        return refreshed

    async def update_role(
        self,
        role_id: uuid.UUID,
        *,
        description: str | None,
        permission_codes: list[str] | None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Role:
        role = await self._roles.get_by_id(role_id)
        if role is None:
            raise NotFoundError(f"Role {role_id} not found.")
        # PRR 2.1: Only super_admin may modify system roles.  The
        # endpoint already enforces require_permission("system:admin"),
        # so any caller here is authenticated as super_admin.

        if description is not None:
            role.description = description
        if permission_codes is not None:
            perms = await self._permissions.get_by_codes(permission_codes)
            found_codes = {p.code for p in perms}
            invalid_codes = set(permission_codes) - found_codes
            if invalid_codes:
                from pawguard.core.exceptions import ValidationFailedError

                raise ValidationFailedError(
                    f"Invalid permission code(s): {', '.join(sorted(invalid_codes))}"
                )
            await self._roles.set_permissions(role.id, [p.id for p in perms])
        await self._audit.record(
            event_type=AuthAuditEventType.ADMIN_ROLE_UPDATED,
            actor_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"role_id": str(role_id), "role_name": role.name},
        )
        await self._invalidate_rbac_cache()
        if permission_codes is not None:
            # role.permissions was loaded before set_permissions() bypassed
            # the ORM relationship to write RolePermission rows directly, so
            # the in-memory collection is now stale.
            refreshed = await self._roles.get_by_id(role.id)
            assert refreshed is not None
            return refreshed
        return role

    async def delete_role(
        self,
        role_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        role = await self._roles.get_by_id(role_id)
        if role is None:
            raise NotFoundError(f"Role {role_id} not found.")
        # PRR 2.1: Only super_admin may delete roles.  The endpoint
        # already enforces require_permission("system:admin").
        await self._roles.delete(role_id)
        await self._audit.record(
            event_type=AuthAuditEventType.ADMIN_ROLE_DELETED,
            actor_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"role_id": str(role_id), "role_name": role.name},
        )
        await self._invalidate_rbac_cache()

    # ── Permission management ────────────────────────────────────────────────

    async def list_permissions(self) -> list[Permission]:
        return await self._permissions.list_all()

    # ── User provisioning ────────────────────────────────────────────────────

    async def list_users(self) -> list[User]:
        return await self._users.list_all()

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        return user

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        phone: str | None,
        role_names: list[str],
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        normalized_email = email.lower()
        existing = await self._users.get_by_email(normalized_email)
        if existing is not None:
            from pawguard.core.exceptions import ConflictError

            raise ConflictError("A user with this email already exists.")

        user = User(
            email=normalized_email,
            full_name=full_name,
            phone=phone,
            hashed_password=await asyncio.to_thread(hash_password, password),
            is_active=True,
            is_verified=False,
        )
        await self._users.create(user)

        if role_names:
            role_ids: list[uuid.UUID] = []
            for name in role_names:
                role = await self._roles.get_by_name(name)
                if role is not None:
                    role_ids.append(role.id)
            if role_ids:
                await self._user_roles.set_roles(user.id, role_ids)

        fresh = await self._users.get_by_id(user.id)
        await self._audit.record(
            event_type=AuthAuditEventType.ADMIN_USER_CREATED,
            actor_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"user_id": str(user.id), "email": normalized_email, "role_names": role_names},
        )
        return fresh or user

    async def update_user(
        self,
        user_id: uuid.UUID,
        *,
        full_name: str | None = None,
        phone: str | None = None,
        is_active: bool | None = None,
        role_names: list[str] | None = None,
        password: str | None = None,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")

        if full_name is not None:
            user.full_name = full_name
        if phone is not None:
            user.phone = phone
        if is_active is not None:
            user.is_active = is_active

        if role_names is not None:
            role_ids: list[uuid.UUID] = []
            for name in role_names:
                role = await self._roles.get_by_name(name)
                if role is not None:
                    role_ids.append(role.id)
            await self._user_roles.set_roles(user_id, role_ids)

        if password is not None:
            user.hashed_password = await asyncio.to_thread(hash_password, password)

        await self._users._session.flush()
        await self._users._session.refresh(user)
        fresh = await self._users.get_by_id(user_id)
        await self._audit.record(
            event_type=AuthAuditEventType.ADMIN_USER_UPDATED,
            actor_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"user_id": str(user_id)},
        )
        return fresh or user

    async def delete_user(
        self,
        user_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        user.deleted_at = datetime.now(UTC)
        await self._audit.record(
            event_type=AuthAuditEventType.ADMIN_USER_DELETED,
            actor_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"user_id": str(user_id), "email": user.email},
        )

    async def restore_and_reset_password(
        self,
        *,
        email: str,
        password: str,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        """Restore a soft-deleted user and reset their password (admin dev tool)."""
        user = await self._users.get_by_email_any(email.lower())
        if user is None:
            raise NotFoundError(f"No user with email {email} found.")
        user.deleted_at = None
        user.is_active = True
        user.hashed_password = await asyncio.to_thread(hash_password, password)
        await self._users._session.flush()
        await self._users._session.refresh(user)
        await self._audit.record(
            event_type=AuthAuditEventType.ADMIN_USER_UPDATED,
            actor_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                "user_id": str(user.id),
                "email": email,
                "action": "restore_and_reset_password",
            },
        )
        return user

    # ── User-level permission overrides ────────────────────────────────────

    async def grant_user_permissions(
        self,
        user_id: uuid.UUID,
        permission_codes: list[str],
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> list[str]:
        """Grant direct permission overrides to a user (supplements role permissions)."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        perms = await self._permissions.get_by_codes(permission_codes)
        found_codes = {p.code for p in perms}
        invalid_codes = set(permission_codes) - found_codes
        if invalid_codes:
            from pawguard.core.exceptions import ValidationFailedError

            raise ValidationFailedError(
                f"Invalid permission code(s): {', '.join(sorted(invalid_codes))}"
            )
        up_repo = self._user_permissions
        assert up_repo is not None
        for p in perms:
            await up_repo.grant_permission(user_id, p.id, granted_by=actor_id)
        await self._invalidate_rbac_cache()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.ADMIN_ROLE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "user_id": str(user_id),
                    "action": "grant_permissions",
                    "permission_codes": permission_codes,
                },
            )
        return sorted(found_codes)

    async def revoke_user_permission(
        self,
        user_id: uuid.UUID,
        permission_code: str,
        *,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """Revoke a single direct permission override from a user."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        perm = await self._permissions.get_by_code(permission_code)
        if perm is None:
            raise NotFoundError(f"Permission '{permission_code}' not found.")
        up_repo = self._user_permissions
        assert up_repo is not None
        revoked = await up_repo.revoke_permission(user_id, perm.id)
        await self._invalidate_rbac_cache()
        if self._audit and actor_id:
            await self._audit.record(
                event_type=AuthAuditEventType.ADMIN_ROLE_UPDATED,
                actor_id=actor_id,
                ip_address=ip_address or "",
                user_agent="",
                metadata={
                    "user_id": str(user_id),
                    "action": "revoke_permission",
                    "permission_code": permission_code,
                },
            )
        return revoked

    async def list_user_permissions(self, user_id: uuid.UUID) -> list[str]:
        """List all direct permission overrides for a user."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        up_repo = self._user_permissions
        assert up_repo is not None
        perms = await up_repo.list_user_permissions(user_id)
        return [p.code for p in perms]
