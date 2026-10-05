/**
 * The Explorador's `?fila=<n>`: a link from the edits log (indicator spec §5)
 * opens that row's drawer once the filtered rows are in.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useFilters } from '../lib/useFilters'
import { RouterProvider } from '../router'
import { makeRow, makeSummary } from '../test/factories'
import { ExploradorPage } from './ExploradorPage'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, getSummary: vi.fn(), listRows: vi.fn(), getPmfDetail: vi.fn() }
})
vi.mock('../components/RowDetailDrawer', () => ({
  RowDetailDrawer: ({
    row,
    onClose,
  }: {
    row: { source_row_number: number }
    onClose: () => void
  }) => (
    <div data-testid="drawer">
      fila {row.source_row_number}
      <button type="button" onClick={onClose}>
        Cerrar
      </button>
    </div>
  ),
}))
const { getSummary, listRows, getPmfDetail } = await import('../api')

function Page() {
  return <ExploradorPage filterController={useFilters()} activeImportId={12} />
}

function renderAt(path: string) {
  window.history.replaceState({}, '', path)
  return render(
    <RouterProvider initialPath={path}>
      <Page />
    </RouterProvider>,
  )
}

const page = (rows: number[]) => ({
  ok: true as const,
  data: {
    items: rows.map((n) => makeRow({ source_row_number: n, pmf: 'MP001' })),
    next_cursor: null,
    has_more: false,
    total_count: rows.length,
  },
})

describe('Explorador ?fila=', () => {
  beforeEach(() => {
    vi.mocked(getSummary).mockResolvedValue({ ok: true, data: makeSummary() })
    vi.mocked(listRows).mockResolvedValue(page([3, 7]))
    vi.mocked(getPmfDetail).mockReset()
  })

  it('opens the row once the rows load, and closing drops fila from the address', async () => {
    renderAt('/transelec/explorador?q=MP001&fila=7')
    expect(await screen.findByTestId('drawer')).toHaveTextContent('fila 7')
    expect(getPmfDetail).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(screen.queryByTestId('drawer')).not.toBeInTheDocument()
    expect(window.location.search).toBe('?q=MP001')
  })

  it('falls back to the PMF detail when the row is not on the first page', async () => {
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: true,
      data: {
        pmf: 'MP001',
        row_count: 1,
        basis_estado_resumido: 'estado_resumido_first_row',
        estado_resumido: null,
        rows: [makeRow({ source_row_number: 90, pmf: 'MP001' })],
      },
    })
    renderAt('/transelec/explorador?q=MP001&fila=90')
    expect(await screen.findByTestId('drawer')).toHaveTextContent('fila 90')
    expect(getPmfDetail).toHaveBeenCalledWith('MP001')
  })

  it('says so when the row is not in the active version, and drops fila', async () => {
    vi.mocked(getPmfDetail).mockResolvedValue({ ok: false, status: 404, error: 'No encontrado' })
    renderAt('/transelec/explorador?q=MP001&fila=999')
    expect(
      await screen.findByText(/No se encontró esta fila en la versión activa\./),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('drawer')).not.toBeInTheDocument()
    expect(window.location.search).toBe('?q=MP001')
  })
})
