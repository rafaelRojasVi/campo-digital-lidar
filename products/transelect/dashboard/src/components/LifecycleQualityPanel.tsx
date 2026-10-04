/**
 * Calidad: the PMFs `lifecycle_pmf_v1` could not place, and those whose rows
 * disagree on their status (spec 2026-10-04). Listed with their row and
 * reason so a person reads the planilla; nothing here is resolved.
 * The lifecycle wording is provisional until Campo Digital confirms it.
 */
import { EMPTY_FILTERS as EMPTY, type TranselecFilterState, type TranselecLifecycle } from '../api'
import { formatInteger } from '../format'
import { searchFromFilters } from '../lib/filterUrl'
import { LIFECYCLE_FLAG_LABELS, LIFECYCLE_REASON_LABELS, needsReview } from '../lib/lifecycle'
import { Link, ROUTES } from '../router'
import { HowCalculated } from '../ui/HowCalculated'

export function LifecycleQualityPanel({
  lifecycle,
  filters,
}: {
  lifecycle: TranselecLifecycle
  /** Carried into the links, so the finding opens under the same scope. */
  filters?: TranselecFilterState
}) {
  const review = lifecycle.rows.filter(needsReview)
  const search = filters ? searchFromFilters(filters) : ''

  return (
    <div data-testid="lifecycle-quality">
      <ul className="quality" aria-label="PMF que la regla de «Estado» no pudo clasificar">
        <li className="quality-item" data-tone={review.length > 0 ? 'warn' : 'calm'}>
          <p className="quality-headline">
            <b data-testid="lifecycle-review-count">{formatInteger(review.length)}</b>
            <span>PMF para revisar en «Estado» (provisional)</span>
          </p>
          {review.length === 0 ? (
            <p className="quality-what">
              Ningún PMF por revisar: la regla reconoce el estado de todos y sus filas coinciden.
            </p>
          ) : (
            <>
              <ul className="variant-list review-list" data-testid="lifecycle-review-list">
                {review.map((row) => (
                  <li
                    key={row.source_row_number}
                    data-testid={`lifecycle-review-${row.source_row_number}`}
                  >
                    <b>{row.pmf}</b> · fila {formatInteger(row.source_row_number)} ·{' '}
                    {[
                      row.lifecycle_reason ? LIFECYCLE_REASON_LABELS[row.lifecycle_reason] : null,
                      ...row.lifecycle_flags.map((flag) => LIFECYCLE_FLAG_LABELS[flag]),
                    ]
                      .filter(Boolean)
                      .join('. ')}{' '}
                    ·{' '}
                    <Link
                      to={`${ROUTES.estado}${
                        searchFromFilters({ ...(filters ?? EMPTY), q: row.pmf })
                      }`}
                      className="quality-go"
                    >
                      Buscar {row.pmf} en Estado
                    </Link>
                  </li>
                ))}
              </ul>
              <p className="quality-todo">
                <b>Qué revisar:</b> los valores de «Estado» y «Estado resumido» de esas filas en la
                planilla.
              </p>
              <Link to={`${ROUTES.estado}${search}`} className="quality-go">
                Ver en Estado →
              </Link>
            </>
          )}
          <HowCalculated bases={[lifecycle.basis]} testId="how-lifecycle-review" />
        </li>
      </ul>
    </div>
  )
}
