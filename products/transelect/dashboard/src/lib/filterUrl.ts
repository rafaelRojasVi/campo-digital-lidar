/**
 * The filter state, carried in the URL.
 *
 * TR-FUNC-017 requires every section to agree about what "the current view"
 * means. The shipped application achieved that by fetching all five read
 * endpoints together inside one component. That still holds — see
 * `useDashboardData` — but it could only ever hold *within* one page: opening
 * a second section dropped the filters, and a filtered view could not be
 * linked, bookmarked or reloaded.
 *
 * Putting the state in the query string fixes all three, and makes the
 * guarantee observable: the parameters in the address bar are produced by the
 * same `filterParams` serializer the API client sends, so a reader can
 * compare the URL against the network request and see they match.
 *
 * The parameter names are the API's own contract, unchanged. This module
 * only reads and writes them.
 */

import { EMPTY_FILTERS, MULTISELECT_FIELDS, type TranselecFilterState } from '../api'

/**
 * Read a filter state out of a `location.search` string.
 *
 * Unknown parameters are ignored rather than rejected, so a URL carrying
 * something this build does not know about still resolves to a usable view.
 */
export function filtersFromSearch(search: string): TranselecFilterState {
  const params = new URLSearchParams(search)
  const filters: TranselecFilterState = {
    ...EMPTY_FILTERS,
    q: params.get('q') ?? '',
  }
  for (const field of MULTISELECT_FIELDS) {
    filters[field] = params.getAll(field).filter((value) => value !== '')
  }
  return filters
}

/**
 * Serialize a filter state back into a `?a=b` string (empty when no filter is
 * active, so an unfiltered view has a clean URL rather than a trail of empty
 * parameters).
 *
 * `extra` carries the non-filter query state a section owns — the Explorador's
 * open PMF drawer, for instance — so one writer owns the whole query string
 * and two features cannot erase each other's parameters.
 */
export function searchFromFilters(
  filters: TranselecFilterState,
  extra: Record<string, string | null | undefined> = {},
): string {
  const params = new URLSearchParams()
  const q = filters.q.trim()
  if (q) params.set('q', q)
  for (const field of MULTISELECT_FIELDS) {
    for (const value of filters[field]) params.append(field, value)
  }
  for (const [key, value] of Object.entries(extra)) {
    if (value !== null && value !== undefined && value !== '') params.set(key, value)
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

/** One removable filter, as the active-filter chips render them. */
export interface ActiveFilterChip {
  key: string
  field: 'q' | (typeof MULTISELECT_FIELDS)[number]
  label: string
  value: string
}

export const FIELD_LABELS: Record<(typeof MULTISELECT_FIELDS)[number], string> = {
  estado_resumido: 'Estado resumido',
  empresa: 'Empresa',
  pas: 'PAS',
  sector: 'Sector',
  tipo_propietario: 'Tipo de propietario',
  aef: 'AEF',
  quien_solicita: 'Quién solicita',
}

/**
 * Every active filter, flattened into one removable list.
 *
 * A reader should never have to open a panel to find out what is narrowing
 * the view — that is exactly the state the shipped filter rail could hide.
 */
export function activeFilterChips(filters: TranselecFilterState): ActiveFilterChip[] {
  const chips: ActiveFilterChip[] = []
  const q = filters.q.trim()
  if (q) chips.push({ key: `q:${q}`, field: 'q', label: 'Búsqueda', value: q })
  for (const field of MULTISELECT_FIELDS) {
    for (const value of filters[field]) {
      chips.push({ key: `${field}:${value}`, field, label: FIELD_LABELS[field], value })
    }
  }
  return chips
}

/** Remove one chip from a filter state, returning the narrowed-less state. */
export function withoutChip(
  filters: TranselecFilterState,
  chip: ActiveFilterChip,
): TranselecFilterState {
  if (chip.field === 'q') return { ...filters, q: '' }
  return {
    ...filters,
    [chip.field]: filters[chip.field].filter((value) => value !== chip.value),
  }
}

/** Count of active filters, for the disclosure trigger's badge. */
export function activeFilterCount(filters: TranselecFilterState): number {
  return activeFilterChips(filters).length
}
