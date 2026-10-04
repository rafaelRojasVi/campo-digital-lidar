"""The «Estado» read without a database.

``_closed_pmfs`` is what the 90 días hábiles route reuses to answer «no
aplica». The path guard keeps API paths and dashboard page paths apart:
``app.main`` mounts the Transelec router at ``/transelec`` as well as
``/api/transelec``, so a dashboard page sharing an API path would answer a
reload with JSON. That is why the page is ``/transelec/estado`` and the read
is ``/transelec/lifecycle`` (as the AEF page is ``seguimiento-aef``).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.routers.transelec import _closed_pmfs


def _row(source_row_number: int, pmf: str, estado_resumido: str, estado: str) -> Any:
    return SimpleNamespace(
        source_row_number=source_row_number,
        pmf=pmf,
        estado=estado,
        estado_resumido=estado_resumido,
        numero_ingreso="ING-1",
        numero_ingreso_2=None,
    )


def test_closed_pmfs_are_the_approved_descartado_and_desistido_ones() -> None:
    rows: list[Any] = [
        _row(1, "MP001", "Aprobado", "Aprobado"),
        _row(2, "MP002", "En tramite", "Rechazado"),
        _row(3, "MP003", "Descartado", "Descartado"),
        _row(4, "MP004", "Desistido", "Desistido"),
        _row(5, "MP005", "Tachado", "Tachado"),
        _row(6, "MP006", "Aprobado", "Recurso reposicion"),
    ]

    assert _closed_pmfs(rows) == frozenset({"MP001", "MP003", "MP004"})


def test_no_transelec_api_path_is_also_a_dashboard_page_path() -> None:
    from app.main import TRANSELEC_SPA_PAGE_PATHS, app

    # ``app.routes`` nests included routers; the OpenAPI schema lists every path.
    api_paths = {path.lstrip("/") for path in app.openapi()["paths"]}

    assert "api/transelec/lifecycle" in api_paths
    assert api_paths & TRANSELEC_SPA_PAGE_PATHS == set()
