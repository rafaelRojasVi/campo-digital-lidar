import { useMemo } from 'react'
import { groupChangePairs } from '../lib/comparison.ts'
import type { FilterState } from '../lib/filters.ts'
import { formatInt } from '../lib/format.ts'
import type {
  FeatureCollection,
  SourceFieldChange,
  SourceFieldComparison,
} from '../types.ts'

interface ComparisonPanelProps {
  comparison: SourceFieldComparison
  collection: FeatureCollection
  filters: FilterState
  onFiltersChange: (filters: FilterState) => void
  onSelectFeature: (featureOrdinal: number) => void
}

function ChangeTable({
  changes,
  collection,
  onSelectFeature,
}: {
  changes: SourceFieldChange[]
  collection: FeatureCollection
  onSelectFeature: (featureOrdinal: number) => void
}) {
  const byOrdinal = useMemo(() => {
    const map = new Map<number, { predio: string; rodal: string }>()
    for (const feature of collection.features) {
      map.set(feature.properties.feature_ordinal, {
        predio: feature.properties.nom_predio ?? '·',
        rodal:
          feature.properties.n_rodal === null || feature.properties.n_rodal === ''
            ? '·'
            : feature.properties.n_rodal,
      })
    }
    return map
  }, [collection])

  if (changes.length === 0) {
    return <p className="comparison__none">Sin diferencias en este par de campos.</p>
  }

  return (
    <div className="table__scroll comparison__scroll">
      <table className="table__grid">
        <thead>
          <tr>
            <th>Predio</th>
            <th className="table__cell--num">Rodal</th>
            <th>Antes</th>
            <th>Después</th>
            <th className="table__cell--num">OBJECTID</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((change) => {
            const context = byOrdinal.get(change.feature_ordinal)

            return (
              <tr
                key={change.feature_ordinal}
                onClick={() => onSelectFeature(change.feature_ordinal)}
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onSelectFeature(change.feature_ordinal)
                  }
                }}
              >
                <td>{context?.predio ?? '·'}</td>
                <td className="table__cell--num">{context?.rodal ?? '·'}</td>
                <td>
                  <code>{change.before ?? '(vacío)'}</code>
                </td>
                <td>
                  <code>{change.after ?? '(vacío)'}</code>
                </td>
                <td className="table__cell--num">{change.source_objectid ?? '·'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// Literal source-field differences within one snapshot. This panel never
// labels a difference as progress, completed management, or approval; the
// vocabulary of the detailed codes is still unconfirmed by the stakeholder.
export function ComparisonPanel({
  comparison,
  collection,
  filters,
  onFiltersChange,
  onSelectFeature,
}: ComparisonPanelProps) {
  const codePairs = useMemo(
    () => groupChangePairs(comparison.cod_uso_vs_cod_uso_2026.changes),
    [comparison],
  )

  const filterActive = filters.codeChange === 'changed'

  return (
    <div className="comparison">
      <div className="comparison__header">
        <p className="comparison__semantics">
          Diferencias literales entre los campos 2024 y 2026 de la misma instantánea. No
          representan transiciones de flujo de trabajo ni gestión realizada.
        </p>
        <button
          type="button"
          className={`button${filterActive ? '' : ' button--ghost'}`}
          aria-pressed={filterActive}
          onClick={() =>
            onFiltersChange({ ...filters, codeChange: filterActive ? null : 'changed' })
          }
        >
          {filterActive ? 'Quitar filtro del mapa' : 'Filtrar mapa: solo con diferencia'}
        </button>
      </div>

      <div className="comparison__columns">
        <section className="comparison__section" aria-label="Clase de uso 2024 frente a 2026">
          <h3 className="comparison__title">
            Clase de uso · <code>Uso2024</code> → <code>Uso2026</code>
            <span className="comparison__count">
              {formatInt(comparison.uso_2024_vs_uso_2026.changed_feature_count)} con diferencia
            </span>
          </h3>
          <ChangeTable
            changes={comparison.uso_2024_vs_uso_2026.changes}
            collection={collection}
            onSelectFeature={onSelectFeature}
          />
        </section>

        <section
          className="comparison__section"
          aria-label="Código detallado 2024 frente a 2026"
        >
          <h3 className="comparison__title">
            Código detallado · <code>Cod_Uso</code> → <code>CodUso_2026</code>
            <span className="comparison__count">
              {formatInt(comparison.cod_uso_vs_cod_uso_2026.changed_feature_count)} con
              diferencia
            </span>
          </h3>

          {codePairs.length > 0 ? (
            <ul className="comparison__pairs" aria-label="Pares de valores más frecuentes">
              {codePairs.slice(0, 6).map((pair) => (
                <li key={`${pair.before}-${pair.after}`}>
                  <code>{pair.before}</code> → <code>{pair.after}</code>
                  <span className="comparison__pair-count">×{formatInt(pair.count)}</span>
                </li>
              ))}
            </ul>
          ) : null}

          <ChangeTable
            changes={comparison.cod_uso_vs_cod_uso_2026.changes}
            collection={collection}
            onSelectFeature={onSelectFeature}
          />
        </section>
      </div>
    </div>
  )
}
