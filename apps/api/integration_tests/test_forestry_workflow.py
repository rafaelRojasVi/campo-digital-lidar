"""Rodales upload → review → publish → view → restore, end to end over PostGIS.

Real platform sessions, real CSRF tokens, the real object store (under
``tmp_path``) and committed transactions, exactly as in production; every
table the flow touches is emptied after each test. All shapefiles are
synthetic (``forestry_family_fixtures``); no client data is used.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from app.access import Role
from app.access_repository import grant_product_role, resolve_or_create_app_user
from app.csrf import CSRF_HEADER_NAME
from app.deps import SESSION_COOKIE_NAME, get_object_store
from app.main import app
from app.object_store import LocalObjectStore
from app.routers import forestry_workflow
from app.session_store import PlatformSessionStore
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, text
from test_forestry_ingestion import BOWTIE

from forestry_family_fixtures import (
    Ring,
    family_members,
    source_row,
    square_ring,
    zip_bytes,
)

_sessions = PlatformSessionStore()
_SAME_ORIGIN = "http://testserver"
_ATTACKER_ORIGIN = "https://evil.example"


def rectangle(x0: float, y0: float, width: float, height: float) -> Ring:
    """Clockwise (exterior) rectangle ring."""

    return [(x0, y0), (x0, y0 + height), (x0 + width, y0 + height), (x0 + width, y0), (x0, y0)]


def shifted(ring: Ring, dx: float) -> Ring:
    return [(x + dx, y) for x, y in ring]


# Version A: five rodales in a row.
VERSION_A_ROWS = [
    source_row(objectid=1, cod_predial="P1", nom_predio="Predio Uno", n_rodal="1"),
    source_row(objectid=2, cod_predial="P1", nom_predio="Predio Uno", n_rodal="2"),
    source_row(objectid=3, cod_predial="P1", nom_predio="Predio Uno", n_rodal="3"),
    source_row(objectid=4, cod_predial="P1", nom_predio="Predio Uno", n_rodal="4"),
    source_row(objectid=5, cod_predial="P2", nom_predio="Predio Dos", n_rodal="1"),
]
VERSION_A_GEOMETRIES = [
    [square_ring(0.0, 0.0, 10.0)],
    [square_ring(20.0, 0.0, 10.0)],
    [square_ring(40.0, 0.0, 10.0)],
    [square_ring(60.0, 0.0, 10.0)],
    [square_ring(80.0, 0.0, 10.0)],
]

# Version B, against A:
# - rodal 1: same geometry, OBJECTID renumbered (11)      -> same_geometry [objectid]
# - rodal 2: same geometry, Uso2026 changed                -> same_geometry [uso_2026]
# - rodal 3: redrawn as an (invalid) bowtie over the same square -> geometry_changed
# - rodal 4: two halves where one square was               -> uncertain (not "cut")
# - P2 rodal 1: gone                                       -> removed
# - a new square far away                                  -> added
VERSION_B_ROWS = [
    source_row(objectid=11, cod_predial="P1", nom_predio="Predio Uno", n_rodal="1"),
    source_row(
        objectid=2, cod_predial="P1", nom_predio="Predio Uno", n_rodal="2", uso_2026="CLASE B"
    ),
    source_row(objectid=3, cod_predial="P1", nom_predio="Predio Uno", n_rodal="3"),
    source_row(objectid=4, cod_predial="P1", nom_predio="Predio Uno", n_rodal="4"),
    source_row(objectid=6, cod_predial="P1", nom_predio="Predio Uno", n_rodal="4"),
    source_row(objectid=7, cod_predial="P3", nom_predio="Predio Tres", n_rodal="1"),
]
VERSION_B_GEOMETRIES = [
    [square_ring(0.0, 0.0, 10.0)],
    [square_ring(20.0, 0.0, 10.0)],
    [shifted(BOWTIE, 40.0)],
    [rectangle(60.0, 0.0, 5.0, 10.0)],
    [rectangle(65.0, 0.0, 5.0, 10.0)],
    [square_ring(200.0, 0.0, 10.0)],
]


def family_zip(
    tmp_path: Path,
    name: str,
    rows: list[dict[str, object]],
    geometries: list[Any],
    **options: Any,
) -> bytes:
    members = family_members(
        tmp_path / name, rows, base_name="Degenfeld_Sintetico", geometries=geometries, **options
    )
    return zip_bytes(members)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "object-store")


@pytest.fixture
def client(
    integration_engine: Engine, store: LocalObjectStore
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_object_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _isolated_tables(integration_engine: Engine) -> Generator[None, None, None]:
    yield
    with integration_engine.begin() as connection:
        connection.execute(
            text("UPDATE forestry.publication_state SET published_snapshot_id = NULL")
        )
        for table in (
            "forestry.publication_event",
            "forestry.snapshot_upload",
            "forestry.source_feature",
            "forestry.shapefile_snapshot",
            "platform.source_observation",
            "platform.source_snapshot",
            "platform.source_asset",
            "platform.source_system",
            "platform.audit_event",
            "platform.session",
            "platform.product_grant",
            "platform.app_user",
        ):
            connection.execute(text(f"DELETE FROM {table}"))


def sign_in(
    client: TestClient, engine: Engine, name: str, grants: tuple[tuple[str, Role], ...]
) -> None:
    """Sign ``client`` in as a fresh Google-style account holding ``grants``."""

    with engine.begin() as connection:
        user = resolve_or_create_app_user(
            connection,
            identity_kind="google",
            identity_key=f"sub-{name}",
            display_name=name,
            email=f"{name}@campodigital.cl",
        )
        for product_key, role in grants:
            grant_product_role(connection, app_user_id=user.id, product_key=product_key, role=role)
        secret = _sessions.create_session(connection, app_user_id=user.id, ttl=timedelta(hours=1))

    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, secret)
    client.headers.pop(CSRF_HEADER_NAME, None)
    token = client.get("/api/auth/csrf")
    assert token.status_code == 200, token.text
    client.headers[CSRF_HEADER_NAME] = token.json()["csrf_token"]


def upload(client: TestClient, content: bytes, filename: str = "entrega.zip") -> Response:
    return client.post(
        "/api/forestry/uploads",
        files={"file": (filename, content, "application/zip")},
        headers={"Origin": _SAME_ORIGIN},
    )


def activate(
    client: TestClient,
    action: str,
    snapshot_id: int,
    *,
    expected: int | None,
    acknowledge: bool = False,
) -> Response:
    return client.post(
        f"/api/forestry/snapshots/{snapshot_id}/{action}",
        json={"expected_published_snapshot_id": expected, "acknowledge_review": acknowledge},
        headers={"Origin": _SAME_ORIGIN},
    )


def published_id(client: TestClient) -> int | None:
    response = client.get("/api/forestry/snapshots/published")
    if response.status_code == 404:
        return None
    assert response.status_code == 200, response.text
    return int(response.json()["shapefile_snapshot_id"])


def count(engine: Engine, sql: str) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text(sql)).scalar_one())


def audit_types(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.execute(text("SELECT event_type FROM platform.audit_event ORDER BY id"))
            .scalars()
            .all()
        )


# ---------------------------------------------------------------------------
# The whole flow
# ---------------------------------------------------------------------------


def test_upload_review_publish_view_restore(
    client: TestClient, integration_engine: Engine, tmp_path: Path, store: LocalObjectStore
) -> None:
    sign_in(client, integration_engine, "admin", (("forestry", Role.ADMIN),))
    zip_a = family_zip(tmp_path, "a", VERSION_A_ROWS, VERSION_A_GEOMETRIES)
    zip_b = family_zip(tmp_path, "b", VERSION_B_ROWS, VERSION_B_GEOMETRIES)

    # Upload A: pending, nothing published.
    uploaded_a = upload(client, zip_a, "Degenfeld_A.zip")
    assert uploaded_a.status_code == 200, uploaded_a.text
    body_a = uploaded_a.json()
    assert body_a["status"] == "uploaded"
    assert body_a["version_status"] == "pending"
    assert body_a["feature_count"] == 5
    assert body_a["layer_name"] == "Degenfeld_Sintetico"
    a = body_a["shapefile_snapshot_id"]
    assert published_id(client) is None

    # The original ZIP is kept on the object store (the volume in production).
    with integration_engine.connect() as connection:
        key = connection.execute(
            text(
                "SELECT s.object_storage_key FROM forestry.snapshot_upload u "
                "JOIN platform.source_snapshot s ON s.id = u.source_snapshot_id "
                "WHERE u.shapefile_snapshot_id = :id"
            ),
            {"id": a},
        ).scalar_one()
    assert store.open(key).read() == zip_a

    # Review A: source details and numbers; nothing to compare against yet.
    review_a = client.get(f"/api/forestry/snapshots/{a}/review").json()
    assert review_a["version"]["status"] == "pending"
    assert review_a["version"]["crs_name"] == "WGS_1984_UTM_Zone_18S"
    assert review_a["version"]["storage_srid"] == 32718
    assert review_a["version"]["feature_count"] == 5
    assert review_a["version"]["total_geometry_area_source_units"] == pytest.approx(500.0)
    assert review_a["version"]["uploads"][0]["original_filename"] == "Degenfeld_A.zip"
    assert review_a["version"]["uploads"][0]["uploaded_by_display_name"] == "admin"
    assert review_a["comparison"] is None
    assert review_a["review_required"] is False
    assert review_a["can_publish"] is True

    # Publish A.
    first = activate(client, "publish", a, expected=None)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "published"
    assert published_id(client) == a

    # Upload B: pending; the published version is untouched.
    uploaded_b = upload(client, zip_b, "Degenfeld_B.zip")
    assert uploaded_b.status_code == 200, uploaded_b.text
    b = uploaded_b.json()["shapefile_snapshot_id"]
    assert uploaded_b.json()["version_status"] == "pending"
    assert published_id(client) == a

    # Review B against A.
    review = client.get(f"/api/forestry/snapshots/{b}/review")
    assert review.status_code == 200, review.text
    review_b = review.json()
    assert review_b["published_version"]["shapefile_snapshot_id"] == a
    assert review_b["version"]["geometry_invalid_count"] == 1
    assert review_b["invalid_geometries"][0]["feature_ordinal"] == 3
    comparison = review_b["comparison"]
    assert comparison["counts"] == {
        "uncertain": 1,
        "geometry_changed": 1,
        "removed": 1,
        "added": 1,
        "same_geometry": 2,
    }
    assert comparison["unchanged_count"] == 0
    assert comparison["review_required_count"] == 2
    assert review_b["review_required"] is True

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for item in comparison["items"]:
        by_kind.setdefault(item["kind"], []).append(item)

    renumbered, reclassified = sorted(
        by_kind["same_geometry"], key=lambda item: item["pending"][0]["feature_ordinal"]
    )
    assert renumbered["changed_fields"] == ["objectid"]
    assert renumbered["same_objectid"] is False
    assert reclassified["changed_fields"] == ["uso_2026"]
    assert reclassified["same_objectid"] is True

    (redrawn,) = by_kind["geometry_changed"]
    assert [ref["feature_ordinal"] for ref in redrawn["published"]] == [3]
    assert [ref["feature_ordinal"] for ref in redrawn["pending"]] == [3]

    # One square where two halves now are: grouped, never called a cut.
    (split,) = by_kind["uncertain"]
    assert [ref["feature_ordinal"] for ref in split["published"]] == [4]
    assert [ref["feature_ordinal"] for ref in split["pending"]] == [4, 5]
    assert all(o["overlap_ratio_of_smaller"] == pytest.approx(1.0) for o in split["overlaps"])
    assert "cort" not in review.text.lower()
    assert "cut" not in review.text.lower()

    assert [ref["feature_ordinal"] for ref in by_kind["removed"][0]["published"]] == [5]
    assert [ref["feature_ordinal"] for ref in by_kind["added"][0]["pending"]] == [6]

    # Viewers see only the published map, not the pending upload.
    viewer = TestClient(app)
    sign_in(viewer, integration_engine, "viewer", (("forestry", Role.VIEWER),))
    assert published_id(viewer) == a
    assert viewer.get(f"/api/forestry/snapshots/{b}").status_code == 404
    assert viewer.get(f"/api/forestry/snapshots/{b}/feature-collection").status_code == 404
    assert viewer.get(f"/api/forestry/snapshots/{b}/review").status_code == 403
    viewer_versions = viewer.get("/api/forestry/versions").json()
    assert [v["shapefile_snapshot_id"] for v in viewer_versions["versions"]] == [a]

    # Publishing needs the acknowledgement, and a review of the current state.
    refused = activate(client, "publish", b, expected=a)
    assert refused.status_code == 409
    assert "confirme" in refused.json()["detail"]
    stale = activate(client, "publish", b, expected=None, acknowledge=True)
    assert stale.status_code == 409
    assert "cambió" in stale.json()["detail"]
    assert published_id(client) == a

    published_b = activate(client, "publish", b, expected=a, acknowledge=True)
    assert published_b.status_code == 200, published_b.text
    assert published_b.json()["previous_snapshot_id"] == a
    assert published_id(client) == b
    assert published_id(viewer) == b

    # A was published before: it can only come back through «Restaurar».
    assert activate(client, "publish", a, expected=b).status_code == 409
    assert activate(client, "restore", b, expected=b).status_code == 409

    restored = activate(client, "restore", a, expected=b)
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "restored"
    assert published_id(client) == a
    assert published_id(viewer) == a

    # History: statuses, sources, uploaders and the activation trail.
    versions = client.get("/api/forestry/versions").json()
    assert versions["published_snapshot_id"] == a
    statuses = {v["shapefile_snapshot_id"]: v["status"] for v in versions["versions"]}
    assert statuses == {a: "published", b: "previously_published"}
    assert [(e["event_type"], e["shapefile_snapshot_id"]) for e in versions["events"]] == [
        ("restore", a),
        ("publish", b),
        ("publish", a),
    ]
    assert {e["actor_display_name"] for e in versions["events"]} == {"admin"}

    # Uploading A's content again is recognised, and changes nothing.
    again = upload(client, zip_a, "Degenfeld_A_copia.zip")
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "already_uploaded"
    assert again.json()["shapefile_snapshot_id"] == a
    assert published_id(client) == a
    assert count(integration_engine, "SELECT count(*) FROM forestry.shapefile_snapshot") == 2
    assert count(integration_engine, "SELECT count(*) FROM forestry.snapshot_upload") == 3

    assert audit_types(integration_engine) == [
        "forestry.snapshot.uploaded",
        "forestry.snapshot.published",
        "forestry.snapshot.uploaded",
        "forestry.snapshot.publish_refused",
        "forestry.snapshot.publish_refused",
        "forestry.snapshot.published",
        "forestry.snapshot.publish_refused",
        "forestry.snapshot.publish_refused",
        "forestry.snapshot.restored",
        "forestry.snapshot.uploaded",
    ]


def test_an_identical_upload_of_the_published_version_compares_as_unchanged(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    sign_in(client, integration_engine, "admin", (("forestry", Role.ADMIN),))
    a = upload(client, family_zip(tmp_path, "a", VERSION_A_ROWS, VERSION_A_GEOMETRIES)).json()
    assert activate(client, "publish", a["shapefile_snapshot_id"], expected=None).status_code == 200

    # Same features, one attribute changed so the family content differs.
    rows = [dict(row) for row in VERSION_A_ROWS]
    rows[0]["desc_uso"] = "Otra descripción"
    b = upload(client, family_zip(tmp_path, "b", rows, VERSION_A_GEOMETRIES)).json()

    review = client.get(f"/api/forestry/snapshots/{b['shapefile_snapshot_id']}/review").json()
    assert review["comparison"]["unchanged_count"] == 4
    assert review["comparison"]["counts"]["same_geometry"] == 1
    assert review["comparison"]["review_required_count"] == 0
    assert review["review_required"] is False


# ---------------------------------------------------------------------------
# Permissions and CSRF
# ---------------------------------------------------------------------------


def test_viewers_and_other_products_cannot_upload_review_or_publish(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    content = family_zip(tmp_path, "a", VERSION_A_ROWS, VERSION_A_GEOMETRIES)
    sign_in(client, integration_engine, "operator", (("forestry", Role.OPERATOR),))
    pending = upload(client, content).json()["shapefile_snapshot_id"]

    for name, grants in (
        ("viewer", (("forestry", Role.VIEWER),)),
        ("transelec-admin", (("transelect", Role.ADMIN),)),
        ("nobody", ()),
    ):
        sign_in(client, integration_engine, name, grants)
        assert upload(client, content).status_code == 403, name
        assert client.get(f"/api/forestry/snapshots/{pending}/review").status_code == 403, name
        assert activate(client, "publish", pending, expected=None).status_code == 403, name
        assert activate(client, "restore", pending, expected=None).status_code == 403, name

    assert published_id_as_admin(client, integration_engine) is None
    assert count(integration_engine, "SELECT count(*) FROM forestry.snapshot_upload") == 1


def published_id_as_admin(client: TestClient, engine: Engine) -> int | None:
    sign_in(client, engine, "checker", (("forestry", Role.ADMIN),))
    return published_id(client)


def test_an_operator_can_upload_and_publish(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    sign_in(client, integration_engine, "operator", (("forestry", Role.OPERATOR),))
    snapshot = upload(client, family_zip(tmp_path, "a", VERSION_A_ROWS, VERSION_A_GEOMETRIES))
    assert snapshot.status_code == 200
    snapshot_id = snapshot.json()["shapefile_snapshot_id"]
    assert activate(client, "publish", snapshot_id, expected=None).status_code == 200


def test_anonymous_uploads_are_refused_before_the_body_is_read(client: TestClient) -> None:
    response = client.post(
        "/api/forestry/uploads",
        files={"file": ("a.zip", b"x" * 1000, "application/zip")},
        headers={"Origin": _SAME_ORIGIN},
    )
    assert response.status_code == 401
    assert (
        client.post(
            "/api/forestry/snapshots/1/publish", json={"expected_published_snapshot_id": None}
        ).status_code
        == 401
    )


def test_mutations_without_a_valid_csrf_token_or_from_another_origin_are_refused(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    content = family_zip(tmp_path, "a", VERSION_A_ROWS, VERSION_A_GEOMETRIES)
    sign_in(client, integration_engine, "admin", (("forestry", Role.ADMIN),))
    token = client.headers.pop(CSRF_HEADER_NAME)

    assert upload(client, content).status_code == 403
    assert activate(client, "publish", 1, expected=None).status_code == 403

    client.headers[CSRF_HEADER_NAME] = token
    cross_origin = client.post(
        "/api/forestry/uploads",
        files={"file": ("a.zip", content, "application/zip")},
        headers={"Origin": _ATTACKER_ORIGIN},
    )
    assert cross_origin.status_code == 403
    assert count(integration_engine, "SELECT count(*) FROM forestry.shapefile_snapshot") == 0


# ---------------------------------------------------------------------------
# Malformed and unacceptable uploads leave nothing behind
# ---------------------------------------------------------------------------


def _bad_uploads(tmp_path: Path) -> list[tuple[str, str, bytes, str]]:
    good = family_members(
        tmp_path / "good", VERSION_A_ROWS, base_name="Capa", geometries=VERSION_A_GEOMETRIES
    )
    traversal = dict(good)
    traversal["../Capa.shp"] = traversal.pop("Capa.shp")
    missing_prj = {name: data for name, data in good.items() if not name.endswith(".prj")}
    bomb = dict(good)
    bomb["Capa.shp.xml"] = b"\x00" * (8 * 1024 * 1024)
    wrong_crs = family_members(
        tmp_path / "crs",
        VERSION_A_ROWS,
        base_name="Capa",
        geometries=VERSION_A_GEOMETRIES,
        prj_text='GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984"]]',
    )
    null_shape = family_members(
        tmp_path / "null",
        VERSION_A_ROWS[:2],
        base_name="Capa",
        geometries=[[square_ring(0.0, 0.0, 10.0)], None],
    )
    truncated = zip_bytes(good)[:200]
    return [
        ("not a zip", "a.zip", b"this is not a zip", "not_zip"),
        ("truncated", "a.zip", truncated, "not_zip"),
        ("path traversal", "a.zip", zip_bytes(traversal), "unsafe_member"),
        ("missing .prj", "a.zip", zip_bytes(missing_prj), "missing_members"),
        ("zip bomb", "a.zip", zip_bytes(bomb), "compression_ratio"),
        ("wrong CRS", "a.zip", zip_bytes(wrong_crs), "crs_mismatch"),
        ("null geometry", "a.zip", zip_bytes(null_shape), "null_geometry"),
    ]


def test_malformed_zips_are_refused_and_leave_nothing_behind(
    client: TestClient, integration_engine: Engine, tmp_path: Path, store: LocalObjectStore
) -> None:
    sign_in(client, integration_engine, "admin", (("forestry", Role.ADMIN),))

    for label, filename, content, reason in _bad_uploads(tmp_path):
        response = upload(client, content, filename)
        assert response.status_code == 422, (label, response.text)
        assert response.json()["reason"] == reason, label
        detail = response.json()["detail"]
        assert "Traceback" not in detail and "/tmp" not in detail, label

    assert count(integration_engine, "SELECT count(*) FROM forestry.shapefile_snapshot") == 0
    assert count(integration_engine, "SELECT count(*) FROM platform.source_snapshot") == 0
    assert (
        not list((store.root / "sha256").glob("*/*")) if (store.root / "sha256").exists() else True
    )
    assert audit_types(integration_engine) == ["forestry.snapshot.upload_rejected"] * 7


def test_a_non_zip_filename_is_refused(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    sign_in(client, integration_engine, "admin", (("forestry", Role.ADMIN),))
    content = family_zip(tmp_path, "a", VERSION_A_ROWS, VERSION_A_GEOMETRIES)

    assert upload(client, content, "entrega.shp").status_code == 422


def test_an_oversized_upload_is_refused(
    client: TestClient,
    integration_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sign_in(client, integration_engine, "admin", (("forestry", Role.ADMIN),))
    monkeypatch.setattr(forestry_workflow, "FORESTRY_MAX_UPLOAD_BYTES", 1000)

    response = upload(client, family_zip(tmp_path, "a", VERSION_A_ROWS, VERSION_A_GEOMETRIES))

    assert response.status_code == 413
    assert count(integration_engine, "SELECT count(*) FROM forestry.shapefile_snapshot") == 0


def test_a_declared_body_over_the_route_limit_is_refused_before_reading(
    client: TestClient, integration_engine: Engine
) -> None:
    sign_in(client, integration_engine, "admin", (("forestry", Role.ADMIN),))

    response = client.post(
        "/api/forestry/uploads",
        content=b"",
        headers={
            "Origin": _SAME_ORIGIN,
            "Content-Type": "multipart/form-data; boundary=x",
            "Content-Length": str(200 * 1024 * 1024),
        },
    )

    assert response.status_code == 413
