"""Failure detail written to the audit ledger and the log must carry no row content.

``app.audit``'s contract is that callers never pass secrets or raw source
content in ``metadata``. A SQLAlchemy ``StatementError`` passed through
verbatim would violate it: its ``str()`` appends the failing statement and
its bound parameters, and for the Transelec projection those parameters are
every column value of the failing rows.
"""

from __future__ import annotations

from app.routers.transelec import _safe_failure_detail
from app.transelec_publication import ImportNotFoundError
from sqlalchemy.exc import DataError, IntegrityError

from transelec_ingestion.import_projection import (
    ImportInvariantError,
    ImportProjectionError,
)
from transelec_ingestion.xlsx_contract import TranselecWorkbookError

_ROW_VALUE = "PMF-CONFIDENCIAL-001"
_STATEMENT = "INSERT INTO platform.transelec_resumen_row (pmf, predio_group_key) VALUES (%s, %s)"
_PARAMETERS = [{"pmf": _ROW_VALUE, "predio_group_key": f"{_ROW_VALUE}-9-9"}]


class _Diagnostic:
    constraint_name = "ck_transelec_resumen_row_example"


class _OrigWithDiagnostic(Exception):
    diag = _Diagnostic()


def test_the_leak_this_guards_against_is_real() -> None:
    """Premise check: an unsanitized database error really does embed the
    projected row values in its own string representation."""

    exc = DataError(_STATEMENT, _PARAMETERS, Exception("value too long"))

    assert _ROW_VALUE in str(exc)
    assert "[parameters:" in str(exc)


def test_database_error_detail_excludes_statement_and_parameters() -> None:
    detail = _safe_failure_detail(DataError(_STATEMENT, _PARAMETERS, Exception("value too long")))

    assert _ROW_VALUE not in detail
    assert "parameters" not in detail
    assert "INSERT INTO" not in detail
    assert detail == "DataError"


def test_database_error_detail_keeps_the_violated_constraint_name() -> None:
    """Enough to diagnose the failure, nothing of the data behind it."""

    exc = IntegrityError(_STATEMENT, _PARAMETERS, _OrigWithDiagnostic("constraint violated"))

    detail = _safe_failure_detail(exc)

    assert detail == "IntegrityError: constraint ck_transelec_resumen_row_example"
    assert _ROW_VALUE not in detail


def test_an_unaudited_exception_type_is_reduced_to_its_name() -> None:
    """The allowlist must stay safe for exception types nobody has reviewed."""

    detail = _safe_failure_detail(RuntimeError(f"unexpected failure near {_ROW_VALUE}"))

    assert detail == "RuntimeError"
    assert _ROW_VALUE not in detail


def test_structural_contract_errors_keep_their_full_message() -> None:
    detail = _safe_failure_detail(
        TranselecWorkbookError("Resumen schema mismatch: positional=[(4, 'PMF', 'Otro')]")
    )

    assert detail == (
        "TranselecWorkbookError: Resumen schema mismatch: positional=[(4, 'PMF', 'Otro')]"
    )


def test_structural_invariant_and_publication_errors_keep_their_full_message() -> None:
    assert _safe_failure_detail(ImportInvariantError("business_rows persisted=3 expected=4")) == (
        "ImportInvariantError: business_rows persisted=3 expected=4"
    )
    assert _safe_failure_detail(ImportProjectionError("rows=[2, 5]")) == (
        "ImportProjectionError: rows=[2, 5]"
    )
    assert _safe_failure_detail(
        ImportNotFoundError("No committed transelec_import with id=7.")
    ) == ("ImportNotFoundError: No committed transelec_import with id=7.")
