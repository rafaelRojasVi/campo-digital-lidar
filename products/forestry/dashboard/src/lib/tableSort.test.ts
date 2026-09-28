import { describe, expect, it } from 'vitest'
import { sortFeatures } from './tableSort.ts'
import { testFeatures } from '../test/fixtures.ts'

describe('sortFeatures', () => {
  const features = testFeatures()

  it('defaults to feature-ordinal order', () => {
    const sorted = sortFeatures(features, { key: 'ordinal', ascending: true })
    expect(sorted.map((f) => f.properties.feature_ordinal)).toEqual([1, 2, 3, 4, 5, 6])
  })

  it('sorts rodal numerically with blanks last', () => {
    const sorted = sortFeatures(features, { key: 'rodal', ascending: true })
    expect(sorted.map((f) => f.properties.n_rodal)).toEqual(['0', '5', '10', '11', '12', ''])
  })

  it('sorts by Sup_ha descending', () => {
    const sorted = sortFeatures(features, { key: 'supHa', ascending: false })
    expect(sorted[0]?.properties.sup_ha).toBe(12.5)
    expect(sorted[sorted.length - 1]?.properties.sup_ha).toBe(0.3)
  })

  it('does not mutate the input array', () => {
    const input = [...features]
    sortFeatures(input, { key: 'supHa', ascending: false })
    expect(input.map((f) => f.properties.feature_ordinal)).toEqual([1, 2, 3, 4, 5, 6])
  })
})
