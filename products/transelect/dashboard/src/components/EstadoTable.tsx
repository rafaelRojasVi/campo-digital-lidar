/**
 * One row per PMF, under `lifecycle_pmf_v1`. A row opens the PMF drawer by
 * click, Enter or Space, like every other queue in the dashboard.
 */
import type { LifecycleRow } from '../api'
import { ESTADO_COLUMNS, type EstadoColumn } from '../lib/estadoColumns'
import { editedAmong, webFieldsDescription } from '../lib/webEdits'
import { WebChip } from './WebChip'

function withExtraColumns(extra: readonly EstadoColumn[]): EstadoColumn[] {
  const columns: EstadoColumn[] = []
  for (const base of ESTADO_COLUMNS) {
    columns.push(base, ...extra.filter((column) => column.after === base.key))
  }
  const known = new Set(ESTADO_COLUMNS.map((column) => column.key))
  return [...columns, ...extra.filter((column) => !column.after || !known.has(column.after))]
}

export function EstadoTable({
  rows,
  selectedRow,
  onOpen,
  extraColumns = [],
  emptyText = 'No hay PMF en el alcance seleccionado.',
}: {
  rows: readonly LifecycleRow[]
  /** `source_row_number` of the row whose drawer is open. */
  selectedRow: number | null
  onOpen: (row: LifecycleRow) => void
  /**
   * Added to the lifecycle columns (e.g. «Plazo CONAF»). `after` names the base
   * column one follows, so it is read beside the PMF at any width; without it
   * the column goes last.
   */
  extraColumns?: readonly EstadoColumn[]
  emptyText?: string
}) {
  const columns = withExtraColumns(extraColumns)
  // A cell is marked «web» when a field it shows was edited on the panel.
  const edited = (row: LifecycleRow, column: EstadoColumn) =>
    column.webFields ? editedAmong(row, column.webFields) : []
  const anyEdited = rows.some((row) => columns.some((column) => edited(row, column).length > 0))

  return (
    <>
      {anyEdited && (
        <p className="hint estado-web-note" data-testid="estado-web-note">
          Los valores marcados «web» se editaron en el panel; la planilla publicada no cambió.
        </p>
      )}
      <div className="tablewrap" data-testid="estado-table">
        <table className="queue-table rows-table estado-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th scope="col" key={column.key}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.source_row_number}
                tabIndex={0}
                aria-selected={selectedRow === row.source_row_number}
                aria-haspopup="dialog"
                data-testid={`estado-row-${row.source_row_number}`}
                onClick={() => onOpen(row)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onOpen(row)
                  }
                }}
              >
                {columns.map((column) => {
                  const fields = edited(row, column)
                  return (
                    <td key={column.key} data-col={column.key}>
                      {column.render(row)}
                      {fields.length > 0 && <WebChip description={webFieldsDescription(fields)} />}
                    </td>
                  )
                })}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="empty">
                  {emptyText}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}
