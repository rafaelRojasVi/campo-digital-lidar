/**
 * The five multi-select filter fields (TR-FUNC-018-022).
 *
 * Free-text search (017), Limpiar (023), CSV export (037) and print (038)
 * moved out of this component in the UX rearchitecture: search is now the
 * Explorador's primary control and the three actions live in that page's
 * toolbar, beside the dataset they act on. Their behaviour is covered in
 * `src/pages/ExploradorPage.test.tsx`, which exercises them where they now
 * are; the filter semantics asserted below are unchanged.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EMPTY_FILTERS } from '../api'
import { FilterPanel } from './FilterPanel'

const options = {
  estado_resumido: ['Aprobado', 'En tramite', 'Pendiente', 'Tachado'],
  empresa: ['Austral', 'Ñuble Forestal'],
  pas: ['PAS 148'],
  sector: ['Norte', 'Sur'],
  tipo_propietario: ['Particular', 'Servidumbre firmada'],
  aef: ['Presentado'],
  quien_solicita: ['Persona A'],
}

const base = {
  filters: EMPTY_FILTERS,
  options,
  optionsLoading: false,
  onChange: () => {},
}

describe('FilterPanel (TR-FUNC-018-022)', () => {
  it('renders the five multi-select controls', () => {
    render(<FilterPanel {...base} />)
    for (const label of ['Estado resumido', 'Empresa', 'PAS', 'Sector', 'Tipo de propietario']) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument()
    }
  })

  it('ORs selections within one multi-select (TR-FUNC-018)', async () => {
    const onChange = vi.fn()
    const { rerender } = render(<FilterPanel {...base} onChange={onChange} />)

    await userEvent.click(screen.getByRole('button', { name: /Estado resumido/ }))
    await userEvent.click(screen.getByLabelText('Aprobado'))
    expect(onChange).toHaveBeenLastCalledWith('estado_resumido', ['Aprobado'])

    rerender(
      <FilterPanel
        {...base}
        filters={{ ...EMPTY_FILTERS, estado_resumido: ['Aprobado'] }}
        onChange={onChange}
      />,
    )
    await userEvent.click(screen.getByLabelText('Tachado'))
    expect(onChange).toHaveBeenLastCalledWith('estado_resumido', ['Aprobado', 'Tachado'])
  })

  it('keeps different fields independent so the API can AND them (TR-FUNC-019-022)', async () => {
    const onChange = vi.fn()
    render(
      <FilterPanel
        {...base}
        filters={{ ...EMPTY_FILTERS, estado_resumido: ['Aprobado'] }}
        onChange={onChange}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: /Sector/ }))
    await userEvent.click(screen.getByLabelText('Norte'))

    // Only the field that was touched is reported; the caller merges it into
    // the shared filter state, so one field can never clear another.
    expect(onChange).toHaveBeenLastCalledWith('sector', ['Norte'])
  })

  it('disables a field with no options and says while the lists are still loading', () => {
    render(<FilterPanel {...base} options={{ ...options, pas: [] }} optionsLoading />)
    expect(screen.getByRole('button', { name: /PAS/ })).toBeDisabled()
    expect(screen.getByText(/Cargando las opciones de filtro/)).toBeInTheDocument()
  })
})
