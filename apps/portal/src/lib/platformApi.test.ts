import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type FetchCall = [string, RequestInit | undefined]

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: async () => body,
  } as Response
}

/** Re-import the module so its per-session token cache starts empty. */
async function freshApi(): Promise<typeof import('./platformApi')> {
  vi.resetModules()
  return import('./platformApi')
}

function calls(): FetchCall[] {
  return (globalThis.fetch as unknown as { mock: { calls: FetchCall[] } }).mock.calls
}

function csrfCallCount(): number {
  return calls().filter(([url]) => url === '/api/auth/csrf').length
}

function headerOf(url: string, name: string): string | undefined {
  const call = calls().find(([candidate]) => candidate === url)
  const headers = call?.[1]?.headers as Record<string, string> | undefined
  return headers?.[name]
}

describe('platformApi CSRF handling', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async (url: string) => {
      if (url === '/api/auth/csrf') {
        return jsonResponse({ csrf_token: 'token-1', header_name: 'X-CSRF-Token' })
      }
      return jsonResponse({ ok: true })
    }) as unknown as typeof fetch
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('does not request or send a CSRF token for reads', async () => {
    const api = await freshApi()

    await api.listJobs()

    expect(csrfCallCount()).toBe(0)
    expect(headerOf('/api/ingesta/jobs', 'X-CSRF-Token')).toBeUndefined()
  })

  it('sends a session-bound CSRF token on mutations', async () => {
    const api = await freshApi()

    await api.retryJob(7)

    expect(csrfCallCount()).toBe(1)
    expect(headerOf('/api/ingesta/jobs/7/retry', 'X-CSRF-Token')).toBe('token-1')
  })

  it('reuses one token across several mutations', async () => {
    const api = await freshApi()

    await api.retryJob(1)
    await api.retryJob(2)

    expect(csrfCallCount()).toBe(1)
  })

  it('drops the cached token on login and logout, since it is session-bound', async () => {
    const api = await freshApi()

    await api.retryJob(1)
    await api.logout()
    await api.retryJob(2)

    expect(csrfCallCount()).toBe(2)
  })

  it('refreshes the token and retries once when the server rejects it', async () => {
    let rejectedOnce = false
    globalThis.fetch = vi.fn(async (url: string) => {
      if (url === '/api/auth/csrf') {
        return jsonResponse({ csrf_token: 'token-1', header_name: 'X-CSRF-Token' })
      }
      if (!rejectedOnce) {
        rejectedOnce = true
        return jsonResponse({ detail: 'CSRF verification failed.' }, 403)
      }
      return jsonResponse({ ok: true })
    }) as unknown as typeof fetch

    const api = await freshApi()
    const result = await api.retryJob(1)

    expect(result.ok).toBe(true)
    expect(csrfCallCount()).toBe(2)
  })

  it('does not retry a non-CSRF 403', async () => {
    globalThis.fetch = vi.fn(async (url: string) => {
      if (url === '/api/auth/csrf') {
        return jsonResponse({ csrf_token: 'token-1', header_name: 'X-CSRF-Token' })
      }
      return jsonResponse({ detail: 'Not permitted for this product.' }, 403)
    }) as unknown as typeof fetch

    const api = await freshApi()
    const result = await api.retryJob(1)

    expect(result).toEqual({
      ok: false,
      status: 403,
      error: 'Not permitted for this product.',
    })
    expect(calls().filter(([url]) => url === '/api/ingesta/jobs/1/retry')).toHaveLength(1)
  })
})
