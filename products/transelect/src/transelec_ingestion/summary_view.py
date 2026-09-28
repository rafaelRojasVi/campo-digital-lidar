"""Pure KPI/chart/status-hero aggregation behind ``GET /transelec/summary``.

Implements TR-FUNC-001-012 and TR-FUNC-014-016 from one already-filtered set
of ``transelec_resumen_row`` rows, so a single filter state can never make
the KPI row, the two donut charts, and the status hero disagree (TR-FUNC-017's
acceptance test) — every number here is derived from the exact same input
list, mirroring the source HTML's single shared in-memory ``view``.

TR-FUNC-013 (owner-status table) is deliberately NOT computed here: it is
predio-grain but keyed by ``Tipo de propietario`` too, and lives in its own
module (``owner_status_view``) behind its own endpoint, per the design doc.

No canonical PMF/predio status rollup is invented anywhere in this module —
every status-dependent number is computed via one of the three explicitly
named, evidenced legacy bases in ``status_rollups``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from transelec_ingestion.status_rollups import (
    RolledRow,
    bucket_3way,
    estado_resumido_conflicts,
    estado_resumido_first_row,
    first_row_wins,
    hero_state,
    normalized_label,
    pending_priority_legacy,
)

_STATIC_NUMERO_RESOLUCION = "No disponible"  # TR-FUNC-016: the field does not exist in the source.

# There is no owner field in the source contract at all. ``Tipo de
# propietario`` is a tenure *category* (``Servidumbre firmada``, ``Poseedor``,
# ``BNUP``, concession variants) shared by hundreds of rows, and the surnames
# embedded in ``Predio Ref`` are free text inside a label that sometimes names
# several properties at once. Neither identifies an owner, so no owner count
# is computed anywhere — this literal is what the API returns in its place,
# the same way TR-FUNC-016 reports an absent resolution-number field.
_OWNER_IDENTITY_UNAVAILABLE = "No disponible en el origen"

# ``Predio Ref``'s one literal "this row has no reforestation" marker. Matched
# on the normalized label, so an accented or differently-cased spelling of the
# same sentinel in a future import is still excluded.
_REFORESTACION_SENTINEL_LABEL = "Sin reforestacion"
_REFORESTACION_SENTINELS = frozenset({normalized_label(_REFORESTACION_SENTINEL_LABEL)})

# A ``Predio Ref`` label naming more than one property, as far as an explicit
# separator can tell. A lower bound, not a count: ``Ref003 Ref004_ Nawrath``
# names two properties with no separator at all, so this heuristic misses it.
_COMPOSITE_LABEL = re.compile(r"\s\+\s|\s+y\s+|/")

REFORESTACION_DEFINICION = (
    "Valores distintos y no vacíos de «Predio Ref», excluyendo el literal "
    "«Sin reforestacion». Es un conteo de etiquetas de origen, no de predios "
    "identificados: «Predio Ref» no es un identificador y algunas etiquetas "
    "nombran más de un predio."
)


@dataclass(frozen=True, slots=True)
class SummaryInputRow:
    """One filtered ``transelec_resumen_row``, projected for summary math."""

    source_row_number: int
    pmf: str
    predio_group_key: str
    estado: str | None
    estado_resumido: str | None
    numero_ingreso: str | None
    tipo_propietario: str | None
    predio_ref: str | None
    id_predio_unico: str | None
    superficie_corta: float | None
    rol: str | None
    empresa: str | None = None
    rol_ref: str | None = None

    def _as_rolled_row(self) -> RolledRow:
        return RolledRow(
            source_row_number=self.source_row_number,
            pmf=self.pmf,
            predio_group_key=self.predio_group_key,
            estado=self.estado,
            estado_resumido=self.estado_resumido,
            numero_ingreso=self.numero_ingreso,
            tipo_propietario=self.tipo_propietario,
        )


@dataclass(frozen=True, slots=True)
class Bucket3WayCounts:
    aprobado: int
    en_tramite: int
    pendiente_o_tachado: int


@dataclass(frozen=True, slots=True)
class HeroStateCounts:
    aprobado: int
    en_tramite: int
    pendiente: int
    tachado: int
    sin_estado: int


@dataclass(frozen=True, slots=True)
class LabelledCount:
    """One row of a breakdown: the raw source spelling, and how many.

    ``label`` is the first spelling the source used for this state — never a
    normalized or prettified rewrite. ``normalized`` is the key the fold
    grouped on, exposed so a caller can reconcile two labels that merged.
    """

    label: str | None
    normalized: str | None
    count: int


@dataclass(frozen=True, slots=True)
class EmpresaBreakdown:
    """One company's PMF-grain slice of the headline.

    ``pmf_count`` is the number of distinct PMFs whose first source row
    names this company, so the companies partition the PMF population
    exactly and their subtotals reconcile to the overall total by
    construction rather than by coincidence.
    """

    empresa: str | None
    pmf_count: int
    estado_resumido: HeroStateCounts


@dataclass(frozen=True, slots=True)
class EstadoResumidoConflict:
    """One PMF carrying more than one ``Estado resumido`` in the source."""

    pmf: str
    valores: list[str | None]
    canonico: str | None
    estado_detalle: str | None
    source_row_number: int


@dataclass(frozen=True, slots=True)
class ReforestacionResult:
    """Everything the source can actually support about reforestation.

    Deliberately short of what was asked for. Marianne asked how many
    reforestation *properties* and how many reforestation *owners* there
    are; the workbook answers neither. It carries three reforestation
    columns — ``Predio Ref``, ``Rol Ref``, ``N° Area de Ref`` — none of
    which is an identifier, and no owner column at all. So this reports
    label counts under their exact definition, names the sentinel it
    excluded, lists the labels that visibly name more than one property,
    and returns a literal rather than a number where the owner count would
    go.
    """

    definicion: str
    predio_ref_labels: list[str]
    predio_ref_count: int
    rol_ref_count: int
    sentinel_label: str
    sentinel_row_count: int
    etiquetas_compuestas: list[str]
    propietarios: str


@dataclass(frozen=True, slots=True)
class SummaryResult:
    row_count: int

    # KPIs — TR-FUNC-001-008
    pmf_count: int
    predio_count: int
    rol_count: int
    surface_total: float
    basis_estado_resumido: str
    aprobados_pmf_count: int
    en_tramite_pmf_count: int
    basis_pending_priority: str
    pendientes_prioritarios_pmf_count: int
    con_servidumbre_predio_count: int

    # Charts — TR-FUNC-009/010
    avance_por_predio: Bucket3WayCounts
    avance_por_pmf: Bucket3WayCounts

    # Status hero — TR-FUNC-011
    estado_resumido_hero_predio: HeroStateCounts

    # Reforestación chips — TR-FUNC-012
    predios_reforestacion: list[str] = field(default_factory=list)

    # PMF-grain headline — "¿Cuál es el estado de los planes de manejo?"
    estado_resumido_pmf: HeroStateCounts = field(
        default_factory=lambda: HeroStateCounts(0, 0, 0, 0, 0)
    )
    estado_detalle_pmf: list[LabelledCount] = field(default_factory=list)
    estado_resumido_valores: dict[str, list[str]] = field(default_factory=dict)
    por_empresa: list[EmpresaBreakdown] = field(default_factory=list)
    reforestacion: ReforestacionResult = field(default_factory=lambda: _empty_reforestacion())

    # Data-quality indicators — TR-FUNC-014-016
    calidad_filas_sin_id_predial_unico: int = 0
    calidad_pmf_sin_numero_ingreso: int = 0
    calidad_numero_resolucion: str = _STATIC_NUMERO_RESOLUCION
    calidad_pmf_estado_resumido_conflictivo: list[EstadoResumidoConflict] = field(
        default_factory=list
    )


def _is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


def build_summary(rows: Sequence[SummaryInputRow]) -> SummaryResult:
    """Compute every summary number from one already-filtered row set."""

    rolled = [row._as_rolled_row() for row in rows]

    # One shared PMF-grain dedup for every headline figure below. Computing
    # it once is not merely an optimisation: it is what makes "a PMF belongs
    # to exactly one headline bucket" structural rather than a property four
    # separate call sites each have to preserve.
    pmf_representative = first_row_wins(rolled, key="pmf")

    pmf_count = len({row.pmf for row in rows})
    predio_count = len({row.predio_group_key for row in rows})
    rol_count = len({row.rol for row in rows if row.rol is not None})
    surface_total = sum(row.superficie_corta for row in rows if row.superficie_corta is not None)

    pmf_status = estado_resumido_first_row(rolled, key="pmf")
    aprobados_pmf_count = sum(
        1 for value in pmf_status.values() if (value or "").strip().lower() == "aprobado"
    )
    en_tramite_pmf_count = sum(
        1
        for value in pmf_status.values()
        if (value or "").strip().lower() in {"en tramite", "en trámite"}
    )

    pending_by_pmf = pending_priority_legacy(rolled, key="pmf")
    pendientes_prioritarios_pmf_count = sum(1 for pending in pending_by_pmf.values() if pending)

    servidumbre_predios = {
        row.predio_group_key
        for row in rows
        if row.tipo_propietario is not None and "servidumbre" in row.tipo_propietario.lower()
    }

    predio_status = estado_resumido_first_row(rolled, key="predio_group_key")
    avance_por_predio = _bucket_counts(predio_status.values())
    avance_por_pmf = _bucket_counts(pmf_status.values())
    hero_predio = _hero_counts(predio_status.values())

    reforestacion = _build_reforestacion(rows)

    estado_resumido_pmf = _hero_counts(pmf_status.values())
    estado_detalle_pmf = _labelled_counts(row.estado for row in pmf_representative.values())
    estado_resumido_valores = _estado_resumido_valores(rows)
    por_empresa = _empresa_breakdown(rows, pmf_representative)
    conflicts = _estado_resumido_conflicts(rolled, pmf_representative)

    calidad_filas_sin_id_predial_unico = sum(1 for row in rows if _is_blank(row.id_predio_unico))

    calidad_pmf_sin_numero_ingreso = sum(
        1 for row in pmf_representative.values() if _is_blank(row.numero_ingreso)
    )

    return SummaryResult(
        row_count=len(rows),
        pmf_count=pmf_count,
        predio_count=predio_count,
        rol_count=rol_count,
        surface_total=surface_total,
        basis_estado_resumido="estado_resumido_first_row",
        aprobados_pmf_count=aprobados_pmf_count,
        en_tramite_pmf_count=en_tramite_pmf_count,
        basis_pending_priority="pending_priority_legacy",
        pendientes_prioritarios_pmf_count=pendientes_prioritarios_pmf_count,
        con_servidumbre_predio_count=len(servidumbre_predios),
        avance_por_predio=avance_por_predio,
        avance_por_pmf=avance_por_pmf,
        estado_resumido_hero_predio=hero_predio,
        predios_reforestacion=reforestacion.predio_ref_labels,
        estado_resumido_pmf=estado_resumido_pmf,
        estado_detalle_pmf=estado_detalle_pmf,
        estado_resumido_valores=estado_resumido_valores,
        por_empresa=por_empresa,
        reforestacion=reforestacion,
        calidad_filas_sin_id_predial_unico=calidad_filas_sin_id_predial_unico,
        calidad_pmf_sin_numero_ingreso=calidad_pmf_sin_numero_ingreso,
        calidad_pmf_estado_resumido_conflictivo=conflicts,
    )


def _bucket_counts(values: Iterable[str | None]) -> Bucket3WayCounts:
    aprobado = en_tramite = pendiente_o_tachado = 0
    for value in values:
        bucket = bucket_3way(value)
        if bucket == "aprobado":
            aprobado += 1
        elif bucket == "en_tramite":
            en_tramite += 1
        else:
            pendiente_o_tachado += 1
    return Bucket3WayCounts(
        aprobado=aprobado, en_tramite=en_tramite, pendiente_o_tachado=pendiente_o_tachado
    )


def _hero_counts(values: Iterable[str | None]) -> HeroStateCounts:
    counts = {"aprobado": 0, "en_tramite": 0, "pendiente": 0, "tachado": 0, "sin_estado": 0}
    for value in values:
        counts[hero_state(value)] += 1
    return HeroStateCounts(**counts)


def _empty_reforestacion() -> ReforestacionResult:
    """The shape an empty filtered scope yields — zeros, never ``None``."""

    return ReforestacionResult(
        definicion=REFORESTACION_DEFINICION,
        predio_ref_labels=[],
        predio_ref_count=0,
        rol_ref_count=0,
        sentinel_label=_REFORESTACION_SENTINEL_LABEL,
        sentinel_row_count=0,
        etiquetas_compuestas=[],
        propietarios=_OWNER_IDENTITY_UNAVAILABLE,
    )


def _labelled_counts(values: Iterable[str | None]) -> list[LabelledCount]:
    """Group raw values by ``normalized_label``, keeping the first spelling.

    Ordered by descending count, then by label, so the breakdown reads
    largest-first and two runs over the same data always agree. A blank or
    missing value keeps its own explicit bucket rather than being dropped:
    an absent state is information, and silently omitting it would make the
    breakdown stop summing to its population.
    """

    buckets: dict[str | None, LabelledCount] = {}
    for value in values:
        key = normalized_label(value)
        current = buckets.get(key)
        if current is None:
            buckets[key] = LabelledCount(label=value, normalized=key, count=1)
        else:
            buckets[key] = LabelledCount(
                label=current.label, normalized=key, count=current.count + 1
            )
    return sorted(buckets.values(), key=lambda item: (-item.count, item.label or ""))


def _empresa_breakdown(
    rows: Sequence[SummaryInputRow], pmf_representative: Mapping[str, RolledRow]
) -> list[EmpresaBreakdown]:
    """Per-company PMF-grain counts that partition the PMF population.

    A company is attributed to a PMF, not to a row, and by the very same
    first-row-wins representative the headline uses. That is what makes the
    subtotals reconcile: each PMF lands in exactly one company, so the
    companies' ``pmf_count`` values sum to the overall PMF total and each
    status bucket sums across companies to the overall bucket — even if a
    future import puts one PMF's rows under two companies, which the
    reviewed snapshot does not.
    """

    empresa_by_row_number = {row.source_row_number: row.empresa for row in rows}

    grouped: dict[str | None, list[str | None]] = {}
    labels: dict[str | None, str | None] = {}
    for representative in pmf_representative.values():
        raw = empresa_by_row_number.get(representative.source_row_number)
        key = normalized_label(raw)
        labels.setdefault(key, raw)
        grouped.setdefault(key, []).append(representative.estado_resumido)

    return sorted(
        (
            EmpresaBreakdown(
                empresa=labels[key],
                pmf_count=len(states),
                estado_resumido=_hero_counts(states),
            )
            for key, states in grouped.items()
        ),
        key=lambda item: (-item.pmf_count, item.empresa or ""),
    )


def _estado_resumido_conflicts(
    rolled: Sequence[RolledRow], pmf_representative: Mapping[str, RolledRow]
) -> list[EstadoResumidoConflict]:
    """PMFs the source gives more than one ``Estado resumido``.

    The canonical value is the representative row's — the same row every
    headline figure already reads — so this record says exactly which
    evidence the headline kept and which it set aside, rather than implying
    the choice was made here.
    """

    return [
        EstadoResumidoConflict(
            pmf=pmf,
            valores=list(valores),
            canonico=pmf_representative[pmf].estado_resumido,
            estado_detalle=pmf_representative[pmf].estado,
            source_row_number=pmf_representative[pmf].source_row_number,
        )
        for pmf, valores in sorted(estado_resumido_conflicts(rolled, key="pmf").items())
    ]


def _distinct_labels(values: Iterable[str | None]) -> list[str]:
    """Distinct non-blank values, deduped on ``normalized_label``, sorted."""

    seen: dict[str | None, str] = {}
    for value in values:
        if value is None or not value.strip():
            continue
        seen.setdefault(normalized_label(value), value.strip())
    return sorted(seen.values())


def _build_reforestacion(rows: Sequence[SummaryInputRow]) -> ReforestacionResult:
    """Reforestation reference counts, under a definition stated in full.

    ``Predio Ref`` is a free-text label, not a key. The reviewed snapshot
    has 33 distinct non-blank values, one of which is the literal
    ``Sin reforestacion`` (excluded here, leaving 32) and six of which name
    several properties in one string (``Ref. 2_Toro + Ref. 35 Barria``,
    ``Ref036_ Reyes y Ref037_ Reyes``, …). So 32 is a count of labels, and
    the name of the metric says so. Turning it into a count of properties
    needs a source identifier that does not exist yet — see the stakeholder
    questions in the design record.
    """

    sentinel_rows = 0
    predio_ref_values: list[str | None] = []
    for row in rows:
        if normalized_label(row.predio_ref) in _REFORESTACION_SENTINELS:
            sentinel_rows += 1
            continue
        predio_ref_values.append(row.predio_ref)

    labels = _distinct_labels(predio_ref_values)

    return ReforestacionResult(
        definicion=REFORESTACION_DEFINICION,
        predio_ref_labels=labels,
        predio_ref_count=len(labels),
        rol_ref_count=len(_distinct_labels(row.rol_ref for row in rows)),
        sentinel_label=_REFORESTACION_SENTINEL_LABEL,
        sentinel_row_count=sentinel_rows,
        etiquetas_compuestas=[label for label in labels if _COMPOSITE_LABEL.search(label)],
        propietarios=_OWNER_IDENTITY_UNAVAILABLE,
    )


def _estado_resumido_valores(rows: Sequence[SummaryInputRow]) -> dict[str, list[str]]:
    """The raw ``Estado resumido`` spellings observed behind each hero state.

    A headline bucket is a normalized state; the Explorador filters on the
    literal source value. Returning the spellings the scope actually
    contains lets a status card link to the exact filter that reproduces it,
    without the frontend carrying a second copy of the status vocabulary
    that could drift from this one.

    Row grain on purpose: the click-through filters rows, so every spelling
    present anywhere in scope belongs in the filter, not only the ones the
    PMF representatives happen to use.
    """

    valores: dict[str, dict[str, None]] = {}
    for row in rows:
        raw = (row.estado_resumido or "").strip()
        if not raw:
            continue
        valores.setdefault(hero_state(row.estado_resumido), {})[raw] = None
    return {state: sorted(spellings) for state, spellings in valores.items()}
