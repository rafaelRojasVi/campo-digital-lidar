/**
 * The session lifecycle the demo depends on: signed out -> sign-in screen ->
 * a session that takes effect without a browser reload -> sign out -> a
 * different identity, with the navigation each role is actually entitled to.
 *
 * Role-based hiding here is presentation only. The server is the authority
 * and is covered separately — see
 * apps/api/integration_tests/test_transelec_router.py's
 * `test_viewer_is_forbidden_on_every_mutation_route`.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Me } from './api'
import { ROUTES } from './router'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    getMe: vi.fn(),
    devLogin: vi.fn(),
    logout: vi.fn(),
    getActiveImport: vi.fn(),
    getSummary: vi.fn(),
    getPending: vi.fn(),
    getOwnerStatus: vi.fn(),
    getReport: vi.fn(),
    listRows: vi.fn(),
  }
})

const api = await import('./api')

const ADMIN_LABEL = 'Entrar como administrador de demostración'
const VIEWER_LABEL = 'Ver como Javier — solo lectura'

const ADMIN: Me = {
  identity_key: 'dev-admin',
  display_name: 'Dev Admin',
  product_grants: [{ product_key: 'transelect', role: 'admin' }],
}

const VIEWER: Me = {
  identity_key: 'dev-viewer',
  display_name: 'Dev Viewer',
  product_grants: [{ product_key: 'transelect', role: 'viewer' }],
}

const UNAUTHENTICATED = { ok: false as const, status: 401, error: 'Not authenticated.' }
const NOTHING_PUBLISHED = {
  ok: false as const,
  status: 404,
  error: 'No hay una versión publicada de Transelec.',
}

/**
 * The product navigation only. Scoped deliberately: the "nothing published
 * yet" empty state offers a publisher its own "Importar planilla" call to
 * action, so an unscoped query would pass even if the nav were wrong.
 */
function nav() {
  return within(screen.getByRole('navigation', { name: 'Secciones de Transelec' }))
}

function stubDashboardReads() {
  // The dashboard's own data is not what these tests are about; every read
  // answers "nothing published yet", which is a real, rendered state.
  for (const fn of [api.getSummary, api.getPending, api.getOwnerStatus, api.getReport, api.listRows]) {
    vi.mocked(fn).mockResolvedValue(NOTHING_PUBLISHED as never)
  }
  vi.mocked(api.getActiveImport).mockResolvedValue(NOTHING_PUBLISHED)
}

