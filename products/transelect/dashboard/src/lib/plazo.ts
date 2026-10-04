/**
 * `plazo_conaf_90_habiles_v1` in Spanish, for the «Estado» table, the drawer
 * and Calidad.
 *
 * The count is the server's (`transelec_ingestion/plazo_conaf.py`): 90
 * business days — Monday to Friday without Chile's national holidays — from
 * the most recent ingreso, with «today» the server's date in Chile. This
 * module only words it. Provisional until Campo Digital answers when CONAF's
 * term starts and whether it pauses (spec 2026-10-04, open questions).
 */
import type { PlazoEstado, PlazoPmf, TranselecPlazos } from '../api'
import { formatDate, formatInteger } from '../format'

export const PLAZO_ESTADO_LABELS: Record<PlazoEstado, string> = {
  vencido: 'Vencido',
  por_vencer: 'Por vencer',
  en_plazo: 'En plazo',
  sin_fecha: 'Sin fecha',
  sin_fecha_texto: 'Sin fecha legible',
  conflicto: 'Fechas distintas',
  no_aplica: 'No aplica',
}

/** The existing `.pill-*` tones. */
export const PLAZO_ESTADO_PILL: Record<PlazoEstado, string> = {
  vencido: 'pill-pendiente',
  por_vencer: 'pill-en-tramite',
  en_plazo: 'pill-aprobado',
  sin_fecha: 'pill-otro',
  sin_fecha_texto: 'pill-otro',
  conflicto: 'pill-otro',
  no_aplica: 'pill-tachado',
}

const BASE_FIELD_LABELS: Record<NonNullable<PlazoPmf['base_field']>, string> = {
  fecha_ingreso_2: 'Fecha de ingreso2',
  fecha_ingreso: 'Fecha de ingreso1',
}

function habiles(count: number): string {
  return `${formatInteger(count)} ${count === 1 ? 'día hábil' : 'días hábiles'}`
}

function calendarDays(count: number): string {
  return `${formatInteger(count)} ${count === 1 ? 'día' : 'días'}`
}

/** «vence el …», «vence hoy», «venció el …», or why there is no count. */
export function plazoText(plazo: PlazoPmf): string {
  switch (plazo.estado) {
    case 'no_aplica':
      return 'Proceso cerrado'
    case 'sin_fecha':
      return 'Sin fecha de ingreso'
    case 'sin_fecha_texto':
      return `«${BASE_FIELD_LABELS[plazo.base_field ?? 'fecha_ingreso']}» no se pudo leer como una fecha`
    case 'conflicto':
      return 'Las filas del PMF tienen fechas de ingreso distintas'
    case 'vencido': {
      const since = -(plazo.remaining_business_days ?? 0)
      const ended = `venció el ${formatDate(plazo.deadline)}`
      return since > 0 ? `${ended} · hace ${habiles(since)}` : ended
    }
    default: {
      const left = plazo.remaining_business_days ?? 0
      if (left === 0) return `vence hoy (${formatDate(plazo.deadline)})`
      return `vence el ${formatDate(plazo.deadline)} · ${left === 1 ? 'queda' : 'quedan'} ${habiles(left)}`
    }
  }
}

/** Which ingreso the clock started from, and its date. */
export function plazoBaseText(plazo: PlazoPmf): string {
  if (!plazo.base_field || !plazo.base_date) return '—'
  return `${BASE_FIELD_LABELS[plazo.base_field]} · ${formatDate(plazo.base_date)}`
}

/** The planilla's «90 dias» against the computed deadline. */
export function cruceText(plazo: PlazoPmf): string {
  switch (plazo.cruce) {
    case 'coincide':
      return 'Coincide con el cálculo'
    case 'difiere': {
      const difference = plazo.diferencia_dias ?? 0
      const side = difference < 0 ? 'antes' : 'después'
      return `Difiere: la planilla dice ${formatDate(plazo.planilla_90_dias)}, ${calendarDays(Math.abs(difference))} ${side} del cálculo`
    }
    case 'sin_dato':
      return 'La planilla no trae una fecha «90 dias» legible'
    default:
      return 'Sin cálculo con qué comparar'
  }
}

export function indexPlazos(data: TranselecPlazos | null): Map<string, PlazoPmf> {
  return new Map((data?.pmfs ?? []).map((entry) => [entry.pmf, entry]))
}

/** What the drawer needs about one PMF's term. */
export interface PlazoDetail {
  entry: PlazoPmf
  /** ISO date: the server's «today» in Chile. */
  observedOn: string
  calendarVersion: string
}

export function plazoDetail(data: TranselecPlazos | null, pmf: string): PlazoDetail | null {
  const entry = data?.pmfs.find((candidate) => candidate.pmf === pmf)
  if (!data || !entry) return null
  return { entry, observedOn: data.observed_on, calendarVersion: data.calendar.version }
}
