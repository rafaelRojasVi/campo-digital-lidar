/**
 * `/transelec/pendientes` — the pending-priority working surface.
 *
 * Everything here is computed by `GET /transelec/pending` under the current
 * filter state, using `pending_priority_legacy` (`isPendingPMF`: blank
 * `N Ingreso` OR raw `Estado` containing "rechaz"). That rule genuinely
 * disagrees with the `Estado resumido`-based approval figures on the Resumen
 * — the same PMF can be "En trámite" there and "pendiente prioritario" here.
 * The divergence is stated in the copy rather than silently reconciled, and
 * both basis identifiers stay on screen.
 *
 * Two things changed from the shipped pending zone, neither of them a rule:
 *
 *  1. The three stage counts were printed twice, as tiles and then again
 *     immediately below as labelled progress bars with the same three
 *     numbers. They are printed once, as one composition bar, which also
 *     shows how the three relate to each other rather than only how each
 *     compares to the largest.
 *  2. The 90-day consultation (TR-FUNC-031) lives here, as a toggle on the
 *     page whose scope it shares, instead of as a panel that appeared in the
 *     middle of the dashboard.
 *
 * And, from the dashboard UI pass: every queue row now opens the same PMF
 * detail drawer as the Explorador (the rows were styled as hoverable but did
 * nothing), and the two buttons that both only cleared the filters — which
 * did nothing at all on an unfiltered page — are one «Quitar filtros» button
 * that appears only when there is a filter to remove. The rule identifiers
 * moved into «Cómo se calcula».
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  type ResumenRow,
  type TranselecPending,
  getPending,
  observedServerNow,
} from '../api'
import { OverduePanel } from '../components/OverduePanel'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { RowDetailDrawer } from '../components/RowDetailDrawer'
import { StatusPill } from '../components/StatusPill'
import { cell, formatInteger, formatNumber } from '../format'
import { activeFilterChips, withoutChip } from '../lib/filterUrl'
import { classifyFailure } from '../lib/apiState'
import { PENDING_STAGE_LABELS, PENDING_STAGE_ORDER } from '../lib/pendingStage'
import { collectAllRows } from '../lib/rowCollection'
import { selectOverdueRows } from '../lib/overdue'
import { useReads, type FilterController } from '../lib/useFilters'
import { CompositionBar, type CompositionSegment } from '../ui/CompositionBar'
import { HowCalculated } from '../ui/HowCalculated'
import { Chip, Figure, SectionHeader } from '../ui/Primitives'

/**
 * The three stage buckets come from the API's `pending_stage_legacy`
 * heuristic, which the parity matrix characterises as INFERENCE-quality and
 * not a confirmed CONAF taxonomy. That is stated in the copy, not implied.
 */
function stageSegments(pending: TranselecPending): CompositionSegment[] {
  const tones = ['late', 'progress', 'struck'] as const
  return PENDING_STAGE_ORDER.map((stage, index) => ({
    key: stage,
    label: PENDING_STAGE_LABELS[stage],
    value: pending.stages[stage],
    tone: tones[index],
  }))
}

export function PendientesPage({
  filterController,
  sourceFields = null,
}: {
  filterController: FilterController
  /** Contract fields the published workbook had, for the detail drawer. */
  sourceFields?: readonly string[] | null
}) {
  const { filters, replaceFilters, reset } = filterController
  const key = JSON.stringify(filters)

  const { data, loading, failure } = useReads<TranselecPending>(
    useCallback(
      () => getPending(filters),
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

  // The 90-day consultation reacts to the filter state the way every other
  // read does, rather than being run once when the toggle is pressed. Its own
  // copy tells the reader its scope is the active filters, so it must never
  // keep showing rows computed under a filter state the page has left behind.
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
        title="Pendientes"
        meta="PMF no presentados a CONAF y aquellos cuyo estado vigente indica rechazo."
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

      {!data && loading && (
        <LoadingBlock label="Cargando los PMF pendientes…" shape="bar" />
      )}

      {data && (
        <section id="pendingzone" data-testid="pending-zone">
          <div className="pending-lead">
            <Figure
              lead
              testId="pending-count"
              value={`${formatInteger(data.pending_pmf_count)} de ${formatInteger(
                data.total_pmf_count,
              )}`}
              label="PMF pendientes prioritarios"
              note={`${formatNumber(data.pending_pmf_percentage)}% de los PMF del alcance seleccionado`}
            />
            <CompositionBar
              title="Etapa, según el texto de «Estado»"
              noun="PMF pendientes"
              testId="pending-stage"
              lead={false}
              segments={stageSegments(data)}
            />
          </div>

          <p className="hint">
            Un PMF es pendiente prioritario si le falta el N.º de ingreso o si su «Estado» menciona
            un rechazo. Esto no se basa en el «Estado resumido» del Resumen, así que un PMF puede
            figurar «En trámite» allí y aparecer aquí. La etapa se deduce del texto de «Estado»; no
            es una clasificación confirmada por CONAF.
          </p>
          <HowCalculated bases={[data.basis, data.stage_basis]} testId="pending-how" />

          <div className="btns no-print" style={{ margin: 'var(--s-5) 0' }}>
            {chips.length > 0 && (
              <button
                type="button"
                className="btn alt"
                onClick={reset}
                data-testid="clear-pending-filters"
              >
                Quitar filtros y ver todos los pendientes
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

          <section className="ruled" aria-labelledby="pending-rows-title">
            <SectionHeader
              id="pending-rows-title"
              title="Cola de PMF pendientes"
              meta={`${formatInteger(data.rows.length)} filas de origen · seleccione una para ver el detalle del PMF`}
            />
            <div className="tablewrap">
              <table className="queue-table rows-table">
                <thead>
                  <tr>
                    <th scope="col">PMF</th>
                    <th scope="col">Predio de reforestación</th>
                    <th scope="col">Carpeta PMF</th>
                    <th scope="col">Carpeta normalizada</th>
                    <th scope="col">Predio</th>
                    <th scope="col">Rol</th>
                    <th scope="col">Estado resumido</th>
                    <th scope="col">Motivo</th>
                    <th scope="col">N.º ingreso</th>
                    <th scope="col">Empresa</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr
                      key={row.source_row_number}
                      tabIndex={0}
                      aria-selected={openRow?.source_row_number === row.source_row_number}
                      aria-haspopup="dialog"
                      data-testid={`pending-row-${row.source_row_number}`}
                      onClick={() => setOpenRow(row)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          setOpenRow(row)
                        }
                      }}
                    >
                      <td>
                        <b>{row.pmf}</b>
                      </td>
                      <td>{cell(row.predio_ref, 'Sin información')}</td>
                      <td>{cell(row.carpeta_source)}</td>
                      <td>{cell(row.carpeta_normalizada)}</td>
                      <td>{cell(row.numero_predio)}</td>
                      <td>{cell(row.rol)}</td>
                      <td>
                        <StatusPill value={row.estado_resumido} />
                      </td>
                      <td>{cell(row.tipo_rechazo, '—')}</td>
                      <td>{cell(row.numero_ingreso, 'Sin ingreso')}</td>
                      <td>{cell(row.empresa)}</td>
                    </tr>
                  ))}
                  {data.rows.length === 0 && (
                    <tr>
                      <td colSpan={10} className="empty">
                        No hay PMF pendientes prioritarios para el alcance seleccionado.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </section>
      )}

      {openRow && (
        <RowDetailDrawer
          row={openRow}
          onClose={() => setOpenRow(null)}
          sourceFields={sourceFields}
        />
      )}
    </div>
  )
}
