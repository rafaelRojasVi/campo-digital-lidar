/**
 * The «Pendientes prioritarios» rule the «Estado» section replaced
 * (`pending_priority_legacy`, `pending_stage_legacy`).
 *
 * Kept reachable and closed by default: the functional parity matrix
 * (TR-FUNC-007/032/033) requires the source dashboards' own rules to stay
 * available beside a new basis, and the Resumen still counts with this one.
 * Moved here unchanged from the former `PendientesPage`; its stage bar keeps
 * its old tones inside this closed disclosure.
 */
import { useCallback, useEffect, useRef } from 'react'
import { type ResumenRow, type TranselecFilterState, type TranselecPending, getPending } from '../api'
import { cell, formatInteger, formatNumber } from '../format'
import { PENDING_STAGE_LABELS, PENDING_STAGE_ORDER } from '../lib/pendingStage'
import { useReads } from '../lib/useFilters'
import { CompositionBar, type CompositionSegment } from '../ui/CompositionBar'
import { HowCalculated } from '../ui/HowCalculated'
import { Figure, SectionHeader } from '../ui/Primitives'
import { AlertBanner, LoadingBlock } from './StateViews'
import { StatusPill } from './StatusPill'

function stageSegments(pending: TranselecPending): CompositionSegment[] {
  const tones = ['none', 'progress', 'struck'] as const
  return PENDING_STAGE_ORDER.map((stage, index) => ({
    key: stage,
    label: PENDING_STAGE_LABELS[stage],
    value: pending.stages[stage],
    tone: tones[index],
  }))
}

export function LegacyPendingSection({
  filters,
  selectedRow,
  onOpenRow,
  reveal = false,
}: {
  filters: TranselecFilterState
  selectedRow: number | null
  onOpenRow: (row: ResumenRow) => void
  /** Open the disclosure, scroll it into view and focus its summary (TR-FUNC-024). */
  reveal?: boolean
}) {
  const details = useRef<HTMLDetailsElement>(null)
  const key = JSON.stringify(filters)

  const { data, loading, failure } = useReads<TranselecPending>(
    useCallback(
      () => getPending(filters),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [key],
    ),
    [key],
  )

  useEffect(() => {
    const element = details.current
    if (!reveal || !element) return
    element.open = true
    element.scrollIntoView({ block: 'start' })
    element.querySelector('summary')?.focus({ preventScroll: true })
  }, [reveal])

  return (
    <details ref={details} className="how legacy-pending" data-testid="legacy-pending">
      <summary>Pendientes prioritarios (regla anterior)</summary>
      <div className="how-body">
        {failure && <AlertBanner title={failure.title}>{failure.message}</AlertBanner>}
        {!data && loading && <LoadingBlock label="Cargando los PMF pendientes…" shape="bar" />}
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
              Regla anterior a «Estado», que el Resumen todavía usa: un PMF es pendiente
              prioritario si le falta el N.º de ingreso o si su «Estado» menciona un rechazo. No se
              basa en el «Estado resumido». La etapa se deduce del texto de «Estado»; no es una
              clasificación confirmada por CONAF.
            </p>
            <HowCalculated bases={[data.basis, data.stage_basis]} testId="pending-how" />

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
                      aria-selected={selectedRow === row.source_row_number}
                      aria-haspopup="dialog"
                      data-testid={`pending-row-${row.source_row_number}`}
                      onClick={() => onOpenRow(row)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          onOpenRow(row)
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
        )}
      </div>
    </details>
  )
}
