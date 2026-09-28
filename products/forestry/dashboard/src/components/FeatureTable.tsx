import { useEffect, useMemo, useRef, useState } from 'react'
import { downloadCsv } from '../lib/csv.ts'
import { formatHa, formatInt } from '../lib/format.ts'
import { qualityFlagLabel } from '../lib/qualityLabels.ts'
import { sortFeatures } from '../lib/tableSort.ts'
import type { SortKey, SortState } from '../lib/tableSort.ts'
import type { GeoFeature } from '../types.ts'

interface FeatureTableProps {
  features: GeoFeature[]
  selectedOrdinal: number | null
  onSelectFeature: (featureOrdinal: number) => void
  snapshotId: number
}

const PAGE_SIZE = 25

const COLUMNS: { key: SortKey | null; label: string; className?: string }[] = [
  { key: 'predio', label: 'Predio' },
  { key: 'rodal', label: 'Rodal', className: 'table__cell--num' },
  { key: 'uso2026', label: 'Uso 2026' },
  { key: 'codigo2026', label: 'Código 2026' },
  { key: null, label: 'Descripción' },
  { key: 'supHa', label: 'Sup. (ha)', className: 'table__cell--num' },
  { key: null, label: 'Evidencia' },
]

export function FeatureTable({
  features,
  selectedOrdinal,
  onSelectFeature,
  snapshotId,
}: FeatureTableProps) {
  const [sort, setSort] = useState<SortState>({ key: 'ordinal', ascending: true })
  const [page, setPage] = useState(0)
  const [prevFeatures, setPrevFeatures] = useState(features)
  const [prevSelected, setPrevSelected] = useState(selectedOrdinal)

  const sorted = useMemo(() => sortFeatures(features, sort), [features, sort])

  // Render-time state adjustments (no effect round-trips): a new filter
  // result returns to the first page; a new selection jumps to its page so
  // map/table stay synchronized.
  if (features !== prevFeatures) {
    setPrevFeatures(features)
    setPage(0)
  }

  if (selectedOrdinal !== prevSelected) {
    setPrevSelected(selectedOrdinal)
    if (selectedOrdinal !== null) {
      const index = sorted.findIndex(
        (feature) => feature.properties.feature_ordinal === selectedOrdinal,
      )
      if (index >= 0) {
        setPage(Math.floor(index / PAGE_SIZE))
      }
    }
  }

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount - 1)
  const pageRows = sorted.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE)

  // Keep the selected row visible inside the table's own scroll area.
  const selectedRowRef = useRef<HTMLTableRowElement | null>(null)
  useEffect(() => {
    // scrollIntoView is absent in some environments (jsdom).
    selectedRowRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [selectedOrdinal, safePage])

  const toggleSort = (key: SortKey) => {
    setSort((current) =>
      current.key === key ? { key, ascending: !current.ascending } : { key, ascending: true },
    )
    setPage(0)
  }

  if (features.length === 0) {
    return (
      <div className="table__empty" role="status">
        <p>Sin resultados para los filtros actuales.</p>
      </div>
    )
  }

  return (
    <div className="table">
      <div className="table__toolbar">
        <p className="table__summary">
          {formatInt(features.length)} {features.length === 1 ? 'polígono' : 'polígonos'} ·
          página {safePage + 1} de {pageCount}
        </p>
        <div className="table__toolbar-actions">
          <button
            type="button"
            className="button button--ghost"
            onClick={() => downloadCsv(sorted, snapshotId)}
          >
            Exportar CSV ({formatInt(features.length)})
          </button>
          <div className="table__pager">
            <button
              type="button"
              className="button button--ghost"
              disabled={safePage === 0}
              onClick={() => setPage(safePage - 1)}
            >
              Anterior
            </button>
            <button
              type="button"
              className="button button--ghost"
              disabled={safePage >= pageCount - 1}
              onClick={() => setPage(safePage + 1)}
            >
              Siguiente
            </button>
          </div>
        </div>
      </div>

      <div className="table__scroll">
        <table className="table__grid">
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column.label} className={column.className}>
                  {column.key !== null ? (
                    <button
                      type="button"
                      className="table__sort"
                      onClick={() => toggleSort(column.key as SortKey)}
                      aria-label={`Ordenar por ${column.label}`}
                    >
                      {column.label}
                      {sort.key === column.key ? (
                        <span aria-hidden="true">{sort.ascending ? ' ↑' : ' ↓'}</span>
                      ) : null}
                    </button>
                  ) : (
                    column.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((feature) => {
              const p = feature.properties
              const isSelected = p.feature_ordinal === selectedOrdinal

              return (
                <tr
                  key={p.feature_ordinal}
                  ref={isSelected ? selectedRowRef : undefined}
                  className={isSelected ? 'table__row--selected' : undefined}
                  onClick={() => onSelectFeature(p.feature_ordinal)}
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      onSelectFeature(p.feature_ordinal)
                    }
                  }}
                >
                  <td>
                    {p.nom_predio ?? '·'}
                    {p.cod_predial !== null ? (
                      <span className="table__muted"> {p.cod_predial}</span>
                    ) : null}
                  </td>
                  <td className="table__cell--num">{p.n_rodal === '' || p.n_rodal === null ? '·' : p.n_rodal}</td>
                  <td>{p.uso_2026 ?? '·'}</td>
                  <td>{p.cod_uso_2026 ?? '·'}</td>
                  <td className="table__cell--desc">{p.desc_uso ?? '·'}</td>
                  <td className="table__cell--num">
                    {p.sup_ha !== null ? formatHa(p.sup_ha) : '·'}
                  </td>
                  <td>
                    {p.quality_flags.length > 0 ? (
                      <span
                        className="table__flags"
                        title={p.quality_flags.map(qualityFlagLabel).join(', ')}
                      >
                        {p.quality_flags.length}
                      </span>
                    ) : null}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
