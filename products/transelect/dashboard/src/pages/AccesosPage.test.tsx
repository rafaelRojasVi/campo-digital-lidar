import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AccesosPage } from './AccesosPage'
import { DatosPage } from './DatosPage'
import { ROUTES, RouterProvider } from '../router'
import type { ProductGrantee } from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, listTranselecGrants: vi.fn(), grantTranselecRole: vi.fn() }
})

const { listTranselecGrants, grantTranselecRole } = await import('../api')

const admin: ProductGrantee = {
  app_user_id: 1,
  email: 'admin@campodigital.cl',
  display_name: 'Administración',
  role: 'admin',
}

describe('AccesosPage', () => {
  beforeEach(() => {
    vi.mocked(listTranselecGrants).mockReset()
    vi.mocked(grantTranselecRole).mockReset()
  })

  it('lists who holds a Transelec role', async () => {
    vi.mocked(listTranselecGrants).mockResolvedValue({ ok: true, data: [admin] })
    render(<AccesosPage />)

    await waitFor(() => expect(screen.getByTestId('grantees')).toBeInTheDocument())
    expect(screen.getByText('admin@campodigital.cl')).toBeInTheDocument()
    expect(screen.getByText('Administrador')).toBeInTheDocument()
  })

  it('offers only viewer and operator, never admin', async () => {
    vi.mocked(listTranselecGrants).mockResolvedValue({ ok: true, data: [admin] })
    render(<AccesosPage />)

    const select = await screen.findByLabelText('Rol')
    const values = Array.from((select as HTMLSelectElement).options).map((o) => o.value)
    expect(values).toEqual(['viewer', 'operator'])
  })

  it('grants the chosen role and refreshes the list', async () => {
    const operator: ProductGrantee = {
      app_user_id: 2,
      email: 'operador@campodigital.cl',
      display_name: 'Operación',
      role: 'operator',
    }
    vi.mocked(listTranselecGrants)
      .mockResolvedValueOnce({ ok: true, data: [admin] })
      .mockResolvedValueOnce({ ok: true, data: [admin, operator] })
    vi.mocked(grantTranselecRole).mockResolvedValue({ ok: true, data: operator })
    render(<AccesosPage />)

    await userEvent.type(await screen.findByLabelText('Correo'), 'Operador@campodigital.cl ')
    await userEvent.selectOptions(screen.getByLabelText('Rol'), 'operator')
    await userEvent.click(screen.getByRole('button', { name: 'Otorgar acceso' }))

    expect(grantTranselecRole).toHaveBeenCalledWith('Operador@campodigital.cl ', 'operator')
    expect(await screen.findByText('Acceso actualizado')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('operador@campodigital.cl')).toBeInTheDocument())
  })

  it('explains that the account must sign in first when the API answers 404', async () => {
    vi.mocked(listTranselecGrants).mockResolvedValue({ ok: true, data: [admin] })
    vi.mocked(grantTranselecRole).mockResolvedValue({
      ok: false,
      status: 404,
      error: 'No user has signed in with that email yet.',
    })
    render(<AccesosPage />)

    await userEvent.type(await screen.findByLabelText('Correo'), 'nuevo@campodigital.cl')
    await userEvent.click(screen.getByRole('button', { name: 'Otorgar acceso' }))

    expect(await screen.findByText(/todavía no ha iniciado sesión/)).toBeInTheDocument()
  })
})

describe('DatosPage access tab', () => {
  beforeEach(() => {
    vi.mocked(listTranselecGrants).mockReset()
  })

  function renderDatos(isAdmin: boolean, path: string = ROUTES.importar) {
    render(
      <RouterProvider initialPath={path}>
        <DatosPage
          route={path as typeof ROUTES.importar}
          activeImport={null}
          onActiveVersionChanged={vi.fn()}
          isAdmin={isAdmin}
        />
      </RouterProvider>,
    )
  }

  it('hides the Accesos tab from operators', () => {
    renderDatos(false, ROUTES.versiones)
    expect(screen.queryByRole('link', { name: 'Accesos' })).not.toBeInTheDocument()
  })

  it('refuses the Accesos pane to an operator who types its URL', () => {
    renderDatos(false, ROUTES.accesos)
    expect(
      screen.getByText('Sólo los administradores de Transelec pueden gestionar accesos.'),
    ).toBeInTheDocument()
    expect(listTranselecGrants).not.toHaveBeenCalled()
  })

  it('shows the Accesos tab to administrators', () => {
    vi.mocked(listTranselecGrants).mockResolvedValue({ ok: true, data: [admin] })
    renderDatos(true, ROUTES.accesos)
    expect(screen.getByRole('link', { name: 'Accesos' })).toHaveAttribute('aria-current', 'page')
  })
})
