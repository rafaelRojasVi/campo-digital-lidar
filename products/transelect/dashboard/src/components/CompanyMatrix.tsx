/**
 * The company comparison, as a compact matrix beneath the overall result.
 *
 * Javier's 29-Jul summary gives Campo Digital and ECORES a full repeated
 * breakdown each — the same six figures, twice, in two separate blocks, with
 * the reader left to do the subtraction. One matrix with a total row does the
 * comparison the repetition was standing in for, and makes the arithmetic
 * checkable: the column totals are the headline's own buckets, so a reader
 * can verify the subtotals reconcile without leaving the page.
 *
 * A company is attributed per PMF, not per row, by the same first-row-wins
 * representative the headline uses — which is what makes the reconciliation
 * structural rather than a property of this particular workbook.
 */
import type { TranselecFilterState, TranselecSummary } from '../api'
import { formatInteger } from '../format'
import { searchFromFilters } from '../lib/filterUrl'
import { STATUS_ORDER, statusBuckets } from '../lib/statusHeadline'
import { Link, ROUTES } from '../router'

export function CompanyMatrix({
  summary,
  filters,
}: {
  summary: TranselecSummary
  filters: TranselecFilterState
}) {
  const buckets = statusBuckets(summary)
  const columns = STATUS_ORDER.filter((key) => buckets.some((bucket) => bucket.key === key))

  if (summary.por_empresa.length === 0) {
    return <p className="empty">Sin empresas informadas para el alcance seleccionado.</p>
  }

  return (
    <div className="tablewrap">
      <table className="breakdown" data-testid="company-matrix">
        <caption className="sr-only">
          Estado resumido de los planes de manejo por empresa. La fila TOTAL coincide con el
          encabezado de la página.
        </caption>
        <thead>
          <tr>
            <th scope="col">Empresa</th>
            <th scope="col" className="numeric">
              PMF
            </th>
            {columns.map((key) => (
              <th scope="col" className="numeric" key={key}>
                {buckets.find((bucket) => bucket.key === key)?.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {summary.por_empresa.map((company) => (
            <tr key={company.empresa ?? 'sin-empresa'}>
              <td>
                {company.empresa === null ? (
                  <span className="muted">Sin empresa informada</span>
                ) : (
                  <Link
                    to={`${ROUTES.explorador}${searchFromFilters({
                      ...filters,
                      empresa: [company.empresa],
                    })}`}
                  >
                    {company.empresa}
                  </Link>
                )}
              </td>
              <td className="numeric" data-testid={`empresa-${company.empresa ?? 'sin-empresa'}`}>
                {formatInteger(company.pmf_count)}
              </td>
              {columns.map((key) => (
                <td className="numeric" key={key}>
                  {formatInteger(company.estado_resumido[key])}
                </td>
              ))}
            </tr>
          ))}
          <tr className="total">
            <td>TOTAL</td>
            <td className="numeric" data-testid="empresa-total">
              <b>{formatInteger(summary.pmf_count)}</b>
            </td>
            {columns.map((key) => (
              <td className="numeric" key={key}>
                {formatInteger(summary.estado_resumido_pmf[key])}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  )
}
