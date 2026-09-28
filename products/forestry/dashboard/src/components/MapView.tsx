import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { metersPerPixel, multiPolygonToLatLngs, tooltipHtml } from '../lib/mapData.ts'
import { lonLatToUtm, multiPolygonUtmBbox, utmToLonLat } from '../lib/proj.ts'
import {
  cloneCoordinates,
  countDraftVertices,
  isClosedRing,
  moveDraftVertex,
  multiPolygonAreaSquareMeters,
  pickHandleIndices,
  simplifyDraftCoordinates,
  straightCutCandidates,
  type DraftCoordinates,
} from '../lib/draftGeometry.ts'
import {
  createDraftHistory,
  pushDraftHistory,
  redoDraftHistory,
  undoDraftHistory,
  type DraftHistoryState,
} from '../lib/draftHistory.ts'
import type { ColorEncoding } from '../lib/palette.ts'
import type { FeatureCollection, GeoFeature } from '../types.ts'
import type { ZoomRequest } from '../App.tsx'

interface MapViewProps {
  collection: FeatureCollection
  filteredFeatures: GeoFeature[]
  encoding: ColorEncoding | null
  selectedOrdinal: number | null
  onSelect: (featureOrdinal: number | null) => void
  zoomRequest: ZoomRequest | null
  fitNonce: number
  onFitToResults: () => void
  sidebarCollapsed: boolean
  mapFocus: boolean
  activeFilterCount: number
  onToggleSidebar: () => void
  onToggleMapFocus: () => void
}

type BasemapMode = 'map' | 'satellite' | 'none'
type DraftMode = 'move' | 'cut'
type SimplifyLevel = 'alto' | 'medio' | 'bajo'

interface CutPreview {
  pieces: [DraftCoordinates, DraftCoordinates]
  selectedIndex: 0 | 1
  beforeCut: DraftCoordinates
}

const OSM_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const OSM_ATTRIBUTION = '© OpenStreetMap contributors'
const SATELLITE_TILE_URL =
  'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const SATELLITE_ATTRIBUTION =
  'Tiles © Esri — Esri, Maxar, Earthstar Geographics, and the GIS User Community'

interface FeatureLayer {
  layer: L.Polygon
  feature: GeoFeature
  visible: boolean
  /* Representative point for polygons too small to see at the current zoom. */
  centroid: L.LatLng
  maxExtentMeters: number
  marker: L.CircleMarker | null
}

const MARKER_MAX_SUBSET = 200
const MARKER_MIN_POLYGON_PX = 8

/**
 * Editable vertex handles are capped per ring. Above this, entering edit mode
 * on a heavy real polygon (measured: 960 vertices, ~430ms of dropped frames
 * once the full ~1,568-feature dataset is on screen) freezes the browser
 * building one draggable DOM marker per source vertex. The underlying draft
 * geometry keeps every source vertex; this only limits how many get a
 * draggable handle. See docs in the V1.1 performance pass for the profile.
 */
const MAX_VERTEX_HANDLES_PER_RING = 180

const SIMPLIFY_LEVELS: { id: SimplifyLevel; label: string; toleranceMeters: number }[] = [
  { id: 'alto', label: 'Alto', toleranceMeters: 2 },
  { id: 'medio', label: 'Medio', toleranceMeters: 10 },
  { id: 'bajo', label: 'Bajo', toleranceMeters: 30 },
]

const DRAFT_STYLE: L.PathOptions = {
  color: '#f3a712',
  weight: 3,
  opacity: 1,
  fillColor: '#f3a712',
  fillOpacity: 0.18,
}

const CUT_RETAINED_STYLE: L.PathOptions = {
  color: '#f3a712',
  weight: 3,
  opacity: 1,
  fillColor: '#f3a712',
  fillOpacity: 0.24,
}

const CUT_REMOVED_STYLE: L.PathOptions = {
  color: '#b3261e',
  weight: 2,
  opacity: 0.75,
  dashArray: '5 4',
  fillColor: '#b3261e',
  fillOpacity: 0.12,
}

