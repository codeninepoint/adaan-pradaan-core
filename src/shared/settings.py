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
    keycloak_mode: str = "fake"  # fake | real
    keycloak_base_url: str | None = None
    keycloak_admin_username: str = "admin"
    keycloak_admin_password: str = "admin"
    keycloak_client_id: str = "tenant-platform"
    # inline = run org-upgrade in the API process (tests/local). temporal = durable workflow.
    workflow_mode: str = "inline"
    temporal_address: str = "localhost:7233"
    temporal_task_queue: str = "org-upgrade"
    # Comma-separated browser origins allowed for CORS (UI → API). Empty = no CORS middleware.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Comma-separated emails promoted to platform operator on GET /auth/me.
    platform_operator_emails: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def platform_operator_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.platform_operator_emails.split(",") if e.strip()}

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
