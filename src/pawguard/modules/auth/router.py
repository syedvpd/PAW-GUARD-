"""Auth endpoints. Routers only authenticate/authorise/validate/call-service/respond (RULE-004)."""

import uuid

import structlog
from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.config import get_settings
from pawguard.core.constants import (
    ACCESS_TOKEN_COOKIE_NAME,
    CLIENT_TYPE_HEADER,
    REFRESH_TOKEN_COOKIE_NAME,
    ClientType,
)
from pawguard.core.exceptions import NotFoundError
from pawguard.core.rate_limiter import rate_limit, resolve_client_ip
from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import (
    CurrentUser,
    get_current_session,
    get_current_user,
)
from pawguard.modules.auth.exceptions import InvalidRefreshTokenError
from pawguard.modules.auth.models import UserSession
from pawguard.modules.auth.repository import (
    EmailVerificationTokenRepository,
    MFARepository,
    OAuthAccountRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    SessionRepository,
    UserRepository,
)
from pawguard.modules.auth.schemas import (
    ChangePasswordRequest,
    EmailVerificationConfirmRequest,
    LoginRequest,
    LoginResponse,
    MFADisableRequest,
    MFAEnrollResponse,
    MFALoginVerifyRequest,
    MFARequiredResponse,
    MFAVerifyRequest,
    OAuthAccountInfo,
    OAuthLinkRequest,
    OAuthLoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    SessionInfo,
    UserProfile,
    UserProfileUpdate,
    UserSummaryResponse,
)
from pawguard.modules.auth.service import AuthenticatedTokens, AuthService, RequestContext
from pawguard.modules.outbox.service import OutboxService
from pawguard.services.audit_service import AuditService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

register_rate_limiter = rate_limit("register", 5, 3600)
login_rate_limiter = rate_limit("login", 10, 60)
refresh_rate_limiter = rate_limit("refresh", 30, 60)
reset_rate_limiter = rate_limit("password_reset", 5, 3600)
# Short numeric codes (TOTP/backup codes) are brute-forceable without a tight throttle.
mfa_verify_rate_limiter = rate_limit("mfa_verify", 10, 300)
mfa_enroll_confirm_rate_limiter = rate_limit("mfa_enroll_confirm", 10, 300)
mfa_disable_rate_limiter = rate_limit("mfa_disable", 10, 300)
email_verify_request_rate_limiter = rate_limit("email_verify_request", 10, 300)
password_change_rate_limiter = rate_limit("password_change", 10, 300)
reset_confirm_rate_limiter = rate_limit("password_reset_confirm", 10, 300)
email_verify_confirm_rate_limiter = rate_limit("email_verify_confirm", 10, 300)
oauth_login_rate_limiter = rate_limit("oauth_login", 10, 60)


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(
        user_repo=UserRepository(db),
        session_repo=SessionRepository(db),
        refresh_token_repo=RefreshTokenRepository(db),
        mfa_repo=MFARepository(db),
        password_reset_repo=PasswordResetTokenRepository(db),
        email_verification_repo=EmailVerificationTokenRepository(db),
        oauth_account_repo=OAuthAccountRepository(db),
        audit_service=AuditService(db),
    )