function formatHa(value: number): string {
  return value.toLocaleString('es-CL', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function markFeatureClick(event: L.LeafletMouseEvent): void {
  const original = event.originalEvent as MouseEvent & { _forestryFeatureClick?: boolean }
  original._forestryFeatureClick = true
}

export function MapView({
  collection,
  filteredFeatures,
  encoding,
  selectedOrdinal,
  onSelect,
  zoomRequest,
  fitNonce,
  onFitToResults,
  sidebarCollapsed,
  mapFocus,
  activeFilterCount,
  onToggleSidebar,
  onToggleMapFocus,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const groupRef = useRef<L.FeatureGroup | null>(null)
  const markerGroupRef = useRef<L.FeatureGroup | null>(null)
  const baseLayerRef = useRef<L.TileLayer | null>(null)
  const layersRef = useRef<Map<number, FeatureLayer>>(new Map())
  const styleForRef = useRef<(featureOrdinal: number) => L.PathOptions>(() => ({}))
  const onSelectRef = useRef(onSelect)

  // Targeted-restyle bookkeeping: avoids re-applying setStyle to every
  // visible layer (measured 1,568 calls) when only selection/draft changes.
  const prevVisibleRef = useRef<Set<number>>(new Set())
  const prevSelectedRef = useRef<number | null>(null)
  const prevDraftRef = useRef<number | null>(null)
  const prevEncodingRef = useRef<ColorEncoding | null>(null)

  const draftLayerRef = useRef<L.Polygon | null>(null)
  const draftMarkerGroupRef = useRef<L.LayerGroup | null>(null)
  const draftCoordinatesRef = useRef<DraftCoordinates | null>(null)
  const draftSeedRef = useRef<DraftCoordinates | null>(null)
  const cutGuideGroupRef = useRef<L.LayerGroup | null>(null)
  const cutStartRef = useRef<[number, number] | null>(null)
  const cutModeRef = useRef(false)
  const cutPreviewActiveRef = useRef(false)
  const cutClickHandlerRef = useRef<(latlng: L.LatLng) => void>(() => undefined)
  const historyRef = useRef<DraftHistoryState>(createDraftHistory())
  const escapeHandlerRef = useRef<() => boolean>(() => false)
  const undoHandlerRef = useRef<() => void>(() => undefined)
  const redoHandlerRef = useRef<() => void>(() => undefined)

  const [basemapMode, setBasemapMode] = useState<BasemapMode>('map')
  const [draftFeatureOrdinal, setDraftFeatureOrdinal] = useState<number | null>(null)
  const [draftAreaHa, setDraftAreaHa] = useState<number | null>(null)
  const [draftVertexCount, setDraftVertexCount] = useState<number | null>(null)
  const [draftHandleCount, setDraftHandleCount] = useState<number | null>(null)
  const [draftVersion, setDraftVersion] = useState(0)
  const [draftMode, setDraftMode] = useState<DraftMode>('move')
  const [cutStatus, setCutStatus] = useState<string | null>(null)
  const [cutPreview, setCutPreview] = useState<CutPreview | null>(null)
  const [simplifyLevel, setSimplifyLevel] = useState<SimplifyLevel | null>(null)
  const [historyTick, setHistoryTick] = useState(0)
  const [panelCollapsed, setPanelCollapsed] = useState(false)

  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  useEffect(() => {
    cutModeRef.current = draftMode === 'cut' && cutPreview === null
    cutPreviewActiveRef.current = cutPreview !== null
  }, [draftMode, cutPreview])

  const clearCutGuide = () => {
    cutGuideGroupRef.current?.clearLayers()
    cutStartRef.current = null
  }

  const resetHistory = () => {
    historyRef.current = createDraftHistory()
    setHistoryTick((tick) => tick + 1)
  }

  const recordHistory = (previous: DraftCoordinates) => {
    historyRef.current = pushDraftHistory(historyRef.current, cloneCoordinates(previous))
    setHistoryTick((tick) => tick + 1)
  }

  // Map lifecycle.
  useEffect(() => {
    const container = containerRef.current
    if (container === null) return

    const map = L.map(container, {
      preferCanvas: true,
      zoomControl: true,
      attributionControl: true,
      zoomSnap: 0.25,
    })
    map.setView([-40.45, -73.35], 10)
    L.control.scale({ metric: true, imperial: false }).addTo(map)
    cutGuideGroupRef.current = L.layerGroup().addTo(map)

    const handleBackgroundClick = (event: L.LeafletMouseEvent) => {
      if (cutModeRef.current) {
        cutClickHandlerRef.current(event.latlng)
        return
      }
      // A cut preview shows two pieces the user picks between; an empty-map
      // click nearby should not silently discard the whole draft. Only the
      // explicit buttons, a piece click, or Escape resolve the preview.
      if (cutPreviewActiveRef.current) return
      const original = event.originalEvent as MouseEvent & { _forestryFeatureClick?: boolean }
      if (original._forestryFeatureClick !== true) onSelectRef.current(null)
    }
    map.on('click', handleBackgroundClick)

    mapRef.current = map

    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(container)

    return () => {
      observer.disconnect()
      map.remove()
      mapRef.current = null
      groupRef.current = null
      baseLayerRef.current = null
      draftLayerRef.current = null
      draftMarkerGroupRef.current = null
      draftCoordinatesRef.current = null
      draftSeedRef.current = null
      cutGuideGroupRef.current = null
      layersRef.current = new Map()
      fittedCollectionRef.current = null
    }
  }, [])

  // Undo / redo / escape keyboard shortcuts, active only while editing.
  useEffect(() => {
    if (draftFeatureOrdinal === null) return

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return

      if (event.key === 'Escape') {
        if (escapeHandlerRef.current()) event.preventDefault()
        return
      }

      const modifier = event.metaKey || event.ctrlKey
      if (!modifier) return
      if (event.key.toLowerCase() !== 'z') return

      event.preventDefault()
      if (event.shiftKey) {
        redoHandlerRef.current()
      } else {
        undoHandlerRef.current()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [draftFeatureOrdinal])

  // Basemap is presentation only. Forestry geometry remains the source layer.
  useEffect(() => {
    const map = mapRef.current
    if (map === null) return

    if (baseLayerRef.current !== null) {
      baseLayerRef.current.remove()
      baseLayerRef.current = null
    }
    if (basemapMode === 'none') return

    const satellite = basemapMode === 'satellite'
    baseLayerRef.current = L.tileLayer(satellite ? SATELLITE_TILE_URL : OSM_TILE_URL, {
      maxZoom: 19,
      attribution: satellite ? SATELLITE_ATTRIBUTION : OSM_ATTRIBUTION,
      crossOrigin: true,
    }).addTo(map)
  }, [basemapMode])

  // Build one Leaflet polygon per source feature, once per collection.
  useEffect(() => {
    const map = mapRef.current
    if (map === null) return

    const group = L.featureGroup().addTo(map)
    groupRef.current = group
    const markerGroup = L.featureGroup().addTo(map)
    markerGroupRef.current = markerGroup
    const layers = new Map<number, FeatureLayer>()

    for (const feature of collection.features) {
      const featureOrdinal = feature.properties.feature_ordinal
      const latLngs = multiPolygonToLatLngs(feature.geometry)
      const layer = L.polygon(latLngs, styleForRef.current(featureOrdinal))

      layer.bindTooltip(tooltipHtml(feature.properties), {
        sticky: true,
        direction: 'top',
        className: 'map-tooltip',
      })

      layer.on('click', (event: L.LeafletMouseEvent) => {
        if (cutModeRef.current) return
        markFeatureClick(event)
        onSelectRef.current(featureOrdinal)
      })

      layer.on('mouseover', () => layer.setStyle({ fillOpacity: 0.92, weight: 2 }))
      layer.on('mouseout', () => layer.setStyle(styleForRef.current(featureOrdinal)))

      const [minx, miny, maxx, maxy] = multiPolygonUtmBbox(feature.geometry)
      const [lon, lat] = utmToLonLat((minx + maxx) / 2, (miny + maxy) / 2)

      layers.set(featureOrdinal, {
        layer,
        feature,
        visible: false,
        centroid: L.latLng(lat, lon),
        maxExtentMeters: Math.max(maxx - minx, maxy - miny),
        marker: null,
      })
    }

    layersRef.current = layers
    prevVisibleRef.current = new Set()
    prevSelectedRef.current = null
    prevDraftRef.current = null
    prevEncodingRef.current = null

    return () => {
      group.remove()
      markerGroup.remove()
      groupRef.current = null
      markerGroupRef.current = null
      layersRef.current = new Map()
    }
  }, [collection])

  // If selection moves away from the locally edited polygon, discard the draft.
  useEffect(() => {
    if (draftFeatureOrdinal !== null && selectedOrdinal !== draftFeatureOrdinal) {
      setDraftFeatureOrdinal(null)
      draftSeedRef.current = null
      clearCutGuide()
      setCutPreview(null)
      setSimplifyLevel(null)
      setDraftMode('move')
      resetHistory()
    }
  }, [draftFeatureOrdinal, selectedOrdinal])

  // Visibility + style: driven by filters, color encoding, selection and draft
  // state. Only layers whose visibility or role actually changed get
  // restyled — measured to cut ~1,568 setStyle calls down to a handful when
  // entering/leaving edit mode or changing selection.
  useEffect(() => {
    const group = groupRef.current
    if (group === null) return

    const visibleOrdinals = new Set(
      filteredFeatures.map((feature) => feature.properties.feature_ordinal),
    )

    const styleFor = (featureOrdinal: number): L.PathOptions => {
      const entry = layersRef.current.get(featureOrdinal)
      const color =
        entry !== undefined && encoding !== null ? encoding.colorFor(entry.feature) : '#9a9890'
      const selected = featureOrdinal === selectedOrdinal
      const editing = featureOrdinal === draftFeatureOrdinal
      const zoom = mapRef.current?.getZoom() ?? 12
      const strokeWeight = zoom >= 12 || visibleOrdinals.size <= 200 ? 0.8 : 0

      return {
        color: editing || selected ? '#14130f' : '#ffffff',
        weight: editing ? 2 : selected ? 2.5 : strokeWeight,
        opacity: editing || selected ? 1 : 0.85,
        fillColor: color,
        fillOpacity: editing ? 0.12 : 0.78,
        dashArray: editing ? '5 4' : undefined,
      }
    }
    styleForRef.current = styleFor

    const previouslyVisible = prevVisibleRef.current
    const encodingChanged = prevEncodingRef.current !== encoding
    const touchedOrdinals = new Set<number>()
    if (prevSelectedRef.current !== null) touchedOrdinals.add(prevSelectedRef.current)
    if (selectedOrdinal !== null) touchedOrdinals.add(selectedOrdinal)
    if (prevDraftRef.current !== null) touchedOrdinals.add(prevDraftRef.current)
    if (draftFeatureOrdinal !== null) touchedOrdinals.add(draftFeatureOrdinal)

    let selectedLayer: L.Polygon | null = null
    for (const [featureOrdinal, entry] of layersRef.current) {
      const visible = visibleOrdinals.has(featureOrdinal)
      const wasVisible = previouslyVisible.has(featureOrdinal)
      if (visible && !entry.visible) {
        group.addLayer(entry.layer)
        entry.visible = true
      } else if (!visible && entry.visible) {
        group.removeLayer(entry.layer)
        entry.visible = false
      }
      if (visible && (!wasVisible || encodingChanged || touchedOrdinals.has(featureOrdinal))) {
        entry.layer.setStyle(styleFor(featureOrdinal))
      }
      if (visible && featureOrdinal === selectedOrdinal) selectedLayer = entry.layer
    }
    if (selectedLayer !== null) selectedLayer.bringToFront()

    prevVisibleRef.current = visibleOrdinals
    prevSelectedRef.current = selectedOrdinal
    prevDraftRef.current = draftFeatureOrdinal
    prevEncodingRef.current = encoding

    const syncMarkers = () => {
      const map = mapRef.current
      const markerGroup = markerGroupRef.current
      if (map === null || markerGroup === null) return

      const useMarkers = visibleOrdinals.size <= MARKER_MAX_SUBSET
      const resolution = metersPerPixel(map.getCenter().lat, map.getZoom())

      for (const [featureOrdinal, entry] of layersRef.current) {
        const wantMarker =
          useMarkers &&
          entry.visible &&
          featureOrdinal !== draftFeatureOrdinal &&
          entry.maxExtentMeters / resolution < MARKER_MIN_POLYGON_PX

        if (wantMarker) {
          const color = encoding !== null ? encoding.colorFor(entry.feature) : '#9a9890'
          if (entry.marker === null) {
            const marker = L.circleMarker(entry.centroid, {
              radius: 4,
              weight: 1,
              color: '#ffffff',
              opacity: 0.9,
              fillColor: color,
              fillOpacity: 0.95,
            })
            marker.bindTooltip(tooltipHtml(entry.feature.properties), {
              sticky: true,
              direction: 'top',
              className: 'map-tooltip',
            })
            marker.on('click', (event: L.LeafletMouseEvent) => {
              if (cutModeRef.current) return
              markFeatureClick(event)
              onSelectRef.current(featureOrdinal)
            })
            entry.marker = marker
          }
          entry.marker.setStyle({ fillColor: color })
          if (!markerGroup.hasLayer(entry.marker)) markerGroup.addLayer(entry.marker)
        } else if (entry.marker !== null && markerGroup.hasLayer(entry.marker)) {
          markerGroup.removeLayer(entry.marker)
        }
      }
    }

    syncMarkers()
    const map = mapRef.current
    if (map !== null) {
      const restyleOnZoom = () => {
        for (const [featureOrdinal, entry] of layersRef.current) {
          if (entry.visible) entry.layer.setStyle(styleFor(featureOrdinal))
        }
        syncMarkers()
      }
      map.on('zoomend', restyleOnZoom)
      return () => {
        map.off('zoomend', restyleOnZoom)
      }
    }
  }, [filteredFeatures, encoding, selectedOrdinal, draftFeatureOrdinal])

  // Local-only draft geometry editor. A seed is used after simplification or
  // cutting; otherwise the immutable source geometry starts the draft.
  useEffect(() => {
    const map = mapRef.current
    if (map === null || draftFeatureOrdinal === null) return

    const entry = layersRef.current.get(draftFeatureOrdinal)
    if (entry === undefined || !entry.feature.properties.geometry_is_valid) return

    const coordinates = cloneCoordinates(
      draftSeedRef.current ?? entry.feature.geometry.coordinates,
    )
    draftCoordinatesRef.current = coordinates
    setDraftAreaHa(multiPolygonAreaSquareMeters(coordinates) / 10_000)
    setDraftVertexCount(countDraftVertices(coordinates))

    // Mutable cache mirroring `coordinates`, one entry per source vertex
    // (including the closing duplicate). Dragging patches only the moved
    // point here instead of reprojecting the whole polygon every event.
    const latLngsCache = multiPolygonToLatLngs({ type: 'MultiPolygon', coordinates })

    const draftLayer = L.polygon(latLngsCache, DRAFT_STYLE).addTo(map)
    draftLayerRef.current = draftLayer

    const markerGroup = L.layerGroup().addTo(map)
    draftMarkerGroupRef.current = markerGroup

    let areaFramePending = false
    const scheduleAreaUpdate = () => {
      if (areaFramePending) return
      areaFramePending = true
      requestAnimationFrame(() => {
        areaFramePending = false
        setDraftAreaHa(multiPolygonAreaSquareMeters(coordinates) / 10_000)
      })
    }

    let totalHandles = 0

    if (draftMode === 'move') {
      for (let polygonIndex = 0; polygonIndex < coordinates.length; polygonIndex += 1) {
        const polygon = coordinates[polygonIndex]
        if (polygon === undefined) continue

        for (let ringIndex = 0; ringIndex < polygon.length; ringIndex += 1) {
          const ring = polygon[ringIndex]
          if (ring === undefined) continue
          const markerCount = isClosedRing(ring) ? ring.length - 1 : ring.length
          const handleIndices =
            markerCount > MAX_VERTEX_HANDLES_PER_RING
              ? pickHandleIndices(ring, MAX_VERTEX_HANDLES_PER_RING)
              : Array.from({ length: markerCount }, (_, index) => index)
          totalHandles += handleIndices.length
          const closed = isClosedRing(ring)
          const lastIndex = ring.length - 1

          for (const vertexIndex of handleIndices) {
            const position = ring[vertexIndex]
            if (position === undefined) continue
            const x = position[0]
            const y = position[1]
            if (x === undefined || y === undefined) continue
            const [lon, lat] = utmToLonLat(x, y)

            const marker = L.marker([lat, lon], {
              draggable: true,
              keyboard: false,
              icon: L.divIcon({
                className: 'draft-vertex',
                html: '<span></span>',
                iconSize: [12, 12],
                iconAnchor: [6, 6],
              }),
            }).addTo(markerGroup)

            marker.on('dragstart', () => {
              const current = draftCoordinatesRef.current
              if (current !== null) recordHistory(current)
            })

            marker.on('drag', () => {
              const point = marker.getLatLng()
              const [nextX, nextY] = lonLatToUtm(point.lng, point.lat)
              moveDraftVertex(coordinates, polygonIndex, ringIndex, vertexIndex, nextX, nextY)

              const ringLatLngs = latLngsCache[polygonIndex]?.[ringIndex]
              if (ringLatLngs !== undefined) {
                const [movedLon, movedLat] = utmToLonLat(nextX, nextY)
                ringLatLngs[vertexIndex] = [movedLat, movedLon]
                if (closed && vertexIndex === 0) {
                  ringLatLngs[lastIndex] = [movedLat, movedLon]
                } else if (closed && vertexIndex === lastIndex) {
                  ringLatLngs[0] = [movedLat, movedLon]
                }
              }
              draftLayer.setLatLngs(latLngsCache)
              scheduleAreaUpdate()
            })

            marker.on('dragend', () => {
              setDraftAreaHa(multiPolygonAreaSquareMeters(coordinates) / 10_000)
            })
          }
        }
      }
    }

    setDraftHandleCount(draftMode === 'move' ? totalHandles : null)
    draftLayer.bringToFront()

    return () => {
      markerGroup.remove()
      draftLayer.remove()
      draftMarkerGroupRef.current = null
      draftLayerRef.current = null
      draftCoordinatesRef.current = null
    }
  }, [draftFeatureOrdinal, draftVersion, draftMode])

  // Two-click straight cut. Only the safe geometry contract in
  // straightCutCandidates can produce a preview.
  useEffect(() => {
    cutClickHandlerRef.current = (latlng: L.LatLng) => {
      if (draftMode !== 'cut' || cutPreview !== null) return
      const current = draftCoordinatesRef.current
      if (current === null) return

      const point = lonLatToUtm(latlng.lng, latlng.lat)
      const guide = cutGuideGroupRef.current
      const start = cutStartRef.current

      if (start === null) {
        cutStartRef.current = point
        guide?.clearLayers()
        L.circleMarker(latlng, {
          radius: 5,
          color: '#8c3b20',
          weight: 2,
          fillColor: '#ffffff',
          fillOpacity: 1,
        }).addTo(guide ?? L.layerGroup())
        setCutStatus('Primer punto listo · haz clic al otro lado. Esc para cancelar.')
        return
      }

      if (guide !== null) {
        const [startLon, startLat] = utmToLonLat(start[0], start[1])
        L.polyline(
          [L.latLng(startLat, startLon), latlng],
          { color: '#b64224', weight: 3, dashArray: '8 5' },
        ).addTo(guide)
        L.circleMarker(latlng, {
          radius: 5,
          color: '#8c3b20',
          weight: 2,
          fillColor: '#ffffff',
          fillOpacity: 1,
        }).addTo(guide)
      }

      const result = straightCutCandidates(current, start, point)
      cutStartRef.current = null

      if (!result.ok) {
        setCutStatus(result.reason + ' Intenta otra línea.')
        window.setTimeout(() => guide?.clearLayers(), 700)
        return
      }

      const selectedIndex = result.largerPieceIndex
      const removedHa = result.areasSquareMeters[selectedIndex === 0 ? 1 : 0] / 10_000
      const preview: CutPreview = {
        pieces: [cloneCoordinates(result.pieces[0]), cloneCoordinates(result.pieces[1])],
        selectedIndex,
        beforeCut: cloneCoordinates(current),
      }
      setCutPreview(preview)
      setCutStatus(
        `Corte listo · se removerían ${formatHa(removedHa)} ha. ` +
          'Haz clic en el lado que quieres conservar.',
      )
    }
  }, [draftMode, cutPreview])

  // While a cut preview is active, show both resulting pieces at once so the
  // user can compare and click the side to keep, instead of only seeing the
  // currently-selected piece.
  useEffect(() => {
    const map = mapRef.current
    if (map === null || cutPreview === null) return

    const retainedCoordinates = cutPreview.pieces[cutPreview.selectedIndex]
    const removedCoordinates = cutPreview.pieces[cutPreview.selectedIndex === 0 ? 1 : 0]

    const retainedLayer = L.polygon(
      multiPolygonToLatLngs({ type: 'MultiPolygon', coordinates: retainedCoordinates }),
      CUT_RETAINED_STYLE,
    ).addTo(map)
    const removedLayer = L.polygon(
      multiPolygonToLatLngs({ type: 'MultiPolygon', coordinates: removedCoordinates }),
      CUT_REMOVED_STYLE,
    ).addTo(map)

    const selectOtherSide = (event: L.LeafletMouseEvent) => {
      markFeatureClick(event)
      setCutPreview((current) =>
        current === null
          ? current
          : { ...current, selectedIndex: current.selectedIndex === 0 ? 1 : 0 },
      )
    }
    removedLayer.on('click', selectOtherSide)
    retainedLayer.on('click', (event: L.LeafletMouseEvent) => markFeatureClick(event))

    retainedLayer.bringToFront()
    draftLayerRef.current?.setStyle({ opacity: 0, fillOpacity: 0 })

    return () => {
      retainedLayer.remove()
      removedLayer.remove()
      draftLayerRef.current?.setStyle(DRAFT_STYLE)
    }
  }, [cutPreview])

  // Initial fit to the whole loaded collection (once per collection object).
  const fittedCollectionRef = useRef<FeatureCollection | null>(null)
  useEffect(() => {
    const map = mapRef.current
    const group = groupRef.current
    if (map === null || group === null || fittedCollectionRef.current === collection) return
    const bounds = group.getBounds()
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [16, 16] })
      fittedCollectionRef.current = collection
    }
  }, [collection, filteredFeatures])

  useEffect(() => {
    if (fitNonce === 0) return
    const map = mapRef.current
    const group = groupRef.current
    if (map === null || group === null) return
    const bounds = group.getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [16, 16] })
  }, [fitNonce])

  useEffect(() => {
    if (zoomRequest === null) return
    const map = mapRef.current
    const entry = layersRef.current.get(zoomRequest.featureOrdinal)
    if (map === null || entry === undefined) return
    const bounds = entry.layer.getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [48, 48], maxZoom: 16 })
  }, [zoomRequest])

  const draftFeature =
    draftFeatureOrdinal === null
      ? null
      : collection.features.find(
          (feature) => feature.properties.feature_ordinal === draftFeatureOrdinal,
        ) ?? null
  const originalAreaHa =
    draftFeature === null ? null : draftFeature.properties.geometry_area_source_units / 10_000

  const previewRetainedAreaHa =
    cutPreview === null
      ? null
      : multiPolygonAreaSquareMeters(cutPreview.pieces[cutPreview.selectedIndex]) / 10_000
  const previewRemovedAreaHa =
    cutPreview === null
      ? null
      : multiPolygonAreaSquareMeters(
          cutPreview.pieces[cutPreview.selectedIndex === 0 ? 1 : 0],
        ) / 10_000

  const displayedAreaHa = previewRetainedAreaHa ?? draftAreaHa
  const areaDifferenceHa =
    originalAreaHa === null || displayedAreaHa === null ? null : displayedAreaHa - originalAreaHa
  const areaDifferencePercent =
    originalAreaHa === null || originalAreaHa === 0 || areaDifferenceHa === null
      ? null
      : (areaDifferenceHa / originalAreaHa) * 100

  const selectedFeature =
    selectedOrdinal === null
      ? null
      : collection.features.find(
          (feature) => feature.properties.feature_ordinal === selectedOrdinal,
        ) ?? null

  const sourceVertexCount =
    draftFeature === null ? null : countDraftVertices(draftFeature.geometry.coordinates)
  const cutSupported =
    draftFeature !== null &&
    draftFeature.geometry.coordinates.length === 1 &&
    draftFeature.geometry.coordinates[0]?.length === 1

  const simplifyPreview = useMemo(() => {
    if (simplifyLevel === null) return null
    const current = draftCoordinatesRef.current
    if (current === null) return null
    const level = SIMPLIFY_LEVELS.find((entry) => entry.id === simplifyLevel)
    if (level === undefined) return null

    const simplified = simplifyDraftCoordinates(current, level.toleranceMeters)
    const beforeCount = countDraftVertices(current)
    const afterCount = countDraftVertices(simplified)
    const beforeAreaHa = multiPolygonAreaSquareMeters(current) / 10_000
    const afterAreaHa = multiPolygonAreaSquareMeters(simplified) / 10_000

    return {
      coordinates: simplified,
      beforeCount,
      afterCount,
      deltaAreaHa: afterAreaHa - beforeAreaHa,
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simplifyLevel, draftVersion, draftFeatureOrdinal])

  const canUndo = historyRef.current.past.length > 0
  const canRedo = historyRef.current.future.length > 0
  void historyTick // re-render trigger for canUndo/canRedo

  const beginDraft = () => {
    if (selectedFeature === null) return
    draftSeedRef.current = null
    resetHistory()
    setSimplifyLevel(null)
    setCutStatus(null)
    setCutPreview(null)
    clearCutGuide()
    setDraftMode('move')
    setDraftFeatureOrdinal(selectedFeature.properties.feature_ordinal)
  }

  const applySimplifyPreview = () => {
    if (simplifyPreview === null) return
    const current = draftCoordinatesRef.current
    if (current !== null) recordHistory(current)
    draftSeedRef.current = simplifyPreview.coordinates
    setSimplifyLevel(null)
    setCutStatus(null)
    setCutPreview(null)
    clearCutGuide()
    setDraftMode('move')
    setDraftVersion((version) => version + 1)
  }

  const cancelSimplifyPreview = () => setSimplifyLevel(null)

  const startCut = () => {
    const current = draftCoordinatesRef.current
    if (current === null) return
    draftSeedRef.current = cloneCoordinates(current)
    setSimplifyLevel(null)
    setCutPreview(null)
    clearCutGuide()
    setCutStatus('Haz clic en dos puntos del borde para trazar el corte. Esc para cancelar.')
    setDraftMode('cut')
  }

  const acceptCut = () => {
    if (cutPreview === null) return
    recordHistory(cutPreview.beforeCut)
    draftSeedRef.current = cloneCoordinates(cutPreview.pieces[cutPreview.selectedIndex])
    setCutPreview(null)
    setCutStatus('Corte aplicado al borrador local. Puedes seguir ajustando puntos.')
    clearCutGuide()
    setDraftMode('move')
    setDraftVersion((version) => version + 1)
  }

  const cancelCut = () => {
    setCutPreview(null)
    clearCutGuide()
    setCutStatus(null)
    setDraftMode('move')
  }

  const resetDraft = () => {
    const current = draftCoordinatesRef.current
    if (current !== null) recordHistory(current)
    draftSeedRef.current = null
    setSimplifyLevel(null)
    setCutPreview(null)
    setCutStatus(null)
    clearCutGuide()
    setDraftMode('move')
    setDraftVersion((version) => version + 1)
  }

  const discardDraft = () => {
    draftSeedRef.current = null
    resetHistory()
    setCutPreview(null)
    setSimplifyLevel(null)
    setCutStatus(null)
    clearCutGuide()
    setDraftMode('move')
    setDraftFeatureOrdinal(null)
  }

  const performUndo = () => {
    const current = draftCoordinatesRef.current
    if (current === null) return
    const step = undoDraftHistory(historyRef.current, cloneCoordinates(current))
    if (step === null) return
    historyRef.current = step.history
    setHistoryTick((tick) => tick + 1)
    draftSeedRef.current = step.coordinates
    setCutPreview(null)
    setSimplifyLevel(null)
    setCutStatus('Cambio deshecho.')
    clearCutGuide()
    setDraftMode('move')
    setDraftVersion((version) => version + 1)
  }

  const performRedo = () => {
    const current = draftCoordinatesRef.current
    if (current === null) return
    const step = redoDraftHistory(historyRef.current, cloneCoordinates(current))
    if (step === null) return
    historyRef.current = step.history
    setHistoryTick((tick) => tick + 1)
    draftSeedRef.current = step.coordinates
    setCutPreview(null)
    setSimplifyLevel(null)
    setCutStatus('Cambio rehecho.')
    clearCutGuide()
    setDraftMode('move')
    setDraftVersion((version) => version + 1)
  }

  undoHandlerRef.current = performUndo
  redoHandlerRef.current = performRedo
  escapeHandlerRef.current = () => {
    if (cutStartRef.current !== null) {
      clearCutGuide()
      setCutStatus('Haz clic en dos puntos del borde para trazar el corte. Esc para cancelar.')
      return true
    }
    if (cutPreview !== null) {
      cancelCut()
      return true
    }
    if (draftMode === 'cut') {
      setDraftMode('move')
      setCutStatus(null)
      return true
    }
    if (simplifyLevel !== null) {
      cancelSimplifyPreview()
      return true
    }
    return false
  }

  return (
    <div className={`map${draftMode === 'cut' ? ' map--cutting' : ''}`}>
      <div ref={containerRef} className="map__canvas" data-testid="map-canvas" />
      <div className="map__controls" aria-label="Controles del mapa">
        <button
          type="button"
          className="map__control-button"
          onClick={onToggleSidebar}
          aria-pressed={!sidebarCollapsed && !mapFocus}
        >
          {sidebarCollapsed || mapFocus ? 'Mostrar filtros' : 'Ocultar filtros'}
          {activeFilterCount > 0 ? ` (${activeFilterCount})` : ''}
        </button>
        <label className="map__basemap-control">
          <span>Fondo</span>
          <select
            className="map__basemap-select"
            value={basemapMode}
            onChange={(event) => setBasemapMode(event.target.value as BasemapMode)}
            aria-label="Fondo del mapa"
          >
            <option value="map">Mapa</option>
            <option value="satellite">Satélite</option>
            <option value="none">Sin fondo</option>
          </select>
        </label>
        <button type="button" className="map__control-button" onClick={onFitToResults}>
          Ajustar a resultados
        </button>
        {selectedFeature !== null && draftFeatureOrdinal === null ? (
          <button
            type="button"
            className="map__control-button map__control-button--draft"
            disabled={!selectedFeature.properties.geometry_is_valid}
            onClick={beginDraft}
            title={
              selectedFeature.properties.geometry_is_valid
                ? 'Crear un borrador local; no modifica la fuente'
                : 'La simulación requiere una geometría fuente válida'
            }
          >
            Simular ajuste
          </button>
        ) : null}
        <button
          type="button"
          className="map__control-button map__control-button--focus"
          aria-pressed={mapFocus}
          onClick={onToggleMapFocus}
        >
          {mapFocus ? 'Salir de modo mapa' : 'Modo mapa'}
        </button>
      </div>

      {draftFeature !== null && originalAreaHa !== null && displayedAreaHa !== null ? (
        <section
          className={`draft-edit${panelCollapsed ? ' draft-edit--collapsed' : ''}`}
          aria-label="Simulación local de límite"
        >
          <div className="draft-edit__heading">
            <div>
              <strong>Simulación de límite</strong>
              <span>
                {draftFeature.properties.n_rodal !== null
                  ? `Rodal ${draftFeature.properties.n_rodal}`
                  : `Polígono #${draftFeature.properties.feature_ordinal}`}
              </span>
            </div>
            <span className="draft-edit__badge">Borrador local</span>
            <button
              type="button"
              className="draft-edit__collapse"
              onClick={() => setPanelCollapsed((collapsed) => !collapsed)}
              aria-expanded={!panelCollapsed}
              title={panelCollapsed ? 'Expandir panel' : 'Minimizar panel'}
            >
              {panelCollapsed ? '▸' : '▾'}
            </button>
          </div>

          <div className="draft-edit__metrics">
            <div>
              <span>Área original</span>
              <strong>{formatHa(originalAreaHa)} ha</strong>
            </div>
            <div>
              <span>{cutPreview !== null ? 'Área resultante' : 'Área estimada'}</span>
              <strong>{formatHa(displayedAreaHa)} ha</strong>
            </div>
            {cutPreview !== null && previewRemovedAreaHa !== null ? (
              <div>
                <span>Área removida</span>
                <strong>{formatHa(previewRemovedAreaHa)} ha</strong>
              </div>
            ) : null}
            <div>
              <span>Diferencia</span>
              <strong>
                {areaDifferenceHa !== null && areaDifferenceHa >= 0 ? '+' : ''}
                {areaDifferenceHa === null ? '—' : formatHa(areaDifferenceHa)} ha
                {areaDifferencePercent === null
                  ? ''
                  : ` (${areaDifferencePercent >= 0 ? '+' : ''}${areaDifferencePercent.toFixed(1)}%)`}
              </strong>
            </div>
          </div>

          {!panelCollapsed ? (
            <>
              <div className="draft-edit__tools" aria-label="Herramientas del borrador">
                <button
                  type="button"
                  className={`draft-tool${draftMode === 'move' ? ' draft-tool--active' : ''}`}
                  onClick={() => {
                    const current = draftCoordinatesRef.current
                    if (current !== null) draftSeedRef.current = cloneCoordinates(current)
                    setCutPreview(null)
                    setSimplifyLevel(null)
                    setCutStatus(null)
                    clearCutGuide()
                    setDraftMode('move')
                  }}
                >
                  Mover puntos
                </button>
                <button
                  type="button"
                  className={`draft-tool${simplifyLevel !== null ? ' draft-tool--active' : ''}`}
                  onClick={() => {
                    setCutPreview(null)
                    setCutStatus(null)
                    clearCutGuide()
                    setDraftMode('move')
                    setSimplifyLevel((level) => (level === null ? 'medio' : null))
                  }}
                >
                  Reducir puntos
                </button>
                <button
                  type="button"
                  className={`draft-tool${draftMode === 'cut' ? ' draft-tool--active' : ''}`}
                  onClick={startCut}
                  disabled={!cutSupported}
                  title={
                    cutSupported
                      ? 'Dibuja una línea recta con dos clics y conserva uno de los lados'
                      : 'Disponible solo para polígonos simples sin huecos ni partes múltiples'
                  }
                >
                  Cortar con línea
                </button>
              </div>

              {simplifyLevel !== null ? (
                <div className="draft-edit__simplify" aria-label="Detalle del límite">
                  <span className="draft-edit__simplify-label">Detalle del límite</span>
                  <div className="draft-edit__simplify-levels">
                    {SIMPLIFY_LEVELS.map((level) => (
                      <button
                        key={level.id}
                        type="button"
                        className={`draft-tool${simplifyLevel === level.id ? ' draft-tool--active' : ''}`}
                        onClick={() => setSimplifyLevel(level.id)}
                      >
                        {level.label}
                      </button>
                    ))}
                  </div>
                  {simplifyPreview !== null ? (
                    <>
                      <p className="draft-edit__simplify-summary">
                        {simplifyPreview.beforeCount} → {simplifyPreview.afterCount} puntos ·
                        variación {simplifyPreview.deltaAreaHa >= 0 ? '+' : ''}
                        {formatHa(simplifyPreview.deltaAreaHa)} ha
                      </p>
                      <div className="draft-edit__cut-actions">
                        <button
                          type="button"
                          className="button button--ghost"
                          onClick={cancelSimplifyPreview}
                        >
                          Cancelar
                        </button>
                        <button type="button" className="button" onClick={applySimplifyPreview}>
                          Aplicar
                        </button>
                      </div>
                    </>
                  ) : null}
                </div>
              ) : null}

              <div className="draft-edit__point-summary">
                <span>
                  Puntos: <strong>{draftVertexCount ?? '—'}</strong>
                  {sourceVertexCount !== null && draftVertexCount !== sourceVertexCount
                    ? ` · fuente ${sourceVertexCount}`
                    : ''}
                </span>
                {draftMode === 'move' &&
                draftHandleCount !== null &&
                draftVertexCount !== null &&
                draftHandleCount < draftVertexCount ? (
                  <span>Controles visibles: {draftHandleCount}</span>
                ) : null}
              </div>

              {cutStatus !== null ? <p className="draft-edit__status">{cutStatus}</p> : null}

              {cutPreview !== null ? (
                <div className="draft-edit__cut-actions">
                  <button
                    type="button"
                    className="button button--ghost"
                    onClick={() =>
                      setCutPreview((current) =>
                        current === null
                          ? current
                          : { ...current, selectedIndex: current.selectedIndex === 0 ? 1 : 0 },
                      )
                    }
                  >
                    Conservar otro lado
                  </button>
                  <button type="button" className="button button--ghost" onClick={cancelCut}>
                    Cancelar corte
                  </button>
                  <button type="button" className="button" onClick={acceptCut}>
                    Aceptar corte
                  </button>
                </div>
              ) : null}

              <p className="draft-edit__note">
                {draftMode === 'cut'
                  ? 'El corte y el área son solo una simulación local. La fuente no cambia.'
                  : 'Arrastra puntos o reduce su cantidad. El área se calcula en EPSG:32718; no se guarda en la fuente.'}
              </p>

              <div className="draft-edit__actions">
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={performUndo}
                  disabled={!canUndo}
                  title="Ctrl/Cmd+Z"
                >
                  Deshacer
                </button>
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={performRedo}
                  disabled={!canRedo}
                  title="Ctrl/Cmd+Shift+Z"
                >
                  Rehacer
                </button>
                <button type="button" className="button button--ghost" onClick={resetDraft}>
                  Reiniciar
                </button>
                <button type="button" className="button" onClick={discardDraft}>
                  Descartar borrador
                </button>
              </div>
            </>
          ) : null}
        </section>
      ) : null}

      {filteredFeatures.length === 0 ? (
        <div className="map__empty" role="status">
          <p>Ningún polígono coincide con los filtros actuales.</p>
        </div>
      ) : null}
    </div>
  )
}
