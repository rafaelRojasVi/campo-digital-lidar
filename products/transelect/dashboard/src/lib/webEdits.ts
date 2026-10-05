/**
 * Web edits, front-end side: the editable fields in the drawer's reading
 * order, labels, tooltips and the datalist suggestions.
 *
 * Mirrors `transelec_ingestion.field_overrides.EDITABLE_FIELDS`; the server
 * is the authority and re-checks every save.
 */
import {
  EMPTY_FILTERS,
  type EditableFieldName,
  type OverrideStatus,
  type ResumenRow,
  type TranselecOverride,
} from '../api'
import { formatDate } from '../format'
import { collectAllRows } from './rowCollection'

export interface EditableFieldSpec {
  name: EditableFieldName
  label: string
  kind: 'text' | 'date'
  /** Offer the values present in the published version as suggestions. */
  suggest: boolean
}

export const EDITABLE_FIELDS: readonly EditableFieldSpec[] = [
  { name: 'estado_resumido', label: 'Estado resumido', kind: 'text', suggest: true },
  { name: 'estado', label: 'Estado vigente', kind: 'text', suggest: true },
  { name: 'tipo_rechazo', label: 'Motivo', kind: 'text', suggest: true },
  { name: 'reingreso_tec', label: 'Reingreso técnico', kind: 'text', suggest: false },
  { name: 'reingreso_legal', label: 'Reingreso legal', kind: 'text', suggest: false },
  { name: 'reingreso_recrep', label: 'Reingreso rec. reposición', kind: 'text', suggest: false },
  { name: 'numero_ingreso', label: 'N.º ingreso', kind: 'text', suggest: false },
  { name: 'fecha_ingreso', label: 'Fecha ingreso', kind: 'date', suggest: false },
  { name: 'numero_ingreso_2', label: 'N.º ingreso 2', kind: 'text', suggest: false },
  { name: 'fecha_ingreso_2', label: 'Fecha ingreso 2', kind: 'date', suggest: false },
  { name: 'fecha_90_dias', label: '90 días', kind: 'date', suggest: false },
]

export const STATUS_LABELS: Record<OverrideStatus, string> = {
  aplicada: 'Aplicada',
  incorporada: 'Ya está en la planilla',
  en_conflicto: 'En conflicto con la planilla',
  huerfana: 'Sin fila en la versión publicada',
}

export function specFor(field: EditableFieldName): EditableFieldSpec {
  const spec = EDITABLE_FIELDS.find((entry) => entry.name === field)
  if (!spec) throw new Error(`unknown editable field ${field}`)
  return spec
}

export function isWebField(row: Pick<ResumenRow, 'web_fields'>, field: EditableFieldName): boolean {
  return (row.web_fields ?? []).includes(field)
}

const FIELD_LIST = new Intl.ListFormat('es', { type: 'conjunction' })

/** «N.º ingreso 2 editado en la web»; several fields joined with «y». */
export function webFieldsDescription(fields: readonly EditableFieldName[]): string {
  const labels = fields.map((field) => specFor(field).label)
  return `${FIELD_LIST.format(labels)} ${labels.length === 1 ? 'editado' : 'editados'} en la web`
}

/** The fields among `fields` this row shows as edited on the web, in that order. */
export function editedAmong(
  row: Pick<ResumenRow, 'web_fields'>,
  fields: readonly EditableFieldName[],
): EditableFieldName[] {
  return fields.filter((field) => isWebField(row, field))
}

export function displayValue(spec: EditableFieldSpec, value: string | null | undefined): string {
  if (value == null || value.trim() === '') return ''
  return spec.kind === 'date' ? formatDate(value) : value
}

const SANTIAGO_DATE = new Intl.DateTimeFormat('es-CL', {
  timeZone: 'America/Santiago',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})

/** dd-mm-aaaa of an edit timestamp in America/Santiago (same zone as the Excel note). */
export function formatEditDate(iso: string): string {
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return formatDate(iso)
  const parts = SANTIAGO_DATE.formatToParts(parsed)
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value ?? ''
  return `${part('day')}-${part('month')}-${part('year')}`
}

export function webTooltip(override: TranselecOverride | undefined, spec: EditableFieldSpec): string {
  if (!override) return 'Editado en la web'
  const before = displayValue(spec, override.planilla_value_at_edit) || '(vacía)'
  return `Editado en la web por ${override.created_by_display_name} · ${formatEditDate(override.created_at)} · en la planilla: ${before}`
}

export function overrideFor(
  overrides: readonly TranselecOverride[],
  row: Pick<ResumenRow, 'source_row_number'>,
  field: EditableFieldName,
): TranselecOverride | undefined {
  return overrides.find(
    (entry) =>
      entry.field === field &&
      entry.source_row_number === row.source_row_number &&
      entry.status === 'aplicada',
  )
}

/** Spacing as the server compares it: NBSP is a space, runs collapse, ends trim. */
function spaced(value: string): string {
  return value.replace(/\u00a0/g, ' ').trim().replace(/\s+/g, ' ')
}

/** Two spellings of one value share this key: case, accents and spacing ignored. */
export function suggestionKey(value: string): string {
  return spaced(value).normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase('es')
}

/**
 * One suggestion per value of `field` in `rows`, ignoring case, accents and
 * spacing (indicator spec §10): each group shows the spelling the rows use
 * most, ties going to the first in Spanish order. Picking one writes it as
 * shown; typing any other value is still allowed, and the server's own
 * comparison rules are unchanged.
 */
export function suggestionsFrom(rows: readonly ResumenRow[], field: EditableFieldName): string[] {
  const groups = new Map<string, Map<string, number>>()
  for (const row of rows) {
    const spelling = spaced(row[field] ?? '')
    if (!spelling) continue
    const key = suggestionKey(spelling)
    const counts = groups.get(key) ?? new Map<string, number>()
    counts.set(spelling, (counts.get(spelling) ?? 0) + 1)
    groups.set(key, counts)
  }
  const byUseThenOrder = ([a, uses]: [string, number], [b, other]: [string, number]) =>
    other - uses || a.localeCompare(b, 'es')
  return [...groups.values()]
    .map((counts) => [...counts.entries()].sort(byUseThenOrder)[0][0])
    .sort((a, b) => a.localeCompare(b, 'es'))
}

let suggestionCache: { importId: number; values: Partial<Record<EditableFieldName, string[]>> } | null =
  null

/** Distinct values per suggestible field of the published version, cached per version. */
export async function loadSuggestions(
  importId: number,
): Promise<Partial<Record<EditableFieldName, string[]>>> {
  if (suggestionCache?.importId === importId) return suggestionCache.values
  const result = await collectAllRows(EMPTY_FILTERS)
  if (!result.ok) return {}
  const values: Partial<Record<EditableFieldName, string[]>> = {}
  for (const spec of EDITABLE_FIELDS) {
    if (spec.suggest) values[spec.name] = suggestionsFrom(result.rows, spec.name)
  }
  suggestionCache = { importId, values }
  return values
}

/** Test seam. */
export function resetSuggestionCache(): void {
  suggestionCache = null
}
