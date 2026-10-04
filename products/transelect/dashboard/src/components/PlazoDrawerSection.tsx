/**
 * «Plazo CONAF (90 días hábiles)» in the PMF drawer: where the clock started,
 * when it ends, the business days counted, and the planilla's own «90 dias»
 * beside the calculation. Everything is the server's
 * (`plazo_conaf_90_habiles_v1`); provisional wording.
 */
import { formatDate, formatInteger } from '../format'
import {
  PLAZO_ESTADO_LABELS,
  PLAZO_ESTADO_PILL,
  type PlazoDetail,
  cruceText,
  plazoBaseText,
  plazoText,
} from '../lib/plazo'
import { Fact } from './Fact'
import { LoadingBlock } from './StateViews'

export type PlazoDrawerStatus = 'loading' | 'error' | 'empty'

const TITLE = 'Plazo CONAF (90 días hábiles)'

function daysText(detail: PlazoDetail): string {
  const { elapsed_business_days: elapsed, remaining_business_days: remaining } = detail.entry
  if (elapsed === null || remaining === null) return '—'
  if (detail.entry.estado === 'vencido' && remaining === 0) {
    // Friday's deadline seen on a Saturday: nothing left, nothing counted past it.
    return `Venció el ${formatDate(detail.entry.deadline)} · ${formatInteger(elapsed)} días hábiles transcurridos`
  }
  if (remaining < 0) {
    return `${formatInteger(elapsed)} transcurridos · ${formatInteger(-remaining)} desde el vencimiento`
  }
  return `${formatInteger(elapsed)} transcurridos · ${formatInteger(remaining)} por transcurrir`
}

/** The block while the read is pending, failed, or has nothing for the PMF. */
export function PlazoDrawerNotice({ status }: { status: PlazoDrawerStatus }) {
  return (
    <section className="drawer-section" aria-labelledby="drawer-plazo-title" data-testid="drawer-plazo">
      <h3 id="drawer-plazo-title">{TITLE}</h3>
      {status === 'loading' && <LoadingBlock label="Calculando el plazo…" lines={2} />}
      {status === 'error' && (
        <p className="hint" role="status">
          No se pudo cargar el plazo de este PMF. El resto del detalle no cambia.
        </p>
      )}
      {status === 'empty' && <p className="hint">Este PMF no tiene plazo calculado.</p>}
    </section>
  )
}

export function PlazoDrawerSection({ detail }: { detail: PlazoDetail }) {
  const { entry } = detail
  return (
    <section className="drawer-section" aria-labelledby="drawer-plazo-title" data-testid="drawer-plazo">
      <h3 id="drawer-plazo-title">{TITLE}</h3>
      <dl className="facts">
        <Fact label="Estado del plazo">
          <span className={`pill ${PLAZO_ESTADO_PILL[entry.estado]}`}>
            {PLAZO_ESTADO_LABELS[entry.estado]}
          </span>{' '}
          <span className="hint">{plazoText(entry)}</span>
        </Fact>
        <Fact label="Cuenta desde">{plazoBaseText(entry)}</Fact>
        <Fact label="Vence">{entry.deadline ? formatDate(entry.deadline) : '—'}</Fact>
        <Fact label="Días hábiles">{daysText(detail)}</Fact>
        <Fact label="«90 dias» de la planilla" wide>
          {entry.planilla_90_dias ? formatDate(entry.planilla_90_dias) : 'Sin fecha'} ·{' '}
          {cruceText(entry)}
        </Fact>
      </dl>
      <p className="hint">
        Días hábiles: lunes a viernes sin feriados nacionales de Chile (calendario holidays{' '}
        {detail.calendarVersion}). Hoy es {formatDate(detail.observedOn)}, la fecha del servidor en
        Chile. Regla provisional hasta que Campo Digital confirme cuándo empieza el plazo.
      </p>
    </section>
  )
}
