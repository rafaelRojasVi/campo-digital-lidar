import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function mockRuntimeFetch(body: unknown = { modules: {} }) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.endsWith('/api/auth/me')) {
        return { ok: false, status: 401, json: async () => ({ detail: 'Not authenticated.' }) }
      }

      return { ok: true, json: async () => body }
    }),
  )
}

beforeEach(() => {
  mockRuntimeFetch()
  window.history.pushState({}, '', '/')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App navigation', () => {
  it('navigates from the home portal into a module shell and back, updating the URL', async () => {
    const user = userEvent.setup()
    render(<App />)

    await screen.findByText('Cubicación LiDAR')

    const [openLidar] = screen.getAllByText('Abrir módulo')
    await user.click(openLidar)

    expect(window.location.pathname).toBe('/modulo/lidar')
    expect(await screen.findByText('Demo no iniciada.')).toBeInTheDocument()

    await user.click(screen.getByText('← Campo Digital'))

    expect(window.location.pathname).toBe('/')
    expect(await screen.findByText('Cubicación LiDAR')).toBeInTheDocument()
  })

  it('supports switching directly between modules via the compact module switcher', async () => {
    const user = userEvent.setup()
    window.history.pushState({}, '', '/modulo/lidar')
    render(<App />)

    await screen.findByText('Demo no iniciada.')

    const switcherLinks = screen.getAllByText('Forestal')
    await user.click(switcherLinks[0])

    expect(window.location.pathname).toBe('/modulo/forestal')
  })

  it('renders the developer status route with per-module ports, separate from the home screen', async () => {
    window.history.pushState({}, '', '/estado')
    render(<App />)

    expect(await screen.findByText('Estado del entorno local')).toBeInTheDocument()
  })

  it('navigates from the home footer into /archivos as a first-class entry', async () => {
    const user = userEvent.setup()
    render(<App />)

    await screen.findByText('Cubicación LiDAR')
    await user.click(screen.getByText('Archivos'))

    expect(window.location.pathname).toBe('/archivos')
    await screen.findByText('Archivos')
  })
})
