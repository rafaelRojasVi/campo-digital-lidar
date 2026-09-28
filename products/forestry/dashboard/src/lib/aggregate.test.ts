import { describe, expect, it } from 'vitest'
import { aggregateByField, selectionStats } from './aggregate.ts'
import { makeFeature, testFeatures } from '../test/fixtures.ts'

describe('selectionStats', () => {
  it('sums source and geometry-derived areas with evidence counts', () => {
    const stats = selectionStats(testFeatures())

    expect(stats.featureCount).toBe(6)
    expect(stats.supHaTotal).toBeCloseTo(27.1, 10)
    expect(stats.geometryAreaSourceUnitsTotal).toBeCloseTo(271_000, 6)
    expect(stats.invalidGeometryCount).toBe(1)
    expect(stats.withQualityEvidenceCount).toBe(4)
    expect(stats.usoFieldDifferenceCount).toBe(1)
    expect(stats.codeFieldDifferenceCount).toBe(2)
  })

  it('handles the empty selection', () => {
    const stats = selectionStats([])
    expect(stats.featureCount).toBe(0)
    expect(stats.supHaTotal).toBe(0)
  })
})

describe('aggregateByField', () => {
  it('groups by source value ordered by descending Sup_ha', () => {
    const aggregates = aggregateByField(testFeatures(), 'uso_2026')

    expect(aggregates[0]?.value).toBe('PLANTACION')
    expect(aggregates[0]?.featureCount).toBe(3)
    expect(aggregates[0]?.supHaTotal).toBeCloseTo(17.7, 10)

    const values = aggregates.map((entry) => entry.value)
    expect(values).toContain('BOSQUE NATIVO')
  })

  it('groups blank values under null', () => {
    const features = [makeFeature({ n_rodal: '' }), makeFeature({ n_rodal: '7' })]
    const aggregates = aggregateByField(features, 'n_rodal')

    expect(aggregates.find((entry) => entry.value === null)?.featureCount).toBe(1)
  })
})
