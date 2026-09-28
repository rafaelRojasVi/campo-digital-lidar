"""Physical schema tests for Transelec import/row/publish-event storage.

`platform.transelec_import` must exist with the shape (§2 "Data model") that
"Task 3" (row projection) and later dashboard tasks depend on. See
`migrations/versions/0008_establish_transelec_import_rows_and_publish_events.py`.
"""

from __future__ import annotations

from sqlalchemy import Engine, inspect

EXPECTED_TRANSELEC_IMPORT_COLUMNS = {
    "id",
    "source_snapshot_id",
    "ingestion_run_id",
    "schema_contract_version",
    "parser_version",
    "business_rows",
    "distinct_pmf",
    "distinct_provisional_predio_ids",
    "surface_total",
    "validated_by_app_user_id",
    "validated_at",
    "created_at",
    # 0009: contract V2's persisted layout report.
    "mapping_report",
    "warning_count",
}

EXPECTED_TRANSELEC_RESUMEN_ROW_COLUMNS = {
    "id",
    "import_id",
    "source_row_number",
    "predio_ref",
    "rol_ref",
    "area_ref",
    "pmf",
    "carpeta_source",
    "carpeta_normalizada",
    "pas",
    "estado",
    "estado_resumido",
    "tipo_rechazo",
    "reingreso_tec",
    "reingreso_legal",
    "reingreso_recrep",
    "tipo_propietario",
    "id_transelec",
    "rol",
    "numero_predio",
    "numero_area_corta",
    "superficie_corta",
    "superficie_total_corta",
    "fecha_ingreso",
    "numero_ingreso",
    "fecha_90_dias",
    "hoy_raw",
    "empresa",
    "id_predio_unico_ii",
    "id_pmf",
    "id_predio_unico",
    "predio_group_key",
    "tramite",
    "sector",
    # 0009: contract V2's AEF tracking block.
    "aef",
    "quien_solicita",
    "fecha_solicitud",
    "fecha_corta",
    "fecha_termino",
    # 0009: raw text found in date columns, with its classification.
    "source_text_dates",
}

EXPECTED_TRANSELEC_PUBLISH_EVENT_COLUMNS = {
    "id",
    "import_id",
    "event_type",
    "actor_user_id",
    "occurred_at",
}


def test_new_transelec_tables_exist(integration_engine: Engine) -> None:
    inspector = inspect(integration_engine)
    tables = set(inspector.get_table_names(schema="platform"))

    assert tables >= {
        "transelec_import",
        "transelec_resumen_row",
        "transelec_publish_event",
    }


def test_transelec_import_has_expected_columns(integration_engine: Engine) -> None:
    inspector = inspect(integration_engine)
    columns = {
        column["name"] for column in inspector.get_columns("transelec_import", schema="platform")
    }

    assert columns == EXPECTED_TRANSELEC_IMPORT_COLUMNS


def test_transelec_resumen_row_has_expected_columns(integration_engine: Engine) -> None:
    inspector = inspect(integration_engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("transelec_resumen_row", schema="platform")
    }

    assert columns == EXPECTED_TRANSELEC_RESUMEN_ROW_COLUMNS


def test_transelec_publish_event_has_expected_columns(integration_engine: Engine) -> None:
    inspector = inspect(integration_engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("transelec_publish_event", schema="platform")
    }

    assert columns == EXPECTED_TRANSELEC_PUBLISH_EVENT_COLUMNS


def test_transelec_resumen_row_source_row_number_is_not_nullable(
    integration_engine: Engine,
) -> None:
    inspector = inspect(integration_engine)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("transelec_resumen_row", schema="platform")
    }

    assert columns["pmf"]["nullable"] is False
    assert columns["predio_group_key"]["nullable"] is False
    assert columns["id_predio_unico"]["nullable"] is True
    assert columns["source_row_number"]["nullable"] is False


def test_dashboard_state_gains_active_import_id_without_losing_active_snapshot_id(
    integration_engine: Engine,
) -> None:
    """Expand-only: the new pointer column arrives; 0004's column stays put."""

    inspector = inspect(integration_engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("transelec_dashboard_state", schema="platform")
    }

    assert "active_import_id" in columns
    assert "active_source_snapshot_id" in columns


