/**
 * Transelec dashboard API client.
 *
 * Every value this application renders comes from one of the real,
 * authenticated platform endpoints below. There is deliberately no fixture,
 * demo-data, or client-side workbook-parsing module in this product surface:
 * the ADR-008 synthetic demo app is a separate application in a separate
 * worktree, and TR-FUNC-040's in-browser XLSX reader is replaced end-to-end
 * by the upload -> validate -> publish pipeline (see `/transelec/importar`).
 *
 * Contracts are taken verbatim from the two backend task reports:
 *  - reads (summary/pmfs/pending/owner-status/report/export/imports)  — Task 4
 *  - mutations (uploads/validate-and-project/publish/restore) + CSRF  — Task 3
 *
 * Transport conventions, matching apps/portal/src/lib/platformApi.ts:
 *  - the browser only ever calls same-origin `/api/*`; the dev proxy (and the
 *    hosting rewrite in production) strips the prefix. No base URL, no CORS.
 *  - `credentials: 'include'` so the HttpOnly `campo_session` cookie rides.
 *  - nothing throws to the UI: failures come back as `{ ok: false }`.
 *  - the CSRF token is fetched at runtime from `GET /auth/csrf` and held only
 *    in memory. It is never compiled into this bundle and never read from a
 *    cookie; it is dropped whenever the session may have changed.
 */

// ---------------------------------------------------------------------------
// Result envelope
// ---------------------------------------------------------------------------

/**
 * `payload` carries the parsed JSON body of a failed response when it had
 * one. Only structured failures use it — today, the import layout review a
 * 422 from validate-and-project returns. `error` stays the display string.
 */
export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; payload?: unknown }

export const NETWORK_ERROR = 'No se pudo contactar la plataforma.'

// ---------------------------------------------------------------------------
// Session / identity
// ---------------------------------------------------------------------------

export type Role = 'admin' | 'operator' | 'viewer'

export interface ProductGrant {
  product_key: string
  role: Role
}

export interface Me {
  identity_key: string
  display_name: string
  product_grants: ProductGrant[]
}

// ---------------------------------------------------------------------------
// Read contracts — Task 4 report, section 2
// ---------------------------------------------------------------------------

export interface Bucket3WayCounts {
  aprobado: number
  en_tramite: number
  pendiente_o_tachado: number
}

export interface HeroStateCounts {
  aprobado: number
  en_tramite: number
  pendiente: number
  tachado: number
  sin_estado: number
}

/** One state of a breakdown, under the raw spelling the source used. */
export interface LabelledCount {
  label: string | null
  normalized: string | null
  count: number
}

export interface EmpresaBreakdown {
  empresa: string | null
  pmf_count: number
  estado_resumido: HeroStateCounts
}

/** One PMF the source gives more than one `Estado resumido`. */
export interface EstadoResumidoConflict {
  pmf: string
  valores: (string | null)[]
  canonico: string | null
  estado_detalle: string | null
  source_row_number: number
}

/**
 * Reforestation reference counts, with the definition attached.
 *
 * `propietarios` is a string, not a number, and deliberately so: the source
 * has no owner field, so there is no owner count to render — and a zero here
 * would read as "there are no owners" rather than "we cannot know".
 */
export interface Reforestacion {
  definicion: string
  predio_ref_labels: string[]
  predio_ref_count: number
  rol_ref_count: number
  sentinel_label: string
  sentinel_row_count: number
  etiquetas_compuestas: string[]
  propietarios: string
}

export interface TranselecSummary {
  import_id: number
  row_count: number
  pmf_count: number
  predio_count: number
  rol_count: number
  surface_total: number
  basis_estado_resumido: string
  aprobados_pmf_count: number
  en_tramite_pmf_count: number
  basis_pending_priority: string
  pendientes_prioritarios_pmf_count: number
  con_servidumbre_predio_count: number
  avance_por_predio: Bucket3WayCounts
  avance_por_pmf: Bucket3WayCounts
  estado_resumido_hero_predio: HeroStateCounts
  estado_resumido_pmf: HeroStateCounts
  estado_detalle_pmf: LabelledCount[]
  /** Hero-state key -> the literal `Estado resumido` spellings behind it. */
  estado_resumido_valores: Record<string, string[]>
  por_empresa: EmpresaBreakdown[]
  reforestacion: Reforestacion
  predios_reforestacion: string[]
  calidad_filas_sin_id_predial_unico: number
  calidad_pmf_sin_numero_ingreso: number
  calidad_numero_resolucion: string
  calidad_pmf_estado_resumido_conflictivo: EstadoResumidoConflict[]
}

