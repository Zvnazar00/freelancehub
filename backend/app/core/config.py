"""Environment-based configuration (12-factor). Values come only from env vars / .env, never from code."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Environment = "development"
    app_name: str = "FreelanceHub API"
    log_level: str = "INFO"

    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+psycopg://freelancehub:freelancehub@localhost:5432/freelancehub"),
        description="SQLAlchemy URL, driver postgresql+psycopg",
    )
    db_pool_size: int = 5
    db_echo: bool = False

    jwt_secret: SecretStr = SecretStr("dev-only-insecure-secret-change-me-please-0000")
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_ttl_seconds: int = Field(default=15 * 60, gt=0)
    refresh_token_ttl_seconds: int = Field(default=30 * 24 * 3600, gt=0)
    refresh_reuse_grace_seconds: int = Field(default=10, ge=0)

    # Auth rate limits: attempts per window, keyed by client IP (+ email for login).
    rate_limit_enabled: bool = True
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 300
    register_rate_limit: int = 5
    register_rate_window_seconds: int = 3600

    cors_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _secure_outside_dev(self) -> "Settings":
        if self.environment == "production":
            secret = self.jwt_secret.get_secret_value()
            if len(secret.encode()) < 32 or secret.startswith("dev-only"):
                raise ValueError("JWT_SECRET must be a random value of at least 32 bytes in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
