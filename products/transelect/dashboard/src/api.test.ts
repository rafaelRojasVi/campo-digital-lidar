import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  EMPTY_FILTERS,
  GOOGLE_LOGIN_PATH,
  NETWORK_ERROR,
  canPublish,
  checkGoogleSignIn,
  devLogin,
  exportCsvUrl,
  filterParams,
  filtersActive,
  getSummary,
  layoutReportFromFailure,
  logout,
  observedServerNow,
  publishImport,
  resetApiClientState,
  transelecRole,
  uploadWorkbook,
  validateAndProject,
} from './api'

const SERVER_DATE = 'Wed, 02 Sep 2026 21:10:00 GMT'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers)
  headers.set('content-type', 'application/json')
  if (!headers.has('date')) headers.set('date', SERVER_DATE)
  return new Response(JSON.stringify(body), { ...init, headers })
}

describe('filter serialization (TR-FUNC-017-022)', () => {
  it('omits every empty field so an unfiltered read carries no query string', () => {
    expect(filterParams(EMPTY_FILTERS).toString()).toBe('')
    expect(filtersActive(EMPTY_FILTERS)).toBe(false)
  })

  it('repeats a multi-select param once per selected value (OR within a field)', () => {
    const params = filterParams({
      ...EMPTY_FILTERS,
      estado_resumido: ['Aprobado', 'En tramite'],
    })
    expect(params.getAll('estado_resumido')).toEqual(['Aprobado', 'En tramite'])
  })

  it('AND-combines different fields in a single query string', () => {
    const params = filterParams({
      ...EMPTY_FILTERS,
      empresa: ['Forestal Uno'],
      sector: ['Norte'],
      q: '  rechaz  ',
    })
    expect(params.getAll('empresa')).toEqual(['Forestal Uno'])
    expect(params.getAll('sector')).toEqual(['Norte'])
    expect(params.get('q')).toBe('rechaz')
  })

  it('reports an active filter state for free text alone', () => {
    expect(filtersActive({ ...EMPTY_FILTERS, q: 'rechaz' })).toBe(true)
    expect(filtersActive({ ...EMPTY_FILTERS, q: '   ' })).toBe(false)
    expect(filtersActive({ ...EMPTY_FILTERS, pas: ['PAS 148'] })).toBe(true)
  })

  it('builds the CSV export URL from the same shared filter contract (TR-FUNC-037)', () => {
    expect(exportCsvUrl(EMPTY_FILTERS)).toBe('/api/transelec/export.csv')
    expect(exportCsvUrl({ ...EMPTY_FILTERS, sector: ['Norte'] })).toBe(
      '/api/transelec/export.csv?sector=Norte',
    )
  })
})

describe('role helpers', () => {
  const me = (role: string) => ({
    identity_key: 'dev-admin',
    display_name: 'Dev Admin',
    product_grants: [{ product_key: 'transelect', role } as never],
  })

  it('reads the Transelec grant only', () => {
    expect(
      transelecRole({
        identity_key: 'x',
        display_name: 'x',
        product_grants: [{ product_key: 'forestry', role: 'admin' }],
      }),
    ).toBeNull()
    expect(transelecRole(me('viewer'))).toBe('viewer')
  })

  it('gates publish to operator and admin', () => {
    expect(canPublish(me('viewer'))).toBe(false)
    expect(canPublish(me('operator'))).toBe(true)
    expect(canPublish(me('admin'))).toBe(true)
    expect(canPublish(null)).toBe(false)
  })
})

