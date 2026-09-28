import { describe, expect, it } from 'vitest'
import {
  EMPTY_FILTERS,
  applyFilters,
  countActiveFilters,
  filterOptions,
  normalizeForSearch,
} from './filters.ts'
import { testFeatures } from '../test/fixtures.ts'

describe('normalizeForSearch', () => {
  it('is case- and accent-insensitive', () => {
    expect(normalizeForSearch('  Vegetación NATIVA ')).toBe('vegetacion nativa')
    expect(normalizeForSearch('PURRETRÚN')).toBe('purretrun')
  })
})

describe('applyFilters', () => {
  const features = testFeatures()

  it('returns everything for empty filters', () => {
    expect(applyFilters(features, EMPTY_FILTERS)).toHaveLength(features.length)
  })

  it('filters by predio name', () => {
    const result = applyFilters(features, { ...EMPTY_FILTERS, nomPredio: 'San Sebastian' })
    expect(result.map((f) => f.properties.feature_ordinal)).toEqual([3])
  })

  it('filters by uso 2026', () => {
    const result = applyFilters(features, { ...EMPTY_FILTERS, uso2026: 'PLANTACION' })
    expect(result.map((f) => f.properties.feature_ordinal)).toEqual([1, 2, 5])
  })

  it('filters by exact rodal', () => {
    const result = applyFilters(features, { ...EMPTY_FILTERS, nRodal: '0' })
    expect(result.map((f) => f.properties.feature_ordinal)).toEqual([6])
  })

  it('filters changed detailed codes (literal field comparison)', () => {
    const changed = applyFilters(features, { ...EMPTY_FILTERS, codeChange: 'changed' })
    expect(changed.map((f) => f.properties.feature_ordinal)).toEqual([2, 5])

    const unchanged = applyFilters(features, { ...EMPTY_FILTERS, codeChange: 'unchanged' })
    expect(unchanged.map((f) => f.properties.feature_ordinal)).toEqual([1, 3, 4, 6])
  })

  it('filters changed uso classes', () => {
    const changed = applyFilters(features, { ...EMPTY_FILTERS, usoChange: 'changed' })
    expect(changed.map((f) => f.properties.feature_ordinal)).toEqual([2])
  })

  it('filters by one quality-evidence class and by any evidence', () => {
    const blankRodal = applyFilters(features, { ...EMPTY_FILTERS, quality: 'blank_rodal' })
    expect(blankRodal.map((f) => f.properties.feature_ordinal)).toEqual([3])

    const anyEvidence = applyFilters(features, { ...EMPTY_FILTERS, quality: 'any' })
    expect(anyEvidence.map((f) => f.properties.feature_ordinal)).toEqual([3, 4, 5, 6])
  })

  it('filters by geometry validity', () => {
    const invalid = applyFilters(features, { ...EMPTY_FILTERS, geometryValid: false })
    expect(invalid.map((f) => f.properties.feature_ordinal)).toEqual([5])
  })

  it('searches accent-insensitively across source fields', () => {
    const result = applyFilters(features, { ...EMPTY_FILTERS, searchText: 'vegetacion' })
    expect(result.map((f) => f.properties.feature_ordinal)).toEqual([6])
  })

  it('finds features by OBJECTID as exact evidence lookup', () => {
    const result = applyFilters(features, { ...EMPTY_FILTERS, searchText: '104' })
    expect(result.map((f) => f.properties.feature_ordinal)).toEqual([4])
  })

  it('combines filters conjunctively and can produce empty results', () => {
    const result = applyFilters(features, {
      ...EMPTY_FILTERS,
      nomPredio: 'Lumaco',
      uso2026: 'PLANTACION',
    })
    expect(result).toHaveLength(0)
  })
})

describe('countActiveFilters', () => {
  it('counts non-empty filters including search text', () => {
    expect(countActiveFilters(EMPTY_FILTERS)).toBe(0)
    expect(
      countActiveFilters({
        ...EMPTY_FILTERS,
        nomPredio: 'Lumaco',
        quality: 'any',
        searchText: 'x',
      }),
    ).toBe(3)
  })
})

describe('filterOptions', () => {
  it('orders values by descending count and omits blanks', () => {
    const options = filterOptions(testFeatures(), 'uso_2026')
    expect(options[0]).toEqual({ value: 'PLANTACION', count: 3 })
    expect(options.map((option) => option.value)).not.toContain('')
  })
})
