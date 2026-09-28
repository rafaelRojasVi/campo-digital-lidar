import type { GeoFeature, QualityFlag, SourceFeatureProperties } from '../types.ts'

// Snapshot-local, literal source-field filters. Each one mirrors a filter the
// read API also supports; they run client-side over the loaded collection so
// map, table, and aggregates stay synchronized without re-downloading
// geometry. "changed"/"unchanged" are literal field comparisons within the
// snapshot, not workflow transitions.

export type ChangeFilter = 'changed' | 'unchanged'

/** `'any'` selects features carrying at least one quality-evidence flag. */
export type QualityFilter = QualityFlag | 'any'

export interface FilterState {
  codPredial: string | null
  nomPredio: string | null
  uso2026: string | null
  uso2024: string | null
  descUso: string | null
  codUso2026: string | null
  codUso: string | null
  nRodal: string | null
  quality: QualityFilter | null
  geometryValid: boolean | null
  usoChange: ChangeFilter | null
  codeChange: ChangeFilter | null
  searchText: string
}

export const EMPTY_FILTERS: FilterState = {
  codPredial: null,
  nomPredio: null,
  uso2026: null,
  uso2024: null,
  descUso: null,
  codUso2026: null,
  codUso: null,
  nRodal: null,
  quality: null,
  geometryValid: null,
  usoChange: null,
  codeChange: null,
  searchText: '',
}

export function countActiveFilters(filters: FilterState): number {
  let active = 0
  if (filters.codPredial !== null) active += 1
  if (filters.nomPredio !== null) active += 1
  if (filters.uso2026 !== null) active += 1
  if (filters.uso2024 !== null) active += 1
  if (filters.descUso !== null) active += 1
  if (filters.codUso2026 !== null) active += 1
  if (filters.codUso !== null) active += 1
  if (filters.nRodal !== null) active += 1
  if (filters.quality !== null) active += 1
  if (filters.geometryValid !== null) active += 1
  if (filters.usoChange !== null) active += 1
  if (filters.codeChange !== null) active += 1
  if (filters.searchText.trim() !== '') active += 1
  return active
}

/** Literal within-snapshot difference of the year-stamped use-class fields. */
export function usoFieldsDiffer(properties: SourceFeatureProperties): boolean {
  return properties.uso_2024 !== properties.uso_2026
}

/** Literal within-snapshot difference of the detailed use-code fields. */
export function codeFieldsDiffer(properties: SourceFeatureProperties): boolean {
  return properties.cod_uso !== properties.cod_uso_2026
}

/** Case- and accent-insensitive normalization for substring search. */
export function normalizeForSearch(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

const SEARCHED_FIELDS: readonly (keyof SourceFeatureProperties)[] = [
  'cod_predial',
  'nom_predio',
  'n_rodal',
  'cod_uso',
  'uso_2024',
  'desc_uso',
  'uso_2026',
  'cod_uso_2026',
]

export function featureMatchesSearch(
  properties: SourceFeatureProperties,
  normalizedQuery: string,
): boolean {
  if (normalizedQuery === '') {
    return true
  }

  for (const field of SEARCHED_FIELDS) {
    const value = properties[field]
    if (typeof value === 'string' && normalizeForSearch(value).includes(normalizedQuery)) {
      return true
    }
  }

  // Numeric identifiers are matched as exact text (source evidence lookup).
  if (
    properties.source_objectid !== null &&
    String(properties.source_objectid) === normalizedQuery
  ) {
    return true
  }

  return String(properties.feature_ordinal) === normalizedQuery
}

function matchesEquality(value: string | null, filter: string | null): boolean {
  return filter === null || value === filter
}

export function featureMatchesFilters(
  properties: SourceFeatureProperties,
  filters: FilterState,
  normalizedQuery: string,
): boolean {
  if (!matchesEquality(properties.cod_predial, filters.codPredial)) return false
  if (!matchesEquality(properties.nom_predio, filters.nomPredio)) return false
  if (!matchesEquality(properties.uso_2026, filters.uso2026)) return false
  if (!matchesEquality(properties.uso_2024, filters.uso2024)) return false
  if (!matchesEquality(properties.desc_uso, filters.descUso)) return false
  if (!matchesEquality(properties.cod_uso_2026, filters.codUso2026)) return false
  if (!matchesEquality(properties.cod_uso, filters.codUso)) return false
  if (!matchesEquality(properties.n_rodal, filters.nRodal)) return false

  if (filters.quality !== null) {
    if (filters.quality === 'any') {
      if (properties.quality_flags.length === 0) return false
    } else if (!properties.quality_flags.includes(filters.quality)) {
      return false
    }
  }

  if (filters.geometryValid !== null && properties.geometry_is_valid !== filters.geometryValid) {
    return false
  }

  if (filters.usoChange !== null) {
    const differs = usoFieldsDiffer(properties)
    if (filters.usoChange === 'changed' ? !differs : differs) return false
  }

  if (filters.codeChange !== null) {
    const differs = codeFieldsDiffer(properties)
    if (filters.codeChange === 'changed' ? !differs : differs) return false
  }

  return featureMatchesSearch(properties, normalizedQuery)
}

/** Apply filters + search to the loaded collection, preserving ordinal order. */
export function applyFilters(features: GeoFeature[], filters: FilterState): GeoFeature[] {
  const normalizedQuery = normalizeForSearch(filters.searchText)

  return features.filter((feature) =>
    featureMatchesFilters(feature.properties, filters, normalizedQuery),
  )
}

export interface FilterOption {
  value: string
  count: number
}

/**
 * Distinct values of one source field across the whole collection, ordered by
 * descending feature count then value. Blank/null values are not offered as
 * options (blank rodal is reachable through the quality-evidence filter).
 */
export function filterOptions(
  features: GeoFeature[],
  field: keyof SourceFeatureProperties,
): FilterOption[] {
  const counts = new Map<string, number>()

  for (const feature of features) {
    const value = feature.properties[field]
    if (typeof value === 'string' && value !== '') {
      counts.set(value, (counts.get(value) ?? 0) + 1)
    }
  }

  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value, 'es'))
}
