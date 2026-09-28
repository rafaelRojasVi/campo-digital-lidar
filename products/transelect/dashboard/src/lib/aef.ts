/**
 * Display vocabulary for the AEF tracking block (contract V2).
 *
 * On a row, the five fields are that row's source values. PMF-level values
 * are resolved by the server (`TranselecAef.pmfs`) with the rows that
 * supplied them; nothing here fills a blank row from a sibling row, or
 * interprets what an AEF value means beyond its literal text — the source
 * does not establish that, so the dashboard does not either.
 */
import type { ChronologyFlag, ResumenRow } from '../api'

export const AEF_FIELDS = [
  'aef',
  'quien_solicita',
  'fecha_solicitud',
  'fecha_corta',
  'fecha_termino',
] as const

export type AefField = (typeof AEF_FIELDS)[number]

export const AEF_FIELD_LABELS: Record<AefField, string> = {
  aef: 'AEF',
  quien_solicita: 'Quién solicita',
  fecha_solicitud: 'Fecha solicitud',
  fecha_corta: 'Fecha corta',
  fecha_termino: 'Fecha término',
}

export const CHRONOLOGY_LABELS: Record<ChronologyFlag, string> = {
  cronologia_corta_antes_de_solicitud: 'Fecha corta anterior a la solicitud',
  cronologia_termino_antes_de_corta: 'Fecha término anterior a la corta',
  cronologia_termino_antes_de_solicitud: 'Fecha término anterior a la solicitud',
}

export function chronologyLabel(flag: string): string {
  return CHRONOLOGY_LABELS[flag as ChronologyFlag] ?? flag
}

/**
 * A row's chronology flags, tolerating a response that omits the list: a
 * missing list means "nothing flagged", never a crash of the whole table.
 */
export function chronologyFlagsOf(row: ResumenRow): readonly ChronologyFlag[] {
  return row.chronology_flags ?? []
}

/** True when the row carries any of the five AEF tracking values. */
export function hasAefTracking(row: ResumenRow): boolean {
  return AEF_FIELDS.some((field) => (row[field] ?? '').trim() !== '')
}

/**
 * Whether the published version's source had AEF columns at all.
 *
 * `null` while unknown (the active-version read has not resolved). Callers
 * must not render "sin registro" for a version whose workbook never had the
 * columns: that would state a fact about rows the source never described.
 */
export function aefInSource(sourceFields: readonly string[] | null | undefined): boolean | null {
  if (!sourceFields) return null
  return AEF_FIELDS.some((field) => sourceFields.includes(field))
}
