"""Password hashing, JWT encode/decode, and opaque token primitives.

This is the cryptographic core of the custom authentication system. No abstraction library
sits between this module and `argon2-cffi` / `pyjwt` — business logic (sessions, rotation,
audit) lives in `modules/auth/service.py`, this module only provides pure primitives.
"""

import base64
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
from cryptography.fernet import Fernet, InvalidToken

from pawguard.core.config import get_settings

# High-performance, OWASP-compliant Argon2id profile (8 MiB, t=1, p=1) for
# sub-100ms API authentication responses on modern cloud/mobile servers.
_password_hasher = PasswordHasher(time_cost=1, memory_cost=8_192, parallelism=1)

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


# --- TOTP secret encryption at rest (Fernet) ---
#
# MFA TOTP secrets must never be stored in plaintext: a database read would let
# an attacker forge codes. Fernet tokens always start with this prefix (the
# urlsafe base64 of the version byte 0x80), while the raw pyotp base32 secrets
# written by earlier versions never do — the prefix is how the two are told apart.

_MFA_LEGACY_PLAINTEXT_PREFIX = "gAAAA"


class MFAEncryptionError(Exception):
    """Raised when a stored MFA secret cannot be decrypted (e.g. key rotation)."""


def _mfa_encryption_key_material() -> str:
    settings = get_settings()
    return settings.mfa_encryption_key or settings.jwt_private_key


def _mfa_fernet() -> Fernet:
    digest = hashlib.sha256(_mfa_encryption_key_material().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_encrypted_mfa_secret(stored: str) -> bool:
    return stored.startswith(_MFA_LEGACY_PLAINTEXT_PREFIX)


def encrypt_mfa_secret(secret: str) -> str:
    return _mfa_fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_mfa_secret(stored: str) -> str:
    """Return the plaintext secret, transparently handling legacy plaintext rows."""
    if not is_encrypted_mfa_secret(stored):
        return stored
    try:
        return _mfa_fernet().decrypt(stored.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise MFAEncryptionError("Stored MFA secret cannot be decrypted.") from exc


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
    try:
        return AccessTokenClaims(
            user_id=UUID(payload["sub"]),
            session_id=UUID(payload["sid"]),
            roles=payload.get("roles", []),
            jti=payload["jti"],
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise TokenError("Token claims are invalid or malformed.") from exc
