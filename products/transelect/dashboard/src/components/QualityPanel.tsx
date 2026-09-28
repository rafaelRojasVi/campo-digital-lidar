/**
 * TR-FUNC-014 / 015 / 016 — what to review in the published workbook.
 *
 * Written for the operators and for Javier, not for whoever wrote the rules:
 * each finding leads with what was found, how many plans or rows it touches
 * and what someone should check in the planilla. The exact calculation, the
 * source column names and the API's rule identifier sit in each finding's
 * «Cómo se calcula» detail, closed by default, for audit.
 *
 * The numbers are the API's, unchanged: 014 counts rows with a blank
 * `ID_Predo_Unico`; 015 counts PMFs whose first source row has no
 * `N Ingreso` (the same first-row choice as the status figures); the
 * conflicting-status count is the length of the API's conflict list; 016 is a
 * permanent literal, because the source has no resolution-number column.
 *
 * A finding reading zero renders calm; only a non-zero count escalates. The
 * tone is never the only signal — the count and its consequence are text.
 */
import type { TranselecFilterState, TranselecSummary } from '../api'
import { formatInteger } from '../format'
import { searchFromFilters } from '../lib/filterUrl'
import { PREDIO_DEFINITION } from '../lib/rules'
import { Link, ROUTES } from '../router'
import { HowCalculated } from '../ui/HowCalculated'

export function QualityPanel({
  summary,
  filters,
}: {
  summary: TranselecSummary
  /** Carried into the links, so a finding opens under the same scope. */
  filters?: TranselecFilterState
}) {
  const sinId = summary.calidad_filas_sin_id_predial_unico
  const sinIngreso = summary.calidad_pmf_sin_numero_ingreso
  const conflicts = summary.calidad_pmf_estado_resumido_conflictivo.length
  const search = filters ? searchFromFilters(filters) : ''

  return (
    <div data-testid="quality-panel">
      <ul className="quality" aria-label="Hallazgos de calidad">
        <li
          className="quality-item"
          data-tone={sinIngreso > 0 ? 'warn' : 'calm'}
          data-finding="sin-ingreso"
        >
          <p className="quality-headline">
            <b data-testid="quality-sin-ingreso">{formatInteger(sinIngreso)}</b>
            <span>PMF sin N.º de ingreso</span>
          </p>
          <p className="quality-what">
            {sinIngreso === 0
              ? 'Todos los planes del alcance tienen N.º de ingreso.'
              : sinIngreso === 1
                ? 'Ese plan no se puede vincular a un expediente CONAF.'
                : 'Esos planes no se pueden vincular a un expediente CONAF.'}
          </p>
          {sinIngreso > 0 && (
            <>
              <p className="quality-todo">
                <b>Qué revisar:</b> completar «N Ingreso» en la planilla, o confirmar que el plan
                todavía no se ha presentado.
              </p>
              <Link to={`${ROUTES.pendientes}${search}`} className="quality-go">
                Ver en Pendientes →
              </Link>
            </>
          )}
          <HowCalculated testId="how-sin-ingreso">
            <p>
              Cada PMF se cuenta una sola vez. Entra en el conteo si la columna{' '}
              <span className="source-col">N Ingreso</span> está vacía en su primera fila de la
              hoja «Resumen» (la de número de fila más bajo): el mismo criterio de «primera fila»
              que usan las cifras de estado (
              <code className="basis-tag" translate="no">
                {summary.basis_estado_resumido}
              </code>
              ).
            </p>
          </HowCalculated>
        </li>

        <li
          className="quality-item"
          data-tone={conflicts > 0 ? 'warn' : 'calm'}
          data-finding="conflictos"
        >
          <p className="quality-headline">
            <b data-testid="quality-conflictos">{formatInteger(conflicts)}</b>
            <span>PMF con estados distintos entre sus filas</span>
          </p>
          <p className="quality-what">
            {conflicts > 0
              ? 'Sus filas no dicen lo mismo en «Estado resumido». En las cifras cada uno se cuenta una vez, con el estado de su primera fila.'
              : 'Cada plan tiene el mismo «Estado resumido» en todas sus filas.'}
          </p>
          {conflicts > 0 && (
            <>
              <p className="quality-todo">
                <b>Qué revisar:</b> confirmar cuál es el estado correcto y corregir las demás
                filas.
              </p>
              <a href="#conflict-title" className="quality-go">
                Ver cuáles son ↓
              </a>
            </>
          )}
        </li>

        <li className="quality-item" data-tone={sinId > 0 ? 'warn' : 'calm'} data-finding="sin-id">
          <p className="quality-headline">
            <b data-testid="quality-sin-id">{formatInteger(sinId)}</b>
            <span>{sinId === 1 ? 'fila sin ID predial único' : 'filas sin ID predial único'}</span>
          </p>
          <p className="quality-what">
            {sinId === 0
              ? 'Todas las filas del alcance tienen identificador de predio.'
              : sinId === 1
                ? 'Esa fila no se puede atribuir con seguridad a un predio identificado.'
                : 'Esas filas no se pueden atribuir con seguridad a un predio identificado.'}
          </p>
          {sinId > 0 && (
            <p className="quality-todo">
              <b>Qué revisar:</b> completar el identificador del predio en esas filas de la
              planilla.
            </p>
          )}
          <HowCalculated testId="how-sin-id">
            <p>
              Se cuentan filas (no PMF ni predios) cuya columna{' '}
              <span className="source-col">ID_Predo_Unico</span> está vacía. {PREDIO_DEFINITION}{' '}
              Por eso una fila sin identificador puede terminar contada como un predio aparte.
            </p>
          </HowCalculated>
        </li>

        <li className="quality-item" data-tone="calm" data-finding="resolucion">
          <p className="quality-headline">
            <b data-testid="quality-resolucion">{summary.calidad_numero_resolucion}</b>
            <span>campo N.º de resolución</span>
          </p>
          <p className="quality-what">
            La planilla no tiene una columna de N.º de resolución, así que este control no se
            puede hacer.
          </p>
        </li>
      </ul>
    </div>
  )
}
