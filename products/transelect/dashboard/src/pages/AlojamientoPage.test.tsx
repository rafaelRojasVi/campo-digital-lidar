/**
 * The hosting page is stakeholder-facing and carries money figures, so the
 * three properties worth defending in a test are not layout: every
 * alternative is present, no figure is ever shown as if it were a quote, and
 * every tool the reader is invited to check is a real, safely-opened link.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AlojamientoPage } from './AlojamientoPage'
import { ROUTES, RouterProvider } from '../router'

function renderPage() {
  render(
    <RouterProvider initialPath={ROUTES.alojamiento}>
      <AlojamientoPage />
    </RouterProvider>,
  )
}

describe('AlojamientoPage', () => {
  it('presents the four alternatives, each with its own cost figure', () => {
    renderPage()

    for (const [id, name] of [
      ['fly', 'Fly.io'],
      ['render', 'Render'],
      ['supabase', 'Supabase'],
      ['azure', 'Azure'],
    ]) {
      const card = screen.getByTestId(`host-${id}`)
      expect(within(card).getByRole('heading', { name: new RegExp(name) })).toBeInTheDocument()
      expect(within(card).getByTestId(`host-${id}-estimate`)).not.toBeEmptyDOMElement()
    }

    expect(screen.getByTestId('host-render-estimate')).toHaveTextContent('US$20–40')
    expect(screen.getByTestId('host-azure-estimate')).toHaveTextContent('US$45–55')

    // No alternative is left as an open "por confirmar": every card shows a
    // figure, and every figure shows what it is made of.
    for (const id of ['fly', 'render', 'supabase', 'azure']) {
      expect(screen.getByTestId(`host-${id}-estimate`)).toHaveTextContent(/US\$/)
      expect(screen.getByTestId(`host-${id}-basis`)).not.toBeEmptyDOMElement()
    }
  })

  it('lists the alternatives from cheapest to most expensive', () => {
    renderPage()

    const order = screen.getAllByTestId(/^host-(fly|render|supabase|azure)$/).map((card) =>
      card.getAttribute('data-testid'),
    )
    expect(order).toEqual(['host-render', 'host-supabase', 'host-fly', 'host-azure'])
  })

  it('never presents a figure as a quote', () => {
    renderPage()

    // The page-level disclaimer, and a per-alternative qualifier on every
    // card: a reader who only looks at one card still sees the caveat.
    expect(screen.getByTestId('cost-disclaimer')).toHaveTextContent(/estimaciones preliminares/i)
    expect(screen.getByTestId('cost-disclaimer')).toHaveTextContent(/no una cotización/i)
    for (const id of ['fly', 'render', 'supabase', 'azure']) {
      expect(screen.getByTestId(`host-${id}-estimate-note`)).not.toBeEmptyDOMElement()
    }
  })

  it('links every tool to its official page, opened safely', () => {
    renderPage()

    const links = screen.getAllByTestId(/^tool-link-/)
    expect(links.length).toBeGreaterThanOrEqual(12)

    for (const link of links) {
      expect(link.getAttribute('href')).toMatch(/^https:\/\//)
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    }
  })

  it('says what the figures exclude and what happens before anything is contracted', () => {
    renderPage()

    expect(screen.getByTestId('cost-exclusions')).toHaveTextContent(/dominio/i)
    expect(screen.getByTestId('next-step')).toHaveTextContent(/antes de contratar/i)
  })
})
