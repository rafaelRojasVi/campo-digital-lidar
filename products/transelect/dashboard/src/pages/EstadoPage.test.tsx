import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EstadoPage } from './EstadoPage'
import { EMPTY_FILTERS, type TranselecAef } from '../api'
import type { FilterController } from '../lib/useFilters'
import { RouterProvider } from '../router'
import { makeLifecycle, makePending } from '../test/factories'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getLifecycle: vi.fn(),
    getPending: vi.fn(),
    getPmfDetail: vi.fn(),
    getAef: vi.fn(),
  }
})

const { getLifecycle, getPending, getPmfDetail, getAef } = await import('../api')

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
})
