# Hosted Product Composition + Portal UX V1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Campo Digital portal explicitly LOCAL/STAGING-aware, add `/archivos` as a first-class nav entry, and host the LiDAR product frontend on Render at $0 with a genuinely empty (not fake, not real-client) evidence state — while Forestry and Transelec show an honest "not yet hosted" state instead of a fake green status.

**Architecture:** The portal already resolves module status/URLs at runtime from a `CampoRuntimeConfig`, currently always sourced from a gitignored, launcher-written `campo-runtime.json` (LOCAL semantics only). We add a second, purely build-time-derived source for STAGING (no fetch, no dynamic file — everything Render needs is baked into the Vite build via `VITE_*` env vars we control), tagged with an explicit `environment: 'local' | 'staging'` field that every consumer (`StatusBadge`, `Estado`, `Module`) branches on for copy. LiDAR becomes hosted by deploying its existing, unmodified dashboard as a new Render static site that talks to the *already-deployed* shared platform API (`apps/api/app/routers/lidar.py`, no DB dependency, already fails safe to `[]` with no `CAMPO_LIDAR_OUTPUT_ROOT` configured) — zero new backend code, zero new Render cost. Forestry and Transelec stay un-hosted this slice; their `/archivos`-adjacent capability and `/modulo/*` pages say so honestly instead of showing "Demo no iniciada" (a local-only phrase that would be misleading on a public URL).

**Tech Stack:** React 19 + TypeScript + Vite + Vitest (portal, unchanged), FastAPI (unchanged, no backend code touched), Render Blueprint (`render.yaml`).

**Spec:** This plan is self-originated from the task brief "HOSTED PRODUCT COMPOSITION + PORTAL UX V1" (delivered directly in conversation, not a separate spec file) plus the repository's own architecture (`docs/platform/company-portal-v1.md`, `docs/adr/ADR-005-render-staging-experiment.md`, `docs/adr/ADR-006-restrict-dev-auth-to-development.md`).

## Global Constraints

- Do not push, do not deploy. `render blueprints validate` may be run locally; nothing is applied.
- Do not implement Entra/Graph. Do not weaken `assert_dev_auth_allowed`, the dev-auth router-mount gate (`APP_ENV == "development"` only), `ENABLE_ONEDRIVE_IMPORT=false`, `STAGING_EXECUTION_MAX_BYTES`, or any product RBAC check in `app.access`.
- No real LAS/LAZ/XLSX/ZIP/client datasets committed or deployed. LiDAR ships with **zero** synthetic fixture data — the existing safe-empty API response (`GET /runs` → `[]`) is the hosted state, per the task's explicit preference for "empty" over "copy the private local report store."
- Do not merge the `feat/forestry-dashboard-v1` or `feat/transelec-hosted-pilot-v1` branches, and do not build a new synthetic Forestry/Transelec dataset in this slice — see Task 0 rationale below. Their `/modulo/*` pages must show an honest not-yet-hosted state, not a fake green card.
- Preserve `make campo-demo` / local iframe composition exactly as-is: every LOCAL-environment code path (i.e. `VITE_CAMPO_ENV` unset) must produce byte-identical copy/behavior to what exists today, verified by every pre-existing test continuing to pass unmodified.
- `apps/portal` build is `tsc -b && vite build`; test is `vitest run`; lint is `oxlint`. `products/lidar/dashboard` build is the same `tsc -b && vite build` pattern, untouched by this plan.
- Render free-tier static sites: no `plan` field, no region field (matches the existing `campo-digital-portal-staging` service in `render.yaml`).

---

## Task 0: Classification record (no code — context for every later task)

This task produces no files; it fixes the classification this plan's later tasks implement, so a reviewer can check Task 1+ against it.

**LiDAR — B (small integration/composition work, not blocked).** `apps/api/app/routers/lidar.py` has no DB dependency (`app.main.py:86` mounts it unconditionally, before any DB-gated route) and `get_output_root()` (`lidar.py:26-38` → `lidar_io.output_root_discovery.resolve_report_root`) already resolves to `SOURCE_NONE` → `[]` on a fresh Render checkout (no sibling worktrees, no `CAMPO_LIDAR_OUTPUT_ROOT` set). The dashboard (`products/lidar/dashboard/src/App.tsx:794-803`) already renders a clean "No hay medición seleccionada" empty state when `runs.length === 0`, and the only real-photo asset (`App.tsx:905-920`, `/local-demo/field-reference.jpeg`) is inside the `{run && (...)}` block (`App.tsx:805`), which never renders when there is no run. **No product code changes are needed** — only new deployment composition (Task 6) and portal wiring (Tasks 1-5).

**Forestry — B on paper, deferred honest-C this slice.** The dashboard (worktree `campo-digital-forestry-dashboard-v1`) has zero static/offline data path (`src/api.ts` always calls `/api/forestry/*`) and would need a hand-built synthetic `FeatureCollection`/`SnapshotSummary` matching `src/types.ts` plus a new static-data branch in `api.ts` — real, scoped work, but it means *inventing* forestry polygon geometry for public display, which risks exactly the "speculative business semantics" and data-fabrication the task brief warns against, and it lives on a branch this slice does not merge. Real Degenfeld data is confirmed never committed to git (only local Postgres, sourced from an external, gitignored ZIP via `CAMPO_DIGITAL_SOURCE_ROOT`), so there is no leak risk either way — the honest answer for *this* slice is "not yet hosted," not a fabricated demo.

**Transelec — C (architecturally blocked as designed).** The hosted-pilot branch's `/api/transelec/*` routes require a live Postgres + object store even to serve their degraded/error state (`apps/api/app/routers/transelec.py`, ~10 `503` call sites depend on `get_database_engine`); Render's $0 tier has no free persistent Postgres beyond the one already-provisioned staging DB, and that branch's own deployment runbook (`products/transelect/docs/deployment.md:141,165,197`) was explicitly designed for **IAP-gated, non-public** access, not open staging. A public $0 deployment would require extracting the UI and replacing the live API with a from-scratch fabricated dataset — out of scope here for the same data-fabrication reason as Forestry.

**Decision:** implement LiDAR hosting (Task 6) plus portal LOCAL/STAGING awareness (Tasks 1-5, 7-13) plus Render composition (Task 6/14); leave Forestry and Transelec honestly "not yet hosted" in STAGING via the same environment-aware copy paths (Tasks 7, 9, 11) with **no new code specific to either product**.

---

## Task 1: Environment detection

**Files:**
- Create: `apps/portal/src/runtime/environment.ts`
- Test: `apps/portal/src/runtime/environment.test.ts`

**Interfaces:**
- Produces: `export type CampoEnvironment = 'local' | 'staging'`, `export function getCampoEnvironment(): CampoEnvironment`

