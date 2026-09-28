import { useState } from 'react'
import { ComparisonPanel } from './ComparisonPanel.tsx'
import { FeatureTable } from './FeatureTable.tsx'
import { QualityPanel } from './QualityPanel.tsx'
import type { FilterState } from '../lib/filters.ts'
import type { SelectionStats } from '../lib/aggregate.ts'
import { formatInt } from '../lib/format.ts'
import type {
  FeatureCollection,
  GeoFeature,
  SnapshotSummary,
  SourceFieldComparison,
} from '../types.ts'

interface DataPanelProps {
  collection: FeatureCollection
  filteredFeatures: GeoFeature[]
  filteredStats: SelectionStats
  comparison: SourceFieldComparison
  summary: SnapshotSummary
  filters: FilterState
  onFiltersChange: (filters: FilterState) => void
  selectedOrdinal: number | null
  onSelectFeature: (featureOrdinal: number) => void
  snapshotId: number
}

type TabId = 'tabla' | 'comparacion' | 'calidad'

export function DataPanel({
  collection,
  filteredFeatures,
  filteredStats,
  comparison,
  summary,
  filters,
  onFiltersChange,
  selectedOrdinal,
  onSelectFeature,
  snapshotId,
}: DataPanelProps) {
  const [tab, setTab] = useState<TabId>('tabla')
  const [collapsed, setCollapsed] = useState(false)

  const tabs: { id: TabId; label: string }[] = [
    { id: 'tabla', label: `Tabla (${formatInt(filteredStats.featureCount)})` },
    {
      id: 'comparacion',
      label: `2024 → 2026 (${formatInt(
        comparison.cod_uso_vs_cod_uso_2026.changed_feature_count,
      )})`,
    },
    { id: 'calidad', label: 'Calidad de datos' },
  ]

  return (
    <section
      className={`data-panel${collapsed ? ' data-panel--collapsed' : ''}`}
      aria-label="Datos de los polígonos filtrados"
    >
      <div className="data-panel__bar">
        <div role="tablist" className="data-panel__tabs" aria-label="Vistas de datos">
          {tabs.map((entry) => (
            <button
              key={entry.id}
              type="button"
              role="tab"
              aria-selected={tab === entry.id}
              className={`data-panel__tab${tab === entry.id ? ' data-panel__tab--active' : ''}`}
              onClick={() => {
                setTab(entry.id)
                setCollapsed(false)
              }}
            >
              {entry.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="data-panel__collapse"
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((value) => !value)}
        >
          {collapsed ? 'Mostrar panel' : 'Ocultar panel'}
        </button>
      </div>

      {!collapsed ? (
        <div className="data-panel__content">
          {tab === 'tabla' ? (
            <FeatureTable
              features={filteredFeatures}
              selectedOrdinal={selectedOrdinal}
              onSelectFeature={onSelectFeature}
              snapshotId={snapshotId}
            />
          ) : null}
          {tab === 'comparacion' ? (
            <ComparisonPanel
              comparison={comparison}
              collection={collection}
              filters={filters}
              onFiltersChange={onFiltersChange}
              onSelectFeature={onSelectFeature}
            />
          ) : null}
          {tab === 'calidad' ? (
            <QualityPanel
              summary={summary}
              filters={filters}
              onFiltersChange={onFiltersChange}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
