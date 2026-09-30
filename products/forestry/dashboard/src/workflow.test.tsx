import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiError } from './api.ts'
import { ImportarPage } from './pages/ImportarPage.tsx'
import { RevisionPage } from './pages/RevisionPage.tsx'
import { VersionesPage } from './pages/VersionesPage.tsx'
import Root from './Root.tsx'
import { testReview, testVersions } from './test/workflowFixtures.ts'

vi.mock('./api.ts', async (importOriginal) => {
  const original = await importOriginal<typeof import('./api.ts')>()
  return {
    ...original,
    fetchForestryRole: vi.fn(),
    fetchVersions: vi.fn(),
    fetchReview: vi.fn(),
    uploadShapefileZip: vi.fn(),
    publishSnapshot: vi.fn(),
    restoreSnapshot: vi.fn(),
  }
})

vi.mock('./App.tsx', () => ({ default: () => <p>mapa-stub</p> }))

const api = vi.mocked(await import('./api.ts'))

beforeEach(() => {
  vi.clearAllMocks()
  window.history.replaceState(null, '', '/rodales/')
})

afterEach(() => {
  window.history.replaceState(null, '', '/rodales/')
})

describe('Cargar versión', () => {
  it('refuses a file that is not a .zip before sending anything', async () => {
    const user = userEvent.setup({ applyAccept: false })
    render(<ImportarPage role="operator" />)

    await user.upload(
      screen.getByLabelText('Elegir archivo'),
      new File(['x'], 'capa.shp', { type: 'application/octet-stream' }),
    )

    expect(screen.getByText('Elija un archivo .zip con la capa completa.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cargar para revisión' })).toBeDisabled()
    expect(api.uploadShapefileZip).not.toHaveBeenCalled()
  })

  it('uploads, then opens the review of the new pending version', async () => {
    api.uploadShapefileZip.mockResolvedValue({
      status: 'uploaded',
      shapefile_snapshot_id: 9,
      version_status: 'pending',
      layer_name: 'Capa',
      feature_count: 6,
      content_sha256: 'a'.repeat(64),
      byte_size: 10,
    })
    const user = userEvent.setup()
    render(<ImportarPage role="operator" />)

    await user.upload(screen.getByLabelText('Elegir archivo'), new File(['zip'], 'capa.zip'))
    await user.click(screen.getByRole('button', { name: 'Cargar para revisión' }))

    expect(window.location.pathname).toBe('/rodales/revision')
    expect(window.location.search).toBe('?version=9&cargada=uploaded')
  })

  it("shows the server's reason when the ZIP is refused, and that nothing changed", async () => {
    api.uploadShapefileZip.mockRejectedValue(
      new ApiError(422, 'refused', 'Faltan archivos obligatorios de la capa: .prj.', 'missing_members'),
    )
    const user = userEvent.setup()
    render(<ImportarPage role="admin" />)

    await user.upload(screen.getByLabelText('Elegir archivo'), new File(['zip'], 'capa.zip'))
    await user.click(screen.getByRole('button', { name: 'Cargar para revisión' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Faltan archivos obligatorios de la capa: .prj.')
    expect(alert).toHaveTextContent('La versión publicada no cambió.')
  })
})

describe('Revisión', () => {
  it('shows source, numbers, invalid geometries and grouped changes, never a cut', async () => {
    api.fetchReview.mockResolvedValue(testReview())
    render(<RevisionPage role="admin" versionId={2} uploadStatus="uploaded" />)

    expect(await screen.findByText('Revisión de la versión N.º 2')).toBeInTheDocument()
    expect(screen.getByText('Archivo cargado')).toBeInTheDocument()
    expect(screen.getByText('entrega_octubre.zip')).toBeInTheDocument()
    expect(screen.getByText('Operadora Sintética')).toBeInTheDocument()
    expect(screen.getByText('WGS_1984_UTM_Zone_18S (EPSG:32718)')).toBeInTheDocument()
    expect(screen.getByText('+1 frente a la publicada')).toBeInTheDocument()
    expect(screen.getByText('Self-intersection[45 5]')).toBeInTheDocument()
    expect(screen.getByText('Correspondencia incierta (1)')).toBeInTheDocument()
    expect(screen.getByText('El OBJECTID cambió; no se usa para emparejar.')).toBeInTheDocument()
    expect(document.body.textContent?.toLowerCase()).not.toMatch(/cortad|corta\b|cosecha/)
  })

  it('publishes only after the acknowledgement and a confirmation', async () => {
    api.fetchReview.mockResolvedValue(testReview())
    api.publishSnapshot.mockResolvedValue({
      status: 'published',
      shapefile_snapshot_id: 2,
      previous_snapshot_id: 1,
      publication_event_id: 5,
      occurred_at: '2026-09-30T12:05:00Z',
    })
    const user = userEvent.setup()
    render(<RevisionPage role="operator" versionId={2} uploadStatus={null} />)

    const publish = await screen.findByRole('button', { name: 'Publicar' })
    expect(publish).toBeDisabled()

    await user.click(screen.getByRole('checkbox'))
    await user.click(publish)

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('¿Publicar la versión N.º 2?')
    expect(dialog).toHaveTextContent('La versión N.º 1 dejará de mostrarse y podrá restaurarse')
    expect(api.publishSnapshot).not.toHaveBeenCalled()

    await user.click(within(dialog).getByRole('button', { name: 'Publicar' }))

    expect(api.publishSnapshot).toHaveBeenCalledWith(2, 1, true)
    expect(window.location.pathname).toBe('/rodales/versiones')
    expect(window.location.search).toBe('?publicada=2')
  })

  it('explains a stale review and offers to refresh it', async () => {
    api.fetchReview.mockResolvedValue(testReview({ review_required: false }))
    api.publishSnapshot.mockRejectedValue(
      new ApiError(409, 'stale', 'La versión publicada cambió mientras usted revisaba.'),
    )
    const user = userEvent.setup()
    render(<RevisionPage role="admin" versionId={2} uploadStatus={null} />)

    await user.click(await screen.findByRole('button', { name: 'Publicar' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Publicar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('cambió mientras usted revisaba')
    await user.click(screen.getByRole('button', { name: 'Actualizar la revisión' }))
    expect(api.fetchReview).toHaveBeenCalledTimes(2)
  })

  it('offers «Restaurar» for a previously published version', async () => {
    api.fetchReview.mockResolvedValue(
      testReview({ can_publish: false, can_restore: true, review_required: true }),
    )
    api.restoreSnapshot.mockResolvedValue({
      status: 'restored',
      shapefile_snapshot_id: 2,
      previous_snapshot_id: 1,
      publication_event_id: 6,
      occurred_at: '2026-09-30T12:05:00Z',
    })
    const user = userEvent.setup()
    render(<RevisionPage role="admin" versionId={2} uploadStatus={null} />)

    await user.click(await screen.findByRole('button', { name: 'Restaurar' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Restaurar' }))

    expect(api.restoreSnapshot).toHaveBeenCalledWith(2, 1)
    expect(window.location.search).toBe('?restaurada=2')
  })

  it('offers no action to a viewer', async () => {
    api.fetchReview.mockResolvedValue(testReview())
    render(<RevisionPage role="viewer" versionId={2} uploadStatus={null} />)

    await screen.findByText('Revisión de la versión N.º 2')
    expect(screen.queryByRole('button', { name: 'Publicar' })).not.toBeInTheDocument()
  })

  it('says when the version does not exist', async () => {
    api.fetchReview.mockRejectedValue(new ApiError(404, 'missing'))
    render(<RevisionPage role="admin" versionId={99} uploadStatus={null} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('No se encontró la versión solicitada.')
  })
})

describe('Versiones', () => {
  it('lists versions with source and uploader, and the publication trail', async () => {
    api.fetchVersions.mockResolvedValue(testVersions())
    render(<VersionesPage role="admin" search={new URLSearchParams()} />)

    expect(await screen.findByText('entrega_octubre.zip')).toBeInTheDocument()
    expect(screen.getByText('Importación controlada')).toBeInTheDocument()
    expect(screen.getByText('Pendiente de revisión')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Revisar y publicar' })).toHaveAttribute(
      'href',
      '/rodales/revision?version=2',
    )
    expect(screen.getByText(/sin usuario \(carga inicial\)/)).toBeInTheDocument()
  })

  it('offers a viewer the map, not the review or the upload', async () => {
    api.fetchVersions.mockResolvedValue(testVersions())
    render(<VersionesPage role="viewer" search={new URLSearchParams()} />)

    await screen.findByText('entrega_octubre.zip')
    expect(screen.queryByRole('link', { name: /Revisar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Cargar versión' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Ver en el mapa' })[0]).toHaveAttribute(
      'href',
      '/rodales/?version=2',
    )
  })

  it('confirms a publication it was sent back from', async () => {
    api.fetchVersions.mockResolvedValue(testVersions())
    render(<VersionesPage role="admin" search={new URLSearchParams('publicada=2')} />)

    expect(await screen.findByText('Versión N.º 2 publicada')).toBeInTheDocument()
  })
})

describe('Root', () => {
  it('routes a direct load of /rodales/versiones to the versions page', async () => {
    api.fetchForestryRole.mockResolvedValue('viewer')
    api.fetchVersions.mockResolvedValue(testVersions())
    window.history.replaceState(null, '', '/rodales/versiones')

    render(<Root />)

    expect(await screen.findByText('Versiones de la capa de rodales')).toBeInTheDocument()
    // A viewer gets no upload link in the header.
    expect(screen.queryByRole('link', { name: 'Cargar versión' })).not.toBeInTheDocument()
  })

  it('routes /rodales/ to the map', async () => {
    api.fetchForestryRole.mockResolvedValue('admin')
    render(<Root />)
    expect(await screen.findByText('mapa-stub')).toBeInTheDocument()
  })

  it('shows «Sin acceso» to an account with no Rodales grant', async () => {
    api.fetchForestryRole.mockResolvedValue(null)
    render(<Root />)
    expect(await screen.findByText('Sin acceso a Rodales')).toBeInTheDocument()
  })

  it('navigates in-app between sections from the header', async () => {
    api.fetchForestryRole.mockResolvedValue('operator')
    api.fetchVersions.mockResolvedValue(testVersions())
    window.history.replaceState(null, '', '/rodales/versiones')
    const user = userEvent.setup()
    render(<Root />)

    await screen.findByText('Versiones de la capa de rodales')
    const nav = screen.getByRole('navigation', { name: 'Secciones de Rodales' })
    await user.click(within(nav).getByRole('link', { name: 'Cargar versión' }))

    expect(window.location.pathname).toBe('/rodales/importar')
    expect(await screen.findByText('Cargar una nueva versión')).toBeInTheDocument()
  })
})