describe('App session lifecycle', () => {
  beforeEach(() => {
    for (const fn of [
      api.getMe,
      api.devLogin,
      api.logout,
      api.getActiveImport,
      api.getSummary,
      api.getPending,
      api.getOwnerStatus,
      api.getReport,
      api.listRows,
    ]) {
      vi.mocked(fn).mockReset()
    }
    stubDashboardReads()
  })

  it('shows the sign-in card, not a "go elsewhere" message, on a 401', async () => {
    vi.mocked(api.getMe).mockResolvedValue(UNAUTHENTICATED)
    render(<App initialPath={ROUTES.resumen} />)

    expect(await screen.findByTestId('login-card')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: ADMIN_LABEL })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: VIEWER_LABEL })).toBeInTheDocument()
    expect(screen.queryByText('Sesión requerida')).not.toBeInTheDocument()
  })

  it('keeps a real platform outage distinct from being signed out', async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      ok: false,
      status: 0,
      error: 'No se pudo contactar la plataforma.',
    })
    render(<App initialPath={ROUTES.resumen} />)

    expect(await screen.findByText('Plataforma no disponible')).toBeInTheDocument()
    expect(screen.queryByTestId('login-card')).not.toBeInTheDocument()
  })

  it('adopts the administrator session immediately, with no browser reload', async () => {
    vi.mocked(api.getMe).mockResolvedValueOnce(UNAUTHENTICATED).mockResolvedValue({
      ok: true,
      data: ADMIN,
    })
    vi.mocked(api.devLogin).mockResolvedValue({ ok: true, data: ADMIN })
    render(<App initialPath={ROUTES.resumen} />)

    await userEvent.click(await screen.findByRole('button', { name: ADMIN_LABEL }))

    expect(await screen.findByTestId('shell-identity')).toHaveTextContent('Dev AdminAdministrador')
    expect(api.devLogin).toHaveBeenCalledWith('dev-admin')
    // The session is re-read from the API, never inferred from the login body.
    expect(api.getMe).toHaveBeenCalledTimes(2)
    expect(screen.queryByTestId('login-card')).not.toBeInTheDocument()

    expect(nav().getByRole('link', { name: 'Datos' })).toBeInTheDocument()
  })

  it('gives the viewer the panel without any administrative navigation', async () => {
    vi.mocked(api.getMe).mockResolvedValueOnce(UNAUTHENTICATED).mockResolvedValue({
      ok: true,
      data: VIEWER,
    })
    vi.mocked(api.devLogin).mockResolvedValue({ ok: true, data: VIEWER })
    render(<App initialPath={ROUTES.resumen} />)

    await userEvent.click(await screen.findByRole('button', { name: VIEWER_LABEL }))

    expect(await screen.findByTestId('shell-identity')).toHaveTextContent('Dev ViewerLectura')
    expect(api.devLogin).toHaveBeenCalledWith('dev-viewer')
    expect(nav().getByRole('link', { name: 'Resumen' })).toBeInTheDocument()
    expect(nav().getByRole('link', { name: 'Explorador' })).toBeInTheDocument()
    expect(nav().getByRole('link', { name: 'Pendientes' })).toBeInTheDocument()
    expect(nav().getByRole('link', { name: 'Calidad' })).toBeInTheDocument()
    // The whole administration section, not just its two old routes.
    expect(nav().queryByRole('link', { name: 'Datos' })).not.toBeInTheDocument()
  })

  it('still refuses the import route to a viewer who navigates straight to it', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ok: true, data: VIEWER })
    render(<App initialPath={ROUTES.importar} />)

    expect(await screen.findByText('Sin autorización')).toBeInTheDocument()
  })

  it('signs out and returns to the sign-in screen, then signs in as the other role', async () => {
    vi.mocked(api.getMe)
      .mockResolvedValueOnce({ ok: true, data: ADMIN }) // already signed in
      .mockResolvedValueOnce(UNAUTHENTICATED) // after logout
      .mockResolvedValue({ ok: true, data: VIEWER }) // after the viewer login
    vi.mocked(api.logout).mockResolvedValue({ ok: true, data: undefined })
    vi.mocked(api.devLogin).mockResolvedValue({ ok: true, data: VIEWER })
    render(<App initialPath={ROUTES.resumen} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Cambiar usuario' }))

    expect(await screen.findByTestId('login-card')).toBeInTheDocument()
    expect(api.logout).toHaveBeenCalledTimes(1)
    // The shell's identity specifically — the demo option's own note also
    // mentions "Dev Admin", and that one is supposed to be on screen here.
    await waitFor(() => expect(screen.queryByTestId('shell-identity')).not.toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: VIEWER_LABEL }))

    expect(await screen.findByTestId('shell-identity')).toHaveTextContent('Dev ViewerLectura')
    expect(nav().queryByRole('link', { name: 'Datos' })).not.toBeInTheDocument()
  })

  it('keeps the user signed in, and says so, when sign-out fails', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ok: true, data: ADMIN })
    vi.mocked(api.logout).mockResolvedValue({
      ok: false,
      status: 0,
      error: 'No se pudo contactar la plataforma.',
    })
    render(<App initialPath={ROUTES.resumen} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Cambiar usuario' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo cerrar la sesión.')
    expect(screen.getByTestId('shell-identity')).toHaveTextContent('Dev AdminAdministrador')
    expect(screen.queryByTestId('login-card')).not.toBeInTheDocument()
  })

  it('offers no sign-out control when there is no session to end', async () => {
    vi.mocked(api.getMe).mockResolvedValue(UNAUTHENTICATED)
    render(<App initialPath={ROUTES.resumen} />)

    await screen.findByTestId('login-card')
    expect(screen.queryByRole('button', { name: 'Cambiar usuario' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cerrar sesión' })).not.toBeInTheDocument()
  })
})
