/**
 * TR-FUNC-013 — "Estado por tipo de propietario".
 *
 * This is the table whose status rule genuinely disagrees with the KPI
 * row's: `owner_stage_legacy` overrides `Estado resumido` with "Rechazado"
 * whenever the raw `Estado` contains "rechaz", so the same predio can be
 * "En trámite" in the hero above and "Rechazado" here. That is Javier's own
 * current behavior, reproduced rather than reconciled — and the design doc
 * requires the rule to be *shown*, not hidden. It is shown twice over: in
 * plain words (the note, and «¿Por qué no coincide?» below the table) and
 * exactly (the «Cómo se calcula» detail, which names the source columns and
 * the API's rule identifier).
 */
import type { TranselecOwnerStatus, TranselecSummary } from '../api'
import { formatInteger, formatPercent } from '../format'
import { buildOwnerStatusTable, type OwnerStatusTable as OwnerTable } from '../lib/ownerStatus'
import { HowCalculated } from '../ui/HowCalculated'

function signed(value: number): string {
  if (value === 0) return '0'
  return value > 0 ? `+${formatInteger(value)}` : `−${formatInteger(-value)}`
}

/**
 * Why this table and the main status disagree, stated for the reader and
 * then shown side by side.
 *
 * Both columns come straight from the API responses the page already holds
 * (`summary.estado_resumido_hero_predio` and this table's own totals), under
 * the same filters and the same one-row-per-predio choice; nothing here
 * recomputes a status. Under the current rules the two differ by the
 * «rechaz» override, plus any predio whose «Estado resumido» is literally
 * «Rechazado» (the main status has no such category and counts it as «sin
 * estado»). The «Rechazado» row therefore has no counterpart on the left.
 */
function OwnerStatusComparison({
  summary,
  table,
}: {
  summary: TranselecSummary
  table: OwnerTable
}) {
  const hero = summary.estado_resumido_hero_predio
  const heroRest = hero.pendiente + hero.tachado + hero.sin_estado
  const heroTotal = hero.aprobado + hero.en_tramite + heroRest
  const rows = [
    { label: 'Aprobado', main: hero.aprobado, owner: table.total.approved },
    { label: 'En trámite', main: hero.en_tramite, owner: table.total.progress },
    { label: 'Rechazado', main: null, owner: table.total.rejected },
    { label: 'Pendiente, tachado o sin estado', main: heroRest, owner: table.total.pending },
  ]

  return (
    <div className="owner-why" data-testid="owner-why">
      <h3>¿Por qué esta tabla no coincide con el estado principal?</h3>
      <ol className="owner-why-list">
        <li>
          <b>Cuenta predios, no planes.</b> El estado principal del Resumen cuenta{' '}
          {formatInteger(summary.pmf_count)} PMF; esta tabla cuenta{' '}
          {formatInteger(table.total.total)} predios, y un plan puede abarcar varios predios.
        </li>
        <li>
          <b>Toma los rechazos de otra columna.</b> Si la columna «Estado» de un predio menciona
          un rechazo, aquí se cuenta como «Rechazado» aunque su «Estado resumido» diga otra cosa.
          En el alcance actual eso ocurre en{' '}
          <b data-testid="owner-why-rejected">{formatInteger(table.total.rejected)}</b>{' '}
          {table.total.rejected === 1 ? 'predio' : 'predios'}.
        </li>
        <li>
          <b>Ninguna de las dos cifras se corrige aquí.</b> Cuál debe usarse para informar es una
          decisión pendiente de Campo Digital.
        </li>
      </ol>
      <div className="tablewrap short">
        <table className="breakdown owner-compare">
          <caption className="sr-only">
            Predios por estado: según «Estado resumido» y según la tabla por propietario.
          </caption>
          <thead>
            <tr>
              <th scope="col">Predios</th>
              <th scope="col" className="numeric">
                Según «Estado resumido»
              </th>
              <th scope="col" className="numeric">
                En la tabla por propietario
              </th>
              <th scope="col" className="numeric">
                Diferencia
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                <td className="numeric">
                  {row.main === null ? (
                    <span className="muted" title="El estado principal no tiene la categoría «Rechazado»">
                      no aplica
                    </span>
                  ) : (
                    formatInteger(row.main)
                  )}
                </td>
                <td className="numeric">{formatInteger(row.owner)}</td>
                <td className="numeric">{signed(row.owner - (row.main ?? 0))}</td>
              </tr>
            ))}
            <tr className="total">
              <th scope="row">Total de predios</th>
              <td className="numeric">{formatInteger(heroTotal)}</td>
              <td className="numeric">{formatInteger(table.total.total)}</td>
              <td className="numeric">{signed(table.total.total - heroTotal)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function OwnerStatusTable({
  ownerStatus,
  summary,
}: {
  ownerStatus: TranselecOwnerStatus
  /** When given, the section also explains how it differs from the main status. */
  summary?: TranselecSummary
}) {
  const table = buildOwnerStatusTable(ownerStatus)

  return (
    <div data-testid="owner-status">
      <h2 id="owner-title">Estado por tipo de propietario</h2>
      <p className="hint" style={{ margin: 'var(--s-3) 0 var(--s-4)' }}>
        Predios del alcance seleccionado ({formatInteger(ownerStatus.total_predio_count)}),
        agrupados por tipo de propietario. Un predio con rechazo en su «Estado» se cuenta como
        «Rechazado», por lo que esta tabla puede clasificar un predio de forma distinta al resto
        del panel.
      </p>
      <div className="tablewrap short">
        <table className="ownerstatus">
          <thead>
            <tr>
              <th scope="col">Tipo de propietario</th>
              <th scope="col">Aprobados</th>
              <th scope="col">En trámite</th>
              <th scope="col">Rechazados</th>
              <th scope="col">Pend./tach.</th>
              <th scope="col">Total</th>
              <th scope="col">% aprobado</th>
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row) => (
              <tr key={row.tipoPropietario}>
                <td>{row.tipoPropietario}</td>
                <td className="ok">{formatInteger(row.approved)}</td>
                <td className="warn">{formatInteger(row.progress)}</td>
                <td className="bad">{formatInteger(row.rejected)}</td>
                <td>{formatInteger(row.pending)}</td>
                <td>
                  <b>{formatInteger(row.total)}</b>
                </td>
                <td className="ok">{formatPercent(row.approvedPercentage)}</td>
              </tr>
            ))}
            {table.rows.length === 0 && (
              <tr>
                <td colSpan={7} className="empty">
                  No hay predios para los filtros aplicados.
                </td>
              </tr>
            )}
            {table.rows.length > 0 && (
              <tr className="total">
                <td>TOTAL</td>
                <td className="ok">{formatInteger(table.total.approved)}</td>
                <td className="warn">{formatInteger(table.total.progress)}</td>
                <td className="bad">{formatInteger(table.total.rejected)}</td>
                <td>{formatInteger(table.total.pending)}</td>
                <td>
                  <b data-testid="owner-status-total">{formatInteger(table.total.total)}</b>
                </td>
                <td className="ok">{formatPercent(table.total.approvedPercentage)}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <HowCalculated bases={[table.basis]} testId="owner-how" />
      {summary && <OwnerStatusComparison summary={summary} table={table} />}
    </div>
  )
}
