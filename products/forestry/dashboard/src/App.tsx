import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  NoSnapshotError,
  fetchComparison,
  fetchFeatureCollection,
  fetchLatestIngestedSnapshot,
  fetchSnapshotSummary,
} from './api.ts'
import { Header } from './components/Header.tsx'
import { KpiStrip } from './components/KpiStrip.tsx'
import { FiltersPanel } from './components/FiltersPanel.tsx'
import { LegendPanel } from './components/LegendPanel.tsx'
import { MapView } from './components/MapView.tsx'
import { DataPanel } from './components/DataPanel.tsx'
import { Inspector } from './components/Inspector.tsx'
import { ActiveFilterBar } from './components/ActiveFilterBar.tsx'
import { ErrorView, LoadingView, NoSnapshotView } from './components/StatusViews.tsx'
import { EMPTY_FILTERS, applyFilters, countActiveFilters } from './lib/filters.ts'
import type { FilterState } from './lib/filters.ts'
import { selectionStats } from './lib/aggregate.ts'
import { buildColorEncoding } from './lib/palette.ts'
import type { ColorDimension } from './lib/palette.ts'
import type {
  FeatureCollection,
  ForestrySnapshot,
  SnapshotSummary,
  SourceFieldComparison,
} from './types.ts'

type LoadPhase =
  | { status: 'loading'; step: string }
  | { status: 'no-snapshot' }
  | { status: 'error'; message: string }
  | {
      status: 'ready'
      snapshot: ForestrySnapshot
      summary: SnapshotSummary
      collection: FeatureCollection
      comparison: SourceFieldComparison
    }

export interface ZoomRequest {
  featureOrdinal: number
  nonce: number
}