/**
 * Chronology inconsistencies the API found between one row's AEF dates.
 * Reported as found: the dates themselves are never corrected.
 */
export type ChronologyFlag =
  | 'cronologia_corta_antes_de_solicitud'
  | 'cronologia_termino_antes_de_corta'
  | 'cronologia_termino_antes_de_solicitud'

export type TextDateResolution =
  | 'parsed_spanish_long'
  | 'multiple_dates'
  | 'placeholder'
  | 'unrecognized'

/**
 * Raw text found in a date column. `parsed` is set only when the whole cell
 * was one written-out Spanish date; otherwise the row has no date for that
 * field and `raw` is the only record of what the workbook said.
 */
export interface SourceTextDate {
  raw: string
  resolution: TextDateResolution
  parsed: string | null
}

/**
 * Every contract field (the 30 V1 fields plus the five V2 AEF tracking
 * fields) and the derived/technical columns. Values are the row's own: a
 * blank on one row never inherits a sibling row's value (PMF-level AEF
 * values are resolved separately, in `TranselecAef.pmfs`).
 */
export interface ResumenRow {
  source_row_number: number
  predio_ref: string | null
  rol_ref: string | null
  area_ref: string | null
  pmf: string
  carpeta_source: string | null
  carpeta_normalizada: string | null
  pas: string | null
  estado: string | null
  estado_resumido: string | null
  tipo_rechazo: string | null
  reingreso_tec: string | null
  reingreso_legal: string | null
  reingreso_recrep: string | null
  tipo_propietario: string | null
  id_transelec: string | null
  rol: string | null
  numero_predio: string | null
  numero_area_corta: string | null
  superficie_corta: number | null
  superficie_total_corta: number | null
  fecha_ingreso: string | null
  numero_ingreso: string | null
  fecha_90_dias: string | null
  hoy_raw: string | null
  empresa: string | null
  id_predio_unico_ii: string | null
  id_pmf: string | null
  id_predio_unico: string | null
  predio_group_key: string
  tramite: string | null
  sector: string | null
  aef: string | null
  quien_solicita: string | null
  fecha_solicitud: string | null
  fecha_corta: string | null
  fecha_termino: string | null
  chronology_flags: ChronologyFlag[]
  /** Per date field whose cell held text; absent or `{}` when none did. */
  source_text_dates?: Record<string, SourceTextDate>
}

export interface TranselecRowsPage {
  items: ResumenRow[]
  next_cursor: string | null
  has_more: boolean
  total_count: number
}

export interface TranselecPmfDetail {
  pmf: string
  row_count: number
  basis_estado_resumido: string
  estado_resumido: string | null
  rows: ResumenRow[]
}

export type PendingStage = 'preparacion' | 'recurso_rechazo' | 'otros'

export interface PendingStageCounts {
  preparacion: number
  recurso_rechazo: number
  otros: number
}

export type PendingRow = ResumenRow & { pending_stage: PendingStage }

export interface TranselecPending {
  basis: string
  pending_pmf_count: number
  total_pmf_count: number
  pending_pmf_percentage: number
  stage_basis: string
  stages: PendingStageCounts
  rows: PendingRow[]
}

export interface OwnerStatusRow {
  tipo_propietario: string | null
  owner_stage: string | null
  predio_count: number
}

export interface TranselecOwnerStatus {
  basis: string
  total_predio_count: number
  rows: OwnerStatusRow[]
}

export interface TranselecReport {
  generated_at: string
  basis_estado_resumido: string
  basis_pending_priority: string
  text: string
}

export interface TranselecImportHistoryRow {
  publish_event_id: number
  import_id: number
  event_type: 'publish' | 'restore'
  occurred_at: string
  actor_app_user_id: number
  actor_display_name: string | null
  filename: string | null
  sha256: string
  business_rows: number
  distinct_pmf: number
  distinct_provisional_predio_ids: number
  surface_total: number
  is_active: boolean
}

