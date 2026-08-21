"""Composable auth dependencies: current user, current session, rate limiting.

These are the dependencies every future module's routers will depend on (RULE-004:
routers authenticate/authorise via dependencies, never inline).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.constants import ACCESS_TOKEN_COOKIE_NAME
from pawguard.core.security import AccessTokenClaims, TokenError, parse_access_token_claims
from pawguard.db.audit import set_actor
from pawguard.db.session import get_db
from pawguard.modules.auth.exceptions import AccountInactiveError, InvalidSessionError
from pawguard.modules.auth.models import User, UserSession
from pawguard.modules.auth.repository import SessionRepository, UserRepository
from pawguard.redis.client import RedisClient, get_redis

# Sessions inactive longer than this are automatically revoked.
SESSION_INACTIVITY_TIMEOUT_DAYS = 30


@dataclass(slots=True)
class CurrentUser:
    user: User
    claims: AccessTokenClaims
    db: AsyncSession
    redis: RedisClient
    session: UserSession | None = None

    @property
    def id(self) -> uuid.UUID:
        return self.user.id


def _extract_access_token(
    request: Request,
    authorization: str | None = Header(default=None),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE_NAME),
) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1]
    if access_token_cookie:
        return access_token_cookie
    raise InvalidSessionError("No authentication credentials were provided.")


async def get_current_user(
    request: Request,
    token: str = Depends(_extract_access_token),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> CurrentUser:
    try:
        claims = parse_access_token_claims(token)
    except TokenError as exc:
        raise InvalidSessionError(str(exc)) from exc

    session_repo = SessionRepository(db)
    user_repo = UserRepository(db)

    session = await session_repo.get_by_id(claims.session_id)
    if session is None or not session.is_active:
        raise InvalidSessionError("Session has been revoked or has expired.")
    if session.expires_at < datetime.now(UTC):
        raise InvalidSessionError("Session has expired.")

    user = await user_repo.get_by_id(claims.user_id)

    if user is None or not user.is_active:
        raise AccountInactiveError("Account is inactive or no longer exists.")

    request.state.user_id = user.id
    set_actor(user.id)
    return CurrentUser(user=user, claims=claims, db=db, redis=redis, session=session)


async def get_optional_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> CurrentUser | None:
    """Resolve the current user when a valid token is presented, else None.

    Used by anonymous-readable public endpoints (adoption directory, lost &
    found listings) so the public site can browse without an account while
    still showing richer, unmasked data to signed-in users.
    """
    token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif access_token_cookie:
        token = access_token_cookie
    if not token:
        return None

    try:
        claims = parse_access_token_claims(token)
    except TokenError:
        return None

    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(claims.session_id)
    if session is None or not session.is_active or session.expires_at < datetime.now(UTC):
        return None

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(claims.user_id)
    if user is None or not user.is_active:
        return None

    request.state.user_id = user.id
    set_actor(user.id)
    return CurrentUser(user=user, claims=claims, db=db, redis=redis, session=session)


async def get_current_session(
    current: CurrentUser = Depends(get_current_user),
) -> UserSession:
    session = current.session
    if session is None:
        session_repo = SessionRepository(current.db)
        session = await session_repo.get_by_id(current.claims.session_id)
    if session is None or not session.is_active:
        raise InvalidSessionError("Session has been revoked or has expired.")

    last_used = session.last_used_at
    if last_used is not None:
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=UTC)
        idle = datetime.now(UTC) - last_used
        if idle > timedelta(days=SESSION_INACTIVITY_TIMEOUT_DAYS):
            session_repo = SessionRepository(current.db)
            await session_repo.revoke(session.id, reason="inactivity_timeout")
            raise InvalidSessionError("Session has expired due to inactivity.")

    return session
