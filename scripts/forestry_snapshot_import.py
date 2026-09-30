"""Controlled import of the Degenfeld 2026 Forestry snapshot into a hosted database.

This is the only supported way to put the real Rodales snapshot into the
hosted platform database until the upload/review/publish workflow exists.
It is deliberately narrow:

- It accepts exactly one archive: the ZIP whose SHA-256 is pinned below, the
  same one Source Evidence V1 and the ingestion-substrate verification were
  run against. Any other file is refused before a database connection opens.
- It refuses a target host that does not match ``--expect-host``, so a stale
  shell environment cannot import into the wrong database.
- It refuses a database already holding a different Forestry snapshot.
- Ingestion and verification run in ONE transaction. Every expected count
  (features, hectares, invalid geometries, quality flags, source-field
  differences, fingerprint, layer, SRID) is checked against what was just
  written; any mismatch rolls the whole transaction back.
- Without ``--commit`` it is a dry run: everything is verified, then rolled
  back, and nothing is written.
- A committed import is recorded as a ``forestry.snapshot.imported`` audit
  event with no actor (it is an operator action, not a signed-in user's).

The archive is only read. Nothing from it is printed beyond the counts
already recorded in products/forestry/docs/ingestion-substrate-v1.md.

Usage (see products/forestry/docs/hosted-release-v1.md for the full runbook):

    APP_ENV=production POSTGRES_HOST=... POSTGRES_PORT=... POSTGRES_DB=... \\
    POSTGRES_USER=... POSTGRES_PASSWORD=... \\
    uv run --extra api python scripts/forestry_snapshot_import.py \\
        --source-root "$CAMPO_DIGITAL_SOURCE_ROOT" --expect-host <host>   # dry run
    ... same command ... --commit                                          # write

Exit codes: 0 verified (and committed with --commit); 2 refused before any
write (wrong file, wrong host, conflicting snapshot); 3 verification failed
and was rolled back.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import Connection, text  # noqa: E402

FORESTRY_SOURCE_ZIP = (
    "01_Gestion_Predial_Forestal/02_Datos_Entrada/01_SAF_DEGENFELD/001_DEGENFELD_2026.zip"
)
# The same provenance system key `make forestry-dev` records locally.
FORESTRY_SYSTEM_KEY = "campo_digital_onedrive"
IMPORTED_EVENT = "forestry.snapshot.imported"


@dataclass(frozen=True)
class ExpectedSnapshot:
    """What the pinned archive must produce once persisted."""

    zip_sha256: str
    family_fingerprint: str
    layer_name: str
    storage_srid: int
    feature_count: int
    total_sup_ha: float
    total_geometry_area_source_units: float
    geometry_invalid_count: int
    quality_flag_counts: dict[str, int] = field(default_factory=dict)
    uso_2024_vs_uso_2026_changes: int = 0
    cod_uso_vs_cod_uso_2026_changes: int = 0


# RESULT recorded on 2026-08-29 (products/forestry/docs/ingestion-substrate-v1.md,
# "Verification against the real source") and re-verified in the browser on
# 2026-08-30 (dashboard-v1.md). Full hashes re-read from the source on
# 2026-09-29.
DEGENFELD_2026 = ExpectedSnapshot(
    zip_sha256="d6d390b8586aa8d198f6f14bed1e2e13a22ee5fcd749a7778baa50bbbad84385",
    family_fingerprint="19beaed51b5c1bc144c8d34d500a21d1e3a31b7a1dbdc674b96ac69225060bd1",
    layer_name="Gdb_Degenfeld2026_mv",
    storage_srid=32718,
    feature_count=1568,
    total_sup_ha=10422.61,
    total_geometry_area_source_units=104226106.7,
    geometry_invalid_count=7,
    quality_flag_counts={
        "blank_rodal": 143,
        "duplicate_predio_rodal_key": 32,
        "truncated_use_code_2026": 8,
        "invalid_geometry": 7,
        "duplicate_geometry": 2,
        "predio_code_name_anomaly": 2,
    },
    uso_2024_vs_uso_2026_changes=1,
    cod_uso_vs_cod_uso_2026_changes=72,
)


class ImportRefusedError(RuntimeError):
    """Refused before anything was written."""


class VerificationFailedError(RuntimeError):
    """Persisted content disagreed with the expectation; rolled back."""


@dataclass(frozen=True)
class ImportOutcome:
    shapefile_snapshot_id: int
    already_persisted: bool
    committed: bool
    checks: tuple[tuple[str, object, object], ...]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def observed_checks(
    connection: Connection, shapefile_snapshot_id: int, expected: ExpectedSnapshot
) -> tuple[tuple[str, object, object], ...]:
    """(name, expected, observed) for every verified property."""

    from app.forestry_reads import snapshot_summary, use_field_comparison

    summary = snapshot_summary(connection, shapefile_snapshot_id)
    comparison = use_field_comparison(connection, shapefile_snapshot_id)
    flags = {name: count for name, count in summary.quality_flag_counts.items() if count}

    return (
        ("family_fingerprint", expected.family_fingerprint, summary.family_fingerprint),
        ("layer_name", expected.layer_name, summary.layer_name),
        ("storage_srid", expected.storage_srid, summary.storage_srid),
        ("feature_count", expected.feature_count, summary.feature_count),
        ("total_sup_ha", expected.total_sup_ha, round(summary.total_sup_ha, 2)),
        (
            "total_geometry_area_source_units",
            expected.total_geometry_area_source_units,
            round(summary.total_geometry_area_source_units, 1),
        ),
        ("geometry_invalid_count", expected.geometry_invalid_count, summary.geometry_invalid_count),
        ("quality_flag_counts", expected.quality_flag_counts, flags),
        (
            "uso_2024_vs_uso_2026_changes",
            expected.uso_2024_vs_uso_2026_changes,
            len(comparison.uso_2024_vs_uso_2026),
        ),
        (
            "cod_uso_vs_cod_uso_2026_changes",
            expected.cod_uso_vs_cod_uso_2026_changes,
            len(comparison.cod_uso_vs_cod_uso_2026),
        ),
    )


def run_import(
    connection: Connection,
    *,
    source_root: Path,
    zip_relative_path: str,
    expected: ExpectedSnapshot,
    commit: bool,
) -> ImportOutcome:
    """Ingest, verify and commit (or roll back) inside one transaction.

    ``connection`` must not be inside a transaction yet.
    """

    from app.audit import record_audit_event
    from app.forestry_persistence import ingest_forestry_snapshot
    from app.forestry_reads import list_shapefile_snapshots

    archive = Path(source_root) / zip_relative_path
    if not archive.is_file():
        raise ImportRefusedError(f"archive not found: {zip_relative_path}")
    actual_sha256 = sha256_of(archive)
    if actual_sha256 != expected.zip_sha256:
        raise ImportRefusedError(
            f"archive SHA-256 {actual_sha256} is not the pinned {expected.zip_sha256}"
        )

    transaction = connection.begin()
    try:
        if not connection.execute(
            text("SELECT to_regclass('forestry.shapefile_snapshot')")
        ).scalar():
            raise ImportRefusedError(
                "forestry schema is missing; run `alembic upgrade head` on this database first"
            )
        others = [
            record
            for record in list_shapefile_snapshots(connection)
            if record.family_fingerprint != expected.family_fingerprint
        ]
        if others:
            raise ImportRefusedError(
                f"the database already holds {len(others)} other Forestry snapshot(s); "
                "this release shows the latest ingested one, so it refuses to add another"
            )

        result = ingest_forestry_snapshot(
            connection,
            source_root=Path(source_root),
            zip_relative_path=zip_relative_path,
            system_key=FORESTRY_SYSTEM_KEY,
        )
        checks = observed_checks(connection, result.shapefile_snapshot_id, expected)
        failed = [name for name, want, got in checks if want != got]
        if failed:
            raise VerificationFailedError(
                "verification failed for: " + ", ".join(failed) + "; rolled back"
            )

        if commit and not result.already_persisted:
            record_audit_event(
                connection,
                actor_app_user_id=None,
                event_type=IMPORTED_EVENT,
                product_key="forestry",
                subject_kind="forestry_snapshot",
                subject_id=str(result.shapefile_snapshot_id),
                metadata={
                    "via": "forestry_snapshot_import",
                    "family_fingerprint": expected.family_fingerprint,
                    "zip_sha256": expected.zip_sha256,
                    "feature_count": expected.feature_count,
                },
            )
    except BaseException:
        transaction.rollback()
        raise

    if commit:
        transaction.commit()
    else:
        transaction.rollback()

    return ImportOutcome(
        shapefile_snapshot_id=result.shapefile_snapshot_id,
        already_persisted=result.already_persisted,
        committed=commit,
        checks=checks,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--source-root",
        type=Path,
        default=os.environ.get("CAMPO_DIGITAL_SOURCE_ROOT"),
        help="Directory holding the Campo Digital source tree (read only). "
        "Defaults to $CAMPO_DIGITAL_SOURCE_ROOT.",
    )
    parser.add_argument(
        "--zip-relative-path",
        default=FORESTRY_SOURCE_ZIP,
        help="Archive path under --source-root (recorded as provenance).",
    )
    parser.add_argument(
        "--expect-host",
        required=True,
        help="Must equal POSTGRES_HOST; guards against importing into the wrong database.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Write the snapshot. Without it, everything is verified and rolled back.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    from app.config import get_settings
    from app.database import build_engine

    settings = get_settings()
    target = (
        f"{settings.postgres_user}@{settings.postgres_host}:{settings.postgres_port}"
        f"/{settings.postgres_db} (APP_ENV={settings.app_env})"
    )
    print(f"target database: {target}")

    if args.source_root is None:
        print("REFUSED: set --source-root or CAMPO_DIGITAL_SOURCE_ROOT", file=sys.stderr)
        return 2
    if settings.postgres_host != args.expect_host:
        print(
            f"REFUSED: POSTGRES_HOST is {settings.postgres_host!r}, "
            f"not the expected {args.expect_host!r}",
            file=sys.stderr,
        )
        return 2

    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            outcome = run_import(
                connection,
                source_root=args.source_root,
                zip_relative_path=args.zip_relative_path,
                expected=DEGENFELD_2026,
                commit=args.commit,
            )
    except ImportRefusedError as exc:
        print(f"REFUSED (nothing written): {exc}", file=sys.stderr)
        return 2
    except VerificationFailedError as exc:
        print(f"FAILED (nothing written): {exc}", file=sys.stderr)
        return 3
    finally:
        engine.dispose()

    for name, want, got in outcome.checks:
        print(f"  ok  {name}: {got}" if want == got else f"  !!  {name}: {got} != {want}")
    state = "already present" if outcome.already_persisted else "new"
    if outcome.committed:
        print(f"COMMITTED: snapshot id {outcome.shapefile_snapshot_id} ({state}), verified.")
    else:
        print(
            f"DRY RUN OK: snapshot would be id {outcome.shapefile_snapshot_id} ({state}); "
            "rolled back, nothing written. Re-run with --commit to write it."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
