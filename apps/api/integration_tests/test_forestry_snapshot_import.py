"""scripts/forestry_snapshot_import.py: verify-before-commit, against PostGIS.

Synthetic archives only. The pinned expectation is swapped for one built
from each synthetic archive, so these tests exercise the same transaction,
refusal and audit logic the real import runs.
"""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from test_forestry_ingestion import build_zip

from forestry_family_fixtures import source_row, square_ring

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import forestry_snapshot_import as importer  # noqa: E402


def _truncate(engine: Engine) -> None:
    # DELETE in dependency order, never TRUNCATE ... CASCADE: a cascade from
    # the provenance tables would also empty seeded platform state.
    with engine.begin() as connection:
        for table in (
            "forestry.source_feature",
            "forestry.shapefile_snapshot",
            "platform.source_observation",
            "platform.source_snapshot",
            "platform.source_asset",
            "platform.source_system",
            "platform.audit_event",
        ):
            connection.execute(text(f"DELETE FROM {table}"))


@pytest.fixture(autouse=True)
def _clean(integration_engine: Engine) -> Iterator[None]:
    # These tests commit, so they start and end from an empty Forestry schema.
    _truncate(integration_engine)
    yield
    _truncate(integration_engine)


def _archive(tmp_path: Path, n_rodal: str = "1") -> str:
    rows = [source_row(objectid=1, cod_predial="P1", nom_predio="Uno", n_rodal=n_rodal, sup_ha=2.5)]
    return build_zip(tmp_path, rows, geometries=[[square_ring(0.0, 0.0, 10.0)]])


def _expected(root: Path, relative: str, engine: Engine) -> importer.ExpectedSnapshot:
    """What a correct import of ``relative`` must produce, observed in a rolled-back ingest."""

    from app.forestry_persistence import ingest_forestry_snapshot

    blank = importer.ExpectedSnapshot(
        zip_sha256="",
        family_fingerprint="",
        layer_name="",
        storage_srid=0,
        feature_count=0,
        total_sup_ha=0.0,
        total_geometry_area_source_units=0.0,
        geometry_invalid_count=0,
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        result = ingest_forestry_snapshot(
            connection,
            source_root=root,
            zip_relative_path=relative,
            system_key=importer.FORESTRY_SYSTEM_KEY,
        )
        observed = {
            name: got
            for name, _, got in importer.observed_checks(
                connection, result.shapefile_snapshot_id, blank
            )
        }
        transaction.rollback()

    assert observed["feature_count"] == 1
    return importer.ExpectedSnapshot(zip_sha256=importer.sha256_of(root / relative), **observed)


def _counts(engine: Engine) -> tuple[int, int]:
    with engine.connect() as connection:
        snapshots = connection.execute(
            text("SELECT count(*) FROM forestry.shapefile_snapshot")
        ).scalar_one()
        events = connection.execute(
            text("SELECT count(*) FROM platform.audit_event WHERE event_type = :t"),
            {"t": importer.IMPORTED_EVENT},
        ).scalar_one()
    return snapshots, events


def test_a_verification_mismatch_writes_nothing(tmp_path: Path, integration_engine: Engine) -> None:
    relative = _archive(tmp_path)
    expected = _expected(tmp_path, relative, integration_engine)

    with (
        integration_engine.connect() as connection,
        pytest.raises(importer.VerificationFailedError, match="feature_count"),
    ):
        importer.run_import(
            connection,
            source_root=tmp_path,
            zip_relative_path=relative,
            expected=dataclasses.replace(expected, feature_count=2),
            commit=True,
        )

    assert _counts(integration_engine) == (0, 0)


def test_a_dry_run_verifies_and_writes_nothing(tmp_path: Path, integration_engine: Engine) -> None:
    relative = _archive(tmp_path)
    expected = _expected(tmp_path, relative, integration_engine)

    with integration_engine.connect() as connection:
        outcome = importer.run_import(
            connection,
            source_root=tmp_path,
            zip_relative_path=relative,
            expected=expected,
            commit=False,
        )

    assert outcome.committed is False
    assert all(want == got for _, want, got in outcome.checks)
    assert _counts(integration_engine) == (0, 0)


def test_a_commit_persists_once_and_audits_once(tmp_path: Path, integration_engine: Engine) -> None:
    relative = _archive(tmp_path)
    expected = _expected(tmp_path, relative, integration_engine)

    for _ in range(2):
        with integration_engine.connect() as connection:
            importer.run_import(
                connection,
                source_root=tmp_path,
                zip_relative_path=relative,
                expected=expected,
                commit=True,
            )

    assert _counts(integration_engine) == (1, 1)


def test_another_file_is_refused_before_any_write(
    tmp_path: Path, integration_engine: Engine
) -> None:
    relative = _archive(tmp_path)
    expected = _expected(tmp_path, relative, integration_engine)
    other = tmp_path / "other"
    other.mkdir()

    with (
        integration_engine.connect() as connection,
        pytest.raises(importer.ImportRefusedError, match="SHA-256"),
    ):
        importer.run_import(
            connection,
            source_root=other,
            zip_relative_path=_archive(other, n_rodal="2"),
            expected=expected,
            commit=True,
        )

    assert _counts(integration_engine) == (0, 0)


def test_a_database_holding_another_snapshot_is_refused(
    tmp_path: Path, integration_engine: Engine
) -> None:
    first_root = tmp_path / "first"
    first_root.mkdir()
    first = _archive(first_root, n_rodal="9")
    with integration_engine.connect() as connection:
        importer.run_import(
            connection,
            source_root=first_root,
            zip_relative_path=first,
            expected=_expected(first_root, first, integration_engine),
            commit=True,
        )

    relative = _archive(tmp_path)
    expected = _expected(tmp_path, relative, integration_engine)
    with (
        integration_engine.connect() as connection,
        pytest.raises(importer.ImportRefusedError, match="other Forestry snapshot"),
    ):
        importer.run_import(
            connection,
            source_root=tmp_path,
            zip_relative_path=relative,
            expected=expected,
            commit=True,
        )

    assert _counts(integration_engine)[0] == 1
