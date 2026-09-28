/**
 * The conflicting-status evidence, as Calidad presents it.
 *
 * The point of this panel is that the conflict stays visible. A dashboard
 * that silently picked one value and showed nothing else would be reporting
 * a cleaner number than the source supports.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EMPTY_FILTERS, type EstadoResumidoConflict } from '../api'
import { ROUTES, RouterProvider } from '../router'
import { ConflictPanel } from './ConflictPanel'

const MP015: EstadoResumidoConflict = {
  pmf: 'MP015',
  valores: ['En tramite', 'Aprobado'],
  canonico: 'En tramite',
  estado_detalle: 'Rechazado',
  source_row_number: 259,
}

function renderPanel(conflicts: EstadoResumidoConflict[]) {
  return render(
    <RouterProvider initialPath={ROUTES.calidad}>
      <ConflictPanel
        conflicts={conflicts}
        basis="estado_resumido_first_row"
        filters={EMPTY_FILTERS}
      />
    </RouterProvider>,
  )
}

describe('ConflictPanel', () => {
  it('lists every summarized value the source carried for the PMF', () => {
    renderPanel([MP015])

    expect(screen.getByText('En tramite · Aprobado')).toBeInTheDocument()
    expect(screen.getByTestId('conflict-canonical-MP015')).toHaveTextContent('En tramite')
  })

  it('names the detailed state and the source row the canonical value came from', () => {
    renderPanel([MP015])

    expect(screen.getByText('Rechazado')).toBeInTheDocument()
    expect(screen.getByText('259')).toBeInTheDocument()
  })

  it('explains the arithmetic it refuses to reproduce', () => {
    renderPanel([MP015])

    expect(screen.getByText(/160 y 159/)).toBeInTheDocument()
    expect(screen.getAllByText(/una sola vez/).length).toBeGreaterThan(0)
    expect(screen.getByText('estado_resumido_first_row')).toBeInTheDocument()
  })

  it('links the PMF to the Explorer so the rows can be inspected', () => {
    renderPanel([MP015])

    expect(screen.getByRole('link', { name: 'MP015' }).getAttribute('href')).toBe(
      `${ROUTES.explorador}?q=MP015`,
    )
  })

  it('says so plainly when the published version has no conflict', () => {
    renderPanel([])

    expect(screen.getByTestId('conflicts-empty')).toHaveTextContent(
      /Ningún PMF .* más de un «Estado resumido»/,
    )
  })
})
