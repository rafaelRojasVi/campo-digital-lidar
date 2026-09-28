from __future__ import annotations

from unittest.mock import Mock

import pytest
from app import database
from app.config import Settings
from app.database import (
    DatabaseUnavailableError,
    build_engine,
    build_session_factory,
    check_database_connection,
)
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError


def test_build_engine_uses_configured_database_url() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        postgres_db="fixture_database",
        postgres_user="fixture_user",
        postgres_password="fixture_secret",
        postgres_host="db.internal",
        postgres_port=6543,
    )

    engine = build_engine(settings)

    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.database == "fixture_database"
        assert engine.url.username == "fixture_user"
        assert engine.url.host == "db.internal"
        assert engine.url.port == 6543
    finally:
        engine.dispose()


def test_build_engine_requires_tls_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        postgres_db="fixture_database",
        postgres_user="fixture_user",
        postgres_password="fixture_secret",
        postgres_host="db.internal",
        postgres_port=6543,
    )
    captured_kwargs: dict[str, object] = {}

    def fake_create_engine(url: object, **kwargs: object) -> Engine:
        captured_kwargs.update(kwargs)
        return create_engine("sqlite+pysqlite:///:memory:")

    monkeypatch.setattr(database, "create_engine", fake_create_engine)

    engine = build_engine(settings)

    try:
        assert captured_kwargs["connect_args"] == {"sslmode": "require"}
    finally:
        engine.dispose()


def test_build_engine_does_not_force_tls_outside_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        postgres_db="fixture_database",
        postgres_user="fixture_user",
        postgres_password="fixture_secret",
        postgres_host="db.internal",
        postgres_port=6543,
    )
    captured_kwargs: dict[str, object] = {}

    def fake_create_engine(url: object, **kwargs: object) -> Engine:
        captured_kwargs.update(kwargs)
        return create_engine("sqlite+pysqlite:///:memory:")

    monkeypatch.setattr(database, "create_engine", fake_create_engine)

    engine = build_engine(settings)

    try:
        assert captured_kwargs["connect_args"] == {}
    finally:
        engine.dispose()


def test_process_engine_is_created_lazily_and_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    calls = 0

    def fake_build_engine() -> Engine:
        nonlocal calls
        calls += 1
        return engine

    database.get_database_engine.cache_clear()
    monkeypatch.setattr(database, "build_engine", fake_build_engine)

    try:
        first = database.get_database_engine()
        second = database.get_database_engine()

        assert first is engine
        assert second is engine
        assert calls == 1
    finally:
        database.get_database_engine.cache_clear()
        engine.dispose()


def test_build_session_factory_binds_engine() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    try:
        session_factory = build_session_factory(engine)

        assert session_factory.kw["bind"] is engine
        assert session_factory.kw["autoflush"] is False
        assert session_factory.kw["expire_on_commit"] is False
    finally:
        engine.dispose()


def test_check_database_connection_accepts_working_engine() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    try:
        check_database_connection(engine)
    finally:
        engine.dispose()


def test_check_database_connection_wraps_sqlalchemy_failure() -> None:
    engine = Mock(spec=Engine)
    engine.connect.side_effect = SQLAlchemyError("sensitive backend detail")

    with pytest.raises(DatabaseUnavailableError) as exc_info:
        check_database_connection(engine)

    assert str(exc_info.value) == "Database connectivity check failed."
    assert "sensitive backend detail" not in str(exc_info.value)
