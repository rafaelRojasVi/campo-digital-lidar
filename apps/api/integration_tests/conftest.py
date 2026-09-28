"""Fixtures for real PostgreSQL/PostGIS integration tests."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine

API_ROOT = Path(__file__).resolve().parents[1]
FORESTRY_TESTS_ROOT = API_ROOT.parents[1] / "products" / "forestry" / "tests"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

# Synthetic Forestry family builders are shared with the Forestry unit tests.
if str(FORESTRY_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(FORESTRY_TESTS_ROOT))

from app.config import Settings  # noqa: E402
from app.database import build_engine  # noqa: E402
from app.db_safety import require_test_database  # noqa: E402


@pytest.fixture(scope="session")
def integration_settings() -> Settings:
    """Return configuration only after proving the DB is disposable."""

    settings = Settings()
    require_test_database(settings)
    return settings


@pytest.fixture(scope="session")
def integration_engine(
    integration_settings: Settings,
) -> Generator[Engine, None, None]:
    """Provide a real SQLAlchemy engine for the disposable test DB."""

    engine = build_engine(integration_settings)

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def integration_connection(
    integration_engine: Engine,
) -> Generator[Connection, None, None]:
    """Provide a real connection rolled back after each integration test."""

    with integration_engine.connect() as connection:
        transaction = connection.begin()

        try:
            yield connection
        finally:
            transaction.rollback()
