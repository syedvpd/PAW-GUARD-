"""Application-wide constants shared across modules."""

from enum import StrEnum


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class ClientType(StrEnum):
    """Identifies which client is calling the API, used to select token transport."""

    WEB = "web"
    MOBILE = "mobile"


class DeviceType(StrEnum):
    WEB = "web"
    IOS = "ios"
    ANDROID = "android"
    UNKNOWN = "unknown"


REQUEST_ID_HEADER = "X-Request-ID"
CLIENT_TYPE_HEADER = "X-Client-Type"
DEVICE_ID_HEADER = "X-Device-ID"

ACCESS_TOKEN_COOKIE_NAME = "pg_access_token"
REFRESH_TOKEN_COOKIE_NAME = "pg_refresh_token"
