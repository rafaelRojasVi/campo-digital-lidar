/**
 * TR-FUNC-031 — "¿Qué ingresos superaron 90 días?"
 *
 * The source dashboards implement this as a global view override built on a
 * hardcoded `new Date('2026-08-26')`, which can never advance. The matrix
 * calls that the one unambiguous, mechanically fixable bug in the whole
 * inventory.
 *
 * Two things differ here, both deliberate and both disclosed on screen:
 *
 *  1. The reference date is the platform API's own observed clock, so the
 *     filter advances with real time instead of freezing.
 *  2. The result is a dedicated panel over the current filtered scope rather
 *     than a silent, global override of the whole dashboard. The read API's
 *     filter contract has no `90 dias` parameter, and faking a global filter
 *     client-side would leave the KPI row, donuts and hero above disagreeing
 *     with the table — the exact inconsistency TR-FUNC-017 exists to
 *     prevent. So the scope of this list is stated in its own heading.
 *
 * What `90 días` actually means remains TR-OPEN-03 and is not interpreted.
 */
import type { ResumenRow } from '../api'
import { cell, formatDate, formatInteger } from '../format'
import { StatusPill } from './StatusPill'

export function OverduePanel({
  rows,
  reference,
  loading,
  error,
  onClose,
}: {
  rows: ResumenRow[]
  reference: Date | null
  loading: boolean
  error: string | null
  onClose: () => void
}) {
  return (
    <section className="panel section" aria-labelledby="overdue-title" data-testid="overdue-panel">
      <h2 id="overdue-title">
        Ingresos con fecha «90 días» vencida{' '}
        <span className="hint" data-testid="overdue-count">
          ({formatInteger(rows.length)} áreas de corta)
        </span>
      </h2>
      <p className="section-note">
        Filas no aprobadas cuya fecha «90 días» es anterior a{' '}
        <b>{reference ? formatDate(reference.toISOString()) : 'la fecha de referencia'}</b>, la
        hora observada del servidor de la plataforma — no una fecha fija en el código, como
        ocurría en las planillas HTML originales. El alcance es el de los filtros activos; los
        indicadores, gráficos y el detalle filtrado de esta página no cambian con esta consulta.
        El significado exacto de la columna «90 días» sigue pendiente de confirmación.
      </p>

      {loading && (
        <p className="loading-row" role="status">
          Revisando las filas del alcance seleccionado…
        </p>
      )}
      {error && (
        <div className="alert alert-error" role="alert">
          <strong>No se pudo revisar el alcance completo</strong>
          {error}
        </div>
      )}

      {!loading && !error && (
        <div className="tablewrap short">
          <table>
            <thead>
              <tr>
                <th scope="col">PMF</th>
                <th scope="col">Rol</th>
                <th scope="col">Predio</th>
                <th scope="col">Estado resumido</th>
                <th scope="col">Estado vigente</th>
                <th scope="col">Fecha de ingreso</th>
                <th scope="col">90 días</th>
                <th scope="col">N.º ingreso</th>
                <th scope="col">Empresa</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.source_row_number}>
                  <td>
                    <b>{row.pmf}</b>
                  </td>
                  <td>{cell(row.rol)}</td>
                  <td>{cell(row.numero_predio)}</td>
                  <td>
                    <StatusPill value={row.estado_resumido} />
                  </td>
                  <td>{cell(row.estado, '—')}</td>
                  <td>{formatDate(row.fecha_ingreso)}</td>
                  <td>{formatDate(row.fecha_90_dias)}</td>
                  <td>{cell(row.numero_ingreso, 'Sin ingreso')}</td>
                  <td>{cell(row.empresa)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={9} className="empty">
                    Ningún ingreso del alcance seleccionado supera la fecha «90 días».
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="btns no-print" style={{ marginTop: 12 }}>
        <button type="button" className="btn alt" onClick={onClose} data-testid="overdue-close">
          Cerrar esta consulta
        </button>
      </div>
    </section>
  )
}
