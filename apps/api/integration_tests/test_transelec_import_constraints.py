"""Database invariant tests for Transelec import/row/publish-event storage.

Exercises, directly against a real PostgreSQL instance, every CHECK and
UNIQUE constraint and every ON DELETE RESTRICT/CASCADE foreign-key behavior
declared in
`migrations/versions/0008_establish_transelec_import_rows_and_publish_events.py`.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError


def insert_source_system(connection: Connection, *, system_key: str) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO platform.source_system (system_key)
            VALUES (:system_key)
            RETURNING id
            """
        ),
        {"system_key": system_key},
    ).scalar_one()


def insert_source_asset(
    connection: Connection,
    source_system_id: int,
    *,
    identity_key: str,
    identity_kind: str = "relative_path",
) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO platform.source_asset (
                source_system_id, identity_kind, identity_key
            )
            VALUES (:source_system_id, :identity_kind, :identity_key)
            RETURNING id
            """
        ),
        {
            "source_system_id": source_system_id,
            "identity_kind": identity_kind,
            "identity_key": identity_key,
        },
    ).scalar_one()


def insert_source_snapshot(
    connection: Connection,
    source_asset_id: int,
    *,
    content_sha256: str,
    byte_size: int = 1,
) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO platform.source_snapshot (
                source_asset_id, content_sha256, byte_size
            )
            VALUES (:source_asset_id, :content_sha256, :byte_size)
            RETURNING id
            """
        ),
        {
            "source_asset_id": source_asset_id,
            "content_sha256": content_sha256,
            "byte_size": byte_size,
        },
    ).scalar_one()


def make_source_snapshot(connection: Connection, *, suffix: str) -> int:
    """Build a fresh source_system/source_asset/source_snapshot chain."""

    system_id = insert_source_system(connection, system_key=f"transelec_import_test_{suffix}")
    asset_id = insert_source_asset(
        connection,
        system_id,
        identity_key=f"PlanillaMaestra-{suffix}.xlsx",
    )
    digest = hashlib.sha256(suffix.encode("utf-8")).hexdigest()
    return insert_source_snapshot(connection, asset_id, content_sha256=digest)


def insert_ingestion_run(
    connection: Connection,
    source_snapshot_id: int,
    *,
    product_key: str = "transelect",
) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO platform.ingestion_run (source_snapshot_id, product_key)
            VALUES (:source_snapshot_id, :product_key)
            RETURNING id
            """
        ),
        {"source_snapshot_id": source_snapshot_id, "product_key": product_key},
    ).scalar_one()


def insert_app_user(connection: Connection, *, identity_key: str) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO platform.app_user (identity_kind, identity_key, display_name)
            VALUES ('dev-local', :identity_key, :identity_key)
            RETURNING id
            """
        ),
        {"identity_key": identity_key},
    ).scalar_one()


def insert_import(
    connection: Connection,
    *,
    suffix: str,
    source_snapshot_id: int | None = None,
    ingestion_run_id: int | None = None,
    validated_by_app_user_id: int | None = None,
    business_rows: int = 10,
    distinct_pmf: int = 2,
    distinct_provisional_predio_ids: int = 1,
    surface_total: float = 100.0,
) -> int:
    if source_snapshot_id is None:
        source_snapshot_id = make_source_snapshot(connection, suffix=suffix)
    if ingestion_run_id is None:
        ingestion_run_id = insert_ingestion_run(connection, source_snapshot_id)
    if validated_by_app_user_id is None:
        validated_by_app_user_id = insert_app_user(connection, identity_key=f"validator-{suffix}")

    return connection.execute(
        text(
            """
            INSERT INTO platform.transelec_import (
                source_snapshot_id, ingestion_run_id, schema_contract_version,
                parser_version, business_rows, distinct_pmf,
                distinct_provisional_predio_ids, surface_total,
                validated_by_app_user_id, validated_at
            )
            VALUES (
                :source_snapshot_id, :ingestion_run_id, 'transelec-resumen-v1',
                'xlsx_contract-v1', :business_rows, :distinct_pmf,
                :distinct_provisional_predio_ids, :surface_total,
                :validated_by_app_user_id, CURRENT_TIMESTAMP
            )
            RETURNING id
            """
        ),
        {
            "source_snapshot_id": source_snapshot_id,
            "ingestion_run_id": ingestion_run_id,
            "business_rows": business_rows,
            "distinct_pmf": distinct_pmf,
            "distinct_provisional_predio_ids": distinct_provisional_predio_ids,
            "surface_total": surface_total,
            "validated_by_app_user_id": validated_by_app_user_id,
        },
    ).scalar_one()


