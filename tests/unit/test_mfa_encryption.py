"""Unit tests for at-rest TOTP secret encryption (issue 8).

Previously `MFADevice.secret_encrypted` held the raw pyotp base32 secret in
plaintext, so any database read exposed the MFA secret. New writes are
Fernet-encrypted, and legacy plaintext rows are verified transparently and
upgraded to encrypted on the first successful verification.
"""

import uuid
from unittest.mock import AsyncMock

import pyotp
import pytest

from pawguard.core.security import (
    MFAEncryptionError,
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    is_encrypted_mfa_secret,
)
from pawguard.modules.auth.models import MFADevice, User
from pawguard.modules.auth.service import AuthService


def _device(secret: str) -> MFADevice:
    return MFADevice(user_id=uuid.uuid4(), device_type="totp", secret_encrypted=secret)


def _user() -> User:
    return User(email="mfa@example.com", hashed_password="x", full_name="MFA User")


class TestMfaSecretEncryptionHelpers:
    def test_round_trip(self) -> None:
        secret = pyotp.random_base32()
        encrypted = encrypt_mfa_secret(secret)
        assert is_encrypted_mfa_secret(encrypted) is True
        assert encrypted != secret
        assert secret not in encrypted
        assert decrypt_mfa_secret(encrypted) == secret

    def test_ciphertexts_are_unique_per_call(self) -> None:
        secret = pyotp.random_base32()
        a = encrypt_mfa_secret(secret)
        b = encrypt_mfa_secret(secret)
        assert a != b  # Fernet nonce makes each ciphertext unique
        assert decrypt_mfa_secret(a) == secret
        assert decrypt_mfa_secret(b) == secret

    def test_legacy_plaintext_is_passed_through(self) -> None:
        secret = pyotp.random_base32()
        assert is_encrypted_mfa_secret(secret) is False
        assert decrypt_mfa_secret(secret) == secret

    def test_invalid_ciphertext_raises(self) -> None:
        with pytest.raises(MFAEncryptionError):
            decrypt_mfa_secret("gAAAAA-not-a-real-token")


class TestTOTPVerification:
    def test_verify_with_encrypted_secret(self) -> None:
        secret = pyotp.random_base32()
        device = _device(encrypt_mfa_secret(secret))
        code = pyotp.TOTP(secret).now()
        assert AuthService._verify_totp(device, code) is True
        assert AuthService._verify_totp(device, "000000") is False

    def test_verify_accepts_legacy_plaintext(self) -> None:
        secret = pyotp.random_base32()
        device = _device(secret)
        code = pyotp.TOTP(secret).now()
        assert AuthService._verify_totp(device, code) is True

    def test_verify_upgrades_legacy_secret_to_encrypted(self) -> None:
        secret = pyotp.random_base32()
        device = _device(secret)
        code = pyotp.TOTP(secret).now()
        assert AuthService._verify_totp(device, code) is True
        assert is_encrypted_mfa_secret(device.secret_encrypted) is True
        assert device.secret_encrypted != secret
        assert decrypt_mfa_secret(device.secret_encrypted) == secret
        assert AuthService._verify_totp(device, code) is True


class TestEnrollMfaStoresEncrypted:
    @pytest.fixture
    def service(self) -> tuple[AuthService, AsyncMock]:
        mfa_repo = AsyncMock()
        service = AuthService(
            user_repo=AsyncMock(),
            session_repo=AsyncMock(),
            refresh_token_repo=AsyncMock(),
            mfa_repo=mfa_repo,
            password_reset_repo=AsyncMock(),
            email_verification_repo=AsyncMock(),
            oauth_account_repo=AsyncMock(),
            audit_service=AsyncMock(),
        )
        return service, mfa_repo

    async def test_new_device_stores_encrypted_secret(self, service) -> None:
        svc, mfa_repo = service
        mfa_repo.get_for_user.return_value = None
        user = _user()

        secret, uri = await svc.enroll_mfa(user=user)

        assert uri  # provisioning URI is returned for the authenticator app
        created: MFADevice = mfa_repo.create.call_args.args[0]
        assert is_encrypted_mfa_secret(created.secret_encrypted) is True
        assert created.secret_encrypted != secret
        assert decrypt_mfa_secret(created.secret_encrypted) == secret

    async def test_re_enroll_rotates_to_encrypted_secret(self, service) -> None:
        svc, mfa_repo = service
        existing = _device(pyotp.random_base32())  # legacy plaintext row
        mfa_repo.get_for_user.return_value = existing
        user = _user()

        secret, _uri = await svc.enroll_mfa(user=user)

        assert existing.secret_encrypted != secret
        assert is_encrypted_mfa_secret(existing.secret_encrypted) is True
        assert decrypt_mfa_secret(existing.secret_encrypted) == secret
        assert existing.is_verified is False
