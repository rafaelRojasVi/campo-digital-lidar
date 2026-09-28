"""Staging execution guards: size/product limits and the staging-only gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import Settings
from app.execution import (
    InProcessStagingExecutionBackend,
    StagingExecutionNotAllowedError,
    job_is_within_staging_limits,
)
from app.object_store import LocalObjectStore
from sqlalchemy import create_engine


def _settings(*, app_env: str) -> Settings:
    return Settings(_env_file=None, postgres_password="x", app_env=app_env)


def test_job_within_limits_when_small_and_not_lidar() -> None:
    assert job_is_within_staging_limits(
        product_key="forestry",
        byte_size=1024,
        max_bytes=25_000_000,
    ) == (True, None)


def test_job_over_size_cap_is_rejected() -> None:
    within, reason = job_is_within_staging_limits(
        product_key="forestry",
        byte_size=30_000_000,
        max_bytes=25_000_000,
    )
    assert within is False
    assert reason == "exceeds staging execution size limit"


def test_lidar_jobs_are_always_rejected_in_staging() -> None:
    within, reason = job_is_within_staging_limits(
        product_key="lidar",
        byte_size=10,
        max_bytes=25_000_000,
    )
    assert within is False
    assert reason == "not processed in staging"


def test_lidar_rejection_takes_priority_over_size() -> None:
    within, reason = job_is_within_staging_limits(
        product_key="lidar",
        byte_size=1,
        max_bytes=25_000_000,
    )
    assert within is False
    assert reason == "not processed in staging"


@pytest.mark.parametrize("app_env", ["development", "test", "production"])
def test_backend_construction_refused_outside_staging(app_env: str, tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    store = LocalObjectStore(tmp_path)

    with pytest.raises(StagingExecutionNotAllowedError):
        InProcessStagingExecutionBackend(engine, store, _settings(app_env=app_env))


def test_backend_constructs_when_staging(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    store = LocalObjectStore(tmp_path)

    backend = InProcessStagingExecutionBackend(engine, store, _settings(app_env="staging"))

    assert backend is not None
