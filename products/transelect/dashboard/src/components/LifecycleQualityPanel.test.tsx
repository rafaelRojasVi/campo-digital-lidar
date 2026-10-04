import { render as renderInDom, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { LifecycleQualityPanel } from './LifecycleQualityPanel'
import { ROUTES, RouterProvider } from '../router'
import { makeLifecycle } from '../test/factories'

function render(node: ReactNode) {
  return renderInDom(<RouterProvider initialPath={ROUTES.calidad}>{node}</RouterProvider>)
}

describe('LifecycleQualityPanel', () => {
  it('lists each PMF to review with its row and its reason', () => {
    render(<LifecycleQualityPanel lifecycle={makeLifecycle()} />)

    expect(screen.getByTestId('lifecycle-review-count')).toHaveTextContent('1')
    const item = screen.getByTestId('lifecycle-review-7')
    expect(item).toHaveTextContent('MP004')
    expect(item).toHaveTextContent('fila 7')
    expect(item).toHaveTextContent('«Estado» y «Estado resumido» no coinciden')
    expect(item).toHaveTextContent('Sus filas no tienen el mismo')
    expect(screen.getByRole('link', { name: 'Ver en Estado →' })).toHaveAttribute(
      'href',
      '/transelec/estado',
    )
  })

  it('lets each listed PMF be reached through a link to Estado filtered to it', () => {
    render(<LifecycleQualityPanel lifecycle={makeLifecycle()} />)

    expect(screen.getByRole('link', { name: 'Buscar MP004 en Estado' })).toHaveAttribute(
      'href',
      '/transelec/estado?q=MP004',
    )
  })

  it('reads calm when every PMF is placed', () => {
    render(<LifecycleQualityPanel lifecycle={makeLifecycle({ rows: [] })} />)

    expect(screen.getByTestId('lifecycle-review-count')).toHaveTextContent('0')
    expect(screen.queryByTestId('lifecycle-review-list')).toBeNull()
  })

  it('keeps the rule one «Cómo se calcula» away', () => {
    render(<LifecycleQualityPanel lifecycle={makeLifecycle()} />)

    const how = screen.getByTestId('how-lifecycle-review')
    expect(how.tagName).toBe('DETAILS')
    expect(how).toHaveTextContent('lifecycle_pmf_v1')
  })
})