export interface TranselecActiveImport {
  import_id: number
  sha256: string
  byte_size: number
  filename: string | null
  schema_contract_version: string
  parser_version: string
  business_rows: number
  distinct_pmf: number
  distinct_provisional_predio_ids: number
  surface_total: number
  validated_at: string
  published_event_type: 'publish' | 'restore'
  published_at: string
  published_by_app_user_id: number
  published_by_display_name: string | null
  warning_count: number
  /**
   * Contract fields the published workbook actually had a column for. A
   * field missing here is "not in this version's source", which the UI must
   * not present as "blank in these rows".
   */
  source_fields: string[]
}

export interface LabelCount {
  label: string | null
  count: number
}

export interface AefValueVariant {
  value: string
  source_rows: number[]
}

/**
 * One tracking field resolved for a PMF from the rows that carry it.
 * `value`: all non-blank rows agree and `source_rows` supplied it.
 * `blank`: no row has a value. `conflict`: rows disagree — no value is
 * chosen, and `variants` lists each one with its rows.
 */
export interface AefPmfField {
  status: 'value' | 'blank' | 'conflict'
  value: string | null
  /** `raw_text`: text from a date column that was not read as a date. */
  value_kind: 'text' | 'date' | 'raw_text' | null
  source_rows: number[]
  variants: AefValueVariant[]
}

export interface AefPmf {
  pmf: string
  total_rows: number
  rows_with_any_tracking: number
  rows_with_aef: number
  source_row_numbers: number[]
  has_conflict: boolean
  chronology_flags: ChronologyFlag[]
  fields: Record<'aef' | 'quien_solicita' | 'fecha_solicitud' | 'fecha_corta' | 'fecha_termino', AefPmfField>
}

export interface TranselecAef {
  basis: 'pmf_from_source_rows'
  source_fields: string[]
  row_count: number
  pmf_count: number
  rows_with_any_tracking: number
  rows_with_aef: number
  rows_with_quien_solicita: number
  rows_with_fecha_solicitud: number
  rows_with_fecha_corta: number
  rows_with_fecha_termino: number
  rows_with_chronology_warning: number
  pmf_with_tracking: number
  pmf_with_aef: number
  pmf_with_conflict: number
  pmf_conflicts_by_field: Record<string, number>
  pmf_with_chronology_warning: number
  por_aef: LabelCount[]
  por_solicitante: LabelCount[]
  pmf_por_aef: LabelCount[]
  pmf_por_solicitante: LabelCount[]
  /** PMF with any tracking value, in source order; values use all their rows. */
  pmfs: AefPmf[]
  /** Row-level detail: the in-scope rows that carry a tracking value. */
  rows: ResumenRow[]
}

// ---------------------------------------------------------------------------
// Import layout review — contract V2 (transelec_ingestion.resumen_layout)
// ---------------------------------------------------------------------------

export type LayoutSeverity = 'error' | 'warning' | 'info'

export interface LayoutIssue {
  code: string
  severity: LayoutSeverity
  /** Spanish, structural: headers, column letters, row numbers, counts. */
  message: string
  field: string | null
  columns: string[]
  /** Worksheet row numbers, capped; `row_count` is the true total. */
  rows: number[]
  row_count: number
}

export type LayoutColumnStatus =
  | 'mapped'
  | 'duplicate_ignored'
  | 'unrecognized_ignored'
  | 'unlabeled_data_ignored'
  | 'separator'

export interface LayoutColumn {
  column: string
  header: string | null
  status: LayoutColumnStatus
  field: string | null
  note: string | null
}

export interface LayoutField {
  field: string
  header: string
  tier: 'identity' | 'required' | 'expected' | 'optional'
  column: string | null
  filled_rows: number
}

export interface LayoutReport {
  parser_version: string
  sheet_name: string
  header_row: number | null
  business_rows: number
  columns: LayoutColumn[]
  fields: LayoutField[]
  auxiliary_regions: {
    first_column: string
    last_column: string
    column_count: number
    reason: string
  }[]
  issues: LayoutIssue[]
  counts: Record<LayoutSeverity, number>
}

export interface TranselecImportReport {
  import_id: number
  schema_contract_version: string
  parser_version: string
  validated_at: string
  warning_count: number
  source_fields: string[]
  mapping_report: LayoutReport | null
}

/** The layout report a refused validate-and-project (422) carries, if any. */
export function layoutReportFromFailure(payload: unknown): LayoutReport | null {
  if (typeof payload !== 'object' || payload === null) return null
  const report = (payload as { report?: unknown }).report
  if (typeof report !== 'object' || report === null) return null
  return Array.isArray((report as LayoutReport).issues) ? (report as LayoutReport) : null
}

