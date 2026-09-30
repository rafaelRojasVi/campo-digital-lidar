"""Accept a Rodales shapefile ZIP from the dashboard as a *pending* snapshot.

The whole use case runs in the caller's transaction and never touches
``forestry.publication_state``: an upload can only add a snapshot, it can
never change what the dashboard serves. Publishing is a separate, explicit
action (``app.forestry_publication``).

Order matters for what an invalid upload leaves behind (nothing):

1. the ZIP directory and members are checked and one layer is extracted
   under server-chosen names (``forestry_ingestion.upload_archive``);
2. the family is validated against Source Contract V1, decoded, and its
   quality evidence computed (``parse_forestry_family``);
3. only then is the ZIP stored in the object store (the persistent volume in
   production), and provenance, the snapshot and the upload record written.

Rejections carry a stable ``reason`` and a Spanish message built from
structure (suffixes, record numbers, column names), never from cell values.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import Connection, text

from app.forestry_persistence import (
    ForestryIngestionError,
    parse_forestry_family,
    persist_parsed_family,
)
from app.forestry_publication import VersionStatus, version_status
from app.object_store import ObjectStore
from app.source_provenance import persist_uploaded_source_provenance
from forestry_ingestion.shapefile_contract import ForestryShapefileError
from forestry_ingestion.upload_archive import UploadArchiveError, extract_upload_archive

FORESTRY_UPLOAD_MEDIA_TYPE = "application/zip"


class ForestryUploadRejectedError(RuntimeError):
    """The upload cannot become a snapshot; nothing was written."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AcceptedUpload:
    """Outcome of one accepted upload."""

    status: Literal["uploaded", "already_uploaded"]
    shapefile_snapshot_id: int
    snapshot_upload_id: int
    source_snapshot_id: int
    content_sha256: str
    byte_size: int
    layer_name: str
    feature_count: int
    version_status: VersionStatus


_RECORD = re.compile(r"record (\d+)")
_DBF_FIELD = re.compile(r"\('([^']*)', '\w', \d+, \d+\)")
_FIELD_KEY = re.compile(r"in field '(\w+)'")


def describe_contract_failure(error: ForestryShapefileError) -> tuple[str, str]:
    """Map a Source Contract V1 failure to (reason, Spanish message).

    Contract messages are structural except one (an unparseable numeric
    value quotes the cell); nothing is copied from them except record
    numbers, DBF column names and field keys.
    """

    message = str(error)
    record = _RECORD.search(message)
    where = f" (registro {record.group(1)})" if record else ""

    if message.startswith("Declared CRS does not match"):
        return (
            "crs_mismatch",
            "El sistema de coordenadas del archivo .prj no es el esperado (WGS 84 / UTM zona 18S, "
            "EPSG:32718). Una capa en otro sistema necesita revisión antes de poder cargarse.",
        )
    if message.startswith("Unsupported source encoding declaration"):
        return "encoding", "La codificación declarada en el archivo .cpg no es UTF-8."
    if message.startswith("DBF schema mismatch"):
        unexpected, _, missing = message.partition("missing=")
        extra = sorted(set(_DBF_FIELD.findall(unexpected)))
        absent = sorted(set(_DBF_FIELD.findall(missing)))
        parts = []
        if absent:
            parts.append("faltan o cambiaron: " + ", ".join(absent))
        if extra:
            parts.append("no esperadas: " + ", ".join(extra))
        suffix = f" ({'; '.join(parts)})" if parts else ""
        return (
            "attribute_schema",
            f"Las columnas de atributos (.dbf) no coinciden con las esperadas{suffix}.",
        )
    if "null shape" in message:
        return "null_geometry", f"Hay un registro sin geometría{where}."
    if "shape type" in message:
        return "geometry_type", f"La capa no es de polígonos{where}."
    if "soft-deleted" in message:
        return (
            "deleted_record",
            f"El archivo .dbf contiene un registro marcado como borrado{where}.",
        )
    if "disagree" in message:
        return (
            "record_mismatch",
            "La cantidad de registros no coincide entre la geometría (.shp/.shx) y los "
            "atributos (.dbf).",
        )
    if message.startswith("Shapefile contains no features"):
        return "empty", "La capa no contiene polígonos."
    if message.startswith("Unparseable numeric value"):
        field_key = _FIELD_KEY.search(message)
        column = f" en la columna {field_key.group(1)}" if field_key else ""
        return "attribute_value", f"Hay un valor numérico que no se puede leer{column}."
    if "truncated" in message or "not a valid shapefile" in message or "length" in message:
        return "damaged", f"Un archivo de la capa está dañado o incompleto{where}."
    return "contract_violation", "La capa no cumple el contrato de origen de Rodales."


def accept_forestry_upload(
    connection: Connection,
    *,
    zip_path: Path,
    original_filename: str,
    store: ObjectStore,
    uploaded_by_app_user_id: int,
) -> AcceptedUpload:
    """Validate, store and record one uploaded ZIP as a pending snapshot."""

    with tempfile.TemporaryDirectory(prefix="forestry-upload-") as scratch:
        try:
            family = extract_upload_archive(zip_path, Path(scratch))
        except UploadArchiveError as error:
            raise ForestryUploadRejectedError(error.reason, str(error)) from error

        try:
            parsed = parse_forestry_family(family.shp_path, layer_name=family.layer_name)
        except ForestryShapefileError as error:
            reason, message = describe_contract_failure(error)
            raise ForestryUploadRejectedError(reason, message) from error
        except ForestryIngestionError as error:
            raise ForestryUploadRejectedError(
                "record_mismatch",
                "La geometría y los atributos de la capa no describen los mismos registros.",
            ) from error

    with zip_path.open("rb") as handle:
        stored = store.put(handle, media_type=FORESTRY_UPLOAD_MEDIA_TYPE)

    provenance = persist_uploaded_source_provenance(
        connection,
        content_sha256=stored.sha256,
        byte_size=stored.byte_size,
        object_storage_key=stored.key,
        original_filename=original_filename,
        media_type=FORESTRY_UPLOAD_MEDIA_TYPE,
    )

    try:
        with connection.begin_nested():
            snapshot_id, already_persisted = persist_parsed_family(
                connection, parsed, source_snapshot_id=provenance.source_snapshot_id
            )
    except ForestryIngestionError as error:
        raise ForestryUploadRejectedError(
            "conflicting_layer",
            "Ya existe una versión con el mismo contenido y otro nombre de capa.",
        ) from error

    upload_id = connection.execute(
        text(
            """
            INSERT INTO forestry.snapshot_upload (
                shapefile_snapshot_id, source_snapshot_id, uploaded_by_app_user_id,
                original_filename, byte_size, content_sha256
            )
            VALUES (:snapshot_id, :source_snapshot_id, :user_id, :filename, :byte_size, :sha256)
            RETURNING id
            """
        ),
        {
            "snapshot_id": snapshot_id,
            "source_snapshot_id": provenance.source_snapshot_id,
            "user_id": uploaded_by_app_user_id,
            "filename": original_filename,
            "byte_size": stored.byte_size,
            "sha256": stored.sha256,
        },
    ).scalar_one()

    return AcceptedUpload(
        status="already_uploaded" if already_persisted else "uploaded",
        shapefile_snapshot_id=snapshot_id,
        snapshot_upload_id=upload_id,
        source_snapshot_id=provenance.source_snapshot_id,
        content_sha256=stored.sha256,
        byte_size=stored.byte_size,
        layer_name=parsed.layer_name,
        feature_count=len(parsed.table.rows),
        version_status=version_status(connection, snapshot_id),
    )
