from __future__ import annotations

from pathlib import Path

import pytest
from app.config import Settings
from pydantic import ValidationError
from pytest import MonkeyPatch


def test_settings_use_local_platform_defaults() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        postgres_password="local-test-secret",
    )

    assert settings.app_env == "development"
    assert settings.postgres_db == "campo_digital"
    assert settings.postgres_user == "campo_digital"
    assert settings.postgres_host == "127.0.0.1"
    assert settings.postgres_port == 5432


def test_settings_requires_explicit_app_env(monkeypatch: MonkeyPatch) -> None:
    """APP_ENV gates whether dev-only authentication may be mounted (see
    app.dev_auth.assert_dev_auth_allowed), so an unset value must fail closed
    at Settings construction rather than silently resolving to development."""

    monkeypatch.delenv("APP_ENV", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, postgres_password="x")


def test_settings_rejects_invalid_app_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, postgres_password="x", app_env="prod")


def test_settings_build_psycopg_sqlalchemy_url() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        postgres_db="test_database",
        postgres_user="test_user",
        postgres_password="p@ss:/?#[]",
        postgres_host="db.internal",
        postgres_port=6543,
    )

    url = settings.database_url

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "test_user"
    assert url.password == "p@ss:/?#[]"
    assert url.host == "db.internal"
    assert url.port == 6543
    assert url.database == "test_database"
    assert "p@ss:/?#[]" not in str(url)


def test_settings_load_postgres_values_from_env_file(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    for key in (
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    ):
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_DB=fixture_database",
                "POSTGRES_USER=fixture_user",
                "POSTGRES_PASSWORD=fixture_secret",
                "POSTGRES_HOST=fixture-db",
                "POSTGRES_PORT=5544",
                "",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file, app_env="development")

    assert settings.postgres_db == "fixture_database"
    assert settings.postgres_user == "fixture_user"
    assert settings.postgres_password.get_secret_value() == "fixture_secret"
    assert settings.postgres_host == "fixture-db"
    assert settings.postgres_port == 5544


def test_settings_repr_does_not_expose_password() -> None:
    secret = "must-not-appear"

    settings = Settings(
        _env_file=None,
        app_env="development",
        postgres_password=secret,
    )

    assert secret not in repr(settings)


def test_new_settings_default_safely() -> None:
    settings = Settings(_env_file=None, app_env="development", postgres_password="x")
    assert settings.enable_onedrive_import is False
    assert settings.staging_execution_max_bytes == 25 * 1024 * 1024
    assert settings.entra_tenant_id is None
    assert settings.platform_bootstrap_admin_tenant_id is None
