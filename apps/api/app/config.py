"""Typed application configuration for Campo Digital platform services."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Literal["development", "test", "staging", "production"] = Field(
        validation_alias="APP_ENV",
    )

    postgres_db: str = Field(
        default="campo_digital",
        validation_alias="POSTGRES_DB",
    )
    postgres_user: str = Field(
        default="campo_digital",
        validation_alias="POSTGRES_USER",
    )
    postgres_password: SecretStr = Field(
        validation_alias="POSTGRES_PASSWORD",
    )
    postgres_host: str = Field(
        default="127.0.0.1",
        validation_alias="POSTGRES_HOST",
    )
    postgres_port: int = Field(
        default=5432,
        validation_alias="POSTGRES_PORT",
        ge=1,
        le=65535,
    )

    entra_tenant_id: str | None = Field(default=None, validation_alias="ENTRA_TENANT_ID")
    entra_client_id: str | None = Field(default=None, validation_alias="ENTRA_CLIENT_ID")
    entra_client_secret: SecretStr | None = Field(
        default=None, validation_alias="ENTRA_CLIENT_SECRET"
    )
    entra_redirect_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias="ENTRA_REDIRECT_BASE_URL",
    )

    platform_token_encryption_key: SecretStr | None = Field(
        default=None, validation_alias="PLATFORM_TOKEN_ENCRYPTION_KEY"
    )

    # Google Workspace sign-in, the Transelec product's identity provider
    # (see app.google_auth and ADR-010). Entra above stays in place for the
    # other products; neither provider's configuration implies the other's.
    google_client_id: str | None = Field(default=None, validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: SecretStr | None = Field(
        default=None, validation_alias="GOOGLE_CLIENT_SECRET"
    )
    google_redirect_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias="GOOGLE_REDIRECT_BASE_URL",
    )
    # The `hd` claim an id_token must carry, exactly, to be accepted. It is
    # the Workspace membership control -- not the email's suffix -- so it is
    # configured rather than inferred, and has no permissive default.
    google_workspace_domain: str = Field(
        default="campodigital.cl",
        validation_alias="GOOGLE_WORKSPACE_DOMAIN",
    )

    # One-time bootstrap: the single Workspace address allowed to receive an
    # ADMIN grant on `transelect` at first sign-in, and on no other product
    # (see app.access_repository.maybe_grant_transelec_bootstrap_admin).
    transelec_bootstrap_admin_email: str | None = Field(
        default=None, validation_alias="TRANSELEC_BOOTSTRAP_ADMIN_EMAIL"
    )

    platform_bootstrap_admin_tenant_id: str | None = Field(
        default=None, validation_alias="PLATFORM_BOOTSTRAP_ADMIN_TENANT_ID"
    )
    platform_bootstrap_admin_object_id: str | None = Field(
        default=None, validation_alias="PLATFORM_BOOTSTRAP_ADMIN_OBJECT_ID"
    )

    # Comma-separated browser origins allowed to drive state-changing
    # requests, checked by app.csrf's second (Origin/Referer) layer. Needed
    # wherever the frontend reaches this API through a proxy/rewrite that
    # forwards the browser's Origin but not its Host (see render.yaml's
    # /api/* rewrite and apps/portal/vite.config.ts's dev proxy). Empty is
    # safe: same-origin requests are always trusted without configuration.
    csrf_trusted_origins: str | None = Field(
        default=None,
        validation_alias="CSRF_TRUSTED_ORIGINS",
    )

    enable_onedrive_import: bool = Field(default=False, validation_alias="ENABLE_ONEDRIVE_IMPORT")
    staging_execution_max_bytes: int = Field(
        default=25 * 1024 * 1024,
        validation_alias="STAGING_EXECUTION_MAX_BYTES",
        gt=0,
    )

    @property
    def database_url(self) -> URL:
        """Build the SQLAlchemy PostgreSQL URL without manual string assembly."""

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    """Return process-level application settings."""

    # BaseSettings resolves required values from runtime sources that mypy
    # cannot infer from the generated constructor signature.
    return Settings()  # type: ignore[call-arg]
