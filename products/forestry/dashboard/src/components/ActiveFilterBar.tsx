import type { FilterState, QualityFilter } from '../lib/filters.ts'

interface ActiveFilterBarProps {
  filters: FilterState
  onFiltersChange: (filters: FilterState) => void
}

const QUALITY_LABELS: Record<QualityFilter, string> = {
  any: 'Con evidencia de calidad',
  invalid_geometry: 'Geometría no válida',
  duplicate_geometry: 'Geometría duplicada',
  blank_rodal: 'Rodal vacío',
  duplicate_predio_rodal_key: 'Predio/rodal repetido',
  predio_code_name_anomaly: 'Anomalía código/nombre predio',
  truncated_use_code_2026: 'Código 2026 truncado',
}

interface Chip {
  key: string
  label: string
  clear: () => void
}

export function ActiveFilterBar({ filters, onFiltersChange }: ActiveFilterBarProps) {
  const chips: Chip[] = []
  const update = (patch: Partial<FilterState>) => onFiltersChange({ ...filters, ...patch })

  if (filters.searchText.trim() !== '') {
    chips.push({
      key: 'search',
      label: `Buscar: ${filters.searchText}`,
      clear: () => update({ searchText: '' }),
    })
  }
  if (filters.codPredial !== null) {
    chips.push({
      key: 'codPredial',
      label: `Predio código: ${filters.codPredial}`,
      clear: () => update({ codPredial: null }),
    })
  }
  if (filters.nomPredio !== null) {
    chips.push({
      key: 'nomPredio',
      label: `Predio: ${filters.nomPredio}`,
      clear: () => update({ nomPredio: null }),
    })
  }
  if (filters.uso2026 !== null) {
    chips.push({
      key: 'uso2026',
      label: `Uso 2026: ${filters.uso2026}`,
      clear: () => update({ uso2026: null }),
    })
  }
  if (filters.uso2024 !== null) {
    chips.push({
      key: 'uso2024',
      label: `Uso 2024: ${filters.uso2024}`,
      clear: () => update({ uso2024: null }),
    })
  }
  if (filters.descUso !== null) {
    chips.push({
      key: 'descUso',
      label: `Descripción: ${filters.descUso}`,
      clear: () => update({ descUso: null }),
    })
  }
  if (filters.codUso2026 !== null) {
    chips.push({
      key: 'codUso2026',
      label: `Código 2026: ${filters.codUso2026}`,
      clear: () => update({ codUso2026: null }),
    })
  }
  if (filters.codUso !== null) {
    chips.push({
      key: 'codUso',
      label: `Código 2024: ${filters.codUso}`,
      clear: () => update({ codUso: null }),
    })
  }
  if (filters.nRodal !== null) {
    chips.push({
      key: 'nRodal',
      label: `Rodal: ${filters.nRodal}`,
      clear: () => update({ nRodal: null }),
    })
  }
  if (filters.quality !== null) {
    chips.push({
      key: 'quality',
      label: QUALITY_LABELS[filters.quality],
      clear: () => update({ quality: null }),
    })
  }
  if (filters.geometryValid !== null) {
    chips.push({
      key: 'geometryValid',
      label: filters.geometryValid ? 'Geometría válida' : 'Geometría no válida',
      clear: () => update({ geometryValid: null }),
    })
  }
  if (filters.usoChange !== null) {
    chips.push({
      key: 'usoChange',
      label: filters.usoChange === 'changed' ? 'Uso 2024→2026: difiere' : 'Uso 2024→2026: igual',
      clear: () => update({ usoChange: null }),
    })
  }
  if (filters.codeChange !== null) {
    chips.push({
      key: 'codeChange',
      label:
        filters.codeChange === 'changed'
          ? 'Código 2024→2026: difiere'
          : 'Código 2024→2026: igual',
      clear: () => update({ codeChange: null }),
    })
  }

  if (chips.length === 0) return null

  return (
    <div className="active-filters" aria-label="Filtros activos">
      <span className="active-filters__label">Filtros activos</span>
      <div className="active-filters__chips">
        {chips.map((chip) => (
          <button
            key={chip.key}
            type="button"
            className="active-filters__chip"
            onClick={chip.clear}
            title={`Quitar ${chip.label}`}
          >
            <span>{chip.label}</span>
            <span aria-hidden="true">×</span>
          </button>
        ))}
      </div>
      <button
        type="button"
        className="active-filters__clear"
        onClick={() =>
          onFiltersChange({
            codPredial: null,
            nomPredio: null,
            uso2026: null,
            uso2024: null,
            descUso: null,
            codUso2026: null,
            codUso: null,
            nRodal: null,
            quality: null,
            geometryValid: null,
            usoChange: null,
            codeChange: null,
            searchText: '',
          })
        }
      >
        Limpiar todos
      </button>
    </div>
  )
}
