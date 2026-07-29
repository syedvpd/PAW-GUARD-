"""Auth-module-specific exceptions. All inherit from AppException for uniform handling."""

from fastapi import status

from pawguard.core.exceptions import AppException


class InvalidCredentialsError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_CREDENTIALS"


class AccountLockedError(AppException):
    status_code = status.HTTP_423_LOCKED
    code = "ACCOUNT_LOCKED"


class AccountInactiveError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "ACCOUNT_INACTIVE"


class EmailAlreadyRegisteredError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "EMAIL_ALREADY_REGISTERED"


class InvalidSessionError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_SESSION"


class InvalidRefreshTokenError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_REFRESH_TOKEN"


class RefreshTokenReuseDetectedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "REFRESH_TOKEN_REUSE_DETECTED"


class MFARequiredError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "MFA_REQUIRED"


class InvalidMFACodeError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_MFA_CODE"


class MFAAlreadyEnabledError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "MFA_ALREADY_ENABLED"


class InvalidTokenError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_TOKEN"


class InsufficientPermissionsError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "INSUFFICIENT_PERMISSIONS"
