import { describe, expect, it } from 'vitest'
import { formatHa, formatInt, shortFingerprint, sourceUnitsToHa } from './format.ts'

describe('es-CL formatting', () => {
  it('formats hectares with comma decimals and dot thousands', () => {
    expect(formatHa(10422.61)).toBe('10.422,61')
    expect(formatHa(0.3)).toBe('0,30')
  })

  it('formats integers with dot thousands', () => {
    expect(formatInt(1568)).toBe('1.568')
  })
})

describe('sourceUnitsToHa', () => {
  it('divides by 10,000 (metre-declared source units)', () => {
    expect(sourceUnitsToHa(104_226_106.7)).toBeCloseTo(10_422.61067, 5)
  })
})

describe('shortFingerprint', () => {
  it('keeps head and tail of long fingerprints', () => {
    expect(
      shortFingerprint('19beaed51b5c1bc144c8d34d500a21d1e3a31b7a1dbdc674b96ac69225060bd1'),
    ).toBe('19beaed5…0bd1')
  })

  it('passes short values through', () => {
    expect(shortFingerprint('abc')).toBe('abc')
  })
})
