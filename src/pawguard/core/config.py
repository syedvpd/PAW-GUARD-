"""Centralised application configuration, loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pawguard.core.constants import Environment


def _resolve_key(inline_pem: str, key_path: str, env_var_name: str) -> str:
    """Prefer an inline PEM from the environment; fall back to the file on disk.

    Env vars can't carry literal newlines, so `\n` escapes are unescaped here.
    """
    if inline_pem.strip():
        return inline_pem.replace("\\n", "\n")

    path = Path(key_path)
    if not path.is_file():
        raise RuntimeError(
            f"No JWT key available: {env_var_name} is unset and {key_path!r} does not exist. "
            f"Set {env_var_name} to the PEM contents in hosted environments, or generate the "
            "keypair locally with `openssl genrsa -out secrets/private_key.pem 2048`."
        )
    return path.read_text(encoding="utf-8")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url", "database_url_frontend", mode="before")
    @classmethod
    def normalize_database_url(cls, v: Any) -> Any:
        if not isinstance(v, str) or not v.strip():
            return v
        
        # 1. Normalize protocol to postgresql+asyncpg
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
            
        # 2. Ensure database name is postgres if it ends with / or has no path
        parts = v.split("://", 1)
        if len(parts) == 2:
            proto, rest = parts
            at_idx = rest.find("@")
            start_search = at_idx if at_idx != -1 else 0
            slash_idx = rest.find("/", start_search)
            if slash_idx == -1:
                v = v + "/postgres"
            else:
                path_part = rest[slash_idx:]
                db_name_part = path_part.split("?")[0]
                if db_name_part == "/" or db_name_part == "":
                    query = ""
                    if "?" in path_part:
                        query = "?" + path_part.split("?", 1)[1]
                    v = proto + "://" + rest[:slash_idx] + "/postgres" + query
        return v

    # --- App ---
    app_name: str = "PawGuard"
    environment: Environment = Environment.LOCAL
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    allowed_hosts: str = "localhost,127.0.0.1"
    cors_origins: str = "http://localhost:3000"
    max_request_body_size: int = 10_485_760  # 10 MB

    # --- Database ---
    database_url: str = "postgresql+asyncpg://pawguard:pawguard@localhost:5432/pawguard"
    database_url_frontend: str = ""
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_echo: bool = False

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- JWT ---
    # In hosted environments the PEM files don't exist (secrets/ is gitignored),
    # so the keys are supplied inline via env vars instead. These take
    # precedence over the *_path settings when set.
    jwt_private_key_pem: str = ""
    jwt_public_key_pem: str = ""
    jwt_private_key_path: str = "./secrets/private_key.pem"
    jwt_public_key_path: str = "./secrets/public_key.pem"
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    pre_auth_token_expire_minutes: int = 5

    # --- MFA ---
    # Optional independent key used to encrypt TOTP secrets at rest (Fernet).
    # When unset, the key is derived from the JWT private key so existing
    # deployments stay zero-config; set this in production so rotating the JWT
    # keypair does not orphan stored MFA secrets.
    mfa_encryption_key: str = ""

    # --- OAuth / Social login ---
    # Audience (client id) of the Google / Apple application this backend
    # verifies provider ID tokens against. OAuth login FAILS CLOSED when
    # unset: a provider token whose `aud` does not match is rejected.
    google_oauth_client_id: str = ""
    apple_oauth_client_id: str = ""

    # --- Cookies ---
    cookie_domain: str = "localhost"
    cookie_secure: bool = False

    # --- S3 ---
    s3_bucket_name: str = "pawguard-media"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # --- Mail ---
    mail_from: str = "no-reply@pawguard.org"
    mail_host: str = "localhost"
    mail_port: int = 1025
    mail_username: str = ""
    mail_password: str = ""
    mail_use_tls: bool = False

    # --- Frontend URLs ---
    web_app_url: str = "http://localhost:3000"
    admin_app_url: str = "http://localhost:5173"

    # --- Rate limiting ---
    login_rate_limit_per_minute: int = 10
    refresh_rate_limit_per_minute: int = 30
    password_reset_rate_limit_per_hour: int = 5

    # --- Organisation ---
    org_name: str = "PawGuard Animal Rescue"
    org_address: str = "123 Shelter Lane, Petville, PA 12345"

    # --- Payments ---
    # Provider is swappable: implement PaymentGateway and register it in
    # core/payments/__init__.py, then flip this one setting.
    payment_provider: str = Field(
        default="razorpay", validation_alias=AliasChoices("PAYMENT_GATEWAY", "PAYMENT_PROVIDER")
    )
    payment_currency: str = Field(default="INR", validation_alias=AliasChoices("PAYMENT_CURRENCY"))
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @computed_field  # type: ignore[prop-decorator]
    @property
    def docs_enabled(self) -> bool:
        return self.environment in (Environment.LOCAL, Environment.STAGING)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jwt_private_key(self) -> str:
        return _resolve_key(
            self.jwt_private_key_pem, self.jwt_private_key_path, "JWT_PRIVATE_KEY_PEM"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jwt_public_key(self) -> str:
        return _resolve_key(
            self.jwt_public_key_pem, self.jwt_public_key_path, "JWT_PUBLIC_KEY_PEM"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