def test_transelec_resumen_row_indexes_exist(integration_engine: Engine) -> None:
    inspector = inspect(integration_engine)
    indexes = {
        index["name"]: set(index["column_names"])
        for index in inspector.get_indexes("transelec_resumen_row", schema="platform")
    }

    assert indexes["ix_transelec_resumen_row_import_pmf"] == {"import_id", "pmf"}
    assert indexes["ix_transelec_resumen_row_import_predio"] == {
        "import_id",
        "predio_group_key",
    }
    assert indexes["ix_transelec_resumen_row_import_estado_resumido"] == {
        "import_id",
        "estado_resumido",
    }
    assert indexes["ix_transelec_resumen_row_import_sector"] == {"import_id", "sector"}
    assert indexes["ix_transelec_resumen_row_import_empresa"] == {"import_id", "empresa"}
    assert indexes["ix_transelec_resumen_row_import_pas"] == {"import_id", "pas"}
    assert indexes["ix_transelec_resumen_row_import_tipo_propietario"] == {
        "import_id",
        "tipo_propietario",
    }


def test_transelec_import_foreign_keys_are_restrictive(integration_engine: Engine) -> None:
    inspector = inspect(integration_engine)
    foreign_keys = inspector.get_foreign_keys("transelec_import", schema="platform")

    expected = {
        "source_snapshot_id": "source_snapshot",
        "ingestion_run_id": "ingestion_run",
        "validated_by_app_user_id": "app_user",
    }

    for column_name, referred_table in expected.items():
        matching = [
            foreign_key
            for foreign_key in foreign_keys
            if foreign_key["constrained_columns"] == [column_name]
        ]
        assert len(matching) == 1, f"expected exactly one FK on {column_name}"

        foreign_key = matching[0]
        assert foreign_key["referred_schema"] == "platform"
        assert foreign_key["referred_table"] == referred_table
        assert foreign_key["options"].get("ondelete") == "RESTRICT"


def test_transelec_resumen_row_import_fk_cascades(integration_engine: Engine) -> None:
    inspector = inspect(integration_engine)
    foreign_keys = inspector.get_foreign_keys("transelec_resumen_row", schema="platform")

    matching = [fk for fk in foreign_keys if fk["constrained_columns"] == ["import_id"]]
    assert len(matching) == 1

    foreign_key = matching[0]
    assert foreign_key["referred_schema"] == "platform"
    assert foreign_key["referred_table"] == "transelec_import"
    assert foreign_key["options"].get("ondelete") == "CASCADE"


def test_transelec_publish_event_foreign_keys_are_restrictive(
    integration_engine: Engine,
) -> None:
    inspector = inspect(integration_engine)
    foreign_keys = inspector.get_foreign_keys("transelec_publish_event", schema="platform")

    expected = {
        "import_id": "transelec_import",
        "actor_user_id": "app_user",
    }

    for column_name, referred_table in expected.items():
        matching = [
            foreign_key
            for foreign_key in foreign_keys
            if foreign_key["constrained_columns"] == [column_name]
        ]
        assert len(matching) == 1, f"expected exactly one FK on {column_name}"

        foreign_key = matching[0]
        assert foreign_key["referred_schema"] == "platform"
        assert foreign_key["referred_table"] == referred_table
        assert foreign_key["options"].get("ondelete") == "RESTRICT"


def test_dashboard_state_active_import_fk_is_restrictive(integration_engine: Engine) -> None:
    inspector = inspect(integration_engine)
    foreign_keys = inspector.get_foreign_keys("transelec_dashboard_state", schema="platform")

    matching = [fk for fk in foreign_keys if fk["constrained_columns"] == ["active_import_id"]]
    assert len(matching) == 1

    foreign_key = matching[0]
    assert foreign_key["referred_schema"] == "platform"
    assert foreign_key["referred_table"] == "transelec_import"
    assert foreign_key["options"].get("ondelete") == "RESTRICT"
