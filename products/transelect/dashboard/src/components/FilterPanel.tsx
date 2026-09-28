/**
 * TR-FUNC-017-022 — the filter controls.
 *
 * The semantics are unchanged: free-text search (017) is OR'd across all 30
 * contract fields server-side; the five multi-selects (018-022) are AND'd
 * with each other and OR'd within themselves; every read endpoint takes the
 * same filter contract.
 *
 * What changed is where they live. The shipped panel was a permanently
 * expanded left rail on the dashboard, about 640 px tall against a 4 210 px
 * page, so five multiselects were always on screen whether or not anyone was
 * filtering, and 85 % of that column was empty grey. Here the five fields sit
 * behind a disclosure on the Explorador, and whatever is actually active is
 * always visible as removable chips — so the panel can be closed without the
 * reader losing track of what is narrowing the view.
 *
 * `Limpiar` is still one code path with several entry points: the toolbar
 * button, each chip's remove control, and the Pendientes section's own reset
 * all write the same empty filter state to the URL.
 */
import type { RefObject } from 'react'
import type { MultiselectField, TranselecFilterState } from '../api'
import { MultiSelectField } from './MultiSelectField'

export type FilterOptions = Record<MultiselectField, string[]>

export const EMPTY_FILTER_OPTIONS: FilterOptions = {
  estado_resumido: [],
  empresa: [],
  pas: [],
  sector: [],
  tipo_propietario: [],
  aef: [],
  quien_solicita: [],
}

export function FilterPanel({
  filters,
  options,
  optionsLoading,
  empresaRef,
  empresaOpenSignal,
  onChange,
}: {
  filters: TranselecFilterState
  options: FilterOptions
  optionsLoading: boolean
  empresaRef?: RefObject<HTMLButtonElement | null>
  empresaOpenSignal?: number
  onChange: (field: keyof TranselecFilterState, value: string[]) => void
}) {
  return (
    <>
      <div className="filters no-print" aria-label="Filtros">
        <MultiSelectField
          label="Estado resumido"
          options={options.estado_resumido}
          selected={filters.estado_resumido}
          onChange={(next) => onChange('estado_resumido', next)}
        />
        <MultiSelectField
          label="Empresa"
          options={options.empresa}
          selected={filters.empresa}
          onChange={(next) => onChange('empresa', next)}
          triggerRef={empresaRef}
          openSignal={empresaOpenSignal}
        />
        <MultiSelectField
          label="PAS"
          options={options.pas}
          selected={filters.pas}
          onChange={(next) => onChange('pas', next)}
        />
        <MultiSelectField
          label="Sector"
          options={options.sector}
          selected={filters.sector}
          onChange={(next) => onChange('sector', next)}
        />
        <MultiSelectField
          label="Tipo de propietario"
          options={options.tipo_propietario}
          selected={filters.tipo_propietario}
          onChange={(next) => onChange('tipo_propietario', next)}
        />
        {/*
          The AEF tracking fields are row-level: only the rows that carry a
          value match. A PMF whose other rows are blank is not included by
          association.
        */}
        <MultiSelectField
          label="AEF"
          options={options.aef}
          selected={filters.aef}
          onChange={(next) => onChange('aef', next)}
        />
        <MultiSelectField
          label="Quién solicita"
          options={options.quien_solicita}
          selected={filters.quien_solicita}
          onChange={(next) => onChange('quien_solicita', next)}
        />
      </div>
      {optionsLoading && (
        <p className="hint no-print" role="status">
          Cargando las opciones de filtro de la versión activa…
        </p>
      )}
    </>
  )
}
