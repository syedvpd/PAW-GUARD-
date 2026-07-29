"""Unit tests for core/security.py — password hashing, JWT, opaque tokens."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from pawguard.core.security import (
    AccessTokenClaims,
    TokenError,
    TokenType,
    create_access_token,
    create_pre_auth_token,
    decode_token,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    needs_rehash,
    parse_access_token_claims,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self) -> None:
        hashed = hash_password("SecureP@ss123")
        assert verify_password("SecureP@ss123", hashed) is True
        assert verify_password("WrongP@ss123", hashed) is False

    def test_hash_is_deterministic(self) -> None:
        """Argon2id includes a random salt; same input produces different hashes."""
        a = hash_password("SameP@ss1")
        b = hash_password("SameP@ss1")
        assert a != b
        assert verify_password("SameP@ss1", a) is True
        assert verify_password("SameP@ss1", b) is True

    def test_needs_rehash(self) -> None:
        hashed = hash_password("NeedsRehash1")
        assert needs_rehash(hashed) is False


class TestOpaqueTokens:
    def test_generate_and_hash(self) -> None:
        raw = generate_opaque_token()
        assert isinstance(raw, str)
        assert len(raw) > 40  # 48 bytes base64-url encoded

        h1 = hash_opaque_token(raw)
        h2 = hash_opaque_token(raw)
        assert h1 == h2
        assert h1 != hash_opaque_token("different")

    def test_tokens_are_unique(self) -> None:
        tokens = {generate_opaque_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_hash_is_irreversible(self) -> None:
        """Verify the hash does not contain the raw token."""
        raw = generate_opaque_token()
        h = hash_opaque_token(raw)
        assert raw not in h


class TestJWTAccessTokens:
    def test_create_and_parse(self) -> None:
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        roles = ["user"]

        token = create_access_token(user_id=user_id, session_id=session_id, roles=roles)
        claims = parse_access_token_claims(token)

        assert claims.user_id == user_id
        assert claims.session_id == session_id
        assert claims.roles == roles
        assert isinstance(claims.jti, str)
        assert claims.expires_at > datetime.now(UTC)

    def test_parse_rejects_wrong_type(self) -> None:
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        pre_token = create_pre_auth_token(user_id=user_id, session_id=session_id)

        with pytest.raises(TokenError, match="Unexpected token type"):
            parse_access_token_claims(pre_token)

    def test_custom_expiry(self) -> None:
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        delta = timedelta(hours=2)
        token = create_access_token(
            user_id=user_id, session_id=session_id, roles=[], expires_delta=delta
        )
        claims = parse_access_token_claims(token)
        expected = datetime.now(UTC) + delta
        assert abs((claims.expires_at - expected).total_seconds()) < 10

    def test_create_pre_auth_token(self) -> None:
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        token = create_pre_auth_token(user_id=user_id, session_id=session_id)
        payload = decode_token(token, expected_type=TokenType.PRE_AUTH)
        assert payload["sub"] == str(user_id)
        assert payload["sid"] == str(session_id)
        assert payload["type"] == TokenType.PRE_AUTH.value
        assert "jti" in payload

    def test_expired_token_raises(self) -> None:
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id,
            session_id=session_id,
            roles=[],
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(TokenError, match="expired"):
            parse_access_token_claims(token)

    def test_tampered_token_raises(self) -> None:
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        token = create_access_token(user_id=user_id, session_id=session_id, roles=[])
        tampered = token + "x"
        with pytest.raises(TokenError, match="invalid|expired"):
            parse_access_token_claims(tampered)

    def test_access_token_claims_dataclass(self) -> None:
        uid = uuid.uuid4()
        sid = uuid.uuid4()
        claims = AccessTokenClaims(
            user_id=uid,
            session_id=sid,
            roles=["admin"],
            jti="abc123",
            expires_at=datetime.now(UTC),
        )
        assert claims.user_id == uid
        assert claims.session_id == sid
        assert claims.roles == ["admin"]
        assert claims.jti == "abc123"
