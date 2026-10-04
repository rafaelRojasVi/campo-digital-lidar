/**
 * `/transelec/estado` — where each plan (PMF) stands in CONAF's process.
 *
 * Replaces «Pendientes» (meeting of 2026-10-02; spec
 * docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md).
 * Everything is computed by `GET /transelec/lifecycle` under the current
 * filter state with `lifecycle_pmf_v1`: the group from the first row's
 * «Estado resumido», the step inside «En trámite» from its «Estado». A
 * rejection is a step, never an end. Whatever the rule does not recognize is
 * «Sin clasificar», with its reason, and is listed in Calidad.
 *
 * Kept from the former page: the filter chips with one «Quitar filtros»
 * button, the 90-day consultation toggle (TR-FUNC-031), and — closed by
 * default — the old «Pendientes prioritarios» rule (`LegacyPendingSection`).
 *
 * `EstadoTable` takes `extraColumns`, so the 90 días hábiles work adds
 * «Plazo CONAF» without touching this page's rule.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  type LifecycleRow,
  type ResumenRow,
  type TranselecLifecycle,
  getLifecycle,
  observedServerNow,
} from '../api'
import { EstadoTable } from '../components/EstadoTable'
import { LegacyPendingSection } from '../components/LegacyPendingSection'
import { OverduePanel } from '../components/OverduePanel'
import { RowDetailDrawer } from '../components/RowDetailDrawer'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { formatInteger } from '../format'
import { classifyFailure } from '../lib/apiState'
import { activeFilterChips, withoutChip } from '../lib/filterUrl'
import { lifecycleGroupSegments, lifecycleStepSegments } from '../lib/lifecycle'
import { selectOverdueRows } from '../lib/overdue'
import { collectAllRows } from '../lib/rowCollection'
import { useReads, type FilterController } from '../lib/useFilters'
import { PENDING_QUEUE_HASH, useRouter } from '../router'
import { CompositionBar } from '../ui/CompositionBar'
import { HowCalculated } from '../ui/HowCalculated'
import { Chip, SectionHeader } from '../ui/Primitives'

export function EstadoPage({
  filterController,
  sourceFields = null,
}: {
  filterController: FilterController
  /** Contract fields the published workbook had, for the detail drawer. */
  sourceFields?: readonly string[] | null
}) {
  const { filters, replaceFilters, reset } = filterController
  const { hash } = useRouter()
  const key = JSON.stringify(filters)

  const { data, loading, failure } = useReads<TranselecLifecycle>(
    useCallback(
      () => getLifecycle(filters),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [key],
    ),
    [key],
  )

  const [openRow, setOpenRow] = useState<ResumenRow | null>(null)
  const [overdueOpen, setOverdueOpen] = useState(false)
  const [overdueRows, setOverdueRows] = useState<ResumenRow[]>([])
  const [overdueLoading, setOverdueLoading] = useState(false)
  const [overdueError, setOverdueError] = useState<string | null>(null)
  const [overdueReference, setOverdueReference] = useState<Date | null>(null)
  const overdueRequestId = useRef(0)

  // The 90-day consultation, moved unchanged from the former Pendientes
  // page: it follows the filter state like every other read, so it never
  // shows rows computed under a scope the page has left.
  useEffect(() => {
    if (!overdueOpen) return

    const id = ++overdueRequestId.current
    let cancelled = false
    setOverdueLoading(true)
    setOverdueError(null)
    setOverdueRows([])

    const reference = observedServerNow() ?? new Date()
    setOverdueReference(reference)

    void collectAllRows(filters).then((result) => {
      if (cancelled || id !== overdueRequestId.current) return
      setOverdueLoading(false)
      if (!result.ok) {
        setOverdueError(classifyFailure(result).message)
        return
      }
      setOverdueRows(selectOverdueRows(result.rows, reference))
    })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overdueOpen, key])

  const chips = activeFilterChips(filters)
  const openLifecycle: LifecycleRow | null =
    openRow && data ? (data.rows.find((entry) => entry.pmf === openRow.pmf) ?? null) : null

  if (failure && !data) {
    return (
      <div className="page">
        <StateBlock view={failure} />
      </div>
    )
  }

  return (
    <div className="page enter">
      <SectionHeader
        title={
          <>
            Estado <span className="hint">(provisional)</span>
          </>
        }
        meta="Dónde está cada PMF en la tramitación CONAF. Un rechazo es un paso, no un final."
      />

      {chips.length > 0 && (
        <div className="active-filters no-print" style={{ paddingBottom: 'var(--s-5)' }}>
          <span className="eyebrow">Alcance filtrado</span>
          {chips.map((chip) => (
            <Chip
              key={chip.key}
              onRemove={() => replaceFilters(withoutChip(filters, chip))}
              removeLabel={`Quitar el filtro ${chip.label}: ${chip.value}`}
            >
              {chip.label}: {chip.value}
            </Chip>
          ))}
        </div>
      )}

      {failure && data && <AlertBanner title={failure.title}>{failure.message}</AlertBanner>}

      {!data && loading && <LoadingBlock label="Cargando el estado de los PMF…" shape="bar" />}

      {data && (
        <section id="estadozone" data-testid="estado-zone">
          <div className="pending-lead">
            <CompositionBar
              title="PMF por grupo"
              noun="PMF"
              testId="estado-group"
              segments={lifecycleGroupSegments(data)}
            />
            <CompositionBar
              title="En trámite, por paso"
              noun="PMF en trámite"
              testId="estado-step"
              lead={false}
              segments={lifecycleStepSegments(data)}
            />
          </div>

          <p className="hint">
            El grupo sale del «Estado resumido» de la primera fila de cada PMF; el paso, de su
            «Estado». «Rechazado» es un paso dentro de «En trámite»: todo rechazo termina en
            «Aprobado», «Descartado» o «Desistido». Lo que esta regla no reconoce queda «Sin
            clasificar» y se lista en Calidad. Categorías provisionales hasta que Campo Digital las
            confirme.
          </p>
          <HowCalculated bases={[data.basis]} testId="estado-how" />

          <div className="btns no-print" style={{ margin: 'var(--s-5) 0' }}>
            {chips.length > 0 && (
              <button
                type="button"
                className="btn alt"
                onClick={reset}
                data-testid="clear-estado-filters"
              >
                Quitar filtros y ver todos los PMF
              </button>
            )}
            <button
              type="button"
              className={overdueOpen ? 'btn' : 'btn alt'}
              aria-pressed={overdueOpen}
              onClick={() => setOverdueOpen((value) => !value)}
              data-quick="overdue"
            >
              {overdueOpen ? 'Ocultar los ingresos sobre 90 días' : '¿Qué ingresos superaron 90 días?'}
            </button>
          </div>

          {overdueOpen && (
            <OverduePanel
              rows={overdueRows}
              reference={overdueReference}
              loading={overdueLoading}
              error={overdueError}
              onClose={() => setOverdueOpen(false)}
            />
          )}

          <section className="ruled" aria-labelledby="estado-rows-title">
            <SectionHeader
              id="estado-rows-title"
              title="PMF del alcance"
              meta={`${formatInteger(data.rows.length)} PMF · seleccione uno para ver su detalle`}
            />
            <EstadoTable
              rows={data.rows}
              selectedRow={openRow?.source_row_number ?? null}
              onOpen={setOpenRow}
            />
          </section>

          <section className="ruled">
            <LegacyPendingSection
              filters={filters}
              reveal={hash === PENDING_QUEUE_HASH}
              selectedRow={openRow?.source_row_number ?? null}
              onOpenRow={setOpenRow}
            />
          </section>
        </section>
      )}

      {openRow && (
        <RowDetailDrawer
          row={openRow}
          lifecycle={openLifecycle}
          onClose={() => setOpenRow(null)}
          sourceFields={sourceFields}
        />
      )}
    </div>
  )
}
