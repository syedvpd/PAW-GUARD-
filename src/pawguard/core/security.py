"""Password hashing, JWT encode/decode, and opaque token primitives.

This is the cryptographic core of the custom authentication system. No abstraction library
sits between this module and `argon2-cffi` / `pyjwt` — business logic (sessions, rotation,
audit) lives in `modules/auth/service.py`, this module only provides pure primitives.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

from pawguard.core.config import get_settings

_password_hasher = PasswordHasher()

OPAQUE_TOKEN_BYTES = 48


class TokenType(StrEnum):
    ACCESS = "access"
    PRE_AUTH = "pre_auth"


class TokenError(Exception):
    """Raised when a JWT is malformed, expired, or fails signature verification."""


@dataclass(slots=True, frozen=True)
class AccessTokenClaims:
    user_id: UUID
    session_id: UUID
    roles: list[str]
    jti: str
    expires_at: datetime


# --- Password hashing (Argon2id) ---


def hash_password(plain_password: str) -> str:
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False
    return True


def needs_rehash(hashed_password: str) -> bool:
    return _password_hasher.check_needs_rehash(hashed_password)


# --- Opaque tokens (refresh tokens, reset tokens, verification tokens) ---


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(OPAQUE_TOKEN_BYTES)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- JWT access tokens (RS256) ---


def create_access_token(
    *,
    user_id: UUID,
    session_id: UUID,
    roles: list[str],
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "roles": roles,
        "type": TokenType.ACCESS.value,
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_private_key, algorithm=settings.jwt_algorithm)


def create_pre_auth_token(*, user_id: UUID, session_id: UUID) -> str:
    """Short-lived token bridging the login -> MFA-verify step. Not a full access token."""
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.pre_auth_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "type": TokenType.PRE_AUTH.value,
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_private_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid.") from exc

    if payload.get("type") != expected_type.value:
        raise TokenError("Unexpected token type.")

    return payload


def parse_access_token_claims(token: str) -> AccessTokenClaims:
    payload = decode_token(token, expected_type=TokenType.ACCESS)
    return AccessTokenClaims(
        user_id=UUID(payload["sub"]),
        session_id=UUID(payload["sid"]),
        roles=payload.get("roles", []),
        jti=payload["jti"],
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )
