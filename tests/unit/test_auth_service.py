"""Unit tests for AuthService MFA-disable re-authentication."""

import uuid
from unittest.mock import AsyncMock

import pyotp
import pytest

from pawguard.core.security import hash_password
from pawguard.modules.auth.exceptions import InvalidCredentialsError, InvalidMFACodeError
from pawguard.modules.auth.models import AuthAuditEventType, MFADevice, User
from pawguard.modules.auth.schemas import MFADisableRequest
from pawguard.modules.auth.service import AuthService, RequestContext


def _make_service() -> AuthService:
    return AuthService(
        user_repo=AsyncMock(),
        session_repo=AsyncMock(),
        refresh_token_repo=AsyncMock(),
        mfa_repo=AsyncMock(),
        password_reset_repo=AsyncMock(),
        email_verification_repo=AsyncMock(),
        oauth_account_repo=AsyncMock(),
        audit_service=AsyncMock(),
    )


def _make_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="jane@example.com",
        full_name="Jane Doe",
        hashed_password=hash_password("CurrentP@ss99"),
        mfa_enabled=True,
    )


def _ctx() -> RequestContext:
    return RequestContext(ip_address="127.0.0.1", user_agent="pytest")


class TestMFADisableRequestValidation:
    def test_requires_at_least_one_credential(self) -> None:
        with pytest.raises(ValueError):
            MFADisableRequest.model_validate({})

    def test_accepts_password(self) -> None:
        req = MFADisableRequest.model_validate({"password": "CurrentP@ss99"})
        assert req.password == "CurrentP@ss99"
        assert req.totp_code is None

    def test_accepts_totp_code(self) -> None:
        req = MFADisableRequest.model_validate({"totp_code": "482913"})
        assert req.totp_code == "482913"
        assert req.password is None


class TestDisableMFA:
    @pytest.mark.asyncio
    async def test_disable_with_correct_password(self) -> None:
        service = _make_service()
        user = _make_user()

        await service.disable_mfa(
            user=user, payload=MFADisableRequest(password="CurrentP@ss99"), ctx=_ctx()
        )

        assert user.mfa_enabled is False
        service._audit.record.assert_awaited_once()
        audit_kwargs = service._audit.record.call_args.kwargs
        assert audit_kwargs["event_type"] == AuthAuditEventType.MFA_DISABLED
        assert audit_kwargs["metadata"] == {"confirmed_via": "password"}

    @pytest.mark.asyncio
    async def test_disable_with_wrong_password_rejected(self) -> None:
        service = _make_service()
        user = _make_user()

        with pytest.raises(InvalidCredentialsError):
            await service.disable_mfa(
                user=user, payload=MFADisableRequest(password="WrongP@ss99"), ctx=_ctx()
            )

        assert user.mfa_enabled is True
        service._audit.record.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disable_with_correct_totp(self) -> None:
        service = _make_service()
        user = _make_user()
        secret = pyotp.random_base32()
        device = MFADevice(user_id=user.id, device_type="totp", secret_encrypted=secret)
        service._mfa.get_for_user.return_value = device

        code = pyotp.totp.TOTP(secret).now()
        await service.disable_mfa(user=user, payload=MFADisableRequest(totp_code=code), ctx=_ctx())

        assert user.mfa_enabled is False
        assert device.is_verified is False
        audit_kwargs = service._audit.record.call_args.kwargs
        assert audit_kwargs["metadata"] == {"confirmed_via": "totp"}

    @pytest.mark.asyncio
    async def test_disable_with_wrong_totp_rejected(self) -> None:
        service = _make_service()
        user = _make_user()
        service._mfa.get_for_user.return_value = MFADevice(
            user_id=user.id,
            device_type="totp",
            secret_encrypted=pyotp.random_base32(),
        )

        with pytest.raises(InvalidMFACodeError):
            await service.disable_mfa(
                user=user, payload=MFADisableRequest(totp_code="000000"), ctx=_ctx()
            )

        assert user.mfa_enabled is True
        service._audit.record.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disable_with_no_device_and_totp_rejected(self) -> None:
        service = _make_service()
        user = _make_user()
        service._mfa.get_for_user.return_value = None

        with pytest.raises(InvalidMFACodeError):
            await service.disable_mfa(
                user=user, payload=MFADisableRequest(totp_code="123456"), ctx=_ctx()
            )

        assert user.mfa_enabled is True


