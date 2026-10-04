import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EstadoTable } from './EstadoTable'
import type { EstadoColumn } from '../lib/estadoColumns'
import { plazoColumn } from '../lib/plazoColumn'
import { indexPlazos } from '../lib/plazo'
import { makeLifecycle, makePlazos } from '../test/factories'

const rows = makeLifecycle().rows

describe('EstadoTable', () => {
  it('shows each PMF with its group, step, rejection type, ingresos and raw reingreso flags', () => {
    render(<EstadoTable rows={rows} selectedRow={null} onOpen={() => {}} />)
    const row = screen.getByTestId('estado-row-3')
    expect(row).toHaveTextContent('MP002')
    expect(row).toHaveTextContent('En trámite')
    expect(row).toHaveTextContent('Rechazado, esperando recurso')
    expect(row).toHaveTextContent('Legal')
    expect(row).toHaveTextContent('ING-900 / —')
    expect(row).toHaveTextContent('— / 1 / —')
  })

  it('marks only the rejected-awaiting-recurso step as the one needing action', () => {
    render(<EstadoTable rows={rows} selectedRow={null} onOpen={() => {}} />)
    const marked = within(screen.getByTestId('estado-row-3')).getByText(
      'Rechazado, esperando recurso',
    )
    expect(marked).toHaveClass('estado-attention')
    expect(screen.getByTestId('estado-row-2').querySelector('.estado-attention')).toBeNull()
  })

  it('places an extra column after a named base column, or last without one', () => {
    const plazo: EstadoColumn = {
      key: 'plazo',
      header: 'Plazo CONAF',
      render: (row) => `plazo de ${row.pmf}`,
      after: 'pmf',
    }
    const last: EstadoColumn = {
      key: 'ultimo',
      header: 'Ultima',
      render: () => 'x',
    }
    render(
      <EstadoTable rows={rows} selectedRow={null} onOpen={() => {}} extraColumns={[plazo, last]} />,
    )
    const headers = screen.getAllByRole('columnheader').map((header) => header.textContent)
    expect(headers.slice(0, 3)).toEqual(['PMF', 'Plazo CONAF', 'Grupo'])
    expect(headers[headers.length - 1]).toBe('Ultima')
    expect(screen.getByTestId('estado-row-2')).toHaveTextContent('plazo de MP001')
  })

  it('opens a PMF by click and by Enter', async () => {
    const onOpen = vi.fn()
    render(<EstadoTable rows={rows} selectedRow={null} onOpen={onOpen} />)
    await userEvent.click(screen.getByTestId('estado-row-2'))
    expect(onOpen).toHaveBeenLastCalledWith(rows[0])
    fireEvent.keyDown(screen.getByTestId('estado-row-5'), { key: 'Enter' })
    expect(onOpen).toHaveBeenLastCalledWith(rows[2])
  })

  it('leaves a click or Enter on the Oficina Virtual controls to them, not to the row', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    const onOpen = vi.fn()
    try {
      render(<EstadoTable rows={rows} selectedRow={null} onOpen={onOpen} />)
      const row = screen.getByTestId('estado-row-3')
      await userEvent.click(within(row).getByRole('button', { name: 'Copiar N.º ING-900' }))
      fireEvent.keyDown(within(row).getByRole('link', { name: /^Abrir Oficina Virtual CONAF/ }), {
        key: 'Enter',
      })
      expect(writeText).toHaveBeenCalledWith('ING-900')
      expect(onOpen).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('shows the «Plazo CONAF» column joined by PMF, and a dash where there is none', () => {
    const byPmf = indexPlazos(makePlazos())
    byPmf.delete('MP003')
    render(
      <EstadoTable
        rows={rows}
        selectedRow={null}
        onOpen={() => {}}
        extraColumns={[plazoColumn(byPmf, false)]}
      />,
    )
    expect(screen.getByRole('columnheader', { name: 'Plazo CONAF' })).toBeInTheDocument()
    expect(screen.getByTestId('plazo-3')).toHaveTextContent('Vencido')
    expect(screen.getByTestId('plazo-3')).toHaveTextContent(
      'venció el 14-07-2026 · hace 35 días hábiles',
    )
    // MP003 (row 5) has no entry: its plazo cell holds only a dash.
    expect(screen.queryByTestId('plazo-5')).toBeNull()
    const cell = screen.getByTestId('estado-row-5').querySelector('td[data-col="plazo"]')
    expect(cell).toHaveTextContent(/^—$/)
  })

  it('words the plazo with its status text, and wraps the long ones in the cell', () => {
    render(
      <EstadoTable
        rows={rows}
        selectedRow={null}
        onOpen={() => {}}
        extraColumns={[plazoColumn(indexPlazos(makePlazos()), false)]}
      />,
    )
    expect(screen.getByTestId('plazo-7')).toHaveTextContent('Fechas distintas')
    expect(screen.getByTestId('plazo-7')).toHaveTextContent(
      'Las filas del PMF tienen fechas de ingreso distintas',
    )
    expect(screen.getByTestId('plazo-2')).toHaveTextContent('No aplica')
    expect(screen.getByTestId('estado-row-7').querySelector('td[data-col="plazo"]')).not.toBeNull()
  })

  it('says it is still calculating while the plazo read is on its way', () => {
    render(
      <EstadoTable
        rows={rows}
        selectedRow={null}
        onOpen={() => {}}
        extraColumns={[plazoColumn(new Map(), true)]}
      />,
    )
    const cell = screen.getByTestId('estado-row-2').querySelector('td[data-col="plazo"]')
    expect(cell).toHaveTextContent('Calculando…')
    expect(screen.queryByTestId('plazo-2')).toBeNull()
  })

  it('says so when the scope has no PMF', () => {
    render(<EstadoTable rows={[]} selectedRow={null} onOpen={() => {}} />)
    expect(screen.getByText('No hay PMF en el alcance seleccionado.')).toBeInTheDocument()
  })
})
