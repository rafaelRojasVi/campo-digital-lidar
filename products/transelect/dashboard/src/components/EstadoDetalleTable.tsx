/**
 * The detailed `Estado` breakdown, as a drill-down under the headline.
 *
 * Same PMF population, same first-row-wins representative, one column
 * further into the source: `Estado resumido` answers "approved, in process
 * or struck out", `Estado` answers "in evaluation, rejected, under which
 * appeal". It reads as a detail of the headline rather than as a competing
 * headline — no lead figure, no colour except on the states that warrant it.
 *
 * Casing variants of one state are already reconciled by the API
 * (`En Evaluacion` and `En evaluacion` are one row here), and the label shown
 * is the source's own first spelling, never a rewrite.
 */
import type { TranselecSummary } from '../api'
import { formatInteger, formatNumber } from '../format'
import { detalleRows } from '../lib/statusHeadline'

export function EstadoDetalleTable({ summary }: { summary: TranselecSummary }) {
  const rows = detalleRows(summary)

  if (rows.length === 0) {
    return <p className="empty">Sin estados detallados para el alcance seleccionado.</p>
  }

  return (
    <div className="tablewrap">
      <table className="breakdown" data-testid="estado-detalle">
        <caption className="sr-only">
          Estado detallado de los planes de manejo, un PMF por fila de origen representativa.
        </caption>
        <thead>
          <tr>
            <th scope="col">Estado (detalle)</th>
            <th scope="col" className="numeric">
              PMF
            </th>
            <th scope="col" className="numeric">
              % del alcance
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td className={row.attention ? 'bad' : undefined}>{row.label}</td>
              <td className="numeric" data-testid={`detalle-${row.key}`}>
                {formatInteger(row.count)}
              </td>
              <td className="numeric muted">{formatNumber(row.percentage)}%</td>
            </tr>
          ))}
          <tr className="total">
            <td>TOTAL</td>
            <td className="numeric" data-testid="detalle-total">
              <b>{formatInteger(rows.reduce((sum, row) => sum + row.count, 0))}</b>
            </td>
            <td className="numeric muted">{formatInteger(summary.pmf_count)} PMF</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}