class TestProfileUpdateValidation:
    def test_requires_at_least_one_field(self) -> None:
        from pawguard.modules.auth.schemas import UserProfileUpdate

        with pytest.raises(ValueError, match="At least one field"):
            UserProfileUpdate.model_validate({})

    def test_rejects_null_or_empty_full_name(self) -> None:
        from pawguard.modules.auth.schemas import UserProfileUpdate

        with pytest.raises(ValueError):
            UserProfileUpdate.model_validate({"full_name": None})

        with pytest.raises(ValueError):
            UserProfileUpdate.model_validate({"full_name": "   "})

    def test_rejects_invalid_phone(self) -> None:
        from pawguard.modules.auth.schemas import UserProfileUpdate

        with pytest.raises(ValueError, match="Invalid phone number format"):
            UserProfileUpdate.model_validate({"phone": "invalid_phone"})

    def test_accepts_valid_update(self) -> None:
        from pawguard.modules.auth.schemas import UserProfileUpdate

        req = UserProfileUpdate.model_validate({"full_name": "New Name", "phone": "+15550100"})
        assert req.full_name == "New Name"
        assert req.phone == "+15550100"

    def test_accepts_extended_profile_fields(self) -> None:
        from datetime import date

        from pawguard.modules.auth.schemas import UserProfileUpdate

        data = {
            "full_name": "Jane Doe",
            "avatar_url": "https://example.com/avatar.jpg",
            "dob": "1995-05-15",
            "gender": "female",
            "address": "123 Rescue Way",
            "city": "Sector 4",
            "state": "Telangana",
            "country": "India",
            "pin_code": "500081",
            "push_notifications": True,
        }
        req = UserProfileUpdate.model_validate(data)
        assert req.full_name == "Jane Doe"
        assert req.profile_picture_url == "https://example.com/avatar.jpg"
        assert req.date_of_birth == date(1995, 5, 15)
        assert req.gender == "female"
        assert req.address_line == "123 Rescue Way"
        assert req.city == "Sector 4"
        assert req.state == "Telangana"
        assert req.country == "India"
        assert req.postal_code == "500081"
        assert req.push_notifications_enabled is True


class TestChangePasswordValidation:
    def test_rejects_same_password(self) -> None:
        from pawguard.modules.auth.schemas import ChangePasswordRequest

        with pytest.raises(ValueError, match="New password must be different"):
            ChangePasswordRequest.model_validate(
                {"current_password": "StrongP@ss99", "new_password": "StrongP@ss99"}
            )


class TestRegisterRequestValidation:
    def test_first_name_required_last_name_optional(self) -> None:
        from pawguard.modules.auth.schemas import RegisterRequest

        # Case 1: First name provided, last name omitted
        req1 = RegisterRequest.model_validate(
            {
                "email": "user.one@example.com",
                "password": "Password123!",
                "first_name": "Barnaby",
            }
        )
        assert req1.full_name == "Barnaby"

        # Case 2: Both first name and last name provided
        req2 = RegisterRequest.model_validate(
            {
                "email": "user.two@example.com",
                "password": "Password123!",
                "first_name": "Barnaby",
                "last_name": "Smith",
            }
        )
        assert req2.full_name == "Barnaby Smith"

    def test_rejects_numbers_in_full_name(self) -> None:
        from pawguard.modules.auth.schemas import RegisterRequest

        with pytest.raises(ValueError, match="alphabetic characters"):
            RegisterRequest.model_validate(
                {
                    "email": "user.three@example.com",
                    "password": "Password123!",
                    "full_name": "Jane Doe 123",
                }
            )

    def test_strict_indian_mobile_number_validation(self) -> None:
        from pawguard.modules.auth.schemas import RegisterRequest

        # Valid +91 10-digit number
        req1 = RegisterRequest.model_validate(
            {
                "email": "user.four@example.com",
                "password": "Password123!",
                "full_name": "Jane Doe",
                "phone": "+91 98765 43210",
            }
        )
        assert req1.phone == "+919876543210"

        # Invalid +91 number (too short / invalid starting digit)
        with pytest.raises(ValueError, match="Indian mobile number"):
            RegisterRequest.model_validate(
                {
                    "email": "user.five@example.com",
                    "password": "Password123!",
                    "full_name": "Jane Doe",
                    "phone": "+9112345",
                }
            )

    def test_email_validation_before_and_after_at(self) -> None:
        from pawguard.modules.auth.schemas import RegisterRequest

        # Invalid email missing top-level domain
        with pytest.raises(ValueError):
            RegisterRequest.model_validate(
                {
                    "email": "bademail@domain",
                    "password": "Password123!",
                    "full_name": "Jane Doe",
                }
            )

        # Invalid email missing username before @
        with pytest.raises(ValueError):
            RegisterRequest.model_validate(
                {
                    "email": "@domain.com",
                    "password": "Password123!",
                    "full_name": "Jane Doe",
                }
            )

    @pytest.mark.asyncio
    async def test_service_rejects_same_password(self) -> None:
        service = _make_service()
        user = _make_user()

        with pytest.raises(InvalidCredentialsError, match="New password must be different"):
            await service.change_password(
                user=user,
                current_password="CurrentP@ss99",
                new_password="CurrentP@ss99",
                current_session_id=uuid.uuid4(),
                ctx=_ctx(),
            )
