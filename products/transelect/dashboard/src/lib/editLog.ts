/**
 * The edits log's wording (indicator spec §4-§6): the pill's text, each
 * entry's state label, its date in Chile time and where it links. Pure, so
 * the header popover and the «Historial» in Ediciones web read the same.
 */
import {
  EMPTY_FILTERS,
  type EditHistoryState,
  type EditableFieldName,
  type TranselecEditHistory,
  type TranselecHistoryEntry,
} from '../api'
import { ROUTES } from '../router'
import { searchFromFilters } from './filterUrl'
import { displayValue, formatEditDate, specFor } from './webEdits'

/** The popover's id: the pill's `popovertarget` and `openEditLog` find it by this. */
export const EDIT_LOG_ID = 'edit-log'

/** How many entries the popover shows; Ediciones web shows every loaded one. */
export const LOG_PREVIEW_COUNT = 8

function editsWord(count: number): string {
  return count === 1 ? 'edición web' : 'ediciones web'
}

/** The pill's full text, which is also its accessible name at every width. */
export function pillLabel(
  history: Pick<TranselecEditHistory, 'in_force_count' | 'needs_review_count'>,
): string {
  const base = `${history.in_force_count} ${editsWord(history.in_force_count)}`
  return history.needs_review_count > 0
    ? `${base} · ${history.needs_review_count} por revisar`
    : base
}

/** The pill exists only after a successful load with something in force or to review. */
export function pillVisible(history: TranselecEditHistory | null): history is TranselecEditHistory {
  return history !== null && history.in_force_count + history.needs_review_count > 0
}

const MUTED: ReadonlySet<EditHistoryState> = new Set<EditHistoryState>([
  'incorporada',
  'incorporated',
  'superseded',
  'discarded',
  'kept',
])

/** Greyed entries: the edit no longer changes what the dashboard shows. */
export function isMuted(state: EditHistoryState): boolean {
  return MUTED.has(state)
}

function byWhom(label: string, who: string | null): string {
  return who ? `${label} · ${who}` : label
}

/** What happened to an edit; null for one in force, which needs no label. */
export function stateLabel(
  entry: Pick<TranselecHistoryEntry, 'state' | 'ended_by_display_name'>,
): string | null {
  switch (entry.state) {
    case 'aplicada':
      return null
    case 'en_conflicto':
      return 'en conflicto: la planilla cambió'
    case 'huerfana':
      return 'sin fila en la versión activa'
    case 'incorporada':
    case 'incorporated':
      return 'ya está en la planilla'
    case 'superseded':
      return 'reemplazada por una edición posterior'
    case 'discarded':
      return byWhom('revertida al valor de la planilla', entry.ended_by_display_name)
    case 'kept':
      return byWhom('conservada al resolver un conflicto', entry.ended_by_display_name)
  }
}

const SANTIAGO = new Intl.DateTimeFormat('es-CL', {
  timeZone: 'America/Santiago',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

function santiago(date: Date): { day: string; time: string } {
  const parts = SANTIAGO.formatToParts(date)
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value ?? ''
  return {
    day: `${part('year')}-${part('month')}-${part('day')}`,
    time: `${part('hour')}:${part('minute')}`,
  }
}

/** «hoy 09:41», «ayer 17:02» or «03-10-2026», in America/Santiago. */
export function formatEditWhen(iso: string, now: Date = new Date()): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return formatEditDate(iso)
  const when = santiago(at)
  const today = santiago(now).day
  if (when.day === today) return `hoy ${when.time}`
  // The calendar day before today's Santiago date (noon UTC avoids any edge).
  const [year, month, day] = today.split('-').map(Number)
  const yesterday = new Date(Date.UTC(year, month - 1, day - 1, 12)).toISOString().slice(0, 10)
  if (when.day === yesterday) return `ayer ${when.time}`
  return formatEditDate(iso)
}

/** A value as the log shows it: dates dd-mm-aaaa, an empty one «(vacío)». */
export function logValue(field: EditableFieldName, value: string | null): string {
  return displayValue(specFor(field), value) || '(vacío)'
}

/** The Explorador filtered to the entry's PMF with its row's drawer open; null without a row. */
export function entryHref(
  entry: Pick<TranselecHistoryEntry, 'pmf' | 'source_row_number'>,
): string | null {
  if (entry.source_row_number === null) return null
  return `${ROUTES.explorador}${searchFromFilters(
    { ...EMPTY_FILTERS, q: entry.pmf },
    { fila: String(entry.source_row_number) },
  )}`
}