export interface TranselecRecentRun {
  ingestion_run_id: number
  source_snapshot_id: number
  filename: string | null
  sha256: string
  requested_by_app_user_id: number
  created_at: string
  import_id: number | null
  is_active: boolean
}

// ---------------------------------------------------------------------------
// Mutation contracts — Task 3 report, section 2
// ---------------------------------------------------------------------------

export interface UploadResult {
  source_snapshot_id: number
  sha256: string
  byte_size: number
  validation_evidence: Record<string, unknown>
  job_id: number
}

export type ValidateStatus = 'validated' | 'already_imported' | 'already_current'

export interface ValidateAndProjectResult {
  status: ValidateStatus
  import_id: number
  source_snapshot_id: number
  ingestion_run_id: number
  schema_contract_version: string
  parser_version: string
  business_rows: number
  distinct_pmf: number
  distinct_provisional_predio_ids: number
  surface_total: number
  validated_at: string
  is_active: boolean
  warning_count: number
  /** Null only for an import validated under contract V1 (no report kept). */
  mapping_report: LayoutReport | null
}

export interface ActivationResult {
  status: 'published' | 'restored'
  event_type: 'publish' | 'restore'
  import_id: number
  previous_import_id: number | null
  publish_event_id: number
  occurred_at: string
  active_import_id: number
}

// ---------------------------------------------------------------------------
// Filters — TR-FUNC-017-022. One shared contract for every read endpoint, so
// KPIs, charts, hero and tables can never disagree under a filter state.
// ---------------------------------------------------------------------------

export interface TranselecFilterState {
  q: string
  estado_resumido: string[]
  empresa: string[]
  pas: string[]
  sector: string[]
  tipo_propietario: string[]
  aef: string[]
  quien_solicita: string[]
}

export const EMPTY_FILTERS: TranselecFilterState = {
  q: '',
  estado_resumido: [],
  empresa: [],
  pas: [],
  sector: [],
  tipo_propietario: [],
  aef: [],
  quien_solicita: [],
}

export const MULTISELECT_FIELDS = [
  'estado_resumido',
  'empresa',
  'pas',
  'sector',
  'tipo_propietario',
  'aef',
  'quien_solicita',
] as const

export type MultiselectField = (typeof MULTISELECT_FIELDS)[number]

export function filtersActive(filters: TranselecFilterState): boolean {
  return (
    filters.q.trim() !== '' ||
    MULTISELECT_FIELDS.some((field) => filters[field].length > 0)
  )
}

/** Serialize a filter state into the API's repeated-query-param contract. */
export function filterParams(filters: TranselecFilterState): URLSearchParams {
  const params = new URLSearchParams()
  const q = filters.q.trim()
  if (q) params.set('q', q)
  for (const field of MULTISELECT_FIELDS) {
    for (const value of filters[field]) params.append(field, value)
  }
  return params
}

function withParams(path: string, params: URLSearchParams): string {
  const query = params.toString()
  return query ? `${path}?${query}` : path
}

// ---------------------------------------------------------------------------
// Transport
// ---------------------------------------------------------------------------

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
const CSRF_REJECTED = 'CSRF verification failed.'
const DEFAULT_CSRF_HEADER = 'X-CSRF-Token'

interface CsrfToken {
  token: string
  headerName: string
}

let csrfToken: CsrfToken | null = null

/**
 * The most recent `Date` response header observed from the platform API.
 *
 * TR-FUNC-031's one mechanical bug fix needs a reference "today" that
 * actually advances, and the source-ingestion rule is that observation time
 * is platform infrastructure, never workbook data. The read API exposes no
 * "server now" endpoint, but every response carries the server's own `Date`
 * header — that is the reference this app uses, so "today" is the API
 * process's clock rather than the viewer's. Null until the first response.
 */
let serverClock: Date | null = null

export function observedServerNow(): Date | null {
  return serverClock
}

/** Test seam: reset the module's cached session/clock observations. */
export function resetApiClientState(): void {
  csrfToken = null
  serverClock = null
}

function rememberServerClock(response: Response): void {
  const header = response.headers.get('date')
  if (!header) return
  const parsed = new Date(header)
  if (!Number.isNaN(parsed.getTime())) serverClock = parsed
}

