import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EstadoPage } from './EstadoPage'
import { EMPTY_FILTERS, type TranselecAef } from '../api'
import type { FilterController } from '../lib/useFilters'
import { RouterProvider } from '../router'
import { makeLifecycle, makePending, makePlazos } from '../test/factories'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getLifecycle: vi.fn(),
    getPending: vi.fn(),
    getPlazos: vi.fn(),
    getPmfDetail: vi.fn(),
    getAef: vi.fn(),
  }
})

const { getLifecycle, getPending, getPlazos, getPmfDetail, getAef } = await import('../api')

const controller: FilterController = {
  filters: EMPTY_FILTERS,
  draftQuery: '',
  setQuery: () => {},
  setField: () => {},
  replaceFilters: () => {},
  reset: () => {},
}

function renderPage(path = '/transelec/estado') {
  render(
    <RouterProvider initialPath={path}>
      <EstadoPage filterController={controller} sourceFields={null} />
    </RouterProvider>,
  )
}

describe('EstadoPage', () => {
  beforeEach(() => {
    vi.mocked(getLifecycle).mockReset()
    vi.mocked(getLifecycle).mockResolvedValue({ ok: true, data: makeLifecycle() })
    vi.mocked(getPending).mockReset()
    vi.mocked(getPending).mockResolvedValue({ ok: true, data: makePending() })
    vi.mocked(getPlazos).mockReset()
    vi.mocked(getPlazos).mockResolvedValue({ ok: true, data: makePlazos() })
    vi.mocked(getPmfDetail).mockReset()
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: false,
      status: 404,
      error: 'No se encontró el PMF solicitado en la versión activa.',
    })
    vi.mocked(getAef).mockReset()
    vi.mocked(getAef).mockResolvedValue({ ok: true, data: { pmfs: [] } as unknown as TranselecAef })
  })

  it('leads with the groups and the steps inside «En trámite»', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('estado-zone')).toBeInTheDocument())
    expect(screen.getByTestId('estado-group-aprobado')).toHaveTextContent('1')
    expect(screen.getByTestId('estado-group-en_tramite')).toHaveTextContent('2')
    expect(screen.getByTestId('estado-group-sin_clasificar')).toHaveTextContent('1')
    expect(screen.getByTestId('estado-step-rechazado_esperando_recurso')).toHaveTextContent('1')
    expect(screen.getByTestId('estado-how')).toHaveTextContent('lifecycle_pmf_v1')
  })

  it('opens the PMF drawer with its «Proceso CONAF» block', async () => {
    renderPage()
    await userEvent.click(await screen.findByTestId('estado-row-3'))
    const block = await screen.findByTestId('drawer-lifecycle')
    expect(block).toHaveTextContent('En trámite')
    expect(block).toHaveTextContent('Rechazado, esperando recurso')
  })

  it('keeps the old pending rule, closed, below the table', async () => {
    renderPage()
    const legacy = await screen.findByTestId('legacy-pending')
    expect(legacy.tagName).toBe('DETAILS')
    expect(legacy).not.toHaveAttribute('open')
    await waitFor(() =>
      expect(within(legacy).getByTestId('pending-count')).toHaveTextContent('2 de 6'),
    )
  })

  it('opens the old pending rule and focuses it when the page is reached with the marker', async () => {
    renderPage('/transelec/estado#pendientes-prioritarios')
    const legacy = await screen.findByTestId('legacy-pending')
    expect(legacy).toHaveAttribute('open')
    expect(within(legacy).getByText('Pendientes prioritarios (regla anterior)')).toHaveFocus()
  })

  it('offers no clear button when nothing is filtered', async () => {
    renderPage()
    await screen.findByTestId('estado-zone')
    expect(screen.queryByTestId('clear-estado-filters')).toBeNull()
  })

  it('adds the «Plazo CONAF» column, joined by PMF', async () => {
    renderPage()
    const cell = await screen.findByTestId('plazo-3')
    expect(cell).toHaveTextContent('Vencido')
    expect(cell).toHaveTextContent('venció el 14-07-2026')
    expect(screen.getByTestId('plazo-5')).toHaveTextContent('En plazo')
  })

  it('shows only the vencidos when asked, with the server date and the former rule beside it', async () => {
    renderPage()
    const toggle = await screen.findByRole('button', {
      name: '¿Qué PMF superaron los 90 días hábiles?',
    })
    await waitFor(() => expect(toggle).toBeEnabled())
    await userEvent.click(toggle)

    expect(screen.getByTestId('plazo-vencidos-count')).toHaveTextContent('1')
    expect(screen.getByTestId('plazo-vencidos-note')).toHaveTextContent('02-09-2026')
    expect(screen.getByTestId('plazo-legacy-count')).toHaveTextContent('2')
    expect(screen.getByTestId('estado-row-3')).toBeInTheDocument()
    expect(screen.queryByTestId('estado-row-5')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Ver todos los PMF' }))
    expect(screen.getByTestId('estado-row-5')).toBeInTheDocument()
    expect(screen.queryByTestId('plazo-vencidos-note')).toBeNull()
  })

  it('opens the drawer with the PMF plazo block', async () => {
    renderPage()
    await screen.findByTestId('plazo-3')
    await userEvent.click(screen.getByTestId('estado-row-3'))
    expect(await screen.findByTestId('drawer-plazo')).toHaveTextContent('Vencido')
  })

  it('keeps the Estado table when the plazo read fails', async () => {
    vi.mocked(getPlazos).mockResolvedValue({ ok: false, status: 500, error: 'boom' })
    renderPage()
    await screen.findByTestId('estado-zone')
    await waitFor(() =>
      expect(screen.getByText('No se pudo calcular el plazo CONAF')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('estado-row-3')).toBeInTheDocument()
    expect(screen.queryByTestId('plazo-3')).toBeNull()
    expect(
      screen.getByRole('button', { name: '¿Qué PMF superaron los 90 días hábiles?' }),
    ).toBeDisabled()
  })

  it('says so in the drawer when the plazo read failed', async () => {
    vi.mocked(getPlazos).mockResolvedValue({ ok: false, status: 500, error: 'boom' })
    renderPage()
    await screen.findByText('No se pudo calcular el plazo CONAF')
    await userEvent.click(screen.getByTestId('estado-row-3'))
    expect(await screen.findByTestId('drawer-plazo')).toHaveTextContent('No se pudo cargar el plazo')
  })

  it('never leaves «Ver todos los PMF» stuck over an unfiltered table when a refetch fails', async () => {
    const view = { filters: { ...EMPTY_FILTERS, q: 'x' } }
    let current: FilterController = controller
    const { rerender } = render(
      <RouterProvider initialPath="/transelec/estado">
        <EstadoPage filterController={current} sourceFields={null} />
      </RouterProvider>,
    )
    const toggle = await screen.findByRole('button', {
      name: '¿Qué PMF superaron los 90 días hábiles?',
    })
    await waitFor(() => expect(toggle).toBeEnabled())
    await userEvent.click(toggle)
    expect(screen.queryByTestId('estado-row-5')).toBeNull()

    vi.mocked(getPlazos).mockResolvedValue({ ok: false, status: 500, error: 'boom' })
    current = { ...controller, filters: view.filters }
    rerender(
      <RouterProvider initialPath="/transelec/estado">
        <EstadoPage filterController={current} sourceFields={null} />
      </RouterProvider>,
    )
    await screen.findByText('No se pudo calcular el plazo CONAF')
    expect(screen.queryByRole('button', { name: 'Ver todos los PMF' })).toBeNull()
    expect(
      screen.getByRole('button', { name: '¿Qué PMF superaron los 90 días hábiles?' }),
    ).toBeDisabled()
  })
})
