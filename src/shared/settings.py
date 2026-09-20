from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

_DEFAULT_JWT = "dev-secret-change-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TENANT_", env_file=".env", extra="ignore")

    app_env: str = "dev"  # dev | test | production
    database_url: str = "postgresql+asyncpg://tenant:tenant@localhost:5432/tenant_platform"
    jwt_secret: str = _DEFAULT_JWT
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_days: int = 7
    platform_realm_name: str = "platform"
    platform_issuer_url: str = "https://platform.auth.platform.io"
    otp_ttl_minutes: int = 30
    reset_token_ttl_minutes: int = 10
    keycloak_mode: str = "fake"  # fake | real (real client not fully wired yet)
    keycloak_base_url: str | None = None

    @model_validator(mode="after")
    def _reject_weak_jwt_outside_dev(self) -> Settings:
        env = (self.app_env or "dev").lower()
        if env in {"dev", "test"}:
            return self
        secret = self.jwt_secret or ""
        if not secret or secret == _DEFAULT_JWT or len(secret) < 32:
            raise ValueError(
                "TENANT_JWT_SECRET must be set to a strong secret (>=32 chars) when TENANT_APP_ENV "
                "is not dev/test"
            )
        if self.keycloak_mode == "fake":
            raise ValueError("TENANT_KEYCLOAK_MODE=fake is not allowed when TENANT_APP_ENV is production")
        return self


settings = Settings()
