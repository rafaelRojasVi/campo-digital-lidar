import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  fetchForestryRole,
  mutationMessage,
  publishSnapshot,
  resetCsrfForTests,
  uploadShapefileZip,
} from './api.ts'

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  resetCsrfForTests()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('mutations', () => {
  it('send the session CSRF token and the reviewed published id', async () => {
    fetchMock
      .mockResolvedValueOnce(json(200, { csrf_token: 'tok-1', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(json(200, { status: 'published' }))

    await publishSnapshot(4, 3, true)

    const [url, init] = fetchMock.mock.calls[1]!
    expect(url).toBe('/api/forestry/snapshots/4/publish')
    expect(init?.method).toBe('POST')
    expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('tok-1')
    expect(JSON.parse(String(init?.body))).toEqual({
      expected_published_snapshot_id: 3,
      acknowledge_review: true,
    })
  })

  it('fetch a fresh token once when the server rejects a stale one', async () => {
    fetchMock
      .mockResolvedValueOnce(json(200, { csrf_token: 'old' }))
      .mockResolvedValueOnce(json(403, { detail: 'CSRF verification failed.' }))
      .mockResolvedValueOnce(json(200, { csrf_token: 'new' }))
      .mockResolvedValueOnce(json(200, { status: 'uploaded', shapefile_snapshot_id: 1 }))

    const result = await uploadShapefileZip(new File(['zip'], 'capa.zip'))

    expect(result.shapefile_snapshot_id).toBe(1)
    expect(new Headers(fetchMock.mock.calls[3]![1]?.headers).get('X-CSRF-Token')).toBe('new')
    expect(fetchMock.mock.calls[3]![1]?.body).toBeInstanceOf(FormData)
  })

  it('carry the server message and reason of a refusal', async () => {
    fetchMock
      .mockResolvedValueOnce(json(200, { csrf_token: 'tok' }))
      .mockResolvedValueOnce(
        json(422, { detail: 'El archivo no es un ZIP válido.', reason: 'not_zip' }),
      )

    const error = await uploadShapefileZip(new File(['x'], 'a.zip')).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).reason).toBe('not_zip')
    expect(mutationMessage(error, 'fallback')).toBe('El archivo no es un ZIP válido.')
  })
})

describe('mutationMessage', () => {
  it('uses plain Spanish for session, permission, size and network failures', () => {
    expect(mutationMessage(new ApiError(401, 'x', 'Not authenticated.'), 'f')).toMatch(/sesión/)
    expect(mutationMessage(new ApiError(403, 'x', 'Not permitted'), 'f')).toMatch(/permiso/)
    expect(mutationMessage(new ApiError(413, 'x'), 'f')).toMatch(/demasiado grande/)
    expect(mutationMessage(new ApiError(0, 'x'), 'f')).toMatch(/conectar/)
    expect(mutationMessage(new Error('boom'), 'fallback')).toBe('fallback')
  })
})

describe('fetchForestryRole', () => {
  it('reads the forestry grant from the session, or null without one', async () => {
    fetchMock.mockResolvedValueOnce(
      json(200, { product_grants: [{ product_key: 'forestry', role: 'operator' }] }),
    )
    expect(await fetchForestryRole()).toBe('operator')

    fetchMock.mockResolvedValueOnce(
      json(200, { product_grants: [{ product_key: 'transelect', role: 'admin' }] }),
    )
    expect(await fetchForestryRole()).toBeNull()
  })
})
