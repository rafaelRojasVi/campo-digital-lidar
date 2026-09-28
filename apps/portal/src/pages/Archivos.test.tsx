import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from '../router/Router'
import { Archivos } from './Archivos'

interface MockResponses {
  me?: unknown
  jobs?: unknown
  audit?: unknown
}

function mockPlatformFetch({ me, jobs = [], audit = [] }: MockResponses) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.endsWith('/api/auth/me')) {
        return me
          ? { ok: true, status: 200, json: async () => me }
          : { ok: false, status: 401, json: async () => ({ detail: 'Not authenticated.' }) }
      }
      if (url.endsWith('/api/ingesta/jobs')) {
        return { ok: true, status: 200, json: async () => jobs }
      }
      if (url.endsWith('/api/ingesta/audit')) {
        return audit
          ? { ok: true, status: 200, json: async () => audit }
          : { ok: false, status: 403, json: async () => ({ detail: 'Admin access required.' }) }
      }

      return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) }
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Archivos', () => {
  it('shows the local-identity picker and no upload control when logged out', async () => {
    mockPlatformFetch({ me: undefined })

    render(
      <RouterProvider>
        <Archivos />
      </RouterProvider>,
    )

    await screen.findByText('dev-admin')
    expect(screen.getByText('dev-operator')).toBeInTheDocument()
    expect(screen.getByText('dev-viewer')).toBeInTheDocument()
    expect(screen.queryByText('Subir')).not.toBeInTheDocument()
  })

  it('a viewer never sees an enabled upload control, even for their granted product', async () => {
    mockPlatformFetch({
      me: {
        identity_key: 'dev-viewer',
        display_name: 'Dev Viewer',
        product_grants: [{ product_key: 'transelect', role: 'viewer' }],
      },
      jobs: [],
    })

    render(
      <RouterProvider>
        <Archivos />
      </RouterProvider>,
    )

    await screen.findByText('Dev Viewer (dev-viewer)')

    const uploadButton = screen.getByText('Subir') as HTMLButtonElement
    expect(uploadButton.disabled).toBe(true)
    const fileInput = screen.getByLabelText('Archivo a subir') as HTMLInputElement
    expect(fileInput.disabled).toBe(true)
  })

  it('a viewer never sees a retry control on a failed job in their granted product', async () => {
    mockPlatformFetch({
      me: {
        identity_key: 'dev-viewer',
        display_name: 'Dev Viewer',
        product_grants: [{ product_key: 'transelect', role: 'viewer' }],
      },
      jobs: [
        {
          id: 1,
          product_key: 'transelect',
          status: 'failed',
          attempt_count: 3,
          created_at: '2026-09-01T00:00:00Z',
          error_summary: 'boom',
        },
      ],
    })

    render(
      <RouterProvider>
        <Archivos />
      </RouterProvider>,
    )

    await screen.findByText('Dev Viewer (dev-viewer)')
    await waitFor(() => expect(screen.getByText('failed')).toBeInTheDocument())
    expect(screen.queryByText('Reintentar')).not.toBeInTheDocument()
  })

  it('an operator sees a retry control on a failed job but no audit section', async () => {
    mockPlatformFetch({
      me: {
        identity_key: 'dev-operator',
        display_name: 'Dev Operator',
        product_grants: [{ product_key: 'forestry', role: 'operator' }],
      },
      jobs: [
        {
          id: 2,
          product_key: 'forestry',
          status: 'failed',
          attempt_count: 3,
          created_at: '2026-09-01T00:00:00Z',
          error_summary: 'boom',
        },
      ],
    })

    render(
      <RouterProvider>
        <Archivos />
      </RouterProvider>,
    )

    await screen.findByText('Dev Operator (dev-operator)')
    await waitFor(() => expect(screen.getByText('Reintentar')).toBeInTheDocument())
    expect(screen.queryByText('Auditoría')).not.toBeInTheDocument()
  })

  it('an admin sees the audit section', async () => {
    mockPlatformFetch({
      me: {
        identity_key: 'dev-admin',
        display_name: 'Dev Admin',
        product_grants: [
          { product_key: 'lidar', role: 'admin' },
          { product_key: 'forestry', role: 'admin' },
          { product_key: 'transelect', role: 'admin' },
        ],
      },
      jobs: [],
      audit: [
        {
          id: 1,
          occurred_at: '2026-09-01T00:00:00Z',
          actor_app_user_id: 1,
          event_type: 'session.created',
          product_key: null,
          subject_kind: null,
          subject_id: null,
        },
      ],
    })

    render(
      <RouterProvider>
        <Archivos />
      </RouterProvider>,
    )

    await screen.findByText('Dev Admin (dev-admin)')
    await waitFor(() => expect(screen.getByText('Auditoría')).toBeInTheDocument())
    await screen.findByText('session.created')
  })
})

describe('Archivos — staging (no sign-in mechanism yet)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('shows an honest sign-in-unavailable message instead of dead dev-login buttons', async () => {
    vi.stubEnv('VITE_CAMPO_ENV', 'staging')
    mockPlatformFetch({ me: undefined })

    render(
      <RouterProvider>
        <Archivos />
      </RouterProvider>,
    )

    await screen.findByText(/inicio de sesión/i)
    expect(screen.queryByText('dev-admin')).not.toBeInTheDocument()
    expect(screen.queryByText('dev-operator')).not.toBeInTheDocument()
    expect(screen.queryByText('dev-viewer')).not.toBeInTheDocument()
  })
})
