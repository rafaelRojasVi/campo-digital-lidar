# ruff: noqa: E501 - hand-rolled OOXML fixture XML has long attribute lines
"""Full worker loop: enqueue -> run_one_job -> artifact recorded."""

from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from pathlib import Path

from app.jobs import enqueue_processing_job
from app.object_store import LocalObjectStore
from app.worker import run_one_job
from sqlalchemy import Engine, text

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""
_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""
_WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Resumen" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""
_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""
_SHEET1_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>placeholder</t></is></c></row>
  </sheetData>
</worksheet>
"""


def _make_minimal_workbook(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("xl/workbook.xml", _WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet1.xml", _SHEET1_XML)
    return path


def test_worker_end_to_end_produces_artifact(integration_engine: Engine, tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "object-store")
    workbook_path = _make_minimal_workbook(tmp_path / "wb.xlsx")

    with workbook_path.open("rb") as handle:
        stored = store.put(
            handle,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with integration_engine.connect() as setup_conn:
        system_id = setup_conn.execute(
            text(
                "INSERT INTO platform.source_system (system_key) VALUES ('worker_e2e_test') RETURNING id"
            )
        ).scalar_one()
        asset_id = setup_conn.execute(
            text(
                "INSERT INTO platform.source_asset (source_system_id, identity_kind, identity_key) "
                "VALUES (:sid, 'relative_path', 'e2e.xlsx') RETURNING id"
            ),
            {"sid": system_id},
        ).scalar_one()
        snapshot_id = setup_conn.execute(
            text(
                "INSERT INTO platform.source_snapshot (source_asset_id, content_sha256, byte_size, object_storage_key) "
                "VALUES (:aid, :sha, :size, :key) RETURNING id"
            ),
            {"aid": asset_id, "sha": stored.sha256, "size": stored.byte_size, "key": stored.key},
        ).scalar_one()
        run_id = setup_conn.execute(
            text(
                "INSERT INTO platform.ingestion_run (source_snapshot_id, product_key) "
                "VALUES (:sid, 'transelect') RETURNING id"
            ),
            {"sid": snapshot_id},
        ).scalar_one()
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="transelect",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    try:
        with integration_engine.connect() as worker_conn:
            did_work = run_one_job(worker_conn, store, worker_id="e2e-worker")
        assert did_work is True

        with integration_engine.connect() as check_conn:
            job_row = check_conn.execute(
                text("SELECT status FROM platform.processing_job WHERE id = :id"), {"id": job_id}
            ).one()
            assert job_row.status == "succeeded"

            attempt_row = check_conn.execute(
                text(
                    "SELECT status FROM platform.processing_attempt WHERE processing_job_id = :id"
                ),
                {"id": job_id},
            ).one()
            assert attempt_row.status == "succeeded"

            artifact_row = check_conn.execute(
                text(
                    "SELECT storage_key, artifact_kind FROM platform.generated_artifact "
                    "WHERE processing_job_id = :id"
                ),
                {"id": job_id},
            ).one()
            assert artifact_row.artifact_kind == "inspection_report"

        with store.open(artifact_row.storage_key) as artifact_handle:
            evidence = json.loads(artifact_handle.read())
        assert "Resumen" in evidence["sheet_names"]
    finally:
        with integration_engine.connect() as cleanup_conn:
            cleanup_conn.execute(
                text("DELETE FROM platform.generated_artifact WHERE processing_job_id = :id"),
                {"id": job_id},
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.processing_attempt WHERE processing_job_id = :id"),
                {"id": job_id},
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.processing_job WHERE id = :id"), {"id": job_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.ingestion_run WHERE id = :id"), {"id": run_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.source_snapshot WHERE id = :id"), {"id": snapshot_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.source_asset WHERE id = :id"), {"id": asset_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.source_system WHERE id = :id"), {"id": system_id}
            )
            cleanup_conn.commit()


def test_missing_object_fails_job_terminally_without_retry(
    integration_engine: Engine, tmp_path: Path
) -> None:
    """A source_snapshot.object_storage_key that no longer resolves — Render's
    free-tier filesystem is ephemeral and cycles on redeploy/spin-down/wake —
    must fail the job on its very first claim with a distinct, visible error,
    never a silent crash or a retry that would just repeat the same failure.
    """

    store = LocalObjectStore(tmp_path / "object-store")
    digest = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    # A well-formed key that is never store.put() into this fresh store —
    # simulates the object having existed at upload time and since vanished.
    never_stored_key = f"sha256/{digest[:2]}/{digest[2:]}"

    with integration_engine.connect() as setup_conn:
        system_id = setup_conn.execute(
            text(
                "INSERT INTO platform.source_system (system_key) VALUES ('worker_e2e_missing_object') "
                "RETURNING id"
            )
        ).scalar_one()
        asset_id = setup_conn.execute(
            text(
                "INSERT INTO platform.source_asset (source_system_id, identity_kind, identity_key) "
                "VALUES (:sid, 'relative_path', 'missing.xlsx') RETURNING id"
            ),
            {"sid": system_id},
        ).scalar_one()
        snapshot_id = setup_conn.execute(
            text(
                "INSERT INTO platform.source_snapshot "
                "(source_asset_id, content_sha256, byte_size, object_storage_key) "
                "VALUES (:aid, :sha, 5, :key) RETURNING id"
            ),
            {"aid": asset_id, "sha": digest, "key": never_stored_key},
        ).scalar_one()
        run_id = setup_conn.execute(
            text(
                "INSERT INTO platform.ingestion_run (source_snapshot_id, product_key) "
                "VALUES (:sid, 'transelect') RETURNING id"
            ),
            {"sid": snapshot_id},
        ).scalar_one()
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="transelect",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    try:
        with integration_engine.connect() as worker_conn:
            did_work = run_one_job(worker_conn, store, worker_id="e2e-worker-missing-object")
        assert did_work is True

        with integration_engine.connect() as check_conn:
            job_row = check_conn.execute(
                text(
                    "SELECT status, error_summary, attempt_count FROM platform.processing_job "
                    "WHERE id = :id"
                ),
                {"id": job_id},
            ).one()
            assert job_row.status == "failed"
            assert job_row.error_summary == "source object unavailable (ephemeral storage cycled)"
            # Claimed exactly once and failed terminally on that same attempt
            # -- fail_job_terminal bypasses the attempt-count-based requeue
            # that fail_job() would otherwise apply.
            assert job_row.attempt_count == 1

            attempt_row = check_conn.execute(
                text(
                    "SELECT status, error_summary FROM platform.processing_attempt "
                    "WHERE processing_job_id = :id"
                ),
                {"id": job_id},
            ).one()
            assert attempt_row.status == "failed"
            assert (
                attempt_row.error_summary == "source object unavailable (ephemeral storage cycled)"
            )
    finally:
        with integration_engine.connect() as cleanup_conn:
            cleanup_conn.execute(
                text("DELETE FROM platform.processing_attempt WHERE processing_job_id = :id"),
                {"id": job_id},
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.processing_job WHERE id = :id"), {"id": job_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.ingestion_run WHERE id = :id"), {"id": run_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.source_snapshot WHERE id = :id"), {"id": snapshot_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.source_asset WHERE id = :id"), {"id": asset_id}
            )
            cleanup_conn.execute(
                text("DELETE FROM platform.source_system WHERE id = :id"), {"id": system_id}
            )
            cleanup_conn.commit()
