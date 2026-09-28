from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import app.main as main_module
import pytest
from app.database import get_database_engine
from app.main import app
from app.object_store import LocalObjectStore, ObjectStoreNotConfiguredError
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError


def test_readiness_returns_ready_when_database_probe_succeeds() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    app.dependency_overrides[get_database_engine] = lambda: engine

    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.pop(get_database_engine, None)
        engine.dispose()

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_is_repeatable_without_connection_leak() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    app.dependency_overrides[get_database_engine] = lambda: engine

    try:
        client = TestClient(app)

        for _ in range(3):
            response = client.get("/ready")
            assert response.status_code == 200
            assert response.json() == {"status": "ready"}
    finally:
        app.dependency_overrides.pop(get_database_engine, None)
        engine.dispose()


def test_readiness_returns_503_without_leaking_backend_error() -> None:
    engine = Mock(spec=Engine)
    engine.connect.side_effect = SQLAlchemyError("password=should-never-appear")
    app.dependency_overrides[get_database_engine] = lambda: engine

    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.pop(get_database_engine, None)

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "should-never-appear" not in response.text


def test_health_remains_available_when_database_is_unavailable() -> None:
    engine = Mock(spec=Engine)
    engine.connect.side_effect = SQLAlchemyError("database unavailable")
    app.dependency_overrides[get_database_engine] = lambda: engine

    try:
        response = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.pop(get_database_engine, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def _ready_with_store(monkeypatch: pytest.MonkeyPatch, get_store: object) -> tuple[int, object]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    app.dependency_overrides[get_database_engine] = lambda: engine
    monkeypatch.setattr(main_module, "get_object_store", get_store)

    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.pop(get_database_engine, None)
        engine.dispose()

    return response.status_code, response.json()


def test_readiness_is_not_ready_when_object_store_is_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unconfigured() -> LocalObjectStore:
        raise ObjectStoreNotConfiguredError("CAMPO_OBJECT_STORE_ROOT must be set")

    assert _ready_with_store(monkeypatch, unconfigured) == (503, {"status": "not_ready"})


def test_readiness_is_not_ready_when_object_store_is_not_writable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = LocalObjectStore(tmp_path / "object-store")

    def failing_probe() -> None:
        raise PermissionError("root-owned volume")

    monkeypatch.setattr(store, "check_writable", failing_probe)

    assert _ready_with_store(monkeypatch, lambda: store) == (503, {"status": "not_ready"})


def test_readiness_is_ready_with_writable_object_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = LocalObjectStore(tmp_path / "object-store")

    assert _ready_with_store(monkeypatch, lambda: store) == (200, {"status": "ready"})


def test_readiness_is_not_ready_when_production_store_has_no_volume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The Railway misconfiguration this guards against: the variable is set
    # and the root entrypoint has created /data/object-store, but no volume is
    # attached, so the path is writable yet lives on the container layer.
    import app.deps as deps_module
    import app.object_store as object_store_module

    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        "600 500 0:52 / / rw,relatime - overlay overlay rw,lowerdir=/l,upperdir=/u\n"
        "601 600 0:55 / /proc rw,nosuid - proc proc rw\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(object_store_module, "PROC_SELF_MOUNTINFO", mountinfo)
    monkeypatch.setattr(deps_module, "_object_store", None)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CAMPO_OBJECT_STORE_ROOT", "/data/object-store")

    assert _ready_with_store(monkeypatch, deps_module.get_object_store) == (
        503,
        {"status": "not_ready"},
    )
    assert deps_module._object_store is None
