import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from '../router/Router'
import { Home } from './Home'

function mockRuntimeFetch(body: unknown = { modules: {} }) {
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
  window.history.pushState({}, '', '/')
})

beforeEach(() => {
  mockRuntimeFetch()
})

describe('Home', () => {
  it('renders all three bounded products with their factual evidence', async () => {
    render(
      <RouterProvider>
        <Home />
      </RouterProvider>,
    )

    expect(await screen.findByText('Cubicación LiDAR')).toBeInTheDocument()
    expect(screen.getByText('Gestión Predial Forestal')).toBeInTheDocument()
    expect(screen.getByText('Transelec')).toBeInTheDocument()

    expect(screen.getByText('1.568 polígonos de origen')).toBeInTheDocument()
    expect(screen.getByText('159 PMF')).toBeInTheDocument()
  })

  it('offers exactly one "Abrir módulo" action per product', () => {
    render(
      <RouterProvider>
        <Home />
      </RouterProvider>,
    )

    const actions = screen.getAllByText('Abrir módulo')
    expect(actions).toHaveLength(3)
  })

  it('never exposes developer diagnostics on the stakeholder home screen', () => {
    const { container } = render(
      <RouterProvider>
        <Home />
      </RouterProvider>,
    )

    const text = container.textContent ?? ''
    for (const forbidden of ['branch', 'commit', 'pytest', 'PID', '127.0.0.1', 'ECONNREFUSED']) {
      expect(text).not.toContain(forbidden)
    }
  })

  it('links to the developer status view without featuring it prominently', () => {
    render(
      <RouterProvider>
        <Home />
      </RouterProvider>,
    )

    expect(screen.getByText('Estado del entorno local')).toBeInTheDocument()
  })
})

describe('Home — staging awareness', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('never shows the local-only "Demo no iniciada" phrase in staging', async () => {
    vi.stubEnv('VITE_CAMPO_ENV', 'staging')

    render(
      <RouterProvider>
        <Home />
      </RouterProvider>,
    )

    await screen.findByText('Cubicación LiDAR')
    expect(screen.queryByText('Demo no iniciada')).not.toBeInTheDocument()
  })

  it('links to /archivos as a first-class nav entry', () => {
    render(
      <RouterProvider>
        <Home />
      </RouterProvider>,
    )

    const link = screen.getByText('Archivos')
    expect(link.closest('a')).toHaveAttribute('href', '/archivos')
  })
})
