import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { OwnerStatusTable } from './OwnerStatusTable'
import { makeOwnerStatus } from '../test/factories'

describe('OwnerStatusTable (TR-FUNC-013)', () => {
  it('renders the source table’s seven columns', () => {
    render(<OwnerStatusTable ownerStatus={makeOwnerStatus()} />)
    const headers = screen.getAllByRole('columnheader').map((node) => node.textContent)
    expect(headers).toEqual([
      'Tipo de propietario',
      'Aprobados',
      'En trámite',
      'Rechazados',
      'Pend./tach.',
      'Total',
      '% aprobado',
    ])
  })

  it('shows the status-rule basis identifier rather than hiding it', () => {
    render(<OwnerStatusTable ownerStatus={makeOwnerStatus()} />)
    expect(screen.getAllByText('owner_stage_legacy').length).toBeGreaterThan(0)
  })

  it('explains, in the section copy, that this rule can disagree with the rest of the page', () => {
    render(<OwnerStatusTable ownerStatus={makeOwnerStatus()} />)
    expect(
      screen.getByText(/puede clasificar un predio de forma distinta al resto del panel/),
    ).toBeInTheDocument()
  })

  it('pivots the API rows and totals them', () => {
    render(<OwnerStatusTable ownerStatus={makeOwnerStatus()} />)
    const rows = screen.getAllByRole('row')
    const particular = rows.find((row) => row.textContent?.startsWith('Particular'))
    expect(within(particular as HTMLElement).getAllByRole('cell').map((c) => c.textContent)).toEqual(
      ['Particular', '0', '1', '2', '0', '3', '0%'],
    )
    expect(screen.getByTestId('owner-status-total')).toHaveTextContent('6')
  })

  it('renders an empty-state row when the filtered scope has no predios', () => {
    render(<OwnerStatusTable ownerStatus={makeOwnerStatus({ rows: [], total_predio_count: 0 })} />)
    expect(screen.getByText('No hay predios para los filtros aplicados.')).toBeInTheDocument()
    expect(screen.queryByTestId('owner-status-total')).not.toBeInTheDocument()
  })
})
