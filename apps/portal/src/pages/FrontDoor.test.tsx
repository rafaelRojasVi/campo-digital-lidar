import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../lib/platformApi'
import { FrontDoor } from './FrontDoor'

vi.mock('../lib/platformApi', async (importOriginal) => {
  const actual = await importOriginal<typeof api>()
  return { ...actual, getMe: vi.fn(), logout: vi.fn() }
})

const me = (grants: api.ProductGrant[]): api.ApiResult<api.Me> => ({
  ok: true,
  data: { identity_key: 'sub-1', display_name: 'Javier Soto', product_grants: grants },
})

describe('FrontDoor', () => {
  beforeEach(() => {
    vi.mocked(api.getMe).mockReset()
    vi.mocked(api.logout).mockReset()
  })

  it('offers Google sign-in when signed out', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ok: false, status: 401, error: 'no session' })
    render(<FrontDoor />)
    const link = await screen.findByRole('link', { name: 'Iniciar sesión con Google' })
    expect(link).toHaveAttribute('href', '/api/auth/google/login')
  })

  it('shows only the projects the user can open', async () => {
    vi.mocked(api.getMe).mockResolvedValue(me([{ product_key: 'transelect', role: 'viewer' }]))
    render(<FrontDoor />)
    expect(await screen.findByText('Hola, Javier Soto')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Transelec/ })).toHaveAttribute('href', '/transelec/')
    expect(screen.queryByText('Rodales')).not.toBeInTheDocument()
  })

  it('shows a project that is not online yet as upcoming, without a link', async () => {
    vi.mocked(api.getMe).mockResolvedValue(
      me([
        { product_key: 'transelect', role: 'admin' },
        { product_key: 'forestry', role: 'admin' },
      ]),
    )
    render(<FrontDoor />)
    expect(await screen.findByText('Rodales')).toBeInTheDocument()
    expect(screen.getByText('Próximamente')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Rodales/ })).not.toBeInTheDocument()
  })

  it('explains an account with no projects', async () => {
    vi.mocked(api.getMe).mockResolvedValue(me([]))
    render(<FrontDoor />)
    expect(await screen.findByText(/no tiene proyectos asignados/)).toBeInTheDocument()
  })

  it('reports an unreachable platform instead of asking to sign in', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ok: false, status: 503, error: 'down' })
    render(<FrontDoor />)
    expect(await screen.findByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Iniciar sesión con Google' })).not.toBeInTheDocument()
  })

  it('signs out back to the sign-in view', async () => {
    vi.mocked(api.getMe).mockResolvedValue(me([{ product_key: 'transelect', role: 'viewer' }]))
    vi.mocked(api.logout).mockResolvedValue({ ok: true, data: undefined })
    render(<FrontDoor />)
    await userEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Iniciar sesión con Google' })).toBeInTheDocument(),
    )
  })

  it('says so when signing out fails, and keeps the session view', async () => {
    vi.mocked(api.getMe).mockResolvedValue(me([{ product_key: 'transelect', role: 'viewer' }]))
    vi.mocked(api.logout).mockResolvedValue({ ok: false, status: 503, error: 'down' })
    render(<FrontDoor />)
    await userEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo cerrar la sesión')
    expect(screen.getByText('Hola, Javier Soto')).toBeInTheDocument()
  })
})
