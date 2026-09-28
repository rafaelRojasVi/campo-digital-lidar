import { describe, expect, it } from 'vitest'
import { metersPerPixel, multiPolygonToLatLngs, tooltipHtml } from './mapData.ts'
import { utmToLonLat } from './proj.ts'
import { makeFeature } from '../test/fixtures.ts'

describe('tooltipHtml', () => {
  it('shows predio, rodal, uso and area', () => {
    const html = tooltipHtml(
      makeFeature({ nom_predio: 'Lumaco', cod_predial: 'LUM', n_rodal: '7', sup_ha: 1.5 })
        .properties,
    )

    expect(html).toContain('Lumaco (LUM)')
    expect(html).toContain('Rodal 7')
    expect(html).toContain('PLANTACION')
    expect(html).toContain('1,50 ha')
  })

  it('escapes HTML in source values', () => {
    const html = tooltipHtml(makeFeature({ nom_predio: '<img src=x>' }).properties)
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img src=x&gt;')
  })

  it('labels blank rodal explicitly', () => {
    const html = tooltipHtml(makeFeature({ n_rodal: '' }).properties)
    expect(html).toContain('Sin rodal')
  })
})

describe('multiPolygonToLatLngs', () => {
  it('reprojects every stored vertex to [lat, lng] without mutating the source', () => {
    const geometry = {
      type: 'MultiPolygon' as const,
      coordinates: [
        [
          [
            [620000, 5490000],
            [620100, 5490000],
            [620100, 5490100],
            [620000, 5490000],
          ],
        ],
      ],
    }
    const originalJson = JSON.stringify(geometry)

    const latLngs = multiPolygonToLatLngs(geometry)

    expect(latLngs).toHaveLength(1)
    expect(latLngs[0]).toHaveLength(1)
    expect(latLngs[0]?.[0]).toHaveLength(4)

    const [expectedLon, expectedLat] = utmToLonLat(620000, 5490000)
    expect(latLngs[0]?.[0]?.[0]?.[0]).toBeCloseTo(expectedLat, 10)
    expect(latLngs[0]?.[0]?.[0]?.[1]).toBeCloseTo(expectedLon, 10)

    expect(JSON.stringify(geometry)).toBe(originalJson)
  })
})

describe('metersPerPixel', () => {
  it('matches the web mercator ground resolution at the equator', () => {
    expect(metersPerPixel(0, 0)).toBeCloseTo(156543.03392, 3)
  })

  it('shrinks with latitude and zoom', () => {
    const atEstate = metersPerPixel(-40.45, 10)
    expect(atEstate).toBeGreaterThan(100)
    expect(atEstate).toBeLessThan(130)
    expect(metersPerPixel(-40.45, 11)).toBeCloseTo(atEstate / 2, 6)
  })
})
