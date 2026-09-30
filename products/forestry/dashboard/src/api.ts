import type {
  ActivationResult,
  FeatureCollection,
  ForestryRole,
  ForestrySnapshot,
  Review,
  SnapshotSummary,
  SourceFeatureDetail,
  SourceFieldComparison,
  UploadResult,
  VersionsResponse,
} from './types.ts'

const API_BASE = '/api/forestry'

/** No Rodales version has been published yet (API 404 on /snapshots/published). */
export class NoSnapshotError extends Error {
  constructor() {
    super('no forestry snapshot is published')
    this.name = 'NoSnapshotError'
  }
}

/**
 * The API responded with an unexpected status (401, 403, 5xx, 404 on known
 * data, …). `detail` is the server's own Spanish, stakeholder-safe message
 * for mutations; `reason` its stable code, when it sent one.
 */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string | null
  readonly reason: string | null

  constructor(status: number, message: string, detail: string | null = null, reason: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.reason = reason
  }
}

async function getJson<T>(path: string): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw new ApiError(0, 'network unreachable')
  }

  if (!response.ok) {
    throw new ApiError(response.status, `request failed (${response.status})`)
  }

  return (await response.json()) as T
}

export async function fetchPublishedSnapshot(): Promise<ForestrySnapshot> {
  try {
    return await getJson<ForestrySnapshot>('/snapshots/published')
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      throw new NoSnapshotError()
    }
    throw error
  }
}

export function fetchSnapshotSummary(snapshotId: number): Promise<SnapshotSummary> {
  return getJson<SnapshotSummary>(`/snapshots/${snapshotId}`)
}

export function fetchFeatureCollection(snapshotId: number): Promise<FeatureCollection> {
  return getJson<FeatureCollection>(`/snapshots/${snapshotId}/feature-collection`)
}

export function fetchComparison(snapshotId: number): Promise<SourceFieldComparison> {
  return getJson<SourceFieldComparison>(`/snapshots/${snapshotId}/source-field-comparison`)
}

export function fetchFeatureDetail(
  snapshotId: number,
  featureOrdinal: number,
): Promise<SourceFeatureDetail> {
  return getJson<SourceFeatureDetail>(`/snapshots/${snapshotId}/features/${featureOrdinal}`)
}

/** No session (401): the viewer must sign in. */
export function isSignedOut(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}

/** Signed in, but without a Rodales (forestry) grant (403). */
export function isForbidden(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403
}

/** Development identities seeded by the platform API's dev sign-in. */
export const DEV_IDENTITIES = [
  { identityKey: 'dev-admin', label: 'Dev Admin (Rodales admin)' },
  { identityKey: 'dev-operator', label: 'Dev Operator (Rodales operador)' },
  { identityKey: 'dev-viewer', label: 'Dev Viewer (solo Transelec)' },
] as const

/**
 * Development-only sign-in (`POST /api/auth/dev-login`, mounted only when the
 * API runs with APP_ENV=development). Production signs in at the front door.
 */
export async function devLogin(identityKey: string): Promise<void> {
  const response = await fetch('/api/auth/dev-login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ identity_key: identityKey }),
  })

  if (!response.ok) {
    throw new ApiError(response.status, `dev sign-in failed (${response.status})`)
  }
}

// ---------------------------------------------------------------------------
// Upload → review → publish → restore
// ---------------------------------------------------------------------------

/** The caller's Rodales role, from the platform session (`/api/auth/me`). */
export async function fetchForestryRole(): Promise<ForestryRole | null> {
  let response: Response
  try {
    response = await fetch('/api/auth/me', { headers: { Accept: 'application/json' } })
  } catch {
    throw new ApiError(0, 'network unreachable')
  }
  if (!response.ok) {
    throw new ApiError(response.status, `request failed (${response.status})`)
  }
  const me = (await response.json()) as {
    product_grants: { product_key: string; role: string }[]
  }
  const grant = me.product_grants.find((entry) => entry.product_key === 'forestry')
  return (grant?.role as ForestryRole | undefined) ?? null
}

