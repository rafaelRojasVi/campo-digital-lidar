from __future__ import annotations

import pytest
from app.config import Settings
from app.db_safety import UnsafeTestDatabaseError, require_test_database


def make_settings(
    *,
    app_env: str = "test",
    database: str = "campo_digital_test",
) -> Settings:
    return Settings(
        _env_file=None,
        app_env=app_env,
        postgres_db=database,
        postgres_user="test_user",
        postgres_password="test_password",
        postgres_host="127.0.0.1",
        postgres_port=5433,
    )


def test_test_environment_and_test_database_are_allowed() -> None:
    require_test_database(make_settings())


def test_development_environment_is_rejected_even_for_test_database() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        require_test_database(
            make_settings(
                app_env="development",
                database="campo_digital_test",
            )
        )


def test_test_environment_is_rejected_for_development_database() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        require_test_database(
            make_settings(
                app_env="test",
                database="campo_digital",
            )
        )


def test_production_environment_is_rejected() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        require_test_database(
            make_settings(
                app_env="production",
                database="campo_digital_test",
            )
        )


def test_staging_environment_is_rejected() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        require_test_database(
            make_settings(
                app_env="staging",
                database="campo_digital_test",
            )
        )
