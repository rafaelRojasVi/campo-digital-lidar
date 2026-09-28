/**
 * The sign-in screen, in both of the shapes it can take.
 *
 * `demoAvailable` is the compile-time boundary from
 * `src/runtime/environment.ts`. These tests pin both branches, including the
 * one that matters most: with the boundary closed, no seeded identity —
 * neither its label nor its key — reaches the DOM at all.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginCard } from './LoginCard'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, devLogin: vi.fn(), checkGoogleSignIn: vi.fn() }
})

const api = await import('../api')

const ADMIN_LABEL = 'Entrar como administrador de demostración'
const VIEWER_LABEL = 'Ver como Javier — solo lectura'

function assign(): ReturnType<typeof vi.fn> {
  const spy = vi.fn()
  vi.stubGlobal('location', { ...window.location, assign: spy })
  return spy
}

describe('LoginCard in local development', () => {
  beforeEach(() => {
    vi.mocked(api.devLogin).mockReset()
    vi.mocked(api.checkGoogleSignIn).mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('offers exactly the two demo identities, and no Google action', () => {
    render(<LoginCard demoAvailable onSignedIn={() => {}} />)

    expect(screen.getByRole('button', { name: ADMIN_LABEL })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: VIEWER_LABEL })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Continuar con Google' })).not.toBeInTheDocument()
  })

  it('says plainly that the seeded identities are local-only', () => {
    render(<LoginCard demoAvailable onSignedIn={() => {}} />)
    expect(
      screen.getByText(/no existen en los entornos publicados de Campo Digital/),
    ).toBeInTheDocument()
  })

  it('signs in as the administrator and hands control back to the session refresh', async () => {
    vi.mocked(api.devLogin).mockResolvedValue({
      ok: true,
      data: { identity_key: 'dev-admin', display_name: 'Dev Admin', product_grants: [] },
    })
    const onSignedIn = vi.fn()
    render(<LoginCard demoAvailable onSignedIn={onSignedIn} />)

    await userEvent.click(screen.getByRole('button', { name: ADMIN_LABEL }))

    expect(api.devLogin).toHaveBeenCalledWith('dev-admin')
    expect(onSignedIn).toHaveBeenCalledTimes(1)
  })

  it('signs in as the viewer with the viewer identity key', async () => {
    vi.mocked(api.devLogin).mockResolvedValue({
      ok: true,
      data: { identity_key: 'dev-viewer', display_name: 'Dev Viewer', product_grants: [] },
    })
    const onSignedIn = vi.fn()
    render(<LoginCard demoAvailable onSignedIn={onSignedIn} />)

    await userEvent.click(screen.getByRole('button', { name: VIEWER_LABEL }))

    expect(api.devLogin).toHaveBeenCalledWith('dev-viewer')
    expect(onSignedIn).toHaveBeenCalledTimes(1)
  })

  it('shows a loading label and blocks a second attempt while one is in flight', async () => {
    let release: ((value: { ok: false; status: number; error: string }) => void) | undefined
    vi.mocked(api.devLogin).mockReturnValue(
      new Promise((resolve) => {
        release = resolve
      }) as ReturnType<typeof api.devLogin>,
    )
    render(<LoginCard demoAvailable onSignedIn={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: ADMIN_LABEL }))

    expect(screen.getByRole('button', { name: 'Iniciando sesión…' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: VIEWER_LABEL })).toBeDisabled()
    expect(screen.getByTestId('login-actions')).toHaveAttribute('aria-busy', 'true')

    release?.({ ok: false, status: 500, error: 'x' })
    await screen.findByRole('button', { name: ADMIN_LABEL })
  })

  it('reports a failed sign-in in Spanish and retries the same identity', async () => {
    vi.mocked(api.devLogin)
      .mockResolvedValueOnce({ ok: false, status: 0, error: 'No se pudo contactar la plataforma.' })
      .mockResolvedValueOnce({
        ok: true,
        data: { identity_key: 'dev-admin', display_name: 'Dev Admin', product_grants: [] },
      })
    const onSignedIn = vi.fn()
    render(<LoginCard demoAvailable onSignedIn={onSignedIn} />)

    await userEvent.click(screen.getByRole('button', { name: ADMIN_LABEL }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('No se pudo iniciar la sesión')
    expect(alert).toHaveTextContent('No se pudo contactar la plataforma.')
    expect(onSignedIn).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))

    expect(api.devLogin).toHaveBeenNthCalledWith(2, 'dev-admin')
    expect(onSignedIn).toHaveBeenCalledTimes(1)
  })

  it('explains a 404 as "not available in this environment" rather than showing Not Found', async () => {
    // What a development build pointed at a hosted API actually gets: the
    // dev-login route is not mounted there at all.
    vi.mocked(api.devLogin).mockResolvedValue({ ok: false, status: 404, error: 'Not Found' })
    render(<LoginCard demoAvailable onSignedIn={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: ADMIN_LABEL }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'El acceso de demostración no está disponible en este entorno.',
    )
    expect(screen.queryByText('Not Found')).not.toBeInTheDocument()
  })
})

describe('LoginCard outside local development', () => {
  beforeEach(() => {
    vi.mocked(api.devLogin).mockReset()
    vi.mocked(api.checkGoogleSignIn).mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders no seeded demo identity at all — not a label, not a key', () => {
    const { container } = render(<LoginCard demoAvailable={false} onSignedIn={() => {}} />)

    expect(screen.queryByRole('button', { name: ADMIN_LABEL })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: VIEWER_LABEL })).not.toBeInTheDocument()
    expect(container.textContent).not.toContain('dev-admin')
    expect(container.textContent).not.toContain('dev-viewer')
    expect(container.textContent).not.toContain('demostración')
  })

  it('offers Google Workspace sign-in and never calls dev-login', async () => {
    const navigate = assign()
    vi.mocked(api.checkGoogleSignIn).mockResolvedValue({ ok: true, data: undefined })
    render(<LoginCard demoAvailable={false} onSignedIn={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: 'Continuar con Google' }))

    expect(navigate).toHaveBeenCalledWith('/api/auth/google/login')
    expect(api.devLogin).not.toHaveBeenCalled()
  })

  it('does not fall back to demo sign-in when Google is unconfigured', async () => {
    const navigate = assign()
    vi.mocked(api.checkGoogleSignIn).mockResolvedValue({
      ok: false,
      status: 503,
      error: 'Google sign-in is not configured.',
    })
    render(<LoginCard demoAvailable={false} onSignedIn={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: 'Continuar con Google' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'El inicio de sesión con Google no está configurado en este entorno.',
    )
    expect(navigate).not.toHaveBeenCalled()
    expect(api.devLogin).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: ADMIN_LABEL })).not.toBeInTheDocument()
  })
})
