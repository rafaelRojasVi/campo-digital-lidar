/**
 * The Resumen's first analytical section: "Estado de los planes de manejo".
 *
 * The composition is deliberately flat — one total, one horizontal bar, one
 * row of aligned status cards — rather than a doughnut. Three or four
 * part-to-whole values whose counts are printed beside them gain nothing from
 * an arc, and a reader comparing "48 en trámite" against "108 aprobados"
 * reads the numbers, not the slices.
 *
 * Every card states its own population and is a real link into the
 * Explorador, filtered to the literal source values that produced it, with
 * the reader's existing filters preserved.
 */
import type { TranselecFilterState, TranselecSummary } from '../api'
import { formatInteger, formatNumber } from '../format'
import { searchFromFilters } from '../lib/filterUrl'
import {
  bucketFilters,
  bucketsReconcile,
  statusBuckets,
  statusSegments,
  type StatusBucket,
} from '../lib/statusHeadline'
import { Link, ROUTES } from '../router'
import { CompositionBar } from '../ui/CompositionBar'
import { HowCalculated } from '../ui/HowCalculated'

function bucketHref(filters: TranselecFilterState, bucket: StatusBucket): string {
  return `${ROUTES.explorador}${searchFromFilters(bucketFilters(filters, bucket))}`
}

export function StatusHeadline({
  summary,
  filters,
}: {
  summary: TranselecSummary
  filters: TranselecFilterState
}) {
  const buckets = statusBuckets(summary)
  const reconciles = bucketsReconcile(buckets, summary.pmf_count)
  const conflicts = summary.calidad_pmf_estado_resumido_conflictivo

  return (
    <section className="lead-block" aria-labelledby="estado-title" data-testid="status-headline">
      <div className="lead-figure">
        <div className="figure lead">
          <div className="figure-value">
            <span data-testid="kpi-pmf-total">{formatInteger(summary.pmf_count)}</span>
          </div>
          <div className="figure-label">planes de manejo (PMF)</div>
          <div className="figure-note">
            {formatInteger(summary.row_count)} filas de detalle en el alcance seleccionado
          </div>
        </div>
      </div>

      <div className="compositions">
        <h2 id="estado-title">Estado de los planes de manejo</h2>
        <CompositionBar
          noun="PMF"
          testId="status-pmf"
          lead={false}
          segments={statusSegments(buckets)}
        />

        <div className="status-cards" data-testid="status-cards">
          {buckets.map((bucket) =>
            bucket.filterValues.length > 0 ? (
              <Link
                key={bucket.key}
                to={bucketHref(filters, bucket)}
                className="status-card"
                data-tone={bucket.tone}
                data-status={bucket.key}
              >
                <span className="status-card-value" data-testid={`status-${bucket.key}`}>
                  {formatInteger(bucket.count)}
                </span>
                <span className="status-card-label">{bucket.label}</span>
                <span className="status-card-sub">
                  {formatNumber(bucket.percentage)}% de {formatInteger(summary.pmf_count)} PMF
                </span>
                <span className="status-card-go">Ver en el explorador →</span>
              </Link>
            ) : (
              <div
                key={bucket.key}
                className="status-card"
                data-tone={bucket.tone}
                data-status={bucket.key}
              >
                <span className="status-card-value" data-testid={`status-${bucket.key}`}>
                  {formatInteger(bucket.count)}
                </span>
                <span className="status-card-label">{bucket.label}</span>
                <span className="status-card-sub">
                  {formatNumber(bucket.percentage)}% de {formatInteger(summary.pmf_count)} PMF
                </span>
                <span className="status-card-go">Sin valor de origen que filtrar</span>
              </div>
            ),
          )}
        </div>

        {!reconciles && (
          <p className="hint" data-testid="status-reconciliation-warning" data-tone="warn">
            Los estados no suman el total de PMF del alcance seleccionado. No use estas cifras
            hasta revisar la sección Calidad.
          </p>
        )}

        {conflicts.length > 0 && (
          <p className="hint" data-testid="status-conflict-note">
            {formatInteger(conflicts.length)}{' '}
            {conflicts.length === 1 ? 'PMF tiene' : 'PMF tienen'} filas con distinto «Estado
            resumido» ({conflicts.map((conflict) => conflict.pmf).join(', ')}). Cada uno se cuenta
            una sola vez, con el estado de su primera fila.{' '}
            <Link to={ROUTES.calidad}>Ver el detalle en Calidad</Link>.
          </p>
        )}

        <HowCalculated bases={[summary.basis_estado_resumido]} testId="status-how" />
      </div>
    </section>
  )
}