def _build_request_context(request: Request) -> RequestContext:
    # resolve_client_ip() trusts the leftmost X-Forwarded-For hop so audit
    # rows record the real caller, not the reverse proxy (mirrors the rate
    # limiter's keying).
    return RequestContext(
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def _is_web_client(client_type: str | None) -> bool:
    return client_type == ClientType.WEB.value


def _cookie_domain() -> str | None:
    """Return None so the browser treats auth cookies as host-only cookies
    without an explicit Domain attribute. This enables same-origin Vercel proxy
    (pawguard-public-web.vercel.app/api/v1) to issue and receive HttpOnly cookies cleanly.
    """
    return None


def _set_auth_cookies(response: Response, *, access_token: str, refresh_token: str | None) -> None:
    settings = get_settings()
    domain = _cookie_domain()
    samesite_mode = "none" if (settings.cookie_secure or True) else "lax"
    is_secure = True

    response.set_cookie(
        ACCESS_TOKEN_COOKIE_NAME,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=is_secure,
        samesite=samesite_mode,
        domain=domain,
    )
    if refresh_token is not None:
        response.set_cookie(
            REFRESH_TOKEN_COOKIE_NAME,
            refresh_token,
            max_age=settings.refresh_token_expire_days * 24 * 3600,
            httponly=True,
            secure=is_secure,
            samesite=samesite_mode,
            domain=domain,
        )


def _clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    domain = _cookie_domain()
    samesite_mode = "none" if (settings.cookie_secure or True) else "lax"
    is_secure = True

    response.delete_cookie(ACCESS_TOKEN_COOKIE_NAME, domain=domain, secure=is_secure, samesite=samesite_mode)
    response.delete_cookie(REFRESH_TOKEN_COOKIE_NAME, domain=domain, secure=is_secure, samesite=samesite_mode)


def _to_login_response(
    tokens: AuthenticatedTokens, *, include_refresh_in_body: bool, is_web: bool = False
) -> LoginResponse:
    return LoginResponse(
        access_token="" if is_web else tokens.access_token,
        refresh_token=tokens.refresh_token if (include_refresh_in_body and not is_web) else None,
        expires_in=tokens.expires_in,
        user=UserProfile.model_validate(tokens.user),
    )


@router.post(
    "/register",
    response_model=ApiResponse[UserProfile],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(register_rate_limiter)],
)
async def register(
    payload: RegisterRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserProfile]:
    user = await auth_service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        phone=payload.phone,
        ctx=_build_request_context(request),
    )
    raw_token = await auth_service.request_email_verification(
        user=user, ctx=_build_request_context(request)
    )
    verify_url = f"{get_settings().web_app_url}/verify-email?token={raw_token}"
    try:
        await OutboxService.enqueue_job(
            db, "send_email_verification_email_job", to=user.email, verify_url=verify_url
        )
    except Exception as exc:
        logger.warning("email_verification_job_enqueue_failed", error=str(exc))
    return ApiResponse(
        data=UserProfile.model_validate(user),
        message="Registration successful. Please verify your email.",
    )


