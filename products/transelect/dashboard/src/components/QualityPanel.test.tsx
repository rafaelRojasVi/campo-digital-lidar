import { render as renderInDom, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ReactNode } from 'react'
import { ROUTES, RouterProvider } from '../router'
import { QualityPanel } from './QualityPanel'
import { makeSummary } from '../test/factories'

function render(node: ReactNode) {
  return renderInDom(<RouterProvider initialPath={ROUTES.calidad}>{node}</RouterProvider>)
}

describe('QualityPanel (TR-FUNC-014/015/016)', () => {
  it('shows the blank-ID row count from the API', () => {
    render(<QualityPanel summary={makeSummary({ calidad_filas_sin_id_predial_unico: 4 })} />)
    expect(screen.getByTestId('quality-sin-id')).toHaveTextContent('4')
    expect(screen.getByText(/filas sin ID predial único/)).toBeInTheDocument()
  })

  it('renders a genuine zero rather than hiding the indicator', () => {
    render(<QualityPanel summary={makeSummary({ calidad_filas_sin_id_predial_unico: 0 })} />)
    expect(screen.getByTestId('quality-sin-id')).toHaveTextContent('0')
  })

  it('shows the PMF-deduped count of PMFs with no N.º de ingreso', () => {
    render(<QualityPanel summary={makeSummary({ calidad_pmf_sin_numero_ingreso: 11 })} />)
    expect(screen.getByTestId('quality-sin-ingreso')).toHaveTextContent('11')
  })

  it('renders the permanent "No disponible" literal for the resolution field', () => {
    render(<QualityPanel summary={makeSummary()} />)
    expect(screen.getByTestId('quality-resolucion')).toHaveTextContent('No disponible')
    expect(screen.getByText(/campo N.º de resolución/)).toBeInTheDocument()
  })

  it('keeps the dedup rule the PMF-level indicator inherits in its «Cómo se calcula»', () => {
    render(<QualityPanel summary={makeSummary()} />)
    const how = screen.getByTestId('how-sin-ingreso')
    expect(how.tagName).toBe('DETAILS')
    expect(how).not.toHaveAttribute('open')
    expect(how).toHaveTextContent('estado_resumido_first_row')
    expect(how).toHaveTextContent('N Ingreso')
  })

  it('leads with plain language: what was found and what to review', () => {
    render(
      <QualityPanel
        summary={makeSummary({ calidad_pmf_sin_numero_ingreso: 3, calidad_filas_sin_id_predial_unico: 0 })}
      />,
    )
    const item = screen.getByTestId('quality-sin-ingreso').closest('li') as HTMLElement
    expect(item).toHaveTextContent('Esos planes no se pueden vincular a un expediente CONAF.')
    expect(item).toHaveTextContent('Qué revisar:')
    // Outside the closed detail, no rule identifier is part of the reading line.
    const visible = [...item.children].filter((node) => node.tagName !== 'DETAILS')
    for (const node of visible) expect(node.textContent).not.toMatch(/_legacy|first_row/)
  })

  it('counts the PMF with conflicting statuses from the API list', () => {
    render(<QualityPanel summary={makeSummary()} />)
    expect(screen.getByTestId('quality-conflictos')).toHaveTextContent(
      String(makeSummary().calidad_pmf_estado_resumido_conflictivo.length),
    )
  })
})
