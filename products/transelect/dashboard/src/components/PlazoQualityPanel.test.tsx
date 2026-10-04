import { render as renderInDom, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { PlazoQualityPanel } from './PlazoQualityPanel'
import { ROUTES, RouterProvider } from '../router'
import { makePlazos } from '../test/factories'

function render(node: ReactNode) {
  return renderInDom(<RouterProvider initialPath={ROUTES.calidad}>{node}</RouterProvider>)
}

describe('PlazoQualityPanel', () => {
  it('lists each PMF whose «90 dias» differs from the calculation, with its row', () => {
    render(<PlazoQualityPanel plazos={makePlazos()} />)

    expect(screen.getByTestId('plazo-difiere-count')).toHaveTextContent('1')
    const item = screen.getByTestId('plazo-difiere-3')
    expect(item).toHaveTextContent('MP002')
    expect(item).toHaveTextContent('fila 3')
    expect(item).toHaveTextContent('Difiere: la planilla dice 02-06-2026, 42 días antes del cálculo')
    expect(screen.getByRole('link', { name: 'Ver en Estado →' })).toHaveAttribute(
      'href',
      '/transelec/estado',
    )
  })

  it('takes the count from the server, not from the legacy row count', () => {
    render(
      <PlazoQualityPanel
        plazos={makePlazos({ cruce_difiere_count: 1, legacy_vencido_row_count: 60 })}
      />,
    )

    expect(screen.getByTestId('plazo-difiere-count')).toHaveTextContent(/^1$/)
  })

  it('reads calm when every «90 dias» matches', () => {
    const plazos = makePlazos()
    render(
      <PlazoQualityPanel
        plazos={{
          ...plazos,
          cruce_difiere_count: 0,
          pmfs: plazos.pmfs.filter((entry) => entry.cruce !== 'difiere'),
        }}
      />,
    )

    expect(screen.getByTestId('plazo-difiere-count')).toHaveTextContent('0')
    expect(screen.queryByTestId('plazo-difiere-list')).toBeNull()
  })

  it('keeps the rule one «Cómo se calcula» away', () => {
    render(<PlazoQualityPanel plazos={makePlazos()} />)

    const how = screen.getByTestId('how-plazo-difiere')
    expect(how.tagName).toBe('DETAILS')
    expect(how).toHaveTextContent('plazo_conaf_90_habiles_v1')
  })
})
