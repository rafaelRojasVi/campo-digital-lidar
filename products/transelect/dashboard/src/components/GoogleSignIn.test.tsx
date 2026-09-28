/**
 * The sign-in panel every deployed Transelec build ships.
 *
 * What these tests pin is not the wording but the two rules the panel must
 * never break: it only ever hands control to the platform's own top-level
 * login route, and when Google is not configured it says so and stops —
 * there is no second way in to fall back to.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GoogleSignIn } from './GoogleSignIn'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, checkGoogleSignIn: vi.fn(), devLogin: vi.fn() }
})

const api = await import('../api')

const GOOGLE_LABEL = 'Continuar con Google'

function assign(): ReturnType<typeof vi.fn> {
  const spy = vi.fn()
  vi.stubGlobal('location', { ...window.location, assign: spy })
  return spy
}

describe('GoogleSignIn', () => {
  beforeEach(() => {
    vi.mocked(api.checkGoogleSignIn).mockReset()
    vi.mocked(api.devLogin).mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('offers a single Google action', () => {
    render(<GoogleSignIn />)

    expect(screen.getByRole('button', { name: GOOGLE_LABEL })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Continuar con Microsoft' })).not.toBeInTheDocument()
  })

  it('hands the browser to the platform login route, as a top-level navigation', async () => {
    const navigate = assign()
    vi.mocked(api.checkGoogleSignIn).mockResolvedValue({ ok: true, data: undefined })
    render(<GoogleSignIn />)

    await userEvent.click(screen.getByRole('button', { name: GOOGLE_LABEL }))

    expect(navigate).toHaveBeenCalledWith('/api/auth/google/login')
  })

  it('says plainly that Google sign-in is unconfigured, and does not navigate', async () => {
    const navigate = assign()
    vi.mocked(api.checkGoogleSignIn).mockResolvedValue({
      ok: false,
      status: 503,
      error: 'Google sign-in is not configured.',
    })
    render(<GoogleSignIn />)

    await userEvent.click(screen.getByRole('button', { name: GOOGLE_LABEL }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'El inicio de sesión con Google no está configurado en este entorno.',
    )
    expect(navigate).not.toHaveBeenCalled()
  })

  it('never falls back to a development identity when Google is unavailable', async () => {
    vi.mocked(api.checkGoogleSignIn).mockResolvedValue({
      ok: false,
      status: 503,
      error: 'Google sign-in is not configured.',
    })
    const { container } = render(<GoogleSignIn />)

    await userEvent.click(screen.getByRole('button', { name: GOOGLE_LABEL }))
    await screen.findByRole('alert')

    expect(api.devLogin).not.toHaveBeenCalled()
    expect(container.textContent).not.toContain('demostración')
    expect(container.textContent).not.toContain('dev-admin')
  })

  it('reports a network failure and retries on demand', async () => {
    const navigate = assign()
    vi.mocked(api.checkGoogleSignIn)
      .mockResolvedValueOnce({ ok: false, status: 0, error: 'No se pudo contactar la plataforma.' })
      .mockResolvedValueOnce({ ok: true, data: undefined })
    render(<GoogleSignIn />)

    await userEvent.click(screen.getByRole('button', { name: GOOGLE_LABEL }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('No se pudo contactar la plataforma.')

    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))

    expect(navigate).toHaveBeenCalledWith('/api/auth/google/login')
  })

  it('blocks a second click while the first attempt is still in flight', async () => {
    let release: ((value: { ok: false; status: number; error: string }) => void) | undefined
    vi.mocked(api.checkGoogleSignIn).mockReturnValue(
      new Promise((resolve) => {
        release = resolve
      }) as ReturnType<typeof api.checkGoogleSignIn>,
    )
    render(<GoogleSignIn />)

    await userEvent.click(screen.getByRole('button', { name: GOOGLE_LABEL }))

    expect(screen.getByTestId('login-actions')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: /Redirigiendo a Google/ })).toBeDisabled()

    release?.({ ok: false, status: 0, error: 'x' })
    await screen.findByRole('button', { name: GOOGLE_LABEL })
  })

  it('tells the reader that a session is not by itself access to Transelec', () => {
    render(<GoogleSignIn />)

    expect(screen.getByTestId('login-actions')).toBeInTheDocument()
    expect(document.body.textContent).toMatch(/permisos sobre este producto/)
  })
})
