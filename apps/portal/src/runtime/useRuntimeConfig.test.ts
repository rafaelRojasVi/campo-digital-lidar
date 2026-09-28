import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useRuntimeConfig } from './useRuntimeConfig'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('useRuntimeConfig', () => {
  it('in local, fetches campo-runtime.json exactly as before', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          modules: { lidar: { status: 'available', url: 'http://127.0.0.1:5174/' } },
        }),
      }),
    )

    const { result } = renderHook(() => useRuntimeConfig())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.config.environment).toBe('local')
    expect(result.current.config.modules.lidar?.url).toBe('http://127.0.0.1:5174/')
  })

  it('in staging, never calls fetch and resolves synchronously from build-time config', async () => {
    vi.stubEnv('VITE_CAMPO_ENV', 'staging')
    vi.stubEnv('VITE_LIDAR_HOSTED_URL', 'https://campo-digital-lidar-staging.onrender.com')
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    const { result } = renderHook(() => useRuntimeConfig())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(result.current.config.environment).toBe('staging')
    expect(result.current.config.modules.lidar?.status).toBe('available')
  })
})
