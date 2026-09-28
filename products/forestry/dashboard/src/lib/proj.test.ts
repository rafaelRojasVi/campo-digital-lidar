import { describe, expect, it } from 'vitest'
import { multiPolygonUtmBbox, utmBboxToLonLatBounds, utmToLonLat } from './proj.ts'

// Authoritative fixtures generated with pyproj 3.x
// (Transformer.from_crs("EPSG:32718", "EPSG:4326", always_xy=True)) over the
// observed snapshot envelope. Tolerance 1e-6 degrees is roughly 0.1 m,
// far tighter than any display need.
const PYPROJ_FIXTURES: [easting: number, northing: number, lon: number, lat: number][] = [
  [617298.09, 5484858.7, -73.6099353729, -40.7788865947],
  [662027.94, 5555261.33, -73.0980643424, -40.1373757394],
  [617298.09, 5555261.33, -73.6229469289, -40.1448088777],
  [662027.94, 5484858.7, -73.0800996247, -40.7712860983],
  [639663.0, 5520060.0, -73.3527984234, -40.4583993844],
  [625000.0, 5500000.0, -73.5217097053, -40.6413934446],
]

describe('utmToLonLat', () => {
  it('matches pyproj EPSG:32718 -> EPSG:4326 within 1e-6 degrees', () => {
    for (const [easting, northing, expectedLon, expectedLat] of PYPROJ_FIXTURES) {
      const [lon, lat] = utmToLonLat(easting, northing)
      expect(lon).toBeCloseTo(expectedLon, 6)
      expect(lat).toBeCloseTo(expectedLat, 6)
    }
  })

  it('places the estate envelope in southern Chile (sanity)', () => {
    const [lon, lat] = utmToLonLat(639663, 5520060)
    expect(lon).toBeGreaterThan(-74)
    expect(lon).toBeLessThan(-73)
    expect(lat).toBeGreaterThan(-41)
    expect(lat).toBeLessThan(-40)
  })
})

describe('utmBboxToLonLatBounds', () => {
  it('covers all four transformed corners', () => {
    const bounds = utmBboxToLonLatBounds([617298.09, 5484858.7, 662027.94, 5555261.33])

    // The west edge bows outward: the min longitude comes from the NW corner.
    expect(bounds.west).toBeCloseTo(-73.6229469289, 6)
    expect(bounds.east).toBeCloseTo(-73.0800996247, 6)
    expect(bounds.south).toBeCloseTo(-40.7788865947, 6)
    expect(bounds.north).toBeCloseTo(-40.1373757394, 6)
  })
})

describe('multiPolygonUtmBbox', () => {
  it('computes the envelope without touching coordinates', () => {
    const geometry = {
      type: 'MultiPolygon' as const,
      coordinates: [
        [
          [
            [620000, 5490000],
            [620100, 5490000],
            [620100, 5490100],
            [620000, 5490100],
            [620000, 5490000],
          ],
        ],
        [
          [
            [621000, 5491000],
            [621050, 5491000],
            [621050, 5491050],
            [621000, 5491000],
          ],
        ],
      ],
    }

    expect(multiPolygonUtmBbox(geometry)).toEqual([620000, 5490000, 621050, 5491050])
  })

  it('rejects empty geometry', () => {
    expect(() =>
      multiPolygonUtmBbox({ type: 'MultiPolygon', coordinates: [] }),
    ).toThrowError('geometry has no coordinates')
  })
})
