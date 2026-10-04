/**
 * Calidad: PMFs whose planilla «90 dias» is not the date 90 business days
 * from their most recent ingreso (`plazo_conaf_90_habiles_v1`). Listed with
 * their row so a person reads the planilla; the planilla is never corrected.
 * The count is the server's PMF-level `cruce_difiere_count`; it is never
 * derived from the legacy row-level count.
 */
import { EMPTY_FILTERS, type TranselecFilterState, type TranselecPlazos } from '../api'
import { formatDate, formatInteger } from '../format'
import { searchFromFilters } from '../lib/filterUrl'
import { cruceText } from '../lib/plazo'
import { Link, ROUTES } from '../router'
import { HowCalculated } from '../ui/HowCalculated'

/** Longer lists stay short on the page; Estado has the rest. */
const LIST_CAP = 10

export function PlazoQualityPanel({
  plazos,
  filters,
}: {
  plazos: TranselecPlazos
  /** Carried into the link, so the finding opens under the same scope. */
  filters?: TranselecFilterState
}) {
  const differ = plazos.pmfs.filter((entry) => entry.cruce === 'difiere')
  const count = plazos.cruce_difiere_count
  const search = filters ? searchFromFilters(filters) : ''

  return (
    <div data-testid="plazo-quality">
      <ul className="quality" aria-label="PMF cuya fecha «90 dias» no coincide con el cálculo">
        <li className="quality-item" data-tone={count > 0 ? 'warn' : 'calm'}>
          <p className="quality-headline">
            <b data-testid="plazo-difiere-count">{formatInteger(count)}</b>
            <span>PMF cuya fecha «90 dias» no coincide con 90 días hábiles desde el ingreso</span>
          </p>
          {count === 0 ? (
            <p className="quality-what">
              En los PMF del alcance con fecha «90 dias» legible, la planilla coincide con el
              cálculo.
            </p>
          ) : (
            <>
              <ul className="variant-list review-list" data-testid="plazo-difiere-list">
                {differ.slice(0, LIST_CAP).map((entry) => (
                  <li
                    key={entry.source_row_number}
                    data-testid={`plazo-difiere-${entry.source_row_number}`}
                  >
                    <b>{entry.pmf}</b> · fila {formatInteger(entry.source_row_number)} ·{' '}
                    {cruceText(entry)}
                    {entry.deadline && <> (cálculo: {formatDate(entry.deadline)})</>} ·{' '}
                    <Link
                      to={`${ROUTES.estado}${searchFromFilters({ ...(filters ?? EMPTY_FILTERS), q: entry.pmf })}`}
                      className="quality-go"
                    >
                      Buscar {entry.pmf} en Estado
                    </Link>
                  </li>
                ))}
                {differ.length > LIST_CAP && (
                  <li className="hint">
                    y {formatInteger(differ.length - LIST_CAP)} más; véalos en Estado.
                  </li>
                )}
              </ul>
              <p className="quality-todo">
                <b>Qué revisar:</b> la columna «90 dias» y la fecha de ingreso de esas filas en la
                planilla. La diferencia puede venir de feriados, de un reingreso o de cómo se cuenta
                el día 1.
              </p>
              <Link to={`${ROUTES.estado}${search}`} className="quality-go">
                Ver en Estado →
              </Link>
            </>
          )}
          <HowCalculated bases={[plazos.basis]} testId="how-plazo-difiere" />
        </li>
      </ul>
    </div>
  )
}
