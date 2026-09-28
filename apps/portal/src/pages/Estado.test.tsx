import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from '../router/Router'
import { Estado } from './Estado'

function mockRuntimeFetch(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => body,
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Estado', () => {
  it('shows the persisted LiDAR measurement count separately from service status', async () => {
    mockRuntimeFetch({
      modules: {
        lidar: { status: 'available', url: 'http://127.0.0.1:5174/', measurementCount: 14 },
      },
    })

    render(
      <RouterProvider>
        <Estado />
      </RouterProvider>,
    )

    await screen.findByText('14')
    expect(screen.getByText(/mediciones/i)).toBeInTheDocument()
  })

  it('never renders a filesystem path, even when one is present in the diagnostic data', async () => {
    mockRuntimeFetch({
      modules: {
        lidar: { status: 'available', url: 'http://127.0.0.1:5174/', measurementCount: 0 },
      },
    })

    render(
      <RouterProvider>
        <Estado />
      </RouterProvider>,
    )

    await screen.findByText('0')
    expect(screen.queryByText(/\/home\//)).not.toBeInTheDocument()
    expect(screen.queryByText(/products\/lidar\/reports/)).not.toBeInTheDocument()
  })

  it('shows a dash for modules without a measurement count', async () => {
    mockRuntimeFetch({
      modules: { forestal: { status: 'available', url: 'http://127.0.0.1:5175/' } },
    })

    render(
      <RouterProvider>
        <Estado />
      </RouterProvider>,
    )

    await screen.findByText('Gestión Predial Forestal')
    const row = screen.getByText('Gestión Predial Forestal').closest('tr')
    expect(row).not.toBeNull()
    expect(row!.textContent).toContain('—')
  })
})

describe('Estado — staging', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('describes hosted availability, not local process ownership', async () => {
    vi.stubEnv('VITE_CAMPO_ENV', 'staging')
    vi.stubEnv('VITE_LIDAR_HOSTED_URL', 'https://campo-digital-lidar-staging.onrender.com')

    render(
      <RouterProvider>
        <Estado />
      </RouterProvider>,
    )

    expect(await screen.findByText('Estado del entorno de staging')).toBeInTheDocument()
    expect(screen.queryByText('Estado del entorno local')).not.toBeInTheDocument()
    expect(screen.queryByText('Iniciado por Campo Demo')).not.toBeInTheDocument()
  })
})