def insert_resumen_row(
    connection: Connection,
    import_id: int,
    *,
    source_row_number: int,
    pmf: str = "MP001",
    predio_group_key: str = "MP001-ROL1-1",
) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO platform.transelec_resumen_row (
                import_id, source_row_number, pmf, predio_group_key
            )
            VALUES (:import_id, :source_row_number, :pmf, :predio_group_key)
            RETURNING id
            """
        ),
        {
            "import_id": import_id,
            "source_row_number": source_row_number,
            "pmf": pmf,
            "predio_group_key": predio_group_key,
        },
    ).scalar_one()


def insert_publish_event(
    connection: Connection,
    *,
    import_id: int,
    actor_user_id: int,
    event_type: str = "publish",
) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO platform.transelec_publish_event (
                import_id, event_type, actor_user_id
            )
            VALUES (:import_id, :event_type, :actor_user_id)
            RETURNING id
            """
        ),
        {
            "import_id": import_id,
            "event_type": event_type,
            "actor_user_id": actor_user_id,
        },
    ).scalar_one()


def expect_integrity_error(
    connection: Connection,
    sql: str,
    parameters: dict[str, Any],
) -> None:
    """Prove a DB invariant without aborting the outer test transaction."""

    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(text(sql), parameters)


# --- transelec_import: UNIQUE(source_snapshot_id) -----------------------------


def test_import_is_unique_per_source_snapshot(integration_connection: Connection) -> None:
    snapshot_id = make_source_snapshot(integration_connection, suffix="uniq1")
    insert_import(integration_connection, suffix="uniq1", source_snapshot_id=snapshot_id)

    other_run_id = insert_ingestion_run(integration_connection, snapshot_id)
    other_user_id = insert_app_user(integration_connection, identity_key="validator-uniq1-second")

    expect_integrity_error(
        integration_connection,
        """
        INSERT INTO platform.transelec_import (
            source_snapshot_id, ingestion_run_id, schema_contract_version,
            parser_version, business_rows, distinct_pmf,
            distinct_provisional_predio_ids, surface_total,
            validated_by_app_user_id, validated_at
        )
        VALUES (
            :source_snapshot_id, :ingestion_run_id, 'transelec-resumen-v1',
            'xlsx_contract-v1', 5, 1, 0, 10.0, :validated_by_app_user_id,
            CURRENT_TIMESTAMP
        )
        """,
        {
            "source_snapshot_id": snapshot_id,
            "ingestion_run_id": other_run_id,
            "validated_by_app_user_id": other_user_id,
        },
    )


# --- transelec_import: CHECK constraints --------------------------------------


def test_import_rejects_non_positive_business_rows(integration_connection: Connection) -> None:
    for business_rows in (0, -1):
        snapshot_id = make_source_snapshot(integration_connection, suffix=f"biz{business_rows}")
        run_id = insert_ingestion_run(integration_connection, snapshot_id)
        user_id = insert_app_user(integration_connection, identity_key=f"biz-{business_rows}")

        expect_integrity_error(
            integration_connection,
            """
            INSERT INTO platform.transelec_import (
                source_snapshot_id, ingestion_run_id, schema_contract_version,
                parser_version, business_rows, distinct_pmf,
                distinct_provisional_predio_ids, surface_total,
                validated_by_app_user_id, validated_at
            )
            VALUES (
                :source_snapshot_id, :run_id, 'transelec-resumen-v1',
                'xlsx_contract-v1', :business_rows, 1, 0, 10.0, :user_id,
                CURRENT_TIMESTAMP
            )
            """,
            {
                "source_snapshot_id": snapshot_id,
                "run_id": run_id,
                "business_rows": business_rows,
                "user_id": user_id,
            },
        )


