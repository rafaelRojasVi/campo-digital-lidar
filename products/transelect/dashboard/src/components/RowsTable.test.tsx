import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { RowsTable } from './RowsTable'
import { makeRow } from '../test/factories'

const base = { loading: false, onOpenRow: () => {}, selectedRow: null }

describe('RowsTable (TR-FUNC-039)', () => {
  it('renders Actualizable’s column set with the two Carpeta columns kept apart', () => {
    render(<RowsTable {...base} rows={[makeRow()]} />)
    const headers = screen.getAllByRole('columnheader').map((node) => node.textContent)
    expect(headers).toEqual([
      'PMF',
      'Predio de reforestación',
      'Carpeta PMF',
      'Carpeta normalizada',
      'Rol',
      'Predio',
      'Área corta',
      'Sup. ha',
      'Estado resumido',
      'AEF',
      'N.º ingreso',
      'Empresa',
      'Propietario',
      'Sector',
    ])
  })

  it('shows both source Carpeta values instead of collapsing them to one', () => {
    render(<RowsTable {...base} rows={[makeRow()]} />)
    const row = within(screen.getByTestId('rows-body')).getAllByRole('row')[0]
    const cells = within(row).getAllByRole('cell').map((cell) => cell.textContent)
    expect(cells[2]).toBe('CARP-E-01')
    expect(cells[3]).toBe('CARP-AC-01')
  })

  it('shows AEF per row, blank stays blank, and flags inverted dates', () => {
    render(
      <RowsTable
        {...base}
        rows={[
          makeRow({
            source_row_number: 2,
            aef: 'Presentado',
            chronology_flags: ['cronologia_termino_antes_de_corta'],
          }),
          makeRow({ source_row_number: 3, aef: null }),
        ]}
      />,
    )
    const [first, second] = within(screen.getByTestId('rows-body')).getAllByRole('row')
    const aefCell = within(first).getAllByRole('cell')[9]
    expect(aefCell).toHaveTextContent('Presentado')
    expect(within(aefCell).getByText('Revisar fechas')).toHaveAttribute(
      'title',
      'Fecha término anterior a la corta',
    )
    expect(within(second).getAllByRole('cell')[9]).toHaveTextContent('—')
  })

  it('renders a blank workbook value as an empty cell, never as "null"', () => {
    render(
      <RowsTable
        {...base}
        rows={[makeRow({ predio_ref: null, rol: null, superficie_corta: null })]}
      />,
    )
    const row = within(screen.getByTestId('rows-body')).getAllByRole('row')[0]
    const cells = within(row).getAllByRole('cell').map((cell) => cell.textContent)
    expect(cells[1]).toBe('Sin información')
    expect(cells[4]).toBe('')
    expect(cells[7]).toBe('0')
    expect(row.textContent).not.toContain('null')
  })

  it('escapes workbook-derived text rather than interpreting it as markup', () => {
    render(<RowsTable {...base} rows={[makeRow({ empresa: '<img src=x onerror="alert(1)">' })]} />)
    const body = screen.getByTestId('rows-body')
    expect(body.querySelector('img')).toBeNull()
    expect(body.textContent).toContain('<img src=x onerror="alert(1)">')
  })

  it('shows an empty state only when it is not still loading', () => {
    const { rerender } = render(<RowsTable {...base} rows={[]} loading />)
    expect(
      screen.queryByText(/No hay registros para los filtros aplicados/),
    ).not.toBeInTheDocument()

    rerender(<RowsTable {...base} rows={[]} />)
    expect(screen.getByText(/No hay registros para los filtros aplicados/)).toBeInTheDocument()
  })

  it('opens a row’s detail by click and by keyboard, so the drawer is not mouse-only', async () => {
    const onOpenRow = vi.fn()
    const row = makeRow()
    render(<RowsTable {...base} rows={[row]} onOpenRow={onOpenRow} />)

    await userEvent.click(screen.getByTestId(`row-${row.source_row_number}`))
    expect(onOpenRow).toHaveBeenCalledWith(row)

    screen.getByTestId(`row-${row.source_row_number}`).focus()
    await userEvent.keyboard('{Enter}')
    expect(onOpenRow).toHaveBeenCalledTimes(2)
  })

  it('marks the row whose detail is open', () => {
    const row = makeRow()
    render(<RowsTable {...base} rows={[row]} selectedRow={row.source_row_number} />)
    expect(screen.getByTestId(`row-${row.source_row_number}`)).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })
})
