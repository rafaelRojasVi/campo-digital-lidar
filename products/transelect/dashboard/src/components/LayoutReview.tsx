/**
 * The operator's review of how an uploaded workbook's `Resumen` sheet was
 * read — what matched, what was ignored, and what needs attention.
 *
 * Everything shown comes from the server's layout report
 * (`transelec_ingestion.resumen_layout`), which is structural by
 * construction: header text, column letters, worksheet row numbers and
 * counts. It never contains a business cell value, so this component cannot
 * leak one either.
 *
 * Issues are ordered by what they mean for the operator: blocking errors
 * (nothing was imported), then warnings (imported, but must be reviewed
 * before publishing), then recorded observations. Most row lists are capped
 * by the server, with the true total stated beside them; text-date and
 * PMF-conflict issues list every affected row, and long lists fold behind a
 * "ver todas" toggle so the review stays readable.
 */
import type { LayoutIssue, LayoutReport } from '../api'
import { formatInteger } from '../format'

const STATUS_LABELS: Record<string, string> = {
  duplicate_ignored: 'Duplicado',
  unrecognized_ignored: 'No reconocido',
  unlabeled_data_ignored: 'Sin encabezado',
  separator: 'Separador',
}

// Beyond this many rows, the list is folded behind a toggle.
const INLINE_ROWS = 20

function IssueReferences({ issue }: { issue: LayoutIssue }) {
  const parts: string[] = []
  if (issue.columns.length > 0) {
    parts.push(`${issue.columns.length === 1 ? 'Columna' : 'Columnas'} ${issue.columns.join(', ')}`)
  }
  const more = issue.row_count - issue.rows.length
  const folded = issue.rows.length > INLINE_ROWS
  if (issue.rows.length > 0 && !folded) {
    const listed = issue.rows.join(', ')
    parts.push(
      `${issue.rows.length === 1 ? 'Fila' : 'Filas'} ${listed}${more > 0 ? ` y ${formatInteger(more)} más` : ''}`,
    )
  }
  if (parts.length === 0 && !folded) return null
  return (
    <span className="issue-refs">
      {parts.join(' · ')}
      {folded && (
        <details className="issue-rows" data-testid="issue-rows">
          <summary>
            {formatInteger(issue.row_count)} filas — ver {more > 0 ? 'las listadas' : 'todas'}
          </summary>
          {issue.rows.join(', ')}
          {more > 0 && ` y ${formatInteger(more)} más`}
        </details>
      )}
    </span>
  )
}

function IssueGroup({
  title,
  tone,
  issues,
  testId,
}: {
  title: string
  tone: 'error' | 'warn' | 'info'
  issues: LayoutIssue[]
  testId: string
}) {
  return (
    <div className={`alert alert-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <strong>
        {title} ({formatInteger(issues.length)})
      </strong>
      <ul className="issue-list" data-testid={testId}>
        {issues.map((issue, index) => (
          <li key={`${issue.code}-${index}`} data-code={issue.code}>
            <span>{issue.message}</span>
            <IssueReferences issue={issue} />
          </li>
        ))}
      </ul>
    </div>
  )
}

export function LayoutReview({
  report,
  heading = 'Revisión de la planilla',
}: {
  report: LayoutReport
  heading?: string
}) {
  const errors = report.issues.filter((issue) => issue.severity === 'error')
  const warnings = report.issues.filter((issue) => issue.severity === 'warning')
  const infos = report.issues.filter((issue) => issue.severity === 'info')
  const mapped = report.columns.filter((column) => column.status === 'mapped')
  const ignored = report.columns.filter((column) => column.status !== 'mapped')
  const filled = new Map(report.fields.map((entry) => [entry.field, entry.filled_rows]))
  const missing = report.fields.filter((entry) => entry.column === null)
  const importable = errors.length === 0

  return (
    <section className="stack-tight layout-review" data-testid="layout-review">
      <h2>{heading}</h2>
      <p className="hint">
        Hoja «{report.sheet_name}»
        {report.header_row !== null && ` · encabezados en la fila ${report.header_row}`}
        {importable && ` · ${formatInteger(report.business_rows)} filas con PMF`} · lector{' '}
        {report.parser_version}
      </p>

      <div className="summary-grid">
        <div>
          <b>{formatInteger(mapped.length)}</b>
          columnas reconocidas
        </div>
        <div>
          <b>{formatInteger(ignored.length + report.auxiliary_regions.length)}</b>
          columnas o regiones ignoradas
        </div>
        <div>
          <b>{formatInteger(warnings.length)}</b>
          advertencias
        </div>
        <div>
          <b>{formatInteger(errors.length)}</b>
          errores que bloquean
        </div>
      </div>

      {errors.length > 0 && (
        <IssueGroup
          title="Bloquea la importación"
          tone="error"
          issues={errors}
          testId="layout-errors"
        />
      )}
      {warnings.length > 0 && (
        <IssueGroup
          title="Requiere revisión antes de publicar"
          tone="warn"
          issues={warnings}
          testId="layout-warnings"
        />
      )}

      <details className="review-details">
        <summary>Columnas reconocidas ({formatInteger(mapped.length)})</summary>
        <div className="tablewrap short">
          <table data-testid="layout-mapped">
            <thead>
              <tr>
                <th scope="col">Columna</th>
                <th scope="col">Encabezado en la planilla</th>
                <th scope="col">Campo en la plataforma</th>
                <th scope="col" className="numeric">
                  Filas con dato
                </th>
                <th scope="col">Nota</th>
              </tr>
            </thead>
            <tbody>
              {mapped.map((column) => (
                <tr key={column.column}>
                  <td>{column.column}</td>
                  <td>{column.header}</td>
                  <td>
                    <code>{column.field}</code>
                  </td>
                  <td className="numeric">
                    {importable && column.field
                      ? formatInteger(filled.get(column.field) ?? 0)
                      : '—'}
                  </td>
                  <td>{column.note ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {missing.length > 0 && (
          <p className="hint">
            Sin columna en esta planilla: {missing.map((entry) => `«${entry.header}»`).join(', ')}.
          </p>
        )}
      </details>

      {(ignored.length > 0 || report.auxiliary_regions.length > 0) && (
        <details className="review-details">
          <summary>
            Ignorado ({formatInteger(ignored.length + report.auxiliary_regions.length)})
          </summary>
          <ul className="issue-list" data-testid="layout-ignored">
            {ignored.map((column) => (
              <li key={column.column}>
                <span>
                  <b>{column.column}</b>
                  {column.header ? ` «${column.header}»` : ''} —{' '}
                  {STATUS_LABELS[column.status] ?? column.status}
                </span>
                {column.note && <span className="issue-refs">{column.note}</span>}
              </li>
            ))}
            {report.auxiliary_regions.map((region) => (
              <li key={region.first_column}>
                <span>
                  <b>
                    {region.first_column}–{region.last_column}
                  </b>{' '}
                  — región auxiliar ({formatInteger(region.column_count)} columnas)
                </span>
                <span className="issue-refs">{region.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {infos.length > 0 && (
        <details className="review-details">
          <summary>Observaciones registradas ({formatInteger(infos.length)})</summary>
          <ul className="issue-list" data-testid="layout-infos">
            {infos.map((issue, index) => (
              <li key={`${issue.code}-${index}`}>
                <span>{issue.message}</span>
                <IssueReferences issue={issue} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
