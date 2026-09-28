import { describe, expect, it } from 'vitest'
import {
  cloneCoordinates,
  countDraftVertices,
  moveDraftVertex,
  multiPolygonAreaSquareMeters,
  pickHandleIndices,
  simplifyDraftCoordinates,
  straightCutCandidates,
} from './draftGeometry.ts'

function circleRing(pointCount: number, radius = 1000): number[][] {
  const ring: number[][] = []
  for (let index = 0; index < pointCount; index += 1) {
    const angle = (index / pointCount) * Math.PI * 2
    ring.push([Math.cos(angle) * radius, Math.sin(angle) * radius])
  }
  ring.push(ring[0]!)
  return ring
}

describe('draft geometry area', () => {
  it('calculates exterior area in source metres', () => {
    const coordinates = [[[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]]]
    expect(multiPolygonAreaSquareMeters(coordinates)).toBe(10_000)
  })

  it('subtracts holes and sums polygon parts', () => {
    const coordinates = [
      [
        [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]],
        [[25, 25], [75, 25], [75, 75], [25, 75], [25, 25]],
      ],
      [[[200, 0], [250, 0], [250, 50], [200, 50], [200, 0]]],
    ]
    expect(multiPolygonAreaSquareMeters(coordinates)).toBe(10_000)
  })

  it('moves a closed-ring first vertex without mutating the source copy', () => {
    const source = [[[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]]]
    const draft = cloneCoordinates(source)

    moveDraftVertex(draft, 0, 0, 0, 10, 20)

    expect(draft[0]?.[0]?.[0]).toEqual([10, 20])
    expect(draft[0]?.[0]?.[4]).toEqual([10, 20])
    expect(source[0]?.[0]?.[0]).toEqual([0, 0])
  })
})

describe('draft point reduction', () => {
  it('reduces near-collinear vertices while preserving closure and source geometry', () => {
    const source = [[[[0, 0], [25, 0.2], [50, -0.1], [75, 0.1], [100, 0], [100, 100], [0, 100], [0, 0]]]]
    const simplified = simplifyDraftCoordinates(source, 1)

    expect(countDraftVertices(simplified)).toBeLessThan(countDraftVertices(source))
    expect(simplified[0]?.[0]?.[0]).toEqual(simplified[0]?.[0]?.at(-1))
    expect(source[0]?.[0]).toHaveLength(8)
    expect(multiPolygonAreaSquareMeters(simplified)).toBeCloseTo(10_000, -1)
  })
})

describe('handle index reduction', () => {
  it('keeps every index when the ring is already small', () => {
    const square = [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]
    expect(pickHandleIndices(square, 180)).toEqual([0, 1, 2, 3])
  })

  it('caps handle count for a large ring without exceeding the max', () => {
    const ring = circleRing(960)
    const indices = pickHandleIndices(ring, 180)

    expect(indices.length).toBeLessThanOrEqual(180)
    expect(indices.length).toBeGreaterThan(0)
    expect(new Set(indices).size).toBe(indices.length)
    for (const index of indices) {
      expect(index).toBeGreaterThanOrEqual(0)
      expect(index).toBeLessThan(960)
    }
  })

  it('returns indices into the real vertex array, not new coordinates', () => {
    const ring = circleRing(500)
    const indices = pickHandleIndices(ring, 50)

    for (const index of indices) {
      expect(ring[index]).toBeDefined()
    }
  })
})

describe('straight draft cuts', () => {
  const square = [[[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]]]

  it('splits a simple polygon into two pieces with conserved area', () => {
    const result = straightCutCandidates(square, [-10, 40], [110, 40])
    expect(result.ok).toBe(true)
    if (!result.ok) return

    expect(result.areasSquareMeters[0] + result.areasSquareMeters[1]).toBeCloseTo(10_000)
    expect(result.areasSquareMeters.sort((a, b) => a - b)).toEqual([4000, 6000])
    expect(result.largerPieceIndex).toBe(0)
  })

  it('refuses multipart or holed geometry instead of guessing topology', () => {
    const withHole = [[
      [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]],
      [[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]],
    ]]
    const result = straightCutCandidates(withHole, [-10, 40], [110, 40])
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toMatch(/polígonos simples/)
  })

  it('requires exactly two clean boundary crossings', () => {
    const result = straightCutCandidates(square, [-10, -10], [-5, -5])
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toMatch(/exactamente dos veces/)
  })
})