async function fetchCsrfToken(): Promise<CsrfToken | null> {
  try {
    const response = await fetch('/api/auth/csrf', { credentials: 'include' })
    rememberServerClock(response)
    if (!response.ok) return null
    const body = (await response.json()) as { csrf_token?: string; header_name?: string }
    if (!body.csrf_token) return null
    return { token: body.csrf_token, headerName: body.header_name ?? DEFAULT_CSRF_HEADER }
  } catch {
    return null
  }
}

async function ensureCsrfToken(): Promise<CsrfToken | null> {
  if (csrfToken !== null) return csrfToken
  csrfToken = await fetchCsrfToken()
  return csrfToken
}

function forgetCsrfToken(): void {
  csrfToken = null
}

async function send(path: string, init: RequestInit | undefined): Promise<Response> {
  const method = (init?.method ?? 'GET').toUpperCase()
  if (SAFE_METHODS.has(method)) {
    const response = await fetch(path, { credentials: 'include', ...init })
    rememberServerClock(response)
    return response
  }

  const token = await ensureCsrfToken()
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) }
  if (token !== null) headers[token.headerName] = token.token

  const response = await fetch(path, { credentials: 'include', ...init, headers })
  rememberServerClock(response)
  return response
}

async function readError(response: Response): Promise<string> {
  return (await readFailure(response)).error
}

async function readFailure(response: Response): Promise<{ error: string; payload?: unknown }> {
  const fallback = response.statusText || `HTTP ${response.status}`
  try {
    const body = (await response.json()) as { detail?: unknown }
    const error = typeof body.detail === 'string' && body.detail ? body.detail : fallback
    return { error, payload: body }
  } catch {
    // no JSON body on this error response; fall back to the status text
    return { error: fallback }
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    let response = await send(path, init)

    // A cached token can go stale when the session is replaced elsewhere.
    // Refresh and retry exactly once, and only for that specific rejection —
    // an ordinary authorization 403 is not fixable by retrying.
    if (response.status === 403) {
      const error = await readError(response)
      if (error !== CSRF_REJECTED) return { ok: false, status: 403, error }
      forgetCsrfToken()
      response = await send(path, init)
    }

    if (!response.ok) {
      const failure = await readFailure(response)
      return failure.payload === undefined
        ? { ok: false, status: response.status, error: failure.error }
        : { ok: false, status: response.status, error: failure.error, payload: failure.payload }
    }

    if (response.status === 204) return { ok: true, data: undefined as T }

    const data = (await response.json()) as T
    return { ok: true, data }
  } catch {
    return { ok: false, status: 0, error: NETWORK_ERROR }
  }
}

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

export function getMe(): Promise<ApiResult<Me>> {
  return request<Me>('/api/auth/me')
}

export function transelecRole(me: Me | null): Role | null {
  if (!me) return null
  const grant = me.product_grants.find((entry) => entry.product_key === 'transelect')
  return grant ? grant.role : null
}

/** ADMIN gate for the access pane (server re-enforces MANAGE_ACCESS). */
export function isTranselecAdmin(me: Me | null): boolean {
  return transelecRole(me) === 'admin'
}

/** OPERATOR/ADMIN gate for the import and version pages (server re-enforces). */
export function canPublish(me: Me | null): boolean {
  const role = transelecRole(me)
  return role === 'admin' || role === 'operator'
}

// ---------------------------------------------------------------------------
// Sign-in / sign-out
//
// No new authentication mechanism lives here. These are thin typed wrappers
// over the endpoints the platform already exposes, with exactly the
// semantics apps/portal/src/lib/platformApi.ts already established:
//
//  - POST /auth/dev-login   mounted ONLY under APP_ENV=development
//                           (apps/api/app/main.py), and its handler re-checks
//                           via app.dev_auth.assert_dev_auth_allowed. Outside
//                           development the route does not exist at all, so
//                           this call 404s — it cannot be talked into working.
//  - POST /auth/logout      mounted everywhere; ends whichever kind of
//                           session the caller has (app/routers/session.py).
//  - GET  /auth/google/login mounted everywhere; Transelec's own identity
//                           provider and the only way to authenticate here
//                           outside development (ADR-010). Microsoft Entra
//                           (/auth/entra/login) remains mounted for the other
//                           products, and this bundle deliberately does not
//                           reach it.
//
// Nothing here writes a token, secret or identity to localStorage,
// sessionStorage or a readable cookie: the session stays in the HttpOnly
// `campo_session` cookie the API sets, and the CSRF token stays in this
// module's memory, exactly as documented at the top of this file.
// ---------------------------------------------------------------------------

