import proj4 from 'proj4'

// The API serves stored geometry exactly as persisted, in the snapshot's
// declared CRS. This module is a display-only projection: the persisted
// source coordinates are never mutated or reinterpreted.
//
// EPSG:32718 = WGS 84 / UTM zone 18S (southern hemisphere, metre units),
// matching `storage_srid` of the persisted snapshot. Definition from the
// EPSG registry (proj4 string form).
export const STORAGE_EPSG = 32718

const UTM18S = '+proj=utm +zone=18 +south +datum=WGS84 +units=m +no_defs +type=crs'

const toWgs84 = proj4(UTM18S, proj4.WGS84)

/** Reproject one stored [easting, northing] pair to [longitude, latitude]. */
export function utmToLonLat(easting: number, northing: number): [number, number] {
  const [lon, lat] = toWgs84.forward([easting, northing])

  if (lon === undefined || lat === undefined || !Number.isFinite(lon) || !Number.isFinite(lat)) {
    throw new Error(`reprojection failed for (${easting}, ${northing})`)
  }

  return [lon, lat]
}

/**
 * Convert one display [longitude, latitude] pair back to the source UTM CRS.
 * Used only for local draft geometry simulation; it never mutates persisted data.
 */
export function lonLatToUtm(longitude: number, latitude: number): [number, number] {
  const [easting, northing] = toWgs84.inverse([longitude, latitude])

  if (
    easting === undefined ||
    northing === undefined ||
    !Number.isFinite(easting) ||
    !Number.isFinite(northing)
  ) {
    throw new Error(`inverse reprojection failed for (${longitude}, ${latitude})`)
  }

  return [easting, northing]
}

export interface LonLatBounds {
  west: number
  south: number
  east: number
  north: number
}

/**
 * Reproject a stored-CRS bounding box `[minx, miny, maxx, maxy]` for display.
 *
 * All four corners are transformed because a UTM rectangle is not axis-aligned
 * in longitude/latitude; the result is the lon/lat envelope of the corners.
 */
export function utmBboxToLonLatBounds(bbox: [number, number, number, number]): LonLatBounds {
  const [minx, miny, maxx, maxy] = bbox
  const corners: [number, number][] = [
    utmToLonLat(minx, miny),
    utmToLonLat(minx, maxy),
    utmToLonLat(maxx, miny),
    utmToLonLat(maxx, maxy),
  ]

  const lons = corners.map((corner) => corner[0])
  const lats = corners.map((corner) => corner[1])

  return {
    west: Math.min(...lons),
    south: Math.min(...lats),
    east: Math.max(...lons),
    north: Math.max(...lats),
  }
}

export interface MultiPolygonLike {
  type: 'MultiPolygon'
  coordinates: number[][][][]
}

/** Envelope of one stored MultiPolygon in the storage CRS (no reprojection). */
export function multiPolygonUtmBbox(
  geometry: MultiPolygonLike,
): [number, number, number, number] {
  let minx = Infinity
  let miny = Infinity
  let maxx = -Infinity
  let maxy = -Infinity

  for (const polygon of geometry.coordinates) {
    for (const ring of polygon) {
      for (const position of ring) {
        const [x, y] = position
        if (x === undefined || y === undefined) {
          continue
        }
        if (x < minx) minx = x
        if (y < miny) miny = y
        if (x > maxx) maxx = x
        if (y > maxy) maxy = y
      }
    }
  }

  if (!Number.isFinite(minx)) {
    throw new Error('geometry has no coordinates')
  }

  return [minx, miny, maxx, maxy]
}
