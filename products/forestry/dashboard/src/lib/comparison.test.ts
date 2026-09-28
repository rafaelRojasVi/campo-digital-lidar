import { describe, expect, it } from 'vitest'
import { groupChangePairs } from './comparison.ts'

describe('groupChangePairs', () => {
  it('groups identical before→after pairs with counts, most frequent first', () => {
    const pairs = groupChangePairs([
      { feature_ordinal: 1, source_objectid: 1, before: 'En11', after: 'Pi26' },
      { feature_ordinal: 2, source_objectid: 2, before: 'En11', after: 'Pi26' },
      { feature_ordinal: 3, source_objectid: 3, before: 'Po99', after: 'Pi26' },
    ])

    expect(pairs).toEqual([
      { before: 'En11', after: 'Pi26', count: 2 },
      { before: 'Po99', after: 'Pi26', count: 1 },
    ])
  })

  it('labels null values explicitly', () => {
    const pairs = groupChangePairs([
      { feature_ordinal: 1, source_objectid: 1, before: null, after: 'BN' },
    ])

    expect(pairs[0]).toEqual({ before: '(vacío)', after: 'BN', count: 1 })
  })
})
