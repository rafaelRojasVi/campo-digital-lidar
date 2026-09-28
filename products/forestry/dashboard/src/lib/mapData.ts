import { utmToLonLat } from './proj.ts'
import { formatHa } from './format.ts'
import type { GeoFeature, SourceFeatureProperties } from '../types.ts'

// Pure map-data helpers, kept out of the Leaflet component so the display
// transformation is unit-testable.

function escapeHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function tooltipHtml(properties: SourceFeatureProperties): string {
  const predio = properties.nom_predio ?? 'Predio sin nombre'
  const code = properties.cod_predial !== null ? ` (${properties.cod_predial})` : ''
  const rodal =
    properties.n_rodal !== null && properties.n_rodal !== ''
      ? `Rodal ${properties.n_rodal}`
      : 'Sin rodal'
  const uso = properties.uso_2026 ?? 'Sin uso 2026'
  const area = properties.sup_ha !== null ? `${formatHa(properties.sup_ha)} ha` : ''

  return (
    `<strong>${escapeHtml(predio)}${escapeHtml(code)}</strong><br/>` +
    `${escapeHtml(rodal)} · ${escapeHtml(uso)}${area === '' ? '' : ` · ${escapeHtml(area)}`}`
  )
}

/**
 * Convert one stored MultiPolygon (EPSG:32718 coordinates, exactly as served)
 * to Leaflet [lat, lng] rings. Display-only reprojection; the source
 * geometry object is not modified.
 */
export function multiPolygonToLatLngs(geometry: GeoFeature['geometry']): [number, number][][][] {
  return geometry.coordinates.map((polygon) =>
    polygon.map((ring) =>
      ring.flatMap((position): [number, number][] => {
        const [x, y] = position
        if (x === undefined || y === undefined) {
          return []
        }
        const [lon, lat] = utmToLonLat(x, y)
        return [[lat, lon]]
      }),
    ),
  )
}

/** Ground resolution of one screen pixel (web mercator approximation). */
export function metersPerPixel(latitude: number, zoom: number): number {
  return (156543.03392 * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom
}