def test_import_rejects_non_positive_distinct_pmf(integration_connection: Connection) -> None:
    for distinct_pmf in (0, -1):
        snapshot_id = make_source_snapshot(integration_connection, suffix=f"pmf{distinct_pmf}")
        run_id = insert_ingestion_run(integration_connection, snapshot_id)
        user_id = insert_app_user(integration_connection, identity_key=f"pmf-{distinct_pmf}")

        expect_integrity_error(
            integration_connection,
            """
            INSERT INTO platform.transelec_import (
                source_snapshot_id, ingestion_run_id, schema_contract_version,
                parser_version, business_rows, distinct_pmf,
                distinct_provisional_predio_ids, surface_total,
                validated_by_app_user_id, validated_at
            )
            VALUES (
                :source_snapshot_id, :run_id, 'transelec-resumen-v1',
                'xlsx_contract-v1', 5, :distinct_pmf, 0, 10.0, :user_id,
                CURRENT_TIMESTAMP
            )
            """,
            {
                "source_snapshot_id": snapshot_id,
                "run_id": run_id,
                "distinct_pmf": distinct_pmf,
                "user_id": user_id,
            },
        )


def test_import_rejects_negative_predio_count(integration_connection: Connection) -> None:
    snapshot_id = make_source_snapshot(integration_connection, suffix="predio-neg")
    run_id = insert_ingestion_run(integration_connection, snapshot_id)
    user_id = insert_app_user(integration_connection, identity_key="predio-neg")

    expect_integrity_error(
        integration_connection,
        """
        INSERT INTO platform.transelec_import (
            source_snapshot_id, ingestion_run_id, schema_contract_version,
            parser_version, business_rows, distinct_pmf,
            distinct_provisional_predio_ids, surface_total,
            validated_by_app_user_id, validated_at
        )
        VALUES (
            :source_snapshot_id, :run_id, 'transelec-resumen-v1',
            'xlsx_contract-v1', 5, 1, -1, 10.0, :user_id, CURRENT_TIMESTAMP
        )
        """,
        {"source_snapshot_id": snapshot_id, "run_id": run_id, "user_id": user_id},
    )


def test_import_allows_zero_predio_count(integration_connection: Connection) -> None:
    """distinct_provisional_predio_ids >= 0 -- zero itself must be legal."""

    import_id = insert_import(
        integration_connection,
        suffix="predio-zero",
        distinct_provisional_predio_ids=0,
    )
    assert import_id > 0


# --- transelec_resumen_row: UNIQUE(import_id, source_row_number) -------------


def test_resumen_row_is_unique_per_import_and_source_row_number(
    integration_connection: Connection,
) -> None:
    import_id = insert_import(integration_connection, suffix="row-uniq")
    insert_resumen_row(integration_connection, import_id, source_row_number=1)

    expect_integrity_error(
        integration_connection,
        """
        INSERT INTO platform.transelec_resumen_row (
            import_id, source_row_number, pmf, predio_group_key
        )
        VALUES (:import_id, 1, 'MP002', 'MP002-ROL2-1')
        """,
        {"import_id": import_id},
    )

    # A different source_row_number for the same import is unaffected.
    second_row_id = insert_resumen_row(integration_connection, import_id, source_row_number=2)
    assert second_row_id > 0


def test_resumen_row_requires_pmf_and_predio_group_key(
    integration_connection: Connection,
) -> None:
    import_id = insert_import(integration_connection, suffix="row-notnull")

    expect_integrity_error(
        integration_connection,
        """
        INSERT INTO platform.transelec_resumen_row (
            import_id, source_row_number, pmf, predio_group_key
        )
        VALUES (:import_id, 1, NULL, 'MP001-ROL1-1')
        """,
        {"import_id": import_id},
    )

    expect_integrity_error(
        integration_connection,
        """
        INSERT INTO platform.transelec_resumen_row (
            import_id, source_row_number, pmf, predio_group_key
        )
        VALUES (:import_id, 1, 'MP001', NULL)
        """,
        {"import_id": import_id},
    )


def test_resumen_row_allows_null_id_predio_unico(integration_connection: Connection) -> None:
    """A blank ID_Predio_Unico is a real, expected case -- must stay legal."""

    import_id = insert_import(integration_connection, suffix="row-null-idpu")

    row_id = integration_connection.execute(
        text(
            """
            INSERT INTO platform.transelec_resumen_row (
                import_id, source_row_number, pmf, predio_group_key, id_predio_unico
            )
            VALUES (:import_id, 1, 'MP001', 'MP001-ROL1-1', NULL)
            RETURNING id
            """
        ),
        {"import_id": import_id},
    ).scalar_one()
    assert row_id > 0


# --- transelec_publish_event: CHECK(event_type IN (...)) --------------------


