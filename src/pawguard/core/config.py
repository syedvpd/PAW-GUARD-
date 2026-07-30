"""Centralised application configuration, loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pawguard.core.constants import Environment


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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
    jwt_private_key_path: str = "./secrets/private_key.pem"
    jwt_public_key_path: str = "./secrets/public_key.pem"
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    pre_auth_token_expire_minutes: int = 5

    # --- Cookies ---
    cookie_domain: str = "localhost"
    cookie_secure: bool = False

    # --- S3 ---
    s3_bucket_name: str = "pawguard-media"
    s3_region: str = "us-east-1"
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

    # --- Payments ---
    # Provider is swappable: implement PaymentGateway and register it in
    # core/payments/__init__.py, then flip this one setting.
    payment_provider: str = "razorpay"
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
        return Path(self.jwt_private_key_path).read_text(encoding="utf-8")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jwt_public_key(self) -> str:
        return Path(self.jwt_public_key_path).read_text(encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
