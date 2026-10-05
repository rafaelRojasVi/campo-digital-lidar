/**
 * The Resumen's first analytical section, as a reader meets it.
 *
 * "¿Cuál es el estado de los planes de manejo?" has to be answered by the
 * page itself — a total, three or four counts, each stating its population
 * and each a route into the filtered Explorador — not reconstructed by the
 * reader from a percentage and a denominator.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EMPTY_FILTERS, type TranselecEditHistory } from '../api'
import { WebEditsContext } from '../lib/webEditsState'
import { ROUTES, RouterProvider } from '../router'
import { makeHistory, makeSummary } from '../test/factories'
import { StatusHeadline } from './StatusHeadline'

function renderHeadline(summary = makeSummary(), filters = EMPTY_FILTERS) {
  return render(
    <RouterProvider initialPath={ROUTES.resumen}>
      <StatusHeadline summary={summary} filters={filters} />
    </RouterProvider>,
  )
}

describe('StatusHeadline', () => {
  it('leads with the plan total and names the question it answers', () => {
    renderHeadline(makeSummary({ pmf_count: 159 }))

    expect(screen.getByTestId('kpi-pmf-total')).toHaveTextContent('159')
    expect(
      screen.getByRole('heading', { name: 'Estado de los planes de manejo' }),
    ).toBeInTheDocument()
  })

  it('shows the three Estado resumido buckets at PMF grain', () => {
    renderHeadline()

    expect(screen.getByTestId('status-aprobado')).toHaveTextContent('3')
    expect(screen.getByTestId('status-en_tramite')).toHaveTextContent('1')
    expect(screen.getByTestId('status-tachado')).toHaveTextContent('1')
  })

  it('states each count against the population it is a part of', () => {
    renderHeadline(
      makeSummary({
        pmf_count: 10,
        estado_resumido_pmf: {
          aprobado: 5,
          en_tramite: 3,
          pendiente: 1,
          tachado: 1,
          sin_estado: 0,
        },
      }),
    )

    const card = screen.getByTestId('status-cards').querySelector('[data-status="aprobado"]')!
    expect(within(card as HTMLElement).getByText(/de 10 PMF/)).toBeInTheDocument()
  })

  it('links each status to the Explorer filtered to that exact status', () => {
    renderHeadline(
      makeSummary({ estado_resumido_valores: { aprobado: ['Aprobado'], tachado: ['Tachado'] } }),
    )

    const card = screen.getByTestId('status-cards').querySelector('[data-status="aprobado"]')!
    expect(card.getAttribute('href')).toBe(`${ROUTES.explorador}?estado_resumido=Aprobado`)
  })

  it('carries the reader existing filters through the click-through', () => {
    renderHeadline(makeSummary({ estado_resumido_valores: { aprobado: ['Aprobado'] } }), {
      ...EMPTY_FILTERS,
      empresa: ['Ecores'],
    })

    const card = screen.getByTestId('status-cards').querySelector('[data-status="aprobado"]')!
    expect(card.getAttribute('href')).toContain('empresa=Ecores')
    expect(card.getAttribute('href')).toContain('estado_resumido=Aprobado')
  })

  it('renders a bucket with no reproducible filter as text, not a dead link', () => {
    renderHeadline(
      makeSummary({
        pmf_count: 7,
        estado_resumido_pmf: {
          aprobado: 3,
          en_tramite: 1,
          pendiente: 1,
          tachado: 1,
          sin_estado: 1,
        },
        estado_resumido_valores: { aprobado: ['Aprobado'] },
      }),
    )

    const card = screen.getByTestId('status-cards').querySelector('[data-status="sin_estado"]')!
    expect(card.tagName).toBe('DIV')
    expect(card.getAttribute('href')).toBeNull()
  })

  it('reports a PMF with conflicting evidence without counting it twice', () => {
    renderHeadline(
      makeSummary({
        pmf_count: 6,
        calidad_pmf_estado_resumido_conflictivo: [
          {
            pmf: 'MP015',
            valores: ['En tramite', 'Aprobado'],
            canonico: 'En tramite',
            estado_detalle: 'Rechazado',
            source_row_number: 259,
          },
        ],
      }),
    )

    const note = screen.getByTestId('status-conflict-note')
    expect(note).toHaveTextContent('MP015')
    expect(note).toHaveTextContent(/una sola vez/)
    expect(screen.queryByTestId('status-reconciliation-warning')).not.toBeInTheDocument()
  })

  it('warns rather than showing buckets that do not account for every plan', () => {
    renderHeadline(makeSummary({ pmf_count: 99 }))
    expect(screen.getByTestId('status-reconciliation-warning')).toBeInTheDocument()
  })

  it('names the rule behind the figures instead of hiding it', () => {
    renderHeadline()
    expect(screen.getByText('estado_resumido_first_row')).toBeInTheDocument()
  })
})

describe('StatusHeadline — totals that include web edits (indicator spec §8)', () => {
  function renderWithEdits(
    webEdited: number,
    history: TranselecEditHistory | null = makeHistory(),
    openLog = vi.fn(),
  ) {
    return render(
      <RouterProvider initialPath={ROUTES.resumen}>
        <WebEditsContext.Provider
          value={{ history, status: history ? 'ready' : 'error', refresh: vi.fn(), openLog }}
        >
          <StatusHeadline
            summary={makeSummary({ web_edited_pmf_count: webEdited })}
            filters={EMPTY_FILTERS}
          />
        </WebEditsContext.Provider>
      </RouterProvider>,
    )
  }

  it('says how many PMF are counted under an edited state, and opens the log', async () => {
    const openLog = vi.fn()
    renderWithEdits(2, makeHistory(), openLog)
    expect(screen.getByTestId('status-web-note')).toHaveTextContent(
      'Incluye 2 PMF con estado editado en la web.',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Ver ediciones' }))
    expect(openLog).toHaveBeenCalledTimes(1)
  })

  it('reads the same for one PMF', () => {
    renderWithEdits(1)
    expect(screen.getByTestId('status-web-note')).toHaveTextContent(
      'Incluye 1 PMF con estado editado en la web.',
    )
  })

  it('offers no «Ver ediciones» when the log is not on the page', () => {
    renderWithEdits(1, null)
    expect(screen.getByTestId('status-web-note')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ver ediciones' })).not.toBeInTheDocument()
  })

  it('says nothing when no counted state was edited', () => {
    renderWithEdits(0)
    expect(screen.queryByTestId('status-web-note')).not.toBeInTheDocument()
  })
})