def test_publish_event_rejects_unknown_event_type(integration_connection: Connection) -> None:
    import_id = insert_import(integration_connection, suffix="event-bad")
    user_id = insert_app_user(integration_connection, identity_key="actor-event-bad")

    expect_integrity_error(
        integration_connection,
        """
        INSERT INTO platform.transelec_publish_event (
            import_id, event_type, actor_user_id
        )
        VALUES (:import_id, 'archive', :actor_user_id)
        """,
        {"import_id": import_id, "actor_user_id": user_id},
    )


@pytest.mark.parametrize("event_type", ["publish", "restore"])
def test_publish_event_accepts_known_event_types(
    integration_connection: Connection, event_type: str
) -> None:
    import_id = insert_import(integration_connection, suffix=f"event-{event_type}")
    user_id = insert_app_user(integration_connection, identity_key=f"actor-{event_type}")

    event_id = insert_publish_event(
        integration_connection,
        import_id=import_id,
        actor_user_id=user_id,
        event_type=event_type,
    )
    assert event_id > 0


# --- ON DELETE CASCADE: transelec_resumen_row -> transelec_import -----------


def test_deleting_import_cascades_to_resumen_rows(integration_connection: Connection) -> None:
    import_id = insert_import(integration_connection, suffix="cascade")
    insert_resumen_row(integration_connection, import_id, source_row_number=1)
    insert_resumen_row(integration_connection, import_id, source_row_number=2)

    integration_connection.execute(
        text("DELETE FROM platform.transelec_import WHERE id = :id"),
        {"id": import_id},
    )

    remaining = integration_connection.execute(
        text("SELECT count(*) FROM platform.transelec_resumen_row WHERE import_id = :id"),
        {"id": import_id},
    ).scalar_one()
    assert remaining == 0


# --- ON DELETE RESTRICT: parents of transelec_import ------------------------


def test_import_parent_deletes_are_restricted(integration_connection: Connection) -> None:
    snapshot_id = make_source_snapshot(integration_connection, suffix="restrict-parents")
    run_id = insert_ingestion_run(integration_connection, snapshot_id)
    user_id = insert_app_user(integration_connection, identity_key="restrict-parents")
    insert_import(
        integration_connection,
        suffix="restrict-parents",
        source_snapshot_id=snapshot_id,
        ingestion_run_id=run_id,
        validated_by_app_user_id=user_id,
    )

    expect_integrity_error(
        integration_connection,
        "DELETE FROM platform.source_snapshot WHERE id = :id",
        {"id": snapshot_id},
    )
    expect_integrity_error(
        integration_connection,
        "DELETE FROM platform.ingestion_run WHERE id = :id",
        {"id": run_id},
    )
    expect_integrity_error(
        integration_connection,
        "DELETE FROM platform.app_user WHERE id = :id",
        {"id": user_id},
    )


# --- ON DELETE RESTRICT: transelec_publish_event's parents ------------------


def test_publish_event_restricts_import_delete(integration_connection: Connection) -> None:
    import_id = insert_import(integration_connection, suffix="restrict-publish-import")
    user_id = insert_app_user(integration_connection, identity_key="restrict-publish-import")
    insert_publish_event(integration_connection, import_id=import_id, actor_user_id=user_id)

    expect_integrity_error(
        integration_connection,
        "DELETE FROM platform.transelec_import WHERE id = :id",
        {"id": import_id},
    )


def test_publish_event_restricts_actor_user_delete(integration_connection: Connection) -> None:
    import_id = insert_import(integration_connection, suffix="restrict-publish-actor")
    user_id = insert_app_user(integration_connection, identity_key="restrict-publish-actor")
    insert_publish_event(integration_connection, import_id=import_id, actor_user_id=user_id)

    expect_integrity_error(
        integration_connection,
        "DELETE FROM platform.app_user WHERE id = :id",
        {"id": user_id},
    )


# --- ON DELETE RESTRICT: transelec_dashboard_state.active_import_id --------


def test_dashboard_state_active_import_restricts_import_delete(
    integration_connection: Connection,
) -> None:
    import_id = insert_import(integration_connection, suffix="restrict-dashboard")

    integration_connection.execute(
        text(
            """
            UPDATE platform.transelec_dashboard_state
            SET active_import_id = :import_id
            WHERE id = 1
            """
        ),
        {"import_id": import_id},
    )

    expect_integrity_error(
        integration_connection,
        "DELETE FROM platform.transelec_import WHERE id = :id",
        {"id": import_id},
    )
