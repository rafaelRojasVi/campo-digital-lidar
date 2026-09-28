/**
 * TR-FUNC-039 — "Detalle filtrado", the row-grain table.
 *
 * Actualizable's 12-column set, with one deliberate correction: its single
 * `Carpeta` column is shown as the two distinct source columns it silently
 * collapsed. The workbook has two different columns both named `Carpeta` —
 * one beside `PMF` (1:1 with it) and one between `Tramite` and `Sector` (a
 * coarser grouping) — and both HTML files keep only whichever one survived a
 * JavaScript object-literal key collision. TR-OPEN-02 is still open, so this
 * table does not choose either — it labels and shows both. The labels name
 * the columns by their neighbours rather than by letter: the 09-Sept-2026
 * layout moved them from E/AC to J/AH.
 *
 * Contract V2 adds an `AEF` column. It is a row-level value: a blank cell is
 * shown as blank on its own row, never borrowed from another row of the PMF.
 *
 * Pagination is real, server-side and cursor-based. The source's hidden
 * `slice(0, 1000)` cap is not reproduced: the row count shown is the API's
 * true `total_count` for the current filter state, never a capped one.
 *
 * New here: a row is a real activation target. Clicking or pressing Enter on
 * one opens the detail drawer for its PMF, because the job this table serves
 * is "scan the list, look at one, carry on" — and the shipped interface had
 * no way to see a single record's full contract row at all.
 */
import type { ResumenRow } from '../api'
import { cell, formatNumber } from '../format'
import { chronologyFlagsOf, chronologyLabel } from '../lib/aef'
import { StatusPill } from './StatusPill'

export function RowsTable({
  rows,
  loading,
  onOpenRow,
  selectedRow,
}: {
  rows: ResumenRow[]
  loading: boolean
  onOpenRow: (row: ResumenRow) => void
  selectedRow: number | null
}) {
  return (
    <div className="tablewrap" aria-busy={loading}>
      <table className="rows-table">
        <thead>
          <tr>
            <th scope="col">PMF</th>
            <th scope="col">Predio de reforestación</th>
            <th scope="col">Carpeta PMF</th>
            <th scope="col">Carpeta normalizada</th>
            <th scope="col">Rol</th>
            <th scope="col">Predio</th>
            <th scope="col">Área corta</th>
            <th scope="col" className="numeric">
              Sup. ha
            </th>
            <th scope="col">Estado resumido</th>
            <th scope="col">AEF</th>
            <th scope="col">N.º ingreso</th>
            <th scope="col">Empresa</th>
            <th scope="col">Propietario</th>
            <th scope="col">Sector</th>
          </tr>
        </thead>
        <tbody data-testid="rows-body">
          {rows.map((row) => (
            <tr
              key={row.source_row_number}
              tabIndex={0}
              aria-selected={selectedRow === row.source_row_number}
              data-testid={`row-${row.source_row_number}`}
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
              <td>{cell(row.rol)}</td>
              <td>{cell(row.numero_predio)}</td>
              <td>{cell(row.numero_area_corta)}</td>
              <td className="numeric">{formatNumber(row.superficie_corta)}</td>
              <td>
                <StatusPill value={row.estado_resumido} />
              </td>
              <td>
                {cell(row.aef) || <span className="aef-empty">—</span>}
                {chronologyFlagsOf(row).length > 0 && (
                  <>
                    {' '}
                    <span
                      className="flag"
                      title={chronologyFlagsOf(row).map(chronologyLabel).join('; ')}
                    >
                      Revisar fechas
                    </span>
                  </>
                )}
              </td>
              <td>{cell(row.numero_ingreso)}</td>
              <td>{cell(row.empresa)}</td>
              <td>{cell(row.tipo_propietario)}</td>
              <td>{cell(row.sector)}</td>
            </tr>
          ))}
          {rows.length === 0 && !loading && (
            <tr>
              <td colSpan={14} className="empty">
                No hay registros para los filtros aplicados. Quite un filtro o limpie la búsqueda
                para ampliar el alcance.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
