"""Composable auth dependencies: current user, current session, rate limiting.

These are the dependencies every future module's routers will depend on (RULE-004:
routers authenticate/authorise via dependencies, never inline).
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.constants import ACCESS_TOKEN_COOKIE_NAME
from pawguard.core.exceptions import TooManyRequestsError
from pawguard.core.security import AccessTokenClaims, TokenError, parse_access_token_claims
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

    @property
    def id(self) -> uuid.UUID:
        return self.user.id


async def _extract_access_token(
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

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(claims.user_id)
    if user is None or not user.is_active:
        raise AccountInactiveError("Account is inactive or no longer exists.")

    request.state.user_id = user.id
    return CurrentUser(user=user, claims=claims, db=db, redis=redis)


async def get_current_session(
    current: CurrentUser = Depends(get_current_user),
) -> UserSession:
    session_repo = SessionRepository(current.db)
    session = await session_repo.get_by_id(current.claims.session_id)
    if session is None or not session.is_active:
        raise InvalidSessionError("Session has been revoked or has expired.")

    # Inactivity timeout — auto-revoke sessions idle longer than threshold.
    idle = datetime.now(UTC) - session.last_used_at
    if idle > timedelta(days=SESSION_INACTIVITY_TIMEOUT_DAYS):
        await session_repo.revoke(session.id, reason="inactivity_timeout")
        raise InvalidSessionError("Session has expired due to inactivity.")

    return session


class RateLimiter:
    """Redis fixed-window rate limiter, scoped to specific sensitive endpoints only."""

    def __init__(self, *, key_prefix: str, limit: int, window_seconds: int) -> None:
        self.key_prefix = key_prefix
        self.limit = limit
        self.window_seconds = window_seconds

    async def __call__(self, request: Request, redis: RedisClient = Depends(get_redis)) -> None:
        identifier = request.client.host if request.client else "unknown"
        window = int(time.time() // self.window_seconds)
        key = f"ratelimit:{self.key_prefix}:{identifier}:{window}"

        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, self.window_seconds)

        if count > self.limit:
            raise TooManyRequestsError("Too many requests. Please try again later.")
