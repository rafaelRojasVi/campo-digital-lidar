import { useId } from 'react'
import type { FilterState } from '../lib/filters.ts'
import { formatHa, formatInt } from '../lib/format.ts'
import { COLOR_DIMENSIONS } from '../lib/palette.ts'
import type { ChangeFilter, QualityFilter } from '../lib/filters.ts'
import type { ColorDimension, ColorEncoding, LegendEntry } from '../lib/palette.ts'

interface LegendPanelProps {
  encoding: ColorEncoding
  colorDimension: ColorDimension
  onColorDimensionChange: (dimension: ColorDimension) => void
  filters: FilterState
  onFiltersChange: (filters: FilterState) => void
}

// The legend doubles as the factual distribution of the selected dimension:
// swatch + source value + Sup_ha sum + proportional bar + polygon count.
// Clicking a categorical entry toggles the matching literal filter.
export function LegendPanel({
  encoding,
  colorDimension,
  onColorDimensionChange,
  filters,
  onFiltersChange,
}: LegendPanelProps) {
  const dimensionId = useId()

  const maxSupHa = Math.max(...encoding.legend.map((entry) => entry.supHaTotal), 1)

  const isEntryActive = (entry: LegendEntry): boolean => {
    switch (encoding.dimension) {
      case 'uso2026':
        return filters.uso2026 === entry.filterValue
      case 'uso2024':
        return filters.uso2024 === entry.filterValue
      case 'predio':
        return filters.nomPredio === entry.filterValue
      case 'cambio':
        return filters.codeChange === entry.filterValue || filters.usoChange === entry.filterValue
      case 'calidad':
        return filters.quality === entry.filterValue
    }
  }

  const toggleEntry = (entry: LegendEntry) => {
    if (entry.filterValue === null) {
      return
    }

    const active = isEntryActive(entry)

    switch (encoding.dimension) {
      case 'uso2026':
        onFiltersChange({ ...filters, uso2026: active ? null : entry.filterValue })
        break
      case 'uso2024':
        onFiltersChange({ ...filters, uso2024: active ? null : entry.filterValue })
        break
      case 'predio':
        onFiltersChange({ ...filters, nomPredio: active ? null : entry.filterValue })
        break
      case 'cambio': {
        // The map encoding is the union of both literal comparisons; the
        // click filter applies the detailed-code comparison, which covers
        // the estate's observed differences.
        const value = active ? null : (entry.filterValue as ChangeFilter)
        onFiltersChange({ ...filters, codeChange: value })
        break
      }
      case 'calidad':
        onFiltersChange({
          ...filters,
          quality: active ? null : (entry.filterValue as QualityFilter),
        })
        break
    }
  }

  return (
    <section className="legend" aria-label="Leyenda del mapa">
      <div className="field">
        <label className="field__label" htmlFor={dimensionId}>
          Colorear por
        </label>
        <select
          id={dimensionId}
          className="field__control"
          value={colorDimension}
          onChange={(event) => onColorDimensionChange(event.target.value as ColorDimension)}
        >
          {COLOR_DIMENSIONS.map((dimension) => (
            <option key={dimension.id} value={dimension.id}>
              {dimension.label}
            </option>
          ))}
        </select>
      </div>

      <ul className="legend__list">
        {encoding.legend.map((entry) => {
          const clickable = entry.filterValue !== null
          const active = isEntryActive(entry)
          const barWidth = Math.max(2, Math.round((entry.supHaTotal / maxSupHa) * 100))

          const row = (
            <>
              <span
                className="legend__swatch"
                style={{ backgroundColor: entry.color }}
                aria-hidden="true"
              />
              <span className="legend__label" title={entry.label}>
                {entry.label}
              </span>
              <span className="legend__ha">{formatHa(entry.supHaTotal)} ha</span>
              <span className="legend__bar" aria-hidden="true">
                <span
                  className="legend__bar-fill"
                  style={{ width: `${barWidth}%`, backgroundColor: entry.color }}
                />
              </span>
              <span className="legend__count">{formatInt(entry.featureCount)} pol.</span>
            </>
          )

          return (
            <li key={entry.key}>
              {clickable ? (
                <button
                  type="button"
                  className={`legend__entry legend__entry--button${
                    active ? ' legend__entry--active' : ''
                  }`}
                  onClick={() => toggleEntry(entry)}
                  aria-pressed={active}
                >
                  {row}
                </button>
              ) : (
                <span className="legend__entry">{row}</span>
              )}
            </li>
          )
        })}
      </ul>

      {encoding.dimension === 'cambio' ? (
        <p className="legend__note">
          Diferencias literales de campos dentro de la instantánea; no representan avance ni
          gestión realizada.
        </p>
      ) : null}
      {encoding.dimension === 'calidad' ? (
        <p className="legend__note">
          Evidencia de calidad de datos observada en la fuente; no son errores que requieran
          acción.
        </p>
      ) : null}
    </section>
  )
}