- [ ] **Step 1: Write the failing test**

```ts
// apps/portal/src/runtime/environment.test.ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getCampoEnvironment } from './environment'

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('getCampoEnvironment', () => {
  it('defaults to local when VITE_CAMPO_ENV is unset', () => {
    expect(getCampoEnvironment()).toBe('local')
  })

  it('returns staging only for the exact value "staging"', () => {
    vi.stubEnv('VITE_CAMPO_ENV', 'staging')
    expect(getCampoEnvironment()).toBe('staging')
  })

  it('treats any other value as local rather than trusting it', () => {
    vi.stubEnv('VITE_CAMPO_ENV', 'production')
    expect(getCampoEnvironment()).toBe('local')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/runtime/environment.test.ts`
Expected: FAIL — `./environment` has no exported member `getCampoEnvironment` (module doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

```ts
// apps/portal/src/runtime/environment.ts
/**
 * Compiled in at Vite build time from VITE_CAMPO_ENV (see render.yaml for the
 * STAGING build's value). Never fetched at runtime, so this is trustworthy
 * even though CampoRuntimeConfig's *contents* (module URLs) are not.
 */
export type CampoEnvironment = 'local' | 'staging'

export function getCampoEnvironment(): CampoEnvironment {
  return import.meta.env.VITE_CAMPO_ENV === 'staging' ? 'staging' : 'local'
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/runtime/environment.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/runtime/environment.ts apps/portal/src/runtime/environment.test.ts
git commit -m "feat(portal): add build-time LOCAL/STAGING environment detection

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 2: Hosted module URL registry

**Files:**
- Create: `apps/portal/src/runtime/hostedModules.ts`
- Test: `apps/portal/src/runtime/hostedModules.test.ts`

**Interfaces:**
- Consumes: `ModuleId` from `./runtimeConfig` (existing: `'lidar' | 'forestal' | 'transelec'`)
- Produces: `export function hostedModuleUrls(): Partial<Record<ModuleId, string>>`

- [ ] **Step 1: Write the failing test**

```ts
// apps/portal/src/runtime/hostedModules.test.ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { hostedModuleUrls } from './hostedModules'

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('hostedModuleUrls', () => {
  it('includes lidar only when VITE_LIDAR_HOSTED_URL is set', () => {
    expect(hostedModuleUrls()).toEqual({})

    vi.stubEnv('VITE_LIDAR_HOSTED_URL', 'https://campo-digital-lidar-staging.onrender.com')
    expect(hostedModuleUrls()).toEqual({
      lidar: 'https://campo-digital-lidar-staging.onrender.com',
    })
  })

  it('never includes forestal or transelec (no hosted build exists this slice)', () => {
    vi.stubEnv('VITE_LIDAR_HOSTED_URL', 'https://campo-digital-lidar-staging.onrender.com')
    const urls = hostedModuleUrls()
    expect(urls.forestal).toBeUndefined()
    expect(urls.transelec).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/runtime/hostedModules.test.ts`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write minimal implementation**

```ts
// apps/portal/src/runtime/hostedModules.ts
import type { ModuleId } from './runtimeConfig'

/**
 * The closed set of STAGING module URLs this build knows about, baked in at
 * build time via render.yaml envVars. Forestry and Transelec have no hosted
 * build this slice (see docs/adr/ADR-007-hosted-product-composition-v1.md)
 * and are deliberately never populated here, even if an env var existed —
 * add their key only alongside a real deployed static site.
 */
export function hostedModuleUrls(): Partial<Record<ModuleId, string>> {
  const urls: Partial<Record<ModuleId, string>> = {}

  const lidarUrl = import.meta.env.VITE_LIDAR_HOSTED_URL
  if (lidarUrl) {
    urls.lidar = lidarUrl
  }

  return urls
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/runtime/hostedModules.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/runtime/hostedModules.ts apps/portal/src/runtime/hostedModules.test.ts
git commit -m "feat(portal): add build-time hosted-module URL registry

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 3: Safe iframe/link URL check for STAGING origins

**Files:**
- Modify: `apps/portal/src/lib/safeUrl.ts`
- Modify: `apps/portal/src/lib/safeUrl.test.ts` (add cases; do not remove existing `isSafeLocalUrl` tests)

**Interfaces:**
- Consumes: `CampoEnvironment` from `../runtime/environment`
- Produces: `export function isSafeIframeUrl(candidate: string | undefined | null, environment: CampoEnvironment): candidate is string` — LOCAL delegates to the existing loopback-only `isSafeLocalUrl`; STAGING accepts only `https:` URLs whose hostname is exactly `campo-digital-lidar-staging.onrender.com` (the one real hosted origin from Task 2, not an open `*.onrender.com` wildcard, so a compromised/typo'd runtime value can never point at an arbitrary onrender.com site someone else owns).

- [ ] **Step 1: Write the failing test**

```ts
// append to apps/portal/src/lib/safeUrl.test.ts
import { isSafeIframeUrl } from './safeUrl'

describe('isSafeIframeUrl', () => {
  it('in local, behaves exactly like isSafeLocalUrl', () => {
    expect(isSafeIframeUrl('http://127.0.0.1:5173/', 'local')).toBe(true)
    expect(isSafeIframeUrl('https://campo-digital-lidar-staging.onrender.com/', 'local')).toBe(
      false,
    )
  })

  it('in staging, accepts only the known hosted LiDAR origin over https', () => {
    expect(
      isSafeIframeUrl('https://campo-digital-lidar-staging.onrender.com/', 'staging'),
    ).toBe(true)
    expect(
      isSafeIframeUrl('http://campo-digital-lidar-staging.onrender.com/', 'staging'),
    ).toBe(false)
  })

  it('in staging, rejects loopback URLs, other onrender.com apps, and unsafe schemes', () => {
    expect(isSafeIframeUrl('http://127.0.0.1:5173/', 'staging')).toBe(false)
    expect(isSafeIframeUrl('https://someone-elses-app.onrender.com/', 'staging')).toBe(false)
    expect(isSafeIframeUrl('javascript:alert(1)', 'staging')).toBe(false)
    expect(isSafeIframeUrl(undefined, 'staging')).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/lib/safeUrl.test.ts`
Expected: FAIL — `isSafeIframeUrl` is not exported.

- [ ] **Step 3: Write minimal implementation**

```ts
// apps/portal/src/lib/safeUrl.ts — append below the existing isSafeLocalUrl
import type { CampoEnvironment } from '../runtime/environment'

/**
 * The one real STAGING hosted origin this build knows about. Deliberately a
 * closed exact-hostname set, not a `*.onrender.com` wildcard: the runtime
 * config that supplies a candidate URL is build-time-trusted (Task 2), but
 * this check stays defense-in-depth against a future config bug pointing an
 * iframe at an arbitrary onrender.com app we don't own.
 */
const ALLOWED_STAGING_HOSTNAMES = new Set(['campo-digital-lidar-staging.onrender.com'])

export function isSafeIframeUrl(
  candidate: string | undefined | null,
  environment: CampoEnvironment,
): candidate is string {
  if (environment === 'local') {
    return isSafeLocalUrl(candidate)
  }

  if (!candidate) {
    return false
  }

  let parsed: URL
  try {
    parsed = new URL(candidate)
  } catch {
    return false
  }

  return parsed.protocol === 'https:' && ALLOWED_STAGING_HOSTNAMES.has(parsed.hostname)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/lib/safeUrl.test.ts`
Expected: PASS (all existing `isSafeLocalUrl` tests + 3 new `isSafeIframeUrl` tests)

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/lib/safeUrl.ts apps/portal/src/lib/safeUrl.test.ts
git commit -m "feat(portal): add environment-aware safe iframe URL check

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 4: `CampoRuntimeConfig` gains an `environment` field and a STAGING builder

**Files:**
- Modify: `apps/portal/src/runtime/runtimeConfig.ts`
- Modify: `apps/portal/src/runtime/runtimeConfig.test.ts` (add cases; keep existing ones passing verbatim)

**Interfaces:**
- Consumes: `getCampoEnvironment` (Task 1), `hostedModuleUrls` (Task 2)
- Produces: `CampoRuntimeConfig.environment: CampoEnvironment` (new field); `export function buildStagingRuntimeConfig(): CampoRuntimeConfig` (new, synchronous, no network)
- `parseRuntimeConfig` keeps its existing signature and always tags `environment: 'local'` (it is only ever called by the LOCAL fetch path) — every existing call site/test is unaffected.

- [ ] **Step 1: Write the failing test**

```ts
// append to apps/portal/src/runtime/runtimeConfig.test.ts
import { afterEach, vi } from 'vitest'
import { buildStagingRuntimeConfig } from './runtimeConfig'

describe('buildStagingRuntimeConfig', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('marks a hosted module available with its build-time URL', () => {
    vi.stubEnv('VITE_LIDAR_HOSTED_URL', 'https://campo-digital-lidar-staging.onrender.com')
    const config = buildStagingRuntimeConfig()

    expect(config.environment).toBe('staging')
    expect(config.modules.lidar).toEqual({
      status: 'available',
      url: 'https://campo-digital-lidar-staging.onrender.com',
    })
  })

  it('marks forestal and transelec unavailable — honest, not fake-green', () => {
    const config = buildStagingRuntimeConfig()

    expect(config.modules.forestal).toEqual({ status: 'unavailable' })
    expect(config.modules.transelec).toEqual({ status: 'unavailable' })
  })
})

describe('parseRuntimeConfig environment tag', () => {
  it('always tags local, since it only ever parses the local launcher file', () => {
    expect(parseRuntimeConfig({ modules: {} }).environment).toBe('local')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/runtime/runtimeConfig.test.ts`
Expected: FAIL — `buildStagingRuntimeConfig` not exported; `environment` undefined on parsed config.

- [ ] **Step 3: Write minimal implementation**

Edit `apps/portal/src/runtime/runtimeConfig.ts`:

```ts
import type { CampoEnvironment } from './environment'
import { hostedModuleUrls } from './hostedModules'

export type ModuleId = 'lidar' | 'forestal' | 'transelec'
export type ModuleStatus = 'available' | 'unavailable'

export interface ModuleRuntimeStatus {
  status: ModuleStatus
  url?: string
  owned?: boolean
  measurementCount?: number
}

export interface CampoRuntimeConfig {
  environment: CampoEnvironment
  generatedAt?: string
  portal?: { port?: number }
  modules: Partial<Record<ModuleId, ModuleRuntimeStatus>>
}

const EMPTY_CONFIG: CampoRuntimeConfig = { environment: 'local', modules: {} }
```

Update `parseRuntimeConfig`'s two early-return branches (`typeof raw !== 'object'`, missing) to return `EMPTY_CONFIG` (already tagged `'local'`), and its final return object to add `environment: 'local'` alongside the existing fields.

Add after `fetchRuntimeConfig`:

```ts
/**
 * STAGING's runtime config: no fetch, no dynamic file (Render's static
 * hosting has no server to generate one) — everything is already compiled
 * into this bundle from Task 2/hostedModuleUrls. Synchronous by design so
 * useRuntimeConfig never shows a loading flicker in STAGING.
 */
export function buildStagingRuntimeConfig(): CampoRuntimeConfig {
  const hosted = hostedModuleUrls()
  const modules: CampoRuntimeConfig['modules'] = {}

  for (const moduleId of ['lidar', 'forestal', 'transelec'] as const) {
    const url = hosted[moduleId]
    modules[moduleId] = url ? { status: 'available', url } : { status: 'unavailable' }
  }

  return { environment: 'staging', modules }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/runtime/runtimeConfig.test.ts`
Expected: PASS (all existing tests unmodified + new ones)

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/runtime/runtimeConfig.ts apps/portal/src/runtime/runtimeConfig.test.ts
git commit -m "feat(portal): tag runtime config with LOCAL/STAGING environment

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 5: `useRuntimeConfig` branches on environment

**Files:**
- Modify: `apps/portal/src/runtime/useRuntimeConfig.ts`
- Create: `apps/portal/src/runtime/useRuntimeConfig.test.ts`

**Interfaces:**
- Consumes: `getCampoEnvironment` (Task 1), `buildStagingRuntimeConfig` (Task 4), existing `fetchRuntimeConfig`
- Produces: same `RuntimeConfigState { config, loading }` as before — no consumer-visible signature change.

- [ ] **Step 1: Write the failing test**

```ts
// apps/portal/src/runtime/useRuntimeConfig.test.ts
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
        json: async () => ({ modules: { lidar: { status: 'available', url: 'http://127.0.0.1:5174/' } } }),
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/runtime/useRuntimeConfig.test.ts`
Expected: FAIL — staging case calls fetch (current implementation always fetches) and `config.environment` is `undefined`.

- [ ] **Step 3: Write minimal implementation**

```ts
// apps/portal/src/runtime/useRuntimeConfig.ts
import { useEffect, useState } from 'react'
import { getCampoEnvironment } from './environment'
import type { CampoRuntimeConfig } from './runtimeConfig'
import { buildStagingRuntimeConfig, fetchRuntimeConfig } from './runtimeConfig'

const EMPTY_CONFIG: CampoRuntimeConfig = { environment: getCampoEnvironment(), modules: {} }

export interface RuntimeConfigState {
  config: CampoRuntimeConfig
  loading: boolean
}

export function useRuntimeConfig(): RuntimeConfigState {
  const [state, setState] = useState<RuntimeConfigState>({
    config: EMPTY_CONFIG,
    loading: true,
  })

  useEffect(() => {
    if (getCampoEnvironment() === 'staging') {
      setState({ config: buildStagingRuntimeConfig(), loading: false })
      return
    }

    const controller = new AbortController()

    fetchRuntimeConfig(controller.signal).then((config) => {
      if (!controller.signal.aborted) {
        setState({ config, loading: false })
      }
    })

    return () => controller.abort()
  }, [])

  return state
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/runtime/useRuntimeConfig.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/runtime/useRuntimeConfig.ts apps/portal/src/runtime/useRuntimeConfig.test.ts
git commit -m "feat(portal): resolve runtime config from build-time state in staging

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 6: `StatusBadge` copy branches on environment

**Files:**
- Modify: `apps/portal/src/components/StatusBadge.tsx`
- Create: `apps/portal/src/components/StatusBadge.test.tsx`

**Interfaces:**
- Consumes: `CampoEnvironment` from `../runtime/environment`
- Produces: `StatusBadge` gains a required `environment: CampoEnvironment` prop. LOCAL labels are byte-identical to today (`'Disponible'` / `'Demo no iniciada'`). STAGING: `'Disponible'` / `'No desplegado en este entorno'`.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/portal/src/components/StatusBadge.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('local unavailable reads "Demo no iniciada", unchanged from today', () => {
    render(<StatusBadge status="unavailable" environment="local" />)
    expect(screen.getByText('Demo no iniciada')).toBeInTheDocument()
  })

  it('staging unavailable reads an honest not-hosted label, never "Demo no iniciada"', () => {
    render(<StatusBadge status="unavailable" environment="staging" />)
    expect(screen.getByText('No desplegado en este entorno')).toBeInTheDocument()
    expect(screen.queryByText('Demo no iniciada')).not.toBeInTheDocument()
  })

  it('available reads "Disponible" in both environments', () => {
    const { rerender } = render(<StatusBadge status="available" environment="local" />)
    expect(screen.getByText('Disponible')).toBeInTheDocument()
    rerender(<StatusBadge status="available" environment="staging" />)
    expect(screen.getByText('Disponible')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/components/StatusBadge.test.tsx`
Expected: FAIL — `environment` prop not accepted / TS error, staging label doesn't exist.

- [ ] **Step 3: Write minimal implementation**

```tsx
// apps/portal/src/components/StatusBadge.tsx
import type { CampoEnvironment } from '../runtime/environment'
import type { ModuleStatus } from '../runtime/runtimeConfig'

const LABELS: Record<CampoEnvironment, Record<ModuleStatus, string>> = {
  local: {
    available: 'Disponible',
    unavailable: 'Demo no iniciada',
  },
  staging: {
    available: 'Disponible',
    unavailable: 'No desplegado en este entorno',
  },
}

export function StatusBadge({
  status,
  environment,
}: {
  status: ModuleStatus
  environment: CampoEnvironment
}) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      <span className="status-badge__dot" aria-hidden="true" />
      {LABELS[environment][status]}
    </span>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/components/StatusBadge.test.tsx`
Expected: PASS (3 tests) — but this will break `ProductPanel`'s call site until Task 7; run the full suite after Task 7, not here.

- [ ] **Step 5: Commit** (bundle with Task 7 — `ProductPanel` must change in the same commit or the build breaks)

---

## Task 7: `ProductPanel` and `Home` thread `environment` through, and Home gains the `/archivos` link

**Files:**
- Modify: `apps/portal/src/components/ProductPanel.tsx`
- Modify: `apps/portal/src/pages/Home.tsx`
- Modify: `apps/portal/src/pages/Home.test.tsx` (add cases; existing cases must pass unmodified)

**Interfaces:**
- Consumes: `StatusBadge` (Task 6), `useRuntimeConfig` (existing)
- `ProductPanel` gains a required `environment: CampoEnvironment` prop, passed straight to `StatusBadge`.

- [ ] **Step 1: Write the failing test**

```tsx
// append to apps/portal/src/pages/Home.test.tsx
describe('Home — staging awareness', () => {
  it('never shows the local-only "Demo no iniciada" phrase in staging', async () => {
    vi.stubEnv('VITE_CAMPO_ENV', 'staging')

    render(
      <RouterProvider>
        <Home />
      </RouterProvider>,
    )

    await screen.findByText('Cubicación LiDAR')
    expect(screen.queryByText('Demo no iniciada')).not.toBeInTheDocument()
    vi.unstubAllEnvs()
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/pages/Home.test.tsx`
Expected: FAIL — `ProductPanel`/`StatusBadge` type error (`environment` missing), no "Archivos" link exists yet.

- [ ] **Step 3: Write minimal implementation**

Edit `apps/portal/src/components/ProductPanel.tsx`:

```tsx
import type { CampoEnvironment } from '../runtime/environment'
// ...existing imports...

interface ProductPanelProps {
  module: ModuleDefinition
  status: ModuleStatus
  environment: CampoEnvironment
  layout: 'visual-left' | 'visual-right' | 'banner'
}

export function ProductPanel({ module, status, environment, layout }: ProductPanelProps) {
  // ...unchanged body, except:
  <StatusBadge status={status} environment={environment} />
  // ...
}
```

Edit `apps/portal/src/pages/Home.tsx`: pass `environment={config.environment}` to each `ProductPanel`, and change the footer to:

```tsx
      <footer className="home__footer">
        <p>3 productos · fuentes trazables · evidencia preservada</p>
        <Link to="/estado" className="home__footer-link">
          {config.environment === 'staging' ? 'Estado del entorno de staging' : 'Estado del entorno local'}
        </Link>
        <Link to="/archivos" className="home__footer-link">
          Archivos
        </Link>
      </footer>
```

(`useRuntimeConfig` returns `{ config }`, already destructured at the top of `Home`; no new hook call needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/pages/Home.test.tsx src/components/StatusBadge.test.tsx`
Expected: PASS — including the two pre-existing Home tests that assert `'Estado del entorno local'` (default environment is `'local'` in tests, unchanged).

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/components/ProductPanel.tsx apps/portal/src/components/StatusBadge.tsx apps/portal/src/components/StatusBadge.test.tsx apps/portal/src/pages/Home.tsx apps/portal/src/pages/Home.test.tsx
git commit -m "feat(portal): environment-aware status copy, add Archivos to home nav

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 8: `Estado` describes hosted availability, not local process ownership, in STAGING

**Files:**
- Modify: `apps/portal/src/pages/Estado.tsx`
- Modify: `apps/portal/src/pages/Estado.test.tsx` (add cases; existing cases must pass unmodified)

**Interfaces:**
- Consumes: `config.environment` from `useRuntimeConfig()` (already in scope in `Estado`)

- [ ] **Step 1: Write the failing test**

```tsx
// append to apps/portal/src/pages/Estado.test.tsx
describe('Estado — staging', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('describes hosted availability, not local process ownership', async () => {
    vi.stubEnv('VITE_CAMPO_ENV', 'staging')
    vi.stubEnv('VITE_LIDAR_HOSTED_URL', 'https://campo-digital-lidar-staging.onrender.com')

    render(
      <RouterProvider>
        <Estado />
      </RouterProvider>,
    )

    expect(await screen.findByText('Estado del entorno de staging')).toBeInTheDocument()
    expect(screen.queryByText('Estado del entorno local')).not.toBeInTheDocument()
    expect(screen.queryByText('Iniciado por Campo Demo')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/pages/Estado.test.tsx`
Expected: FAIL — heading text and column are still the local-only ones regardless of environment.

- [ ] **Step 3: Write minimal implementation**

```tsx
// apps/portal/src/pages/Estado.tsx
export function Estado() {
  const { config, loading } = useRuntimeConfig()
  const isStaging = config.environment === 'staging'

  return (
    <div className="estado">
      <p>
        <Link to="/">← Campo Digital</Link>
      </p>
      <h1>{isStaging ? 'Estado del entorno de staging' : 'Estado del entorno local'}</h1>
      <p className="estado__note">
        {isStaging
          ? 'Entorno de staging público. No contiene datos reales de clientes.'
          : 'Vista de diagnóstico para desarrollo. No representa disponibilidad en producción.'}
      </p>

      {loading ? (
        <p>Cargando…</p>
      ) : (
        <table className="estado__table">
          <thead>
            <tr>
              <th>Módulo</th>
              <th>Estado</th>
              <th>URL{isStaging ? '' : ' local'}</th>
              {!isStaging && <th>Iniciado por Campo Demo</th>}
              <th>Mediciones persistidas</th>
            </tr>
          </thead>
          <tbody>
            {MODULES.map((module) => {
              const status = moduleStatusFor(config, module.id)
              return (
                <tr key={module.id}>
                  <td>{module.title}</td>
                  <td>{status.status}</td>
                  <td>
                    <code>{status.url ?? '—'}</code>
                  </td>
                  {!isStaging && (
                    <td>{status.owned === undefined ? '—' : status.owned ? 'sí' : 'no (ya estaba activo)'}</td>
                  )}
                  <td>{status.measurementCount === undefined ? '—' : status.measurementCount}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      <p className="estado__generated">
        Generado: <code>{config.generatedAt ?? '—'}</code>
      </p>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/pages/Estado.test.tsx`
Expected: PASS — including the three pre-existing local-mode tests (default environment `'local'`, unchanged column set/copy).

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/pages/Estado.tsx apps/portal/src/pages/Estado.test.tsx
git commit -m "feat(portal): make /estado describe staging hosted availability honestly

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 9: `ModuleHeader` uses the environment-aware safe-URL check

**Files:**
- Modify: `apps/portal/src/components/ModuleHeader.tsx`
- Modify: `apps/portal/src/components/ModuleHeader.test.tsx` (existing 3 tests must pass with an added `environment="local"` prop; add 1 staging case)

**Interfaces:**
- `ModuleHeader` gains a required `environment: CampoEnvironment` prop, used only to select `isSafeIframeUrl`'s branch — no other behavior change.

- [ ] **Step 1: Write the failing test**

Update the 3 existing `ModuleHeader.test.tsx` render calls to pass `environment="local"` (they currently omit it — this is a required-prop addition, so TypeScript will fail to compile without it):

```tsx
<ModuleHeader module={forestal} url="http://127.0.0.1:5175/" environment="local" />
```
(same for the other two existing tests), then append:

```tsx
  it('accepts the known staging hosted origin as a safe external-open target', () => {
    render(
      <RouterProvider>
        <ModuleHeader
          module={forestal}
          url="https://campo-digital-lidar-staging.onrender.com/"
          environment="staging"
        />
      </RouterProvider>,
    )

    expect(screen.getByText('Abrir en pestaña nueva')).toHaveAttribute(
      'href',
      'https://campo-digital-lidar-staging.onrender.com/',
    )
  })

  it('in staging, rejects a loopback URL that would only be safe locally', () => {
    render(
      <RouterProvider>
        <ModuleHeader module={forestal} url="http://127.0.0.1:5175/" environment="staging" />
      </RouterProvider>,
    )

    expect(screen.queryByText('Abrir en pestaña nueva')).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/components/ModuleHeader.test.tsx`
Expected: FAIL — TS error, `environment` prop doesn't exist yet on `ModuleHeaderProps`.

- [ ] **Step 3: Write minimal implementation**

```tsx
// apps/portal/src/components/ModuleHeader.tsx
import type { CampoEnvironment } from '../runtime/environment'
import { isSafeIframeUrl } from '../lib/safeUrl'
// ...

interface ModuleHeaderProps {
  module: ModuleDefinition
  url: string | undefined
  environment: CampoEnvironment
}

export function ModuleHeader({ module, url, environment }: ModuleHeaderProps) {
  const { pathname } = useRouter()
  const canOpenExternally = isSafeIframeUrl(url, environment)
  // ...rest unchanged...
```

Remove the now-unused `isSafeLocalUrl` import from this file (keep it exported from `safeUrl.ts` — `Module.tsx`/tests still use it in Task 10/existing tests).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/components/ModuleHeader.test.tsx`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit** (bundle with Task 10 — `Module.tsx` is `ModuleHeader`'s only caller and must pass the new prop in the same commit or the build breaks)

---

## Task 10: `Module.tsx` (module shell) is environment-aware end to end

**Files:**
- Modify: `apps/portal/src/pages/Module.tsx`
- Modify: `apps/portal/src/pages/Module.test.tsx` (existing 4 tests must pass unmodified — default environment is local; add staging cases)

**Interfaces:**
- Consumes: `config.environment` (from `useRuntimeConfig`, already called in `Module.tsx`), `isSafeIframeUrl` (Task 3), `ModuleHeader` (Task 9)

- [ ] **Step 1: Write the failing test**

```tsx
// append to apps/portal/src/pages/Module.test.tsx
describe('ModulePage — staging', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('renders an iframe pointed at the hosted LiDAR origin when available', async () => {
    vi.stubEnv('VITE_CAMPO_ENV', 'staging')
    mockRuntimeFetch({}) // staging never fetches, but keep fetch mocked defensively
    vi.stubEnv('VITE_LIDAR_HOSTED_URL', 'https://campo-digital-lidar-staging.onrender.com')

    render(
      <RouterProvider>
        <ModulePage moduleId="lidar" />
      </RouterProvider>,
    )

    const frame = await screen.findByTitle('Cubicación LiDAR')
    expect(frame).toHaveAttribute('src', 'https://campo-digital-lidar-staging.onrender.com')
  })

  it('shows an honest not-yet-hosted state for forestal, never "Demo no iniciada"', async () => {
    vi.stubEnv('VITE_CAMPO_ENV', 'staging')
    mockRuntimeFetch({})

    render(
      <RouterProvider>
        <ModulePage moduleId="forestal" />
      </RouterProvider>,
    )

    expect(await screen.findByText(/no está disponible públicamente/)).toBeInTheDocument()
    expect(screen.queryByText('Demo no iniciada.')).not.toBeInTheDocument()
    expect(screen.queryByText(/make campo-demo/)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/pages/Module.test.tsx`
Expected: FAIL — iframe still gated by `isSafeLocalUrl` (rejects the https onrender.com URL), and the unavailable copy is always the local "Demo no iniciada." text regardless of environment.

- [ ] **Step 3: Write minimal implementation**

```tsx
// apps/portal/src/pages/Module.tsx
import { isSafeIframeUrl } from '../lib/safeUrl'
import type { CampoEnvironment } from '../runtime/environment'
// remove the old isSafeLocalUrl import

export function ModulePage({ moduleId }: { moduleId: string }) {
  const module = findModule(moduleId)
  const { config, loading } = useRuntimeConfig()
  const [iframeFailed, setIframeFailed] = useState(false)

  if (!module) {
    return (
      <div className="module-shell module-shell--missing">
        <p>Módulo desconocido.</p>
        <Link to="/">Volver a Campo Digital</Link>
      </div>
    )
  }

  const runtimeStatus = moduleStatusFor(config, module.id)
  const safeUrl = isSafeIframeUrl(runtimeStatus.url, config.environment) ? runtimeStatus.url : undefined
  const isAvailable = runtimeStatus.status === 'available' && Boolean(safeUrl)

  return (
    <div className="module-shell">
      <ModuleHeader module={module} url={safeUrl} environment={config.environment} />

      <div className="module-shell__content">
        {loading ? (
          <div className="module-shell__state">Cargando estado del módulo…</div>
        ) : isAvailable && !iframeFailed ? (
          <iframe
            key={safeUrl}
            src={safeUrl}
            title={module.title}
            className="module-shell__frame"
            onError={() => setIframeFailed(true)}
          />
        ) : (
          <ModuleUnavailable moduleId={module.id} environment={config.environment} />
        )}
      </div>
    </div>
  )
}

const EXPECTED_BRANCH: Record<string, string> = {
  lidar: 'products/lidar (esta misma rama)',
  forestal: 'feat/forestry-dashboard-v1',
  transelec: 'feat/transelec-ui-reference-parity-v1',
}

function ModuleUnavailable({
  moduleId,
  environment,
}: {
  moduleId: string
  environment: CampoEnvironment
}) {
  if (environment === 'staging') {
    return (
      <div className="module-shell__state module-shell__state--unavailable">
        <p>Este módulo aún no está disponible públicamente en este entorno.</p>
        <p className="module-shell__state-hint">
          No se publican datos reales de clientes sin sanear primero; este módulo se habilitará
          aquí cuando exista una versión hospedada segura.
        </p>
      </div>
    )
  }

  return (
    <div className="module-shell__state module-shell__state--unavailable">
      <p>Demo no iniciada.</p>
      <p className="module-shell__state-hint">
        Este módulo no está disponible en este entorno local.
      </p>
      <details className="module-shell__details">
        <summary>Detalles técnicos</summary>
        <p>
          Worktree/rama esperada: <code>{EXPECTED_BRANCH[moduleId] ?? moduleId}</code>
        </p>
        <p>
          Inicie la demo completa con <code>make campo-demo</code> desde este repositorio.
        </p>
      </details>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/pages/Module.test.tsx src/components/ModuleHeader.test.tsx`
Expected: PASS — all 4 pre-existing `Module.test.tsx` cases (default local) plus 2 new staging cases; `ModuleHeader.test.tsx`'s 5 cases from Task 9.

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/pages/Module.tsx apps/portal/src/pages/Module.test.tsx apps/portal/src/components/ModuleHeader.tsx apps/portal/src/components/ModuleHeader.test.tsx
git commit -m "feat(portal): module shell renders hosted iframes and honest staging states

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 11: Rename `/ingesta` → `/archivos`, honest staging sign-in state

**Files:**
- Create: `apps/portal/src/pages/Archivos.tsx` (content = `Ingesta.tsx` renamed + staging branch)
- Create: `apps/portal/src/pages/Archivos.test.tsx` (content = `Ingesta.test.tsx` renamed + staging case)
- Delete: `apps/portal/src/pages/Ingesta.tsx`, `apps/portal/src/pages/Ingesta.test.tsx`
- Modify: `apps/portal/src/App.tsx`

**Interfaces:**
- Produces: `export function Archivos()` (was `export function Ingesta()`), route `/archivos` (was `/ingesta`). Everything else in this component (dev-login flow, upload, jobs, audit — `apps/portal/src/lib/platformApi.ts`) is untouched: this is a rename plus one new environment-gated branch, not a rewrite.

- [ ] **Step 1: Write the failing test**

Copy `Ingesta.test.tsx` to `Archivos.test.tsx`, change the import to `import { Archivos } from './Archivos'` and every `<Ingesta />` to `<Archivos />`, keep every existing case as-is, then append:

```tsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/pages/Archivos.test.tsx`
Expected: FAIL — file doesn't exist yet (or, once created from a straight copy, the staging case fails because dev-login buttons still render).

- [ ] **Step 3: Write minimal implementation**

Create `Archivos.tsx` as `Ingesta.tsx`'s content with these changes: rename `export function Ingesta()` → `export function Archivos()`; import `getCampoEnvironment` from `../runtime/environment`; change the heading `<h1>Ingesta local (dev)</h1>` → `<h1>Archivos</h1>` (both the logged-out and logged-in render branches); and replace the logged-out branch's body:

```tsx
  if (!me) {
    const environment = getCampoEnvironment()
    return (
      <div className="ingesta">
        <p>
          <Link to="/">← Campo Digital</Link>
        </p>
        <h1>Archivos</h1>
        {environment === 'staging' ? (
          <p className="ingesta__note">
            El inicio de sesión de plataforma aún no está disponible en este entorno (queda
            pendiente la integración con Entra ID).
          </p>
        ) : (
          <>
            <p className="ingesta__note">
              Autenticación local de desarrollo — no representa un mecanismo de producción.
            </p>
            <div className="ingesta__login" role="group" aria-label="Elegir identidad local">
              {DEV_IDENTITIES.map((identityKey) => (
                <button key={identityKey} type="button" onClick={() => handleLogin(identityKey)}>
                  {identityKey}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    )
  }
```

Leave the logged-in branch (upload/jobs/audit) untouched except the `<h1>` text and CSS class names — no need to rename `ingesta__*` CSS classes (not user-facing, out of scope, avoids touching `apps/portal/src/styles/app.css` unnecessarily).

Delete `Ingesta.tsx` and `Ingesta.test.tsx` (`git rm`).

Edit `App.tsx`:

```tsx
import { Archivos } from './pages/Archivos'
// ...
  if (pathname === '/archivos') {
    return <Archivos />
  }
```

(remove the old `/ingesta` branch and `Ingesta` import).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/pages/Archivos.test.tsx`
Expected: PASS — all 5 renamed pre-existing cases (default local, unchanged behavior) + the new staging case.

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/pages/Archivos.tsx apps/portal/src/pages/Archivos.test.tsx apps/portal/src/App.tsx
git rm apps/portal/src/pages/Ingesta.tsx apps/portal/src/pages/Ingesta.test.tsx
git commit -m "feat(portal): rename /ingesta to /archivos, honest staging sign-in state

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 12: `App.test.tsx` covers `/archivos` navigation from Home

**Files:**
- Modify: `apps/portal/src/App.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// append inside describe('App navigation', ...) in App.test.tsx
  it('navigates from the home footer into /archivos as a first-class entry', async () => {
    const user = userEvent.setup()
    render(<App />)

    await screen.findByText('Cubicación LiDAR')
    await user.click(screen.getByText('Archivos'))

    expect(window.location.pathname).toBe('/archivos')
    await screen.findByText('Archivos')
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/portal && npx vitest run src/App.test.tsx`
Expected: FAIL only if Task 11 wasn't completed first — if run after Task 11, this should already pass (verification step, not new production code).

- [ ] **Step 3: N/A — no implementation change, this task only adds coverage of Task 7 + Task 11 wired together.**

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/portal && npx vitest run src/App.test.tsx`
Expected: PASS (4 tests: 3 pre-existing + 1 new)

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/App.test.tsx
git commit -m "test(portal): cover /archivos navigation from the home footer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 13: Full portal verification (typecheck/lint/build/test)

**Files:** none (verification only)

- [ ] **Step 1:** `cd apps/portal && npm run test` — expect all tests pass (every file touched in Tasks 1-12).
- [ ] **Step 2:** `cd apps/portal && npx tsc -b` — expect no type errors (catches any missed required-prop call site from Tasks 6, 7, 9, 10).
- [ ] **Step 3:** `cd apps/portal && npm run lint` (oxlint) — expect no new warnings/errors.
- [ ] **Step 4:** `cd apps/portal && VITE_CAMPO_ENV=staging VITE_LIDAR_HOSTED_URL=https://campo-digital-lidar-staging.onrender.com npm run build` — expect a clean STAGING production build in `apps/portal/dist`.
- [ ] **Step 5:** `cd apps/portal && npm run build` (no env vars — LOCAL build) — expect a clean build, confirming the LOCAL path still builds with no `VITE_*` vars set (matches how Render would build the portal today before this change, and how `npm run dev` behaves).
- [ ] **Step 6:** From repo root: `uv run python scripts/check_architecture_boundaries.py` — expect no violations (no product frontend code was imported by the portal; only URLs).
- [ ] No commit — this is a checkpoint. If anything fails, fix it and re-run before Task 14.

---

## Task 14: Deploy LiDAR as a Render static site, wire portal STAGING env vars

**Files:**
- Modify: `render.yaml`

- [ ] **Step 1:** Read the current `render.yaml` in full (already done during planning; reproduced below for the diff) and confirm no other in-flight edits conflict.

- [ ] **Step 2: Apply the diff**

Change both existing services' `branch:` from `feat/render-staging-v1` to `feat/hosted-composition-v1` (this is the branch that contains the STAGING-aware portal and the new LiDAR service; the Blueprint must point at the branch that actually contains what it describes):

```yaml
  - name: campo-digital-api-staging
    ...
    branch: feat/hosted-composition-v1
```//api service
```yaml
  - name: campo-digital-portal-staging
    ...
    branch: feat/hosted-composition-v1
```

Add `envVars` to `campo-digital-portal-staging` (it currently has none):

```yaml
    envVars:
      - key: VITE_CAMPO_ENV
        value: staging
      - key: VITE_LIDAR_HOSTED_URL
        value: https://campo-digital-lidar-staging.onrender.com
```

Add a new service after `campo-digital-portal-staging`:

```yaml
  # Static build of the LiDAR product dashboard (products/lidar/dashboard).
  # Talks to the SAME already-deployed campo-digital-api-staging service —
  # apps/api/app/routers/lidar.py has no DB dependency and already resolves
  # to an empty [] with no CAMPO_LIDAR_OUTPUT_ROOT set (see
  # docs/adr/ADR-007-hosted-product-composition-v1.md), so this adds a
  # second free static site and zero new backend surface, zero new data.
  - name: campo-digital-lidar-staging
    type: web
    runtime: static
    repo: https://github.com/rafaelRojasVi/campo-digital-platform.git
    branch: feat/hosted-composition-v1
    buildCommand: cd products/lidar/dashboard && npm ci && npm run build
    staticPublishPath: products/lidar/dashboard/dist
    routes:
      - type: rewrite
        source: /api/*
        destination: https://campo-digital-api-staging.onrender.com/*
      - type: rewrite
        source: /*
        destination: /index.html
```

Update the file's top comment block to mention the new service exists (one added line is enough, do not rewrite the whole header).

- [ ] **Step 3:** `render blueprints validate render.yaml` (from repo root, using the installed `render` CLI v2.23.0). Expect either a pass, or an error naming the specific field to fix (per ADR-005's note, full validation needs the target branch to exist on the remote — if the CLI complains about the branch not existing remotely, that is expected and documented, not a config bug; record the exact output in the final report either way, do not silently ignore a real schema error).
- [ ] **Step 4:** If validation reports a real schema/field error (not the known remote-branch limitation), fix `render.yaml` and re-run Step 3 until only the known limitation (if any) remains.
- [ ] **Step 5: Commit**

```bash
git add render.yaml
git commit -m "feat: add hosted LiDAR static site, wire portal STAGING env vars

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 15: Local browser QA

**Files:** none (manual verification only, using the `run` skill or direct dev servers)

- [ ] **Step 1:** Start the platform API locally (`make platform-local` or equivalent) and the portal (`cd apps/portal && npm run dev`). Visit `/` — confirm unchanged local Home (all copy identical to before this branch).
- [ ] **Step 2:** Visit `/archivos` — confirm the page renders under the new name/route with the dev-identity login buttons (LOCAL — unchanged behavior).
- [ ] **Step 3:** Visit `/estado` — confirm "Estado del entorno local" and the "Iniciado por Campo Demo" column are still present (LOCAL — unchanged).
- [ ] **Step 4:** Build the portal with `VITE_CAMPO_ENV=staging VITE_LIDAR_HOSTED_URL=https://campo-digital-lidar-staging.onrender.com npm run build && npm run preview`, then in a browser visit `/`, `/estado`, `/archivos`, `/modulo/lidar`, `/modulo/forestal`. Confirm: Home shows no "Demo no iniciada"; `/estado` says "Estado del entorno de staging" with no ownership column; `/archivos` shows the honest sign-in-unavailable message with no dev-login buttons; `/modulo/lidar` attempts an iframe to the (not-yet-deployed, so this will show a connection failure in the browser, not a portal bug) hosted URL; `/modulo/forestal` shows the honest not-yet-hosted message, never "Demo no iniciada."
- [ ] **Step 5:** Separately, run `cd products/lidar/dashboard && npm run build && npm run preview` with no backend running, confirm the dashboard's own "No hay medición seleccionada" / "No measurement runs" empty state renders cleanly with no console errors about the (unreachable in this local check) `/local-demo/field-reference.jpeg` — since that panel only renders once a run exists, expect none logged.
- [ ] **Step 6:** Record pass/fail and any screenshots taken for the final report. No commit (QA only).

---

## Task 16: Documentation

**Files:**
- Create: `docs/adr/ADR-007-hosted-product-composition-v1.md`
- Modify: `docs/platform/company-portal-v1.md`
- Modify: `docs/platform/roadmap.md`
- Modify: `docs/es/plataforma/estado-plataforma.md`

- [ ] **Step 1:** Write `ADR-007-hosted-product-composition-v1.md` following the existing ADR-005/ADR-006 format (Status/Context/Decision/Consequences/Related). Content: the Task 0 classification table (LiDAR B, Forestry B-deferred, Transelec C) with the exact evidence cited there; the environment-detection mechanism (Task 1); the closed-allowlist safe-iframe-URL decision (Task 3) and why it's not a `*.onrender.com` wildcard; the decision not to touch dev-auth (ADR-006 stands); the decision not to merge `feat/forestry-dashboard-v1` / `feat/transelec-hosted-pilot-v1` this slice.
- [ ] **Step 2:** Update `docs/platform/company-portal-v1.md`: add `/archivos` to the routes list (currently missing even for the pre-existing `/ingesta`); add a "STAGING hosted composition" section describing the LiDAR static site + honest Forestry/Transelec state, cross-referencing ADR-007; update the "Local composition strategy: iframe" section header to clarify it now covers both LOCAL and STAGING (with a link to ADR-007 for the STAGING half) rather than rewriting it.
- [ ] **Step 3:** Update `docs/platform/roadmap.md`: amend the `/ingesta` page FACT bullet to say `/archivos`; add one new FACT/RESULT bullet dated 2026-09-01 recording the LiDAR hosted staging deployment and the honest Forestry/Transelec state, citing ADR-007.
- [ ] **Step 4:** Add a short new section to `docs/es/plataforma/estado-plataforma.md` (do not rewrite the existing August foundational content) noting: LiDAR ahora es accesible públicamente en staging sin datos reales; Forestal y Transelec aún no están públicamente disponibles y el portal lo indica honestamente; costo incremental sigue siendo USD 0/mes.
- [ ] **Step 5:** `uv run python scripts/update_doc_nav.py` (new/moved doc files exist — ADR-007).
- [ ] **Step 6:** `uv run python scripts/check_doc_links.py` — fix any broken links surfaced.
- [ ] **Step 7:** `make docs-check` — confirm it passes.
- [ ] **Step 8: Commit**

```bash
git add docs/adr/ADR-007-hosted-product-composition-v1.md docs/platform/company-portal-v1.md docs/platform/roadmap.md docs/es/plataforma/estado-plataforma.md
# plus any files scripts/update_doc_nav.py changed
git commit -m "docs: record hosted product composition v1 decision and status

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TwfoCZ32Mzm2ojdWLorL6s"
```

---

## Task 17: Full repo verification pass

**Files:** none (verification only)

- [ ] **Step 1:** `make check` from repo root (format-check, lint, typecheck, architecture-check, test, docs-check) — this runs the Python suite; the portal's own `npm run test`/`tsc -b`/`oxlint` were already verified in Task 13 and are not part of `make check` (no Node step in the root Makefile).
- [ ] **Step 2:** `make test-api` — confirm no backend test regressed (no backend code was touched, this is a safety check).
- [ ] **Step 3:** Re-run Task 13's steps once more as a final gate (portal test/build/typecheck/lint) after the Task 16 doc commit, in case any doc-nav script touched a portal file (it should not, but verify).
- [ ] **Step 4:** Record every command's pass/fail in the final report. Do not proceed to claim completion on a failing command — fix and re-run.

---

## Self-Review Notes (already applied above)

- **Spec coverage:** Outcome 1 → Tasks 1, 4, 5, 8. Outcome 2 → Task 11 (+7 for nav entry). Outcome 3/4 → Task 0. Outcome 5 → Tasks 6, 14 (smallest coherent: one new static site, no new backend, no merge of other branches). Outcome 6 → Task 0/6 rationale (empty state, not a copied report store). Outcome 7 → Tasks 8, 10 (honest unavailable copy for Forestry/Transelec in staging). Outcome 8 → Task 14 (both new resources are Render free tier). Outcome 9 → Global Constraints + Task 0 (no backend files touched at all). Test/QA outcomes → Tasks 13, 15, 16 Step 6-7, 17.
- **Placeholder scan:** every task has literal code/copy, not "add appropriate copy."
- **Type consistency:** `CampoRuntimeConfig.environment`, `CampoEnvironment`, `isSafeIframeUrl(candidate, environment)`, `ModuleUnavailable({ moduleId, environment })`, `ModuleHeaderProps.environment`, `ProductPanelProps.environment`, `StatusBadge({ status, environment })` — same names/shapes used consistently from Task 1 through Task 10.