/**
 * The seeded local identities `devLogin` will accept.
 *
 * Deliberately a TYPE, not a runtime constant: TypeScript erases it, so
 * these two strings exist nowhere in a compiled bundle. The values live in
 * `components/DemoSignIn.tsx`, the one module a `vite build` drops entirely
 * (see the note there), which is what keeps `dev-admin` and `dev-viewer` out
 * of every deployed artifact rather than merely unused within one.
 *
 * A subset of app.dev_auth.SEEDED_DEV_IDENTITIES: `dev-operator` holds no
 * Transelec grant (its default seed is forestry only), so offering it here
 * would hand a demo viewer a 403 wall rather than a product.
 */
export type DemoIdentityKey = 'dev-admin' | 'dev-viewer'

/** Top-level navigation target for Google Workspace sign-in. */
export const GOOGLE_LOGIN_PATH = '/api/auth/google/login'

/**
 * Start a local development session for one seeded identity.
 *
 * The CSRF token is dropped on both sides of the call: the token is keyed by
 * the session secret (app/csrf.py), so one minted before this call cannot
 * verify after it, and a token minted for a previous session must not leak
 * into the new one.
 */
export async function devLogin(identityKey: DemoIdentityKey): Promise<ApiResult<Me>> {
  forgetCsrfToken()
  const result = await request<Me>('/api/auth/dev-login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identity_key: identityKey }),
  })
  forgetCsrfToken()
  return result
}

/** End the current session (server-side and cookie), whatever created it. */
export async function logout(): Promise<ApiResult<void>> {
  const result = await request<void>('/api/auth/logout', { method: 'POST' })
  forgetCsrfToken()
  return result
}

/**
 * Ask whether Google Workspace sign-in is actually configured, without
 * following the redirect to Google.
 *
 * The same shape of probe the platform's Entra sign-in uses, against the
 * Transelec product's own provider: `GET /auth/google/login` answers either a 302
 * towards Google (configured) or a 503 (`GOOGLE_CLIENT_ID` /
 * `GOOGLE_CLIENT_SECRET` or the token encryption key unset — see
 * app/main.py's GoogleNotConfiguredError handler and
 * app/routers/google_auth.py's _require_encryption_key). `redirect:
 * 'manual'` surfaces the redirect as an opaque response instead of
 * following it cross-origin to Google, where the absence of CORS would turn
 * every outcome into an indistinguishable network error.
 *
 * The probe's 302 mints a PKCE/state/nonce flow this app then abandons; the
 * subsequent top-level navigation mints a fresh one and overwrites the
 * short-lived `google_login_flow` cookie, so no half-finished flow is left
 * usable. This never authenticates anyone by itself, and it never sees a
 * Google token: the browser is given a session cookie and nothing else.
 */
export async function checkGoogleSignIn(): Promise<ApiResult<void>> {
  try {
    const response = await fetch(GOOGLE_LOGIN_PATH, {
      credentials: 'include',
      redirect: 'manual',
    })
    if (response.type === 'opaqueredirect' || response.ok) return { ok: true, data: undefined }
    return { ok: false, status: response.status, error: await readError(response) }
  } catch {
    return { ok: false, status: 0, error: NETWORK_ERROR }
  }
}

// ---------------------------------------------------------------------------
// Reads
// ---------------------------------------------------------------------------

export function getSummary(filters: TranselecFilterState): Promise<ApiResult<TranselecSummary>> {
  return request<TranselecSummary>(withParams('/api/transelec/summary', filterParams(filters)))
}

export function listRows(
  filters: TranselecFilterState,
  options: { cursor?: string | null; limit?: number } = {},
): Promise<ApiResult<TranselecRowsPage>> {
  const params = filterParams(filters)
  if (options.cursor) params.set('cursor', options.cursor)
  if (options.limit) params.set('limit', String(options.limit))
  return request<TranselecRowsPage>(withParams('/api/transelec/pmfs', params))
}

export function getPmfDetail(pmf: string): Promise<ApiResult<TranselecPmfDetail>> {
  return request<TranselecPmfDetail>(`/api/transelec/pmfs/${encodeURIComponent(pmf)}`)
}

export function getPending(filters: TranselecFilterState): Promise<ApiResult<TranselecPending>> {
  return request<TranselecPending>(withParams('/api/transelec/pending', filterParams(filters)))
}

