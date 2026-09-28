import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { VersionesPage } from './VersionesPage'
import { ROUTES, RouterProvider } from '../router'
import type { TranselecActiveImport } from '../api'
import { makeActiveImport, makeHistoryRow } from '../test/factories'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, listImportHistory: vi.fn(), restoreImport: vi.fn() }
})

const { listImportHistory, restoreImport } = await import('../api')

function renderPage(
  onChanged = vi.fn(),
  activeImport: TranselecActiveImport | null = makeActiveImport(),
) {
  render(
    <RouterProvider initialPath={ROUTES.versiones}>
      <VersionesPage activeImport={activeImport} onActiveVersionChanged={onChanged} />
    </RouterProvider>,
  )
  return onChanged
}

const history = [
  makeHistoryRow({ publish_event_id: 7, import_id: 14, is_active: true }),
  makeHistoryRow({
    publish_event_id: 5,
    import_id: 12,
    is_active: false,
    occurred_at: '2026-08-20T10:00:00+00:00',
    business_rows: 5,
    distinct_pmf: 4,
  }),
  makeHistoryRow({
    publish_event_id: 3,
    import_id: 12,
    event_type: 'restore',
    is_active: false,
    occurred_at: '2026-08-10T09:00:00+00:00',
  }),
]

describe('VersionesPage', () => {
  beforeEach(() => {
    vi.mocked(listImportHistory).mockReset()
    vi.mocked(restoreImport).mockReset()
  })

  it('lists one row per activation event, marking publishes and restores apart', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({ ok: true, data: history })
    renderPage()

    await waitFor(() => expect(screen.getByTestId('version-7')).toBeInTheDocument())
    expect(screen.getAllByText('Publicación')).toHaveLength(2)
    expect(screen.getByText('Restauración')).toBeInTheDocument()
  })

  it('marks the active version and refuses to restore it', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({ ok: true, data: history })
    renderPage()

    await waitFor(() => expect(screen.getByTestId('version-7')).toBeInTheDocument())
    expect(screen.getByTestId('version-7')).toHaveClass('active')
    expect(screen.getByTestId('restore-14')).toBeDisabled()
    expect(screen.getAllByTestId('restore-12')[0]).toBeEnabled()
  })

  it('asks for an explicit confirmation naming the import before restoring', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({ ok: true, data: history })
    renderPage()

    await waitFor(() => expect(screen.getByTestId('version-5')).toBeInTheDocument())
    await userEvent.click(screen.getAllByTestId('restore-12')[0])

    expect(screen.getByTestId('restore-confirm-message')).toHaveTextContent(
      'Está a punto de volver a activar la importación #12',
    )
    expect(restoreImport).not.toHaveBeenCalled()
  })

  it('does not fire the mutation when the confirmation is cancelled', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({ ok: true, data: history })
    renderPage()

    await waitFor(() => expect(screen.getByTestId('version-5')).toBeInTheDocument())
    await userEvent.click(screen.getAllByTestId('restore-12')[0])
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(restoreImport).not.toHaveBeenCalled()
  })

  it('restores after confirmation and reloads the history', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({ ok: true, data: history })
    vi.mocked(restoreImport).mockResolvedValue({
      ok: true,
      data: {
        status: 'restored',
        event_type: 'restore',
        import_id: 12,
        previous_import_id: 14,
        publish_event_id: 30,
        occurred_at: '2026-09-02T22:00:00+00:00',
        active_import_id: 12,
      },
    })

    const onChanged = renderPage()
    await waitFor(() => expect(screen.getByTestId('version-5')).toBeInTheDocument())
    await userEvent.click(screen.getAllByTestId('restore-12')[0])
    await userEvent.click(screen.getByTestId('confirm-accept'))

    await waitFor(() => expect(screen.getByText('Versión restaurada')).toBeInTheDocument())
    expect(restoreImport).toHaveBeenCalledWith(12)
    expect(onChanged).toHaveBeenCalledTimes(1)
    expect(listImportHistory).toHaveBeenCalledTimes(2)
  })

  it('reports a failed restore without claiming the version changed', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({ ok: true, data: history })
    vi.mocked(restoreImport).mockResolvedValue({
      ok: false,
      status: 500,
      error: 'No se pudo publicar la versión. La versión activa no cambió.',
    })

    const onChanged = renderPage()
    await waitFor(() => expect(screen.getByTestId('version-5')).toBeInTheDocument())
    await userEvent.click(screen.getAllByTestId('restore-12')[0])
    await userEvent.click(screen.getByTestId('confirm-accept'))

    await waitFor(() =>
      expect(screen.getByText('La importación no se completó')).toBeInTheDocument(),
    )
    expect(screen.queryByText('Versión restaurada')).not.toBeInTheDocument()
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('shows an empty state, pointing at the import page, when nothing was ever published', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({ ok: true, data: [] })
    renderPage(vi.fn(), null)

    await waitFor(() => expect(screen.getByTestId('versions-empty')).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'Importe una planilla' })).toBeInTheDocument()
  })

  it('shows the unauthorized state when the session lacks the grant', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({
      ok: false,
      status: 403,
      error: 'Not permitted for this product.',
    })
    renderPage()

    await waitFor(() => expect(screen.getByText('Sin autorización')).toBeInTheDocument())
  })

  /**
   * TR-FUNC-043/046. The provenance block moved here from the dashboard
   * footer in the UX rearchitecture: it belongs beside the history that
   * produced it. The content it must carry is unchanged, and is still the
   * active version's real provenance rather than a static filename string.
   */
  it('summarises the active version’s own provenance', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({ ok: true, data: history })
    renderPage(vi.fn(), makeActiveImport({ import_id: 14, business_rows: 9 }))

    const summary = await screen.findByTestId('provenance-footer')
    expect(summary).toHaveTextContent('#14')
    expect(summary).toHaveTextContent('9')
    expect(summary).toHaveTextContent('transelec-resumen-v1')
    expect(summary).toHaveTextContent('82ba5eaed0b1')
    expect(summary).toHaveTextContent('Dev Admin')
    expect(summary).toHaveTextContent('nunca modifica la planilla de origen')
  })

  it('marks a restore explicitly in the provenance line', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({ ok: true, data: history })
    renderPage(vi.fn(), makeActiveImport({ published_event_type: 'restore' }))

    expect(await screen.findByTestId('provenance-footer')).toHaveTextContent(
      'restauración de una versión anterior',
    )
  })

  it('says there is no provenance to cite when nothing is published', async () => {
    vi.mocked(listImportHistory).mockResolvedValue({ ok: true, data: history })
    renderPage(vi.fn(), null)

    const summary = await screen.findByTestId('provenance-footer')
    expect(summary).toHaveTextContent('todavía no hay procedencia que citar')
    // TR-OPEN-06 stays disclosed even with nothing published.
    expect(summary).toHaveTextContent('los logotipos originales no se reutilizan')
  })
})
