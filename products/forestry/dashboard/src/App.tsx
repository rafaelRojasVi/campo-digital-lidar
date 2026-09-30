import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  NoSnapshotError,
  canUpload,
  devLogin,
  fetchComparison,
  fetchFeatureCollection,
  fetchPublishedSnapshot,
  fetchSnapshotSummary,
  isForbidden,
  isSignedOut,
} from './api.ts'
import { Header } from './components/Header.tsx'
import { KpiStrip } from './components/KpiStrip.tsx'
import { FiltersPanel } from './components/FiltersPanel.tsx'
import { LegendPanel } from './components/LegendPanel.tsx'
import { MapView } from './components/MapView.tsx'
import { DataPanel } from './components/DataPanel.tsx'
import { Inspector } from './components/Inspector.tsx'
import { ActiveFilterBar } from './components/ActiveFilterBar.tsx'
import {
  ErrorView,
  ForbiddenView,
  LoadingView,
  NoSnapshotView,
  SignedOutView,
} from './components/StatusViews.tsx'
import { PLATFORM_FRONT_DOOR_PATH, platformFrontDoorEnabled } from './runtime/frontDoor.ts'
import { EMPTY_FILTERS, applyFilters, countActiveFilters } from './lib/filters.ts'
import type { FilterState } from './lib/filters.ts'
import { selectionStats } from './lib/aggregate.ts'
import { buildColorEncoding } from './lib/palette.ts'
import type { ColorDimension } from './lib/palette.ts'
import { ROUTES, mapPath, onLinkClick } from './router.ts'
import type {
  FeatureCollection,
  ForestryRole,
  ForestrySnapshot,
  SnapshotSummary,
  SourceFieldComparison,
} from './types.ts'

type LoadPhase =
  | { status: 'loading'; step: string }
  | { status: 'no-snapshot' }
  | { status: 'signed-out' }
  | { status: 'forbidden' }
  | { status: 'error'; message: string }
  | {
      status: 'ready'
      snapshot: ForestrySnapshot
      summary: SnapshotSummary
      collection: FeatureCollection
      comparison: SourceFieldComparison
      /** The published version's id, when the map previews another one. */
      previewOf: number | null
    }

export interface ZoomRequest {
  featureOrdinal: number
  nonce: number
}

interface AppProps {
  /** `?version=<id>`: preview that version instead of the published one. */
  versionId?: number | null
  role?: ForestryRole | null
}

function snapshotFromSummary(summary: SnapshotSummary): ForestrySnapshot {
  return {
    shapefile_snapshot_id: summary.shapefile_snapshot_id,
    layer_name: summary.layer_name,
    family_fingerprint: summary.family_fingerprint,
    storage_srid: summary.storage_srid,
    feature_count: summary.feature_count,
    created_at: summary.created_at,
  }
}

async function publishedIdOrNull(): Promise<number | null> {
  try {
    return (await fetchPublishedSnapshot()).shapefile_snapshot_id
  } catch (error) {
    if (error instanceof NoSnapshotError) return null
    throw error
  }
}

export default function App({ versionId = null, role = null }: AppProps) {
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
        let snapshot: ForestrySnapshot
        let publishedId: number | null

        if (versionId === null) {
          snapshot = await fetchPublishedSnapshot()
          publishedId = snapshot.shapefile_snapshot_id
        } else {
          const [summary, published] = await Promise.all([
            fetchSnapshotSummary(versionId),
            publishedIdOrNull(),
          ])
          snapshot = snapshotFromSummary(summary)
          publishedId = published
        }

        if (cancelled) return
        setPhase({ status: 'loading', step: 'Cargando resumen y geometría…' })

        const [summary, collection, comparison] = await Promise.all([
          fetchSnapshotSummary(snapshot.shapefile_snapshot_id),
          fetchFeatureCollection(snapshot.shapefile_snapshot_id),
          fetchComparison(snapshot.shapefile_snapshot_id),
        ])

        if (cancelled) return
        setPhase({
          status: 'ready',
          snapshot,
          summary,
          collection,
          comparison,
          previewOf: publishedId === snapshot.shapefile_snapshot_id ? null : publishedId,
        })
      } catch (error) {
        if (cancelled) return

        if (error instanceof NoSnapshotError) {
          setPhase({ status: 'no-snapshot' })
        } else if (isSignedOut(error)) {
          // On the platform, sign-in lives at the front door.
          if (platformFrontDoorEnabled()) {
            window.location.assign(PLATFORM_FRONT_DOOR_PATH)
            return
          }
          setPhase({ status: 'signed-out' })
        } else if (isForbidden(error)) {
          setPhase({ status: 'forbidden' })
        } else if (versionId !== null && error instanceof ApiError && error.status === 404) {
          setPhase({ status: 'error', message: 'No se encontró la versión solicitada.' })
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
  }, [reloadNonce, versionId])

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

  const handleDevLogin = useCallback((identityKey: string) => {
    void devLogin(identityKey)
      .catch(() => undefined)
      .finally(() => setReloadNonce((nonce) => nonce + 1))
  }, [])

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

  if (phase.status === 'signed-out') {
    return <SignedOutView onDevLogin={handleDevLogin} />
  }

  if (phase.status === 'forbidden') {
    return <ForbiddenView />
  }

  if (phase.status === 'no-snapshot') {
    return <NoSnapshotView onRetry={handleRetry} canUpload={canUpload(role)} />
  }

  if (phase.status === 'error') {
    return <ErrorView message={phase.message} onRetry={handleRetry} />
  }

  const { snapshot, summary, comparison, previewOf } = phase
  const previewing = versionId !== null && previewOf !== null

  return (
    <div className={`app${mapFocus ? ' app--map-focus' : ''}`}>
      <Header
        active={ROUTES.mapa}
        role={role}
        snapshot={snapshot}
        summary={summary}
        preview={previewing}
      />
      {previewing ? (
        <div className="preview-banner" role="status">
          <span>
            Está viendo la versión N.º {snapshot.shapefile_snapshot_id}, que <b>no</b> es la
            versión publicada. Los demás usuarios siguen viendo la versión N.º {previewOf}.
          </span>
          <a
            className="preview-banner__link"
            href={mapPath()}
            onClick={(event) => onLinkClick(event, mapPath())}
          >
            Ver la versión publicada
          </a>
        </div>
      ) : null}
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
