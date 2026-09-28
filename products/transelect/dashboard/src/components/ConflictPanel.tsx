/**
 * PMFs the source gives more than one `Estado resumido`.
 *
 * This is the inconsistency behind the 29-Jul Power BI summary's arithmetic:
 * 101 approved + 56 in process + 3 struck out = 160, against a stated total
 * of 159, because one plan (MP015 there, MP022 in the 14-Aug workbook) is
 * counted in two buckets.
 *
 * The dashboard does not reproduce that total and does not hide the row that
 * causes it. Each conflicting PMF is counted once, under the value on its
 * first source row — the repository's existing first-row-wins contract — and
 * listed here with every value the source carried, so the choice is
 * inspectable and Javier can rule on it.
 */
import type { EstadoResumidoConflict, TranselecFilterState } from '../api'
import { searchFromFilters } from '../lib/filterUrl'
import { Link, ROUTES } from '../router'
import { HowCalculated } from '../ui/HowCalculated'

export function ConflictPanel({
  conflicts,
  basis,
  filters,
}: {
  conflicts: EstadoResumidoConflict[]
  basis: string
  filters: TranselecFilterState
}) {
  if (conflicts.length === 0) {
    return (
      <p className="empty" data-testid="conflicts-empty">
        Ningún PMF del alcance seleccionado tiene más de un «Estado resumido».
      </p>
    )
  }

  return (
    <div data-testid="conflicts">
      <div className="tablewrap">
        <table className="breakdown">
          <caption className="sr-only">
            PMF cuyas filas tienen distinto «Estado resumido», con el estado con que se cuentan
            en las cifras y la fila de la que sale.
          </caption>
          <thead>
            <tr>
              <th scope="col">PMF</th>
              <th scope="col">Estados en sus filas</th>
              <th scope="col">Se cuenta como</th>
              <th scope="col">«Estado» en esa fila</th>
              <th scope="col" className="numeric">
                Fila usada
              </th>
            </tr>
          </thead>
          <tbody>
            {conflicts.map((conflict) => (
              <tr key={conflict.pmf}>
                <td>
                  <Link
                    to={`${ROUTES.explorador}${searchFromFilters({ ...filters, q: conflict.pmf })}`}
                  >
                    {conflict.pmf}
                  </Link>
                </td>
                <td className="warn">
                  {conflict.valores.map((value) => value ?? 'Sin valor').join(' · ')}
                </td>
                <td data-testid={`conflict-canonical-${conflict.pmf}`}>
                  <b>{conflict.canonico ?? 'Sin valor'}</b>
                </td>
                <td>{conflict.estado_detalle ?? 'Sin valor'}</td>
                <td className="numeric">{conflict.source_row_number}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint" style={{ marginTop: 'var(--s-4)' }}>
        En todas las cifras cada uno de estos planes se cuenta una sola vez, con el estado de su
        primera fila. Falta que Campo Digital confirme qué estado corresponde a cada uno.
      </p>
      <HowCalculated bases={[basis]} testId="conflicts-how">
        <p>
          Si se sumaran los estados fila a fila, estos planes se contarían dos veces y el total
          superaría el número de PMF: es exactamente la diferencia entre 160 y 159 en el resumen
          de Power BI del 29 de julio.
        </p>
      </HowCalculated>
    </div>
  )
}
