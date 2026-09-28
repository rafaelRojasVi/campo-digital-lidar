"""SQLAlchemy infrastructure for Campo Digital platform services."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


class DatabaseUnavailableError(RuntimeError):
    """The configured database could not satisfy a connectivity probe."""


def build_engine(settings: Settings | None = None) -> Engine:
    """Create a SQLAlchemy engine from application settings.

    Production reaches a managed Postgres provider over a network Campo
    Digital does not control, unlike local/staging Postgres on a private
    Docker network, so production connections require TLS explicitly.
    """

    resolved_settings = settings or get_settings()
    connect_args = {"sslmode": "require"} if resolved_settings.app_env == "production" else {}

    return create_engine(
        resolved_settings.database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


@lru_cache
def get_database_engine() -> Engine:
    """Return the process-level engine without connecting at import time."""

    return build_engine()


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the application's SQLAlchemy session factory."""

    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


def check_database_connection(engine: Engine) -> None:
    """Verify that the configured database accepts and executes SQL."""

    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError("Database connectivity check failed.") from exc

    if result != 1:
        raise DatabaseUnavailableError("Database connectivity check returned an unexpected result.")