export default function App() {
  const [phase, setPhase] = useState<LoadPhase>({
    status: 'loading',
    step: 'Conectando con la API…',
  })
  const [reloadNonce, setReloadNonce] = useState(0)
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [colorDimension, setColorDimension] = useState<ColorDimension>('uso2026')
  const [selectedOrdinal, setSelectedOrdinal] = useState<number | null>(null)
  const [zoomRequest, setZoomRequest] = useState<ZoomRequest | null>(null)
  const [fitNonce, setFitNonce] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mapFocus, setMapFocus] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setPhase({ status: 'loading', step: 'Conectando con la API…' })

      try {
        const snapshot = await fetchLatestIngestedSnapshot()

        if (cancelled) return
        setPhase({ status: 'loading', step: 'Cargando resumen y geometría…' })

        const [summary, collection, comparison] = await Promise.all([
          fetchSnapshotSummary(snapshot.shapefile_snapshot_id),
          fetchFeatureCollection(snapshot.shapefile_snapshot_id),
          fetchComparison(snapshot.shapefile_snapshot_id),
        ])

        if (cancelled) return
        setPhase({ status: 'ready', snapshot, summary, collection, comparison })
      } catch (error) {
        if (cancelled) return

        if (error instanceof NoSnapshotError) {
          setPhase({ status: 'no-snapshot' })
        } else {
          setPhase({
            status: 'error',
            message: 'No fue posible cargar los datos desde la API.',
          })
        }
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [reloadNonce])

  const collection = phase.status === 'ready' ? phase.collection : null

  const filteredFeatures = useMemo(
    () => (collection === null ? [] : applyFilters(collection.features, filters)),
    [collection, filters],
  )

  const encoding = useMemo(
    () =>
      collection === null ? null : buildColorEncoding(colorDimension, collection.features),
    [collection, colorDimension],
  )

  const filteredStats = useMemo(() => selectionStats(filteredFeatures), [filteredFeatures])

  const selectedFeature = useMemo(() => {
    if (collection === null || selectedOrdinal === null) {
      return null
    }
    return (
      collection.features.find(
        (feature) => feature.properties.feature_ordinal === selectedOrdinal,
      ) ?? null
    )
  }, [collection, selectedOrdinal])

  const activeFilterCount = countActiveFilters(filters)

  const selectAndZoom = useCallback((featureOrdinal: number) => {
    setSelectedOrdinal(featureOrdinal)
    setZoomRequest((previous) => ({
      featureOrdinal,
      nonce: (previous?.nonce ?? 0) + 1,
    }))
  }, [])

  const handleRetry = useCallback(() => setReloadNonce((nonce) => nonce + 1), [])

  const handleToggleSidebar = useCallback(() => {
    if (mapFocus) {
      setMapFocus(false)
      setSidebarCollapsed(false)
      return
    }
    setSidebarCollapsed((collapsed) => !collapsed)
  }, [mapFocus])

  const handleToggleMapFocus = useCallback(() => {
    setMapFocus((focused) => !focused)
    setSidebarOpen(false)
  }, [])

  if (phase.status === 'loading') {
    return <LoadingView step={phase.step} />
  }

  if (phase.status === 'no-snapshot') {
    return <NoSnapshotView onRetry={handleRetry} />
  }

  if (phase.status === 'error') {
    return <ErrorView message={phase.message} onRetry={handleRetry} />
  }

  const { snapshot, summary, comparison } = phase

  return (
    <div className={`app${mapFocus ? ' app--map-focus' : ''}`}>
      <Header snapshot={snapshot} summary={summary} />
      <KpiStrip summary={summary} comparison={comparison} collection={phase.collection} />

      <div className="app__body">
        <button
          type="button"
          className="app__sidebar-toggle"
          aria-expanded={sidebarOpen}
          onClick={() => setSidebarOpen((open) => !open)}
        >
          {sidebarOpen ? 'Cerrar filtros' : 'Buscar y filtrar'}
          {activeFilterCount > 0 ? (
            <span className="app__filter-count">{activeFilterCount}</span>
          ) : null}
        </button>

        <aside
          className={`app__sidebar${sidebarOpen ? ' app__sidebar--open' : ''}${
            sidebarCollapsed ? ' app__sidebar--collapsed' : ''
          }`}
        >
          <FiltersPanel
            collection={phase.collection}
            filters={filters}
            onFiltersChange={setFilters}
            filteredStats={filteredStats}
          />
          {encoding !== null ? (
            <LegendPanel
              encoding={encoding}
              colorDimension={colorDimension}
              onColorDimensionChange={setColorDimension}
              filters={filters}
              onFiltersChange={setFilters}
            />
          ) : null}
        </aside>

        <main className="app__map" aria-label="Mapa del patrimonio">
          <MapView
            collection={phase.collection}
            filteredFeatures={filteredFeatures}
            encoding={encoding}
            selectedOrdinal={selectedOrdinal}
            onSelect={setSelectedOrdinal}
            zoomRequest={zoomRequest}
            fitNonce={fitNonce}
            onFitToResults={() => setFitNonce((nonce) => nonce + 1)}
            sidebarCollapsed={sidebarCollapsed}
            mapFocus={mapFocus}
            activeFilterCount={activeFilterCount}
            onToggleSidebar={handleToggleSidebar}
            onToggleMapFocus={handleToggleMapFocus}
          />
          <ActiveFilterBar filters={filters} onFiltersChange={setFilters} />
        </main>

        {selectedFeature !== null ? (
          <Inspector
            key={selectedFeature.properties.feature_ordinal}
            snapshotId={snapshot.shapefile_snapshot_id}
            feature={selectedFeature}
            onClose={() => setSelectedOrdinal(null)}
            onZoom={() => selectAndZoom(selectedFeature.properties.feature_ordinal)}
          />
        ) : null}
      </div>

      <DataPanel
        collection={phase.collection}
        filteredFeatures={filteredFeatures}
        filteredStats={filteredStats}
        comparison={comparison}
        summary={summary}
        filters={filters}
        onFiltersChange={setFilters}
        selectedOrdinal={selectedOrdinal}
        onSelectFeature={selectAndZoom}
        snapshotId={snapshot.shapefile_snapshot_id}
      />
    </div>
  )
}
