export type ProductKey = 'lidar' | 'forestry' | 'transelect'
export type Role = 'admin' | 'operator' | 'viewer'

export interface ProductGrant {
  product_key: ProductKey
  role: Role
}

export interface Me {
  identity_key: string
  display_name: string
  product_grants: ProductGrant[]
}

export interface UploadResult {
  source_snapshot_id: number
  sha256: string
  byte_size: number
  validation_evidence: Record<string, unknown>
  job_id: number
}

export interface JobView {
  id: number
  product_key: string
  status: string
  attempt_count: number
  created_at: string
  error_summary: string | null
}

export interface AuditEventView {
  id: number
  occurred_at: string
  actor_app_user_id: number | null
  event_type: string
  product_key: string | null
  subject_kind: string | null
  subject_id: string | null
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; status: number; error: string }

export const DEV_IDENTITIES = ['dev-admin', 'dev-operator', 'dev-viewer'] as const

const CSRF_HEADER = 'X-CSRF-Token'
const CSRF_REJECTED = 'CSRF verification failed.'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

/**
 * The API requires a session-bound CSRF token on every state-changing
 * request. It is issued per session by GET /auth/csrf and held only in
 * memory here — never compiled into this bundle, and never read from a
 * cookie. Because it is bound to the session secret, it must be dropped
 * whenever the session changes (login/logout).
 */
let csrfToken: string | null = null

function forgetCsrfToken(): void {
  csrfToken = null
}

async function ensureCsrfToken(): Promise<string | null> {
  if (csrfToken !== null) return csrfToken

  try {
    const response = await fetch('/api/auth/csrf', { credentials: 'include' })
    if (!response.ok) return null
    const body = (await response.json()) as { csrf_token?: string }
    csrfToken = body.csrf_token ?? null
  } catch {
    csrfToken = null
  }

  return csrfToken
}

async function send(path: string, init: RequestInit | undefined): Promise<Response> {
  const method = (init?.method ?? 'GET').toUpperCase()
  if (SAFE_METHODS.has(method)) {
    return fetch(path, { credentials: 'include', ...init })
  }

  const token = await ensureCsrfToken()
  // A plain record rather than Headers: every caller in this module already
  // passes one, and Headers would lowercase the name in the recorded init.
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) }
  if (token !== null) headers[CSRF_HEADER] = token

  return fetch(path, { credentials: 'include', ...init, headers })
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string }
    if (body.detail) return body.detail
  } catch {
    // no JSON body on this error response; keep the status-text fallback
  }
  return response.statusText || `HTTP ${response.status}`
}

/**
 * All requests go through /api, proxied in dev (see vite.config.ts) to the
 * standalone platform API process started by `make platform-local`. Never
 * throws to the caller: network/parse failures come back as `{ ok: false }`,
 * mirroring runtimeConfig.ts's never-throw-to-the-UI convention.
 */
async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    let response = await send(path, init)

    // A token can go stale (the session was replaced elsewhere). Refresh
    // and retry exactly once, and only for that specific rejection — never
    // for an ordinary authorization 403, which a retry cannot fix.
    if (response.status === 403) {
      const error = await readError(response)
      if (error !== CSRF_REJECTED) {
        return { ok: false, status: 403, error }
      }
      forgetCsrfToken()
      response = await send(path, init)
    }

    if (!response.ok) {
      return { ok: false, status: response.status, error: await readError(response) }
    }

    if (response.status === 204) {
      return { ok: true, data: undefined as T }
    }

    const data = (await response.json()) as T
    return { ok: true, data }
  } catch {
    return { ok: false, status: 0, error: 'No se pudo contactar la plataforma.' }
  }
}

export async function devLogin(identityKey: string): Promise<ApiResult<Me>> {
  // A new session invalidates any token bound to the previous one. This is
  // also why dev-login itself carries no token: it establishes the session
  // a token could be bound to, so it cannot require one.
  forgetCsrfToken()
  const result = await request<Me>('/api/auth/dev-login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identity_key: identityKey }),
  })
  forgetCsrfToken()
  return result
}

export function getMe(): Promise<ApiResult<Me>> {
  return request<Me>('/api/auth/me')
}

export async function logout(): Promise<ApiResult<void>> {
  const result = await request<void>('/api/auth/logout', { method: 'POST' })
  forgetCsrfToken()
  return result
}

export function uploadFile(productKey: ProductKey, file: File): Promise<ApiResult<UploadResult>> {
  const formData = new FormData()
  formData.append('product_key', productKey)
  formData.append('file', file)
  return request<UploadResult>('/api/ingesta/upload', { method: 'POST', body: formData })
}

export function listJobs(): Promise<ApiResult<JobView[]>> {
  return request<JobView[]>('/api/ingesta/jobs')
}

export function retryJob(jobId: number): Promise<ApiResult<JobView>> {
  return request<JobView>(`/api/ingesta/jobs/${jobId}/retry`, { method: 'POST' })
}

export function getAuditLog(): Promise<ApiResult<AuditEventView[]>> {
  return request<AuditEventView[]>('/api/ingesta/audit')
}
