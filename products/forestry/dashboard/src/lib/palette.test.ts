import { describe, expect, it } from 'vitest'
import {
  BLANK_COLOR,
  CATEGORICAL_COLORS,
  CHANGED_COLOR,
  OTHER_COLOR,
  QUALITY_COLOR,
  UNCHANGED_COLOR,
  buildColorEncoding,
} from './palette.ts'
import { makeFeature, testFeatures } from '../test/fixtures.ts'

describe('categorical encoding', () => {
  it('assigns distinct colors by descending area, largest first', () => {
    const features = testFeatures()
    const encoding = buildColorEncoding('uso2026', features)

    const first = encoding.legend[0]
    expect(first?.label).toBe('PLANTACION')
    expect(first?.color).toBe(CATEGORICAL_COLORS[0])

    const plantacion = features.find((f) => f.properties.uso_2026 === 'PLANTACION')
    expect(encoding.colorFor(plantacion!)).toBe(CATEGORICAL_COLORS[0])
  })

  it('folds categories beyond the validated 8 slots into a gray "Otros" entry', () => {
    const features = Array.from({ length: 12 }, (_, index) =>
      makeFeature({
        feature_ordinal: index + 1,
        uso_2026: `USO ${String.fromCharCode(65 + index)}`,
        sup_ha: 100 - index,
      }),
    )

    const encoding = buildColorEncoding('uso2026', features)
    const foldEntry = encoding.legend.find((entry) => entry.isFold)

    expect(foldEntry).toBeDefined()
    expect(foldEntry?.color).toBe(OTHER_COLOR)
    expect(foldEntry?.featureCount).toBe(12 - CATEGORICAL_COLORS.length)
    expect(foldEntry?.filterValue).toBeNull()

    const smallest = features[features.length - 1]
    expect(encoding.colorFor(smallest!)).toBe(OTHER_COLOR)
  })

  it('does not fold when the vocabulary fits the palette', () => {
    const encoding = buildColorEncoding('uso2026', testFeatures())
    expect(encoding.legend.some((entry) => entry.isFold)).toBe(false)
  })

  it('groups blank source values separately', () => {
    const features = [makeFeature({ uso_2026: null }), makeFeature({ uso_2026: 'VEGA' })]
    const encoding = buildColorEncoding('uso2026', features)

    expect(encoding.colorFor(features[0]!)).toBe(BLANK_COLOR)
    expect(encoding.legend.find((entry) => entry.key === '__blank__')).toBeDefined()
  })
})

describe('cambio encoding', () => {
  it('marks literal field differences without business semantics', () => {
    const features = testFeatures()
    const encoding = buildColorEncoding('cambio', features)

    const changed = features.find((f) => f.properties.feature_ordinal === 2)
    const unchanged = features.find((f) => f.properties.feature_ordinal === 1)

    expect(encoding.colorFor(changed!)).toBe(CHANGED_COLOR)
    expect(encoding.colorFor(unchanged!)).toBe(UNCHANGED_COLOR)

    const changedEntry = encoding.legend.find((entry) => entry.key === 'changed')
    expect(changedEntry?.featureCount).toBe(2)
  })
})

describe('calidad encoding', () => {
  it('marks features with any quality evidence', () => {
    const features = testFeatures()
    const encoding = buildColorEncoding('calidad', features)

    const withEvidence = features.find((f) => f.properties.feature_ordinal === 5)
    const clean = features.find((f) => f.properties.feature_ordinal === 1)

    expect(encoding.colorFor(withEvidence!)).toBe(QUALITY_COLOR)
    expect(encoding.colorFor(clean!)).not.toBe(QUALITY_COLOR)

    const evidenceEntry = encoding.legend.find((entry) => entry.key === 'with-evidence')
    expect(evidenceEntry?.featureCount).toBe(4)
  })
})