export function getOwnerStatus(
  filters: TranselecFilterState,
): Promise<ApiResult<TranselecOwnerStatus>> {
  return request<TranselecOwnerStatus>(
    withParams('/api/transelec/owner-status', filterParams(filters)),
  )
}

export function getReport(filters: TranselecFilterState): Promise<ApiResult<TranselecReport>> {
  return request<TranselecReport>(withParams('/api/transelec/report', filterParams(filters)))
}

export function getAef(filters: TranselecFilterState): Promise<ApiResult<TranselecAef>> {
  return request<TranselecAef>(withParams('/api/transelec/aef', filterParams(filters)))
}

export function getImportReport(importId: number): Promise<ApiResult<TranselecImportReport>> {
  return request<TranselecImportReport>(`/api/transelec/imports/${importId}/report`)
}

export function getActiveImport(): Promise<ApiResult<TranselecActiveImport>> {
  return request<TranselecActiveImport>('/api/transelec/imports/active')
}

export function listImportHistory(): Promise<ApiResult<TranselecImportHistoryRow[]>> {
  return request<TranselecImportHistoryRow[]>('/api/transelec/imports')
}

export function listRecentUploads(limit = 20): Promise<ApiResult<TranselecRecentRun[]>> {
  return request<TranselecRecentRun[]>(`/api/transelec/uploads/recent?limit=${limit}`)
}

/**
 * The CSV export URL for the current filter state (TR-FUNC-037).
 *
 * Export is a backend endpoint: the 18-column field set, the `;` delimiter,
 * the UTF-8 BOM, the always-blank reserved column and the formula-injection
 * hardening all live server-side, and the response already carries
 * `Content-Type: text/csv; charset=utf-8` plus an attachment
 * `Content-Disposition`. This app only navigates to that URL — it never
 * assembles CSV text from workbook-derived values itself.
 */
export function exportCsvUrl(filters: TranselecFilterState): string {
  return withParams('/api/transelec/export.csv', filterParams(filters))
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export function uploadWorkbook(file: File): Promise<ApiResult<UploadResult>> {
  const formData = new FormData()
  // `product_key` is fixed to `transelect` server-side and is deliberately
  // not sent by this client (Task 3 report, section 2.1).
  formData.append('file', file)
  return request<UploadResult>('/api/transelec/uploads', { method: 'POST', body: formData })
}

export function validateAndProject(
  ingestionRunId: number,
): Promise<ApiResult<ValidateAndProjectResult>> {
  return request<ValidateAndProjectResult>(
    `/api/transelec/imports/${ingestionRunId}/validate-and-project`,
    { method: 'POST' },
  )
}

/**
 * Publish an import. `acknowledgeWarnings` states the operator reviewed the
 * import's layout warnings; the server refuses (409) to publish an import
 * with warnings without it.
 */
export function publishImport(
  importId: number,
  options: { acknowledgeWarnings?: boolean } = {},
): Promise<ApiResult<ActivationResult>> {
  const query = options.acknowledgeWarnings ? '?acknowledge_warnings=true' : ''
  return request<ActivationResult>(`/api/transelec/imports/${importId}/publish${query}`, {
    method: 'POST',
  })
}

export function restoreImport(importId: number): Promise<ApiResult<ActivationResult>> {
  return request<ActivationResult>(`/api/transelec/imports/${importId}/restore`, { method: 'POST' })
}

// ---------------------------------------------------------------------------
// Access administration (admin only)
//
// Thin wrappers over app.routers.access_admin, fixed to the `transelect`
// product. The server requires Action.MANAGE_ACCESS (ADMIN) on both routes
// and a CSRF token on the grant; a grant only resolves for an address that
// has already signed in once.
// ---------------------------------------------------------------------------

export interface ProductGrantee {
  app_user_id: number
  email: string | null
  display_name: string
  role: Role
}

/** Roles this dashboard may hand out. ADMIN stays a deliberate, out-of-band act. */
export type GrantableRole = 'viewer' | 'operator'

export function listTranselecGrants(): Promise<ApiResult<ProductGrantee[]>> {
  return request<ProductGrantee[]>('/api/auth/admin/product-grants/transelect')
}

export function grantTranselecRole(
  email: string,
  role: GrantableRole,
): Promise<ApiResult<ProductGrantee>> {
  return request<ProductGrantee>('/api/auth/admin/product-grants/transelect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email.trim().toLowerCase(), role }),
  })
}