describe('transport', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    resetApiClientState()
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends a GET with credentials and no CSRF token', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ import_id: 1 }))
    const result = await getSummary(EMPTY_FILTERS)

    expect(result).toEqual({ ok: true, data: { import_id: 1 } })
    const [path, init] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/transelec/summary')
    expect(init.credentials).toBe('include')
    expect(init.headers).toBeUndefined()
  })

  it('records the server Date header as the observed reference clock (TR-FUNC-031)', async () => {
    expect(observedServerNow()).toBeNull()
    fetchMock.mockResolvedValueOnce(jsonResponse({}))
    await getSummary(EMPTY_FILTERS)
    expect(observedServerNow()?.toISOString()).toBe('2026-09-02T21:10:00.000Z')
  })

  it('fetches a CSRF token at runtime and sends it on a mutation', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ csrf_token: 'nonce.signature', header_name: 'X-CSRF-Token' }),
      )
      .mockResolvedValueOnce(jsonResponse({ status: 'published' }))

    await publishImport(7)

    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/csrf')
    const [path, init] = fetchMock.mock.calls[1]
    expect(path).toBe('/api/transelec/imports/7/publish')
    expect(init.method).toBe('POST')
    expect(init.headers['X-CSRF-Token']).toBe('nonce.signature')
  })

  it('honours the header name the server reports rather than hardcoding it', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 'abc.def', header_name: 'X-Other-Token' }))
      .mockResolvedValueOnce(jsonResponse({}))

    await publishImport(1)
    expect(fetchMock.mock.calls[1][1].headers['X-Other-Token']).toBe('abc.def')
  })

  it('reuses one cached token across mutations, then drops and refetches it after a CSRF 403', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 'token-1', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(jsonResponse({}))
      .mockResolvedValueOnce(
        jsonResponse({ detail: 'CSRF verification failed.' }, { status: 403 }),
      )
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 'token-2', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }))

    await publishImport(1)
    const second = await publishImport(2)

    expect(second.ok).toBe(true)
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/auth/csrf',
      '/api/transelec/imports/1/publish',
      '/api/transelec/imports/2/publish',
      '/api/auth/csrf',
      '/api/transelec/imports/2/publish',
    ])
    expect(fetchMock.mock.calls[4][1].headers['X-CSRF-Token']).toBe('token-2')
  })

  it('never retries an ordinary authorization 403', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 't', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(
        jsonResponse({ detail: 'Not permitted for this product.' }, { status: 403 }),
      )

    const result = await publishImport(3)

    expect(result).toEqual({ ok: false, status: 403, error: 'Not permitted for this product.' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('surfaces the API detail string for a 422 contract violation', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 't', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(
        jsonResponse(
          { detail: 'La planilla no cumple el contrato de origen esperado. Contacte a soporte.' },
          { status: 422 },
        ),
      )

    const result = await validateAndProject(41)

    expect(result).toEqual({
      ok: false,
      status: 422,
      error: 'La planilla no cumple el contrato de origen esperado. Contacte a soporte.',
      payload: { detail: 'La planilla no cumple el contrato de origen esperado. Contacte a soporte.' },
    })
    expect(layoutReportFromFailure(result.ok ? null : result.payload)).toBeNull()
  })

  it('carries the layout review of a refused import alongside its detail string', async () => {
    const report = {
      parser_version: 'transelec_ingestion.resumen_layout@2',
      sheet_name: 'Resumen',
      header_row: 1,
      business_rows: 0,
      columns: [],
      fields: [],
      auxiliary_regions: [],
      issues: [
        {
          code: 'carpeta_ambigua',
          severity: 'error',
          message: 'La columna L se llama «Carpeta»…',
          field: null,
          columns: ['L'],
          rows: [],
          row_count: 0,
        },
      ],
      counts: { error: 1, warning: 0, info: 0 },
    }
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 't', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Revise', report }, { status: 422 }))

    const result = await validateAndProject(41)

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.error).toBe('Revise')
    expect(layoutReportFromFailure(result.payload)?.issues[0].columns).toEqual(['L'])
  })

  it('never throws on a network failure', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(getSummary(EMPTY_FILTERS)).resolves.toEqual({
      ok: false,
      status: 0,
      error: NETWORK_ERROR,
    })
  })

  it('uploads the file without a product_key field', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 't', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(jsonResponse({ source_snapshot_id: 5 }))

    await uploadWorkbook(new File(['x'], 'resumen.xlsx'))

    const body = fetchMock.mock.calls[1][1].body as FormData
    expect(body.get('product_key')).toBeNull()
    expect((body.get('file') as File).name).toBe('resumen.xlsx')
  })
})

describe('sign-in and sign-out', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    resetApiClientState()
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts the seeded identity key as JSON, with the session cookie', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({}, { status: 401 })) // no session yet -> no token
      .mockResolvedValueOnce(jsonResponse({ identity_key: 'dev-admin' }))

    const result = await devLogin('dev-admin')

    expect(result).toEqual({ ok: true, data: { identity_key: 'dev-admin' } })
    const [path, init] = fetchMock.mock.calls[1]
    expect(path).toBe('/api/auth/dev-login')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('include')
    expect(JSON.parse(init.body as string)).toEqual({ identity_key: 'dev-admin' })
  })

  it('drops the cached CSRF token across a login, since it is keyed by the session', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 'token-viewer', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(jsonResponse({ status: 'published' }))
      .mockResolvedValueOnce(jsonResponse({}, { status: 401 }))
      .mockResolvedValueOnce(jsonResponse({ identity_key: 'dev-admin' }))
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 'token-admin', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(jsonResponse({ status: 'published' }))

    await publishImport(1)
    await devLogin('dev-admin')
    await publishImport(2)

    expect(fetchMock.mock.calls[4][0]).toBe('/api/auth/csrf')
    expect(fetchMock.mock.calls[5][1].headers['X-CSRF-Token']).toBe('token-admin')
  })

  it('signs out through the same CSRF-protected transport as every other mutation', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 'token-1', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    const result = await logout()

    expect(result).toEqual({ ok: true, data: undefined })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/csrf')
    const [path, init] = fetchMock.mock.calls[1]
    expect(path).toBe('/api/auth/logout')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('include')
    expect(init.headers['X-CSRF-Token']).toBe('token-1')
  })

  it('drops the token after signing out, so it cannot ride a later session', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 'token-1', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse({ csrf_token: 'token-2', header_name: 'X-CSRF-Token' }))
      .mockResolvedValueOnce(jsonResponse({ status: 'published' }))

    await logout()
    await publishImport(3)

    expect(fetchMock.mock.calls[2][0]).toBe('/api/auth/csrf')
    expect(fetchMock.mock.calls[3][1].headers['X-CSRF-Token']).toBe('token-2')
  })

  it('reads the Google redirect without following it cross-origin', async () => {
    fetchMock.mockResolvedValueOnce({ type: 'opaqueredirect', ok: false, status: 0 })

    await expect(checkGoogleSignIn()).resolves.toEqual({ ok: true, data: undefined })
    const [path, init] = fetchMock.mock.calls[0]
    expect(path).toBe(GOOGLE_LOGIN_PATH)
    expect(init.redirect).toBe('manual')
    expect(init.credentials).toBe('include')
  })

  it('surfaces unconfigured Google sign-in as the 503 the API actually returns', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: 'Google sign-in is not configured.' }, { status: 503 }),
    )

    await expect(checkGoogleSignIn()).resolves.toEqual({
      ok: false,
      status: 503,
      error: 'Google sign-in is not configured.',
    })
  })

  it('never claims Google sign-in is available when the platform is unreachable', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(checkGoogleSignIn()).resolves.toEqual({
      ok: false,
      status: 0,
      error: NETWORK_ERROR,
    })
  })
})
