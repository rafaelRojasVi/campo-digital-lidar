/**
 * "Reforestación" — what the source can answer, and what it cannot.
 *
 * Marianne asked two questions here: how many reforestation properties, and
 * how many reforestation owners. The workbook answers neither cleanly, and
 * this panel says so rather than producing a confident number.
 *
 *  - The property figure is a count of distinct `Predio Ref` *labels*, with
 *    the literal `Sin reforestacion` excluded, and the definition printed
 *    beside it. Some labels name more than one property
 *    ("Ref036_ Reyes y Ref037_ Reyes"), so the count is listed as a label
 *    count and the composite labels are shown.
 *  - The owner figure does not exist. `Tipo de propietario` is a tenure
 *    category shared by hundreds of rows, and the surnames inside
 *    `Predio Ref` are free text. So the owner slot carries the API's literal
 *    rather than a number — and deliberately not a zero, which would read as
 *    "there are no owners".
 */
import type { Reforestacion } from '../api'
import { formatInteger } from '../format'
import { HowCalculated } from '../ui/HowCalculated'

export function ReforestacionPanel({ reforestacion }: { reforestacion: Reforestacion }) {
  return (
    <div data-testid="reforestacion-panel">
      <div className="stat-strip">
        <div className="stat" data-stat="ref-predios">
          <span className="stat-label">Etiquetas de «Predio Ref»</span>
          <span className="stat-value" data-testid="kpi-ref-predios">
            {formatInteger(reforestacion.predio_ref_count)}
          </span>
          <span className="stat-sub">
            valores distintos, sin «{reforestacion.sentinel_label}»
          </span>
        </div>
        <div className="stat" data-stat="ref-roles">
          <span className="stat-label">Roles de referencia</span>
          <span className="stat-value" data-testid="kpi-ref-roles">
            {formatInteger(reforestacion.rol_ref_count)}
          </span>
          <span className="stat-sub">valores distintos de «Rol Ref»</span>
        </div>
        <div className="stat" data-stat="ref-propietarios">
          <span className="stat-label">Propietarios de reforestación</span>
          <span className="stat-value" data-testid="kpi-ref-propietarios">
            {reforestacion.propietarios}
          </span>
          <span className="stat-sub">la planilla no tiene un campo de propietario</span>
        </div>
      </div>

      <p className="hint" style={{ marginTop: 'var(--s-4)' }} data-testid="reforestacion-definition">
        {reforestacion.definicion}
      </p>

      {reforestacion.sentinel_row_count > 0 && (
        <p className="hint">
          {formatInteger(reforestacion.sentinel_row_count)}{' '}
          {reforestacion.sentinel_row_count === 1 ? 'fila declara' : 'filas declaran'} «
          {reforestacion.sentinel_label}»: ausencia de reforestación, no un predio, por lo que no
          se cuenta.
        </p>
      )}

      {reforestacion.etiquetas_compuestas.length > 0 && (
        <p className="hint" data-testid="reforestacion-composite">
          {formatInteger(reforestacion.etiquetas_compuestas.length)} etiquetas nombran más de un
          predio ({reforestacion.etiquetas_compuestas.join(' · ')}), por lo que el conteo de
          etiquetas es menor que el número real de predios. Es una cota inferior: una etiqueta
          puede nombrar varios predios sin separador.
        </p>
      )}

      <p className="hint">
        Para saber con certeza cuántos predios y cuántos propietarios de reforestación hay, la
        planilla tendría que identificar cada predio de reforestación y a su propietario (o
        propietarios) en columnas propias. Hoy solo tiene un texto libre por fila.
      </p>
      <HowCalculated testId="reforestacion-how">
        <p>
          Columnas que se proponen a Campo Digital (preguntas abiertas en la documentación de
          diseño):{' '}
          <code translate="no">id_predio_reforestacion</code>,{' '}
          <code translate="no">id_propietario_reforestacion</code> y{' '}
          <code translate="no">nombre_propietario_reforestacion</code>, con una asociación que
          admita más de un propietario por predio.
        </p>
      </HowCalculated>
    </div>
  )
}