export function canUpload(role: ForestryRole | null): boolean {
  return role === 'admin' || role === 'operator'
}

export function fetchVersions(): Promise<VersionsResponse> {
  return getJson<VersionsResponse>('/versions')
}

export function fetchReview(snapshotId: number): Promise<Review> {
  return getJson<Review>(`/snapshots/${snapshotId}/review`)
}

// The CSRF token is bound to the session secret (apps/api/app/csrf.py) and
// held only in memory, never in storage or a cookie.
const CSRF_REJECTED = 'CSRF verification failed.'
let csrf: { token: string; header: string } | null = null

async function csrfHeader(): Promise<{ token: string; header: string }> {
  if (csrf !== null) return csrf
  const response = await fetch('/api/auth/csrf', { headers: { Accept: 'application/json' } })
  if (!response.ok) {
    throw new ApiError(response.status, `csrf token failed (${response.status})`)
  }
  const body = (await response.json()) as { csrf_token: string; header_name?: string }
  csrf = { token: body.csrf_token, header: body.header_name ?? 'X-CSRF-Token' }
  return csrf
}

/** Test hook: forget the cached CSRF token. */
export function resetCsrfForTests(): void {
  csrf = null
}

async function mutate<T>(path: string, init: RequestInit, retried = false): Promise<T> {
  const token = await csrfHeader()
  const headers = new Headers(init.headers)
  headers.set(token.header, token.token)
  headers.set('Accept', 'application/json')

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, method: 'POST', headers })
  } catch {
    throw new ApiError(0, 'network unreachable')
  }

  if (response.ok) {
    return (await response.json()) as T
  }

  let detail: string | null = null
  let reason: string | null = null
  try {
    const body = (await response.json()) as { detail?: unknown; reason?: unknown }
    detail = typeof body.detail === 'string' ? body.detail : null
    reason = typeof body.reason === 'string' ? body.reason : null
  } catch {
    // Not JSON (a proxy error page): keep the status only.
  }

  // A token minted for an earlier session: fetch a fresh one once.
  if (response.status === 403 && detail === CSRF_REJECTED && !retried) {
    csrf = null
    return mutate<T>(path, init, true)
  }

  throw new ApiError(response.status, `request failed (${response.status})`, detail, reason)
}

export function uploadShapefileZip(file: File): Promise<UploadResult> {
  const body = new FormData()
  body.append('file', file, file.name)
  return mutate<UploadResult>('/uploads', { body })
}

function activation(
  action: 'publish' | 'restore',
  snapshotId: number,
  expectedPublishedSnapshotId: number | null,
  acknowledgeReview: boolean,
): Promise<ActivationResult> {
  return mutate<ActivationResult>(`/snapshots/${snapshotId}/${action}`, {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      expected_published_snapshot_id: expectedPublishedSnapshotId,
      acknowledge_review: acknowledgeReview,
    }),
  })
}

export function publishSnapshot(
  snapshotId: number,
  expectedPublishedSnapshotId: number | null,
  acknowledgeReview: boolean,
): Promise<ActivationResult> {
  return activation('publish', snapshotId, expectedPublishedSnapshotId, acknowledgeReview)
}

export function restoreSnapshot(
  snapshotId: number,
  expectedPublishedSnapshotId: number | null,
): Promise<ActivationResult> {
  return activation('restore', snapshotId, expectedPublishedSnapshotId, false)
}

/** Spanish message for a failed mutation: the server's own when it sent one. */
export function mutationMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.detail !== null && error.status !== 0) {
      if (error.status === 401) return 'Su sesión expiró. Vuelva a iniciar sesión.'
      if (error.status === 403) return 'Su cuenta no tiene permiso para esta acción.'
      if (error.status === 413) return 'El archivo es demasiado grande.'
      return error.detail
    }
    if (error.status === 0) return 'No fue posible conectar con la plataforma. Reintente.'
    if (error.status === 413) return 'El archivo es demasiado grande.'
  }
  return fallback
}
