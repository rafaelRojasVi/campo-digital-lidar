import { useId, useMemo, useState } from 'react'
import { EMPTY_FILTERS, countActiveFilters, filterOptions } from '../lib/filters.ts'
import type { ChangeFilter, FilterState, QualityFilter } from '../lib/filters.ts'
import type { SelectionStats } from '../lib/aggregate.ts'
import { formatHa, formatInt } from '../lib/format.ts'
import { QUALITY_FLAG_LABELS } from '../lib/qualityLabels.ts'
import type { FeatureCollection, QualityFlag } from '../types.ts'
import { KNOWN_QUALITY_FLAGS } from '../types.ts'

interface FiltersPanelProps {
  collection: FeatureCollection
  filters: FilterState
  onFiltersChange: (filters: FilterState) => void
  filteredStats: SelectionStats
}

interface SelectFilterProps {
  label: string
  value: string | null
  options: { value: string; count: number }[]
  onChange: (value: string | null) => void
  anyLabel?: string
}

function SelectFilter({ label, value, options, onChange, anyLabel }: SelectFilterProps) {
  const id = useId()

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className="field__control"
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value === '' ? null : event.target.value)}
      >
        <option value="">{anyLabel ?? 'Todos'}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.value} ({formatInt(option.count)})
          </option>
        ))}
      </select>
    </div>
  )
}

function ChangeSelect({
  label,
  value,
  onChange,
}: {
  label: string
  value: ChangeFilter | null
  onChange: (value: ChangeFilter | null) => void
}) {
  const id = useId()

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className="field__control"
        value={value ?? ''}
        onChange={(event) =>
          onChange(event.target.value === '' ? null : (event.target.value as ChangeFilter))
        }
      >
        <option value="">Todos</option>
        <option value="changed">Con diferencia</option>
        <option value="unchanged">Sin diferencia</option>
      </select>
    </div>
  )
}

export function FiltersPanel({
  collection,
  filters,
  onFiltersChange,
  filteredStats,
}: FiltersPanelProps) {
  const searchId = useId()
  const rodalId = useId()
  const rodalListId = useId()
  const validityId = useId()
  const qualityId = useId()
  const [moreOpen, setMoreOpen] = useState(false)

  const options = useMemo(
    () => ({
      predio: filterOptions(collection.features, 'nom_predio'),
      uso2026: filterOptions(collection.features, 'uso_2026'),
      uso2024: filterOptions(collection.features, 'uso_2024'),
      descUso: filterOptions(collection.features, 'desc_uso'),
      codUso2026: filterOptions(collection.features, 'cod_uso_2026'),
      codUso: filterOptions(collection.features, 'cod_uso'),
      rodal: filterOptions(collection.features, 'n_rodal'),
    }),
    [collection],
  )

  const activeCount = countActiveFilters(filters)

  const set = (partial: Partial<FilterState>) => onFiltersChange({ ...filters, ...partial })

  return (
    <section className="filters" aria-label="Búsqueda y filtros">
      <div className="field">
        <label className="field__label" htmlFor={searchId}>
          Buscar
        </label>
        <input
          id={searchId}
          className="field__control filters__search"
          type="search"
          placeholder="Predio, rodal, uso, código, OBJECTID…"
          value={filters.searchText}
          onChange={(event) => set({ searchText: event.target.value })}
        />
      </div>

      <p className="filters__result" role="status">
        <strong>{formatInt(filteredStats.featureCount)}</strong>{' '}
        {filteredStats.featureCount === 1 ? 'polígono' : 'polígonos'} ·{' '}
        <strong>{formatHa(filteredStats.supHaTotal)}</strong> ha
      </p>

      <SelectFilter
        label="Predio"
        value={filters.nomPredio}
        options={options.predio}
        onChange={(value) => set({ nomPredio: value })}
      />

      <SelectFilter
        label="Uso 2026"
        value={filters.uso2026}
        options={options.uso2026}
        onChange={(value) => set({ uso2026: value })}
      />

      <div className="field">
        <label className="field__label" htmlFor={rodalId}>
          Rodal
        </label>
        <input
          id={rodalId}
          className="field__control"
          type="text"
          inputMode="numeric"
          list={rodalListId}
          placeholder="N° exacto de rodal"
          value={filters.nRodal ?? ''}
          onChange={(event) =>
            set({ nRodal: event.target.value === '' ? null : event.target.value })
          }
        />
        <datalist id={rodalListId}>
          {options.rodal.map((option) => (
            <option key={option.value} value={option.value} />
          ))}
        </datalist>
      </div>

      <button
        type="button"
        className="filters__more-toggle"
        aria-expanded={moreOpen}
        onClick={() => setMoreOpen((open) => !open)}
      >
        {moreOpen ? 'Menos filtros' : 'Más filtros'}
      </button>

      {moreOpen ? (
        <div className="filters__more">
          <SelectFilter
            label="Uso 2024"
            value={filters.uso2024}
            options={options.uso2024}
            onChange={(value) => set({ uso2024: value })}
          />
          <SelectFilter
            label="Descripción (DescUso)"
            value={filters.descUso}
            options={options.descUso}
            onChange={(value) => set({ descUso: value })}
          />
          <SelectFilter
            label="Código 2026 (CodUso_2026)"
            value={filters.codUso2026}
            options={options.codUso2026}
            onChange={(value) => set({ codUso2026: value })}
          />
          <SelectFilter
            label="Código estado 2024 (Cod_Uso)"
            value={filters.codUso}
            options={options.codUso}
            onChange={(value) => set({ codUso: value })}
          />

          <ChangeSelect
            label="Clase de uso 2024 vs 2026"
            value={filters.usoChange}
            onChange={(value) => set({ usoChange: value })}
          />
          <ChangeSelect
            label="Código detallado 2024 vs 2026"
            value={filters.codeChange}
            onChange={(value) => set({ codeChange: value })}
          />

          <div className="field">
            <label className="field__label" htmlFor={validityId}>
              Validez de geometría
            </label>
            <select
              id={validityId}
              className="field__control"
              value={filters.geometryValid === null ? '' : String(filters.geometryValid)}
              onChange={(event) =>
                set({
                  geometryValid:
                    event.target.value === '' ? null : event.target.value === 'true',
                })
              }
            >
              <option value="">Todas</option>
              <option value="true">Válidas</option>
              <option value="false">Inválidas</option>
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor={qualityId}>
              Evidencia de calidad de datos
            </label>
            <select
              id={qualityId}
              className="field__control"
              value={filters.quality ?? ''}
              onChange={(event) =>
                set({
                  quality:
                    event.target.value === '' ? null : (event.target.value as QualityFilter),
                })
              }
            >
              <option value="">Todas</option>
              <option value="any">Cualquier evidencia</option>
              {KNOWN_QUALITY_FLAGS.map((flag: QualityFlag) => (
                <option key={flag} value={flag}>
                  {QUALITY_FLAG_LABELS[flag]}
                </option>
              ))}
            </select>
          </div>
        </div>
      ) : null}

      {activeCount > 0 ? (
        <button
          type="button"
          className="button button--ghost filters__clear"
          onClick={() => onFiltersChange(EMPTY_FILTERS)}
        >
          Limpiar filtros ({activeCount})
        </button>
      ) : null}
    </section>
  )
}