@router.post(
    "/login",
    response_model=ApiResponse[LoginResponse] | ApiResponse[MFARequiredResponse],
    dependencies=[Depends(login_rate_limiter)],
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    client_type: str | None = Header(default=None, alias=CLIENT_TYPE_HEADER),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[LoginResponse] | ApiResponse[MFARequiredResponse]:
    result = await auth_service.login(
        email=payload.email,
        password=payload.password,
        device=payload.device,
        ctx=_build_request_context(request),
    )

    if isinstance(result, str):
        return ApiResponse(data=MFARequiredResponse(pre_auth_token=result))

    is_web = _is_web_client(client_type)
    if is_web:
        _set_auth_cookies(
            response, access_token=result.access_token, refresh_token=result.refresh_token
        )
    return ApiResponse(data=_to_login_response(result, include_refresh_in_body=not is_web, is_web=is_web))


@router.post(
    "/mfa/verify",
    response_model=ApiResponse[LoginResponse],
    dependencies=[Depends(mfa_verify_rate_limiter)],
)
async def verify_mfa_login(
    payload: MFALoginVerifyRequest,
    request: Request,
    response: Response,
    client_type: str | None = Header(default=None, alias=CLIENT_TYPE_HEADER),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[LoginResponse]:
    tokens = await auth_service.verify_mfa_login(
        pre_auth_token=payload.pre_auth_token,
        code=payload.code,
        device=payload.device,
        ctx=_build_request_context(request),
    )
    is_web = _is_web_client(client_type)
    if is_web:
        _set_auth_cookies(
            response, access_token=tokens.access_token, refresh_token=tokens.refresh_token
        )
    return ApiResponse(data=_to_login_response(tokens, include_refresh_in_body=not is_web, is_web=is_web))


@router.post(
    "/refresh",
    response_model=ApiResponse[RefreshResponse],
    dependencies=[Depends(refresh_rate_limiter)],
)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    client_type: str | None = Header(default=None, alias=CLIENT_TYPE_HEADER),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[RefreshResponse]:
    raw_token = payload.refresh_token or request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    if not raw_token:
        raise InvalidRefreshTokenError("No refresh token provided.")

    tokens = await auth_service.refresh(
        raw_refresh_token=raw_token, ctx=_build_request_context(request)
    )

    is_web = _is_web_client(client_type)
    if is_web:
        _set_auth_cookies(
            response, access_token=tokens.access_token, refresh_token=tokens.refresh_token
        )

    return ApiResponse(
        data=RefreshResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token if not is_web else None,
            expires_in=tokens.expires_in,
        )
    )


@router.post("/logout", response_model=ApiResponse[None])
async def logout(
    request: Request,
    response: Response,
    current: CurrentUser = Depends(get_current_user),
    session: UserSession = Depends(get_current_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[None]:
    await auth_service.logout(
        session_id=session.id, user_id=current.id, ctx=_build_request_context(request)
    )
    _clear_auth_cookies(response)
    return ApiResponse(message="Logged out.")


@router.post("/logout-all", response_model=ApiResponse[None])
async def logout_all(
    request: Request,
    response: Response,
    current: CurrentUser = Depends(get_current_user),
    session: UserSession = Depends(get_current_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[None]:
    await auth_service.logout_all(
        user_id=current.id, current_session_id=session.id, ctx=_build_request_context(request)
    )
    _clear_auth_cookies(response)
    return ApiResponse(message="Logged out from all devices.")


@router.get("/me", response_model=ApiResponse[UserProfile])
async def get_me(current: CurrentUser = Depends(get_current_user)) -> ApiResponse[UserProfile]:
    return ApiResponse(
        data=UserProfile.model_validate(current.user)
    )


@router.put("/me", response_model=ApiResponse[UserProfile])
async def update_profile(
    payload: UserProfileUpdate,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[UserProfile]:
    user = await auth_service.update_profile(
        current.user.id,
        full_name=payload.full_name,
        phone=payload.phone,
        profile_picture_url=payload.profile_picture_url,
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        address_line=payload.address_line,
        city=payload.city,
        state=payload.state,
        country=payload.country,
        postal_code=payload.postal_code,
        push_notifications_enabled=payload.push_notifications_enabled,
        fcm_token=payload.fcm_token,
        ctx=_build_request_context(request),
    )
    return ApiResponse(
        data=UserProfile.model_validate(user),
        message="Profile updated.",
    )


@router.get("/users/{user_id}/summary", response_model=ApiResponse[UserSummaryResponse])
async def get_user_summary(
    user_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[UserSummaryResponse]:
    """Lightweight user display summary for cards and references (safe for all authenticated roles)."""
    user = await auth_service._users.get_by_id(user_id)
    if user is None:
        raise NotFoundError("User not found.")
    roles = await auth_service._users.get_user_roles(user_id)
    primary_role = roles[0].name if roles else None
    return ApiResponse(
        data=UserSummaryResponse(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            profile_picture_url=user.profile_picture_url,
            role=primary_role,
        )
    )


@router.get("/sessions", response_model=ApiResponse[list[SessionInfo]])
async def list_sessions(
    current: CurrentUser = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[list[SessionInfo]]:
    sessions = await auth_service.list_sessions(user_id=current.id)
    data = [
        SessionInfo.model_validate(s, from_attributes=True).model_copy(
            update={"is_current": s.id == current_session.id}
        )
        for s in sessions
    ]
    return ApiResponse(data=data, message="Active sessions retrieved successfully.")


@router.delete("/sessions/{session_id}", response_model=ApiResponse[None])
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[None]:
    await auth_service.revoke_session(
        user_id=current.id, session_id=session_id, ctx=_build_request_context(request)
    )
    return ApiResponse(message="Session revoked.")


@router.post(
    "/password/change",
    response_model=ApiResponse[None],
    dependencies=[Depends(password_change_rate_limiter)],
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    session: UserSession = Depends(get_current_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[None]:
    await auth_service.change_password(
        user=current.user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        current_session_id=session.id,
        ctx=_build_request_context(request),
    )
    return ApiResponse(message="Password changed. Other sessions have been logged out.")


@router.post(
    "/password/reset/request",
    response_model=ApiResponse[None],
    dependencies=[Depends(reset_rate_limiter)],
)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    raw_token = await auth_service.request_password_reset(
        email=payload.email, ctx=_build_request_context(request)
    )
    if raw_token is not None:
        reset_url = f"{get_settings().web_app_url}/reset-password?token={raw_token}"
        try:
            await OutboxService.enqueue_job(
                db, "send_password_reset_email_job", to=payload.email, reset_url=reset_url
            )
        except Exception as exc:
            logger.warning("password_reset_job_enqueue_failed", error=str(exc))
    return ApiResponse(message="If that email exists, a reset link has been sent.")


@router.post(
    "/password/reset/confirm",
    response_model=ApiResponse[None],
    dependencies=[Depends(reset_confirm_rate_limiter)],
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[None]:
    await auth_service.confirm_password_reset(
        raw_token=payload.token,
        new_password=payload.new_password,
        ctx=_build_request_context(request),
    )
    return ApiResponse(message="Password has been reset.")


@router.post(
    "/email/verify/confirm",
    response_model=ApiResponse[None],
    dependencies=[Depends(email_verify_confirm_rate_limiter)],
)
async def confirm_email_verification(
    payload: EmailVerificationConfirmRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[None]:
    await auth_service.confirm_email_verification(
        raw_token=payload.token, ctx=_build_request_context(request)
    )
    return ApiResponse(message="Email verified.")


@router.post(
    "/email/verify/request",
    response_model=ApiResponse[None],
    dependencies=[Depends(email_verify_request_rate_limiter)],
)
async def request_email_verification(
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[None]:
    await auth_service.request_email_verification(
        user=current.user, ctx=_build_request_context(request)
    )
    return ApiResponse(message="Verification email sent.")


@router.post("/mfa/enroll", response_model=ApiResponse[MFAEnrollResponse])
async def enroll_mfa(
    current: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[MFAEnrollResponse]:
    secret, uri = await auth_service.enroll_mfa(user=current.user)
    return ApiResponse(data=MFAEnrollResponse(secret=secret, provisioning_uri=uri))


@router.post(
    "/mfa/enroll/confirm",
    response_model=ApiResponse[None],
    dependencies=[Depends(mfa_enroll_confirm_rate_limiter)],
)
async def confirm_mfa_enrollment(
    payload: MFAVerifyRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[None]:
    await auth_service.confirm_mfa_enrollment(
        user=current.user, code=payload.code, ctx=_build_request_context(request)
    )
    return ApiResponse(message="MFA enabled.")


@router.post(
    "/mfa/disable",
    response_model=ApiResponse[None],
    dependencies=[Depends(mfa_disable_rate_limiter)],
)
async def disable_mfa(
    payload: MFADisableRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[None]:
    await auth_service.disable_mfa(
        user=current.user, payload=payload, ctx=_build_request_context(request)
    )
    return ApiResponse(message="MFA disabled.")


# ── OAuth / Social Login ──────────────────────────────────────────────────────


@router.post(
    "/oauth/login",
    response_model=ApiResponse[LoginResponse],
    dependencies=[Depends(oauth_login_rate_limiter)],
)
async def oauth_login(
    payload: OAuthLoginRequest,
    request: Request,
    response: Response,
    client_type: str | None = Header(default=None, alias=CLIENT_TYPE_HEADER),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[LoginResponse]:
    tokens = await auth_service.oauth_login(
        provider=payload.provider,
        provider_token=payload.provider_token,
        device=payload.device,
        ctx=_build_request_context(request),
    )
    is_web = _is_web_client(client_type)
    if is_web:
        _set_auth_cookies(
            response, access_token=tokens.access_token, refresh_token=tokens.refresh_token
        )
    return ApiResponse(data=_to_login_response(tokens, include_refresh_in_body=not is_web, is_web=is_web))


@router.get("/oauth/accounts", response_model=ApiResponse[list[OAuthAccountInfo]])
async def list_oauth_accounts(
    current: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[list[OAuthAccountInfo]]:
    accounts = await auth_service.list_oauth_accounts(user_id=current.id)
    return ApiResponse(
        data=[OAuthAccountInfo.model_validate(a, from_attributes=True) for a in accounts]
    )


@router.post("/oauth/link", response_model=ApiResponse[OAuthAccountInfo])
async def link_oauth_account(
    payload: OAuthLinkRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[OAuthAccountInfo]:
    account = await auth_service.link_oauth_account(
        user_id=current.id,
        provider=payload.provider,
        provider_token=payload.provider_token,
        ctx=_build_request_context(request),
    )
    return ApiResponse(
        data=OAuthAccountInfo.model_validate(account, from_attributes=True),
        message=f"{payload.provider.capitalize()} account linked.",
    )


@router.delete("/oauth/accounts/{account_id}", response_model=ApiResponse[None])
async def unlink_oauth_account(
    account_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiResponse[None]:
    await auth_service.unlink_oauth_account(
        user_id=current.id, account_id=account_id, ctx=_build_request_context(request)
    )
    return ApiResponse(message="OAuth account unlinked.")
