# Unified platform, step 1: front door Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One address serves a Campo Digital front door at `/` (Google sign-in, then a project picker) and Transelec at `/transelec/`, with a "Cambiar proyecto" link back to `/`.

**Architecture:** The FastAPI container serves two static builds: the portal (`apps/portal`, new production mode) at the root and Transelec under `/transelec/` (Vite `base` moves from `/` to `/transelec/`). One catch-all route dispatches by first path segment. Transelec, built with `VITE_PLATFORM_FRONT_DOOR=true`, sends a signed-out browser to `/` instead of showing its own sign-in card.

**Tech Stack:** FastAPI + Starlette `StaticFiles`, React 19 + Vite 8 + vitest, Docker multi-stage build.

**Spec:** `docs/superpowers/specs/2026-09-28-unified-platform-design.md` (step 1 of "Delivery steps").

## Global Constraints

- URL layout: `/` portal (Vite `base` `/`), `/transelec/...` Transelec (Vite `base` `/transelec/`), `/api/...` unchanged.
- Navigation, not iframes; `frame-ancestors 'none'` stays.
- The OAuth callback always lands on `/`; no `next=` parameter anywhere.
- Only hashed build assets are cacheable: `/assets/` and `/transelec/assets/`. Everything else keeps `Cache-Control: no-store`.
- Local development is unchanged: `make transelec-dev` and `make campo-demo` keep working; dist-less environments keep the static serving a no-op.
- UI copy in Spanish, no em-dash or en-dash characters in visible copy.
- UI work passes the design-taste-frontend checks and a web-design-guidelines review (Task 3).
- Never commit a workbook or client data.

## Review Focus

- `/transelec/` with a trailing slash (what Vite's base produces) must load Transelec, both from the API (Task 1) and in Transelec's own router (Task 2).
- A signed-out visit to a Transelec deep link (`/transelec/pendientes?...`) must land on the front door, not on an empty page or a sign-in card (Task 2).
- A signed-in user with zero product grants must see a clear explanation, not an empty grid (Task 3).
- `/rodales` (not built yet) and any unknown top-level path must show the front door, never Transelec and never a 500 (Task 1).
- Two builds that both emit `assets/index-<hash>.js` must each be served from their own dist (Task 1).

---

### Task 1: Serve the portal at `/` and Transelec at `/transelec/`

**Files:**
- Modify: `apps/api/app/dashboard_static.py` (replace `mount_dashboard` with `mount_dashboards`)
- Modify: `apps/api/app/main.py:263-305` (wiring)
- Modify: `apps/api/app/http_hardening.py` (`_CACHEABLE_PATH_PREFIXES`)
- Test: `apps/api/tests/test_dashboard_static.py` (rewrite), `apps/api/tests/test_http_hardening.py` (one new test)

**Interfaces:**
- Produces: `PrefixedDashboard(segment: str, dist_dir: Path, page_paths: frozenset[str])`, `dist_dir_from_environment(env_var: str, default: Path) -> Path | None`, `mount_dashboards(app, *, root_dist: Path | None, prefixed: Sequence[PrefixedDashboard], reserved_root_segments: frozenset[str]) -> None`, constants `PORTAL_DIST_ENV = "CAMPO_PORTAL_DIST"`, `TRANSELEC_DIST_ENV = "CAMPO_TRANSELEC_DASHBOARD_DIST"`, `DEFAULT_PORTAL_DIST`, `DEFAULT_TRANSELEC_DIST`. Task 4 relies on the two env var names and default paths (`<repo>/apps/portal/dist`, `<repo>/products/transelect/dashboard/dist`).

- [ ] **Step 1: Rewrite the static-serving tests (failing)**

Replace `apps/api/tests/test_dashboard_static.py` up to (not including) `test_spa_page_paths_match_every_dashboard_route`, and keep that last test unchanged except its import. New content:

```python
"""Tests for app.dashboard_static against a standalone FastAPI app, so they
control the dist directories without a database or a session."""

from __future__ import annotations

import re
from pathlib import Path

from app.dashboard_static import PrefixedDashboard, mount_dashboards
from fastapi import FastAPI
from fastapi.testclient import TestClient

TRANSELEC_PAGES = frozenset({"transelec", "transelec/pendientes"})
RESERVED = frozenset({"api", "health", "transelec"})


def _build(tmp_path: Path, name: str, marker: str) -> Path:
    dist = tmp_path / name
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(f"<html><body>{marker}</body></html>")
    # Both builds emit the same hashed name on purpose (Review Focus).
    (dist / "assets" / "index-abc123.js").write_text(f"console.log('{marker}')")
    return dist


def _client(tmp_path: Path, *, portal: bool = True, transelec: bool = True) -> TestClient:
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    prefixed = (
        [PrefixedDashboard("transelec", _build(tmp_path, "transelec", "transelec shell"), TRANSELEC_PAGES)]
        if transelec
        else []
    )
    mount_dashboards(
        app,
        root_dist=_build(tmp_path, "portal", "portal shell") if portal else None,
        prefixed=prefixed,
        reserved_root_segments=RESERVED,
    )
    return TestClient(app)


def test_no_dist_at_all_registers_nothing(tmp_path: Path) -> None:
    client = _client(tmp_path, portal=False, transelec=False)
    assert client.get("/").status_code == 404


def test_root_serves_the_portal(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/")
    assert response.status_code == 200
    assert "portal shell" in response.text


def test_unknown_top_level_path_falls_back_to_the_portal(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for path in ("/rodales", "/rodales/mapa", "/cualquier-cosa"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "portal shell" in response.text, path


def test_transelec_pages_serve_the_transelec_shell_with_or_without_trailing_slash(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    for path in ("/transelec", "/transelec/", "/transelec/pendientes", "/transelec/pendientes/"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "transelec shell" in response.text, path


def test_each_build_serves_its_own_asset_with_the_same_name(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert "portal shell" in client.get("/assets/index-abc123.js").text
    assert "transelec shell" in client.get("/transelec/assets/index-abc123.js").text


def test_unknown_path_under_transelec_is_a_404_not_a_shell(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/transelec/does-not-exist")
    assert response.status_code == 404
    assert "shell" not in response.text


def test_reserved_segments_404_instead_of_the_portal(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/api/ping").json() == {"ok": "yes"}
    assert client.get("/api/no-such-route").status_code == 404
    assert client.get("/health/anything").status_code == 404


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/transelec/..%2F..%2Fportal%2Findex.html").status_code == 404


def test_transelec_only_still_serves_transelec(tmp_path: Path) -> None:
    client = _client(tmp_path, portal=False)
    assert "transelec shell" in client.get("/transelec").text
    assert client.get("/").status_code == 404
```

Keep `test_spa_page_paths_match_every_dashboard_route` as it is (it reads `products/transelect/dashboard/src/router.tsx` and compares with `app.main.TRANSELEC_SPA_PAGE_PATHS`); keep its `re` import.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest apps/api/tests/test_dashboard_static.py -q`
Expected: collection error, `ImportError: cannot import name 'PrefixedDashboard'`.

- [ ] **Step 3: Implement `mount_dashboards`**

Replace everything in `apps/api/app/dashboard_static.py` after `_resolve_within` (keep `_resolve_within` as is) and replace `DEFAULT_DIST_DIR` / `_dist_dir_from_environment` with:

```python
_REPO_ROOT = Path(__file__).resolve().parents[3]

PORTAL_DIST_ENV = "CAMPO_PORTAL_DIST"
TRANSELEC_DIST_ENV = "CAMPO_TRANSELEC_DASHBOARD_DIST"
DEFAULT_PORTAL_DIST = _REPO_ROOT / "apps" / "portal" / "dist"
DEFAULT_TRANSELEC_DIST = _REPO_ROOT / "products" / "transelect" / "dashboard" / "dist"


def dist_dir_from_environment(env_var: str, default: Path) -> Path | None:
    """The configured build directory, or None when no build is present."""

    configured = os.environ.get(env_var, "").strip()
    candidate = Path(configured) if configured else default
    return candidate if (candidate / "index.html").is_file() else None


@dataclass(frozen=True)
class PrefixedDashboard:
    """A product build served under its own first path segment.

    ``page_paths`` lists the frontend's own page paths (no leading slash,
    e.g. ``"transelec/pendientes"``); they share the segment with the API
    routes, so only these exact paths get the shell.
    """

    segment: str
    dist_dir: Path
    page_paths: frozenset[str]


def mount_dashboards(
    app: FastAPI,
    *,
    root_dist: Path | None,
    prefixed: Sequence[PrefixedDashboard],
    reserved_root_segments: frozenset[str],
) -> None:
    """Serve the portal at ``/`` and each product build under its segment.

    Must be called after every router is registered: it adds a catch-all.
    A no-op when no build is present (local dev, CI).
    """

    if root_dist is None and not prefixed:
        return

    for site in prefixed:
        if (site.dist_dir / "assets").is_dir():
            app.mount(
                f"/{site.segment}/assets",
                StaticFiles(directory=site.dist_dir / "assets"),
                name=f"{site.segment}-assets",
            )
    if root_dist is not None and (root_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root_dist / "assets"), name="portal-assets")

    by_segment = {site.segment: site for site in prefixed}

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_dashboard(full_path: str) -> FileResponse:
        first_segment = full_path.split("/", 1)[0]
        site = by_segment.get(first_segment)

        if site is not None:
            # Vite's base makes "/transelec/" the canonical entry; accept both.
            if full_path.rstrip("/") in site.page_paths:
                return FileResponse(site.dist_dir / "index.html")
            inner = full_path[len(first_segment) + 1 :]
            candidate = _resolve_within(site.dist_dir, inner) if inner else None
            if candidate is not None and candidate.is_file():
                return FileResponse(candidate)
            raise HTTPException(status_code=404)

        if first_segment in reserved_root_segments or root_dist is None:
            raise HTTPException(status_code=404)

        if not full_path:
            return FileResponse(root_dist / "index.html")

        candidate = _resolve_within(root_dist, full_path)
        if candidate is None:
            raise HTTPException(status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(root_dist / "index.html")
```

Add imports at the top: `from collections.abc import Sequence` and `from dataclasses import dataclass`. Update the module docstring's first paragraph to say it serves the portal at `/` and product builds under their own segment.

- [ ] **Step 4: Wire it in `app.main`**

In `apps/api/app/main.py`, change the import to
`from app.dashboard_static import (DEFAULT_PORTAL_DIST, DEFAULT_TRANSELEC_DIST, PORTAL_DIST_ENV, TRANSELEC_DIST_ENV, PrefixedDashboard, dist_dir_from_environment, mount_dashboards)`
and replace the `mount_dashboard(...)` call (keep `TRANSELEC_SPA_PAGE_PATHS` and its comment) with:

```python
_transelec_dist = dist_dir_from_environment(TRANSELEC_DIST_ENV, DEFAULT_TRANSELEC_DIST)

mount_dashboards(
    app,
    root_dist=dist_dir_from_environment(PORTAL_DIST_ENV, DEFAULT_PORTAL_DIST),
    prefixed=(
        [PrefixedDashboard("transelec", _transelec_dist, TRANSELEC_SPA_PAGE_PATHS)]
        if _transelec_dist is not None
        else []
    ),
    reserved_root_segments=frozenset(
        {
            "health",
            "ready",
            "runs",
            "ingesta",
            "auth",
            "api",
            # Reserved even where unmounted (production), so they 404
            # instead of falling through to the portal.
            "docs",
            "redoc",
            "openapi.json",
        }
    ),
)
```

Update the comment above it: the portal is served at `/`, Transelec under `/transelec/`, still a no-op without builds.

- [ ] **Step 5: Cache `/transelec/assets/` like `/assets/`**

Add to `apps/api/tests/test_http_hardening.py`, next to `test_hashed_static_assets_stay_cacheable` (reuse its `_headers_app` helper; add a matching route `@app.get("/transelec/assets/index-abc.js")` to that helper the same way `/assets/index-abc.js` is defined at line ~329):

```python
def test_transelec_hashed_assets_stay_cacheable() -> None:
    response = _headers_app("production").get("/transelec/assets/index-abc.js")
    assert "cache-control" not in response.headers or response.headers["cache-control"] != "no-store"
```

Mirror the exact assertion style of `test_hashed_static_assets_stay_cacheable`. Then in `apps/api/app/http_hardening.py` set:

```python
_CACHEABLE_PATH_PREFIXES = ("/assets/", "/transelec/assets/")
```

- [ ] **Step 6: Run the API suite**

Run: `uv run pytest apps/api/tests -q && uv run ruff check apps/api && uv run ruff format --check apps/api`
Expected: all pass (the previous `test_main_docs_exposure.py` still passes: `/docs` stays reserved).

- [ ] **Step 7: Commit**

```bash
git add apps/api
git commit -m "feat(api): serve the portal at / and Transelec under /transelec/"
```

---

### Task 2: Transelec under `/transelec/`, "Cambiar proyecto", sign-in at the front door

**Files:**
- Modify: `products/transelect/dashboard/vite.config.ts` (add `base: '/transelec/'`)
- Create: `products/transelect/dashboard/src/runtime/frontDoor.ts`
- Modify: `products/transelect/dashboard/src/App.tsx:~134` (401 branch)
- Modify: `products/transelect/dashboard/src/components/AppHeader.tsx:~170` (link)
- Modify: `products/transelect/dashboard/src/router.tsx` (normalize trailing slash)
- Modify: `products/transelect/dashboard/src/styles/components.css` (`.project-switch`)
- Modify: `scripts/transelec_dev.py:153,179` (URLs under `/transelec/`)
- Test: `products/transelect/dashboard/src/runtime/frontDoor.test.ts`, `src/App.test.tsx`, `src/components/Chrome.test.tsx`, router test file (see Step 1)

**Interfaces:**
- Produces: `platformFrontDoorEnabled(): boolean` (true only when built with `VITE_PLATFORM_FRONT_DOOR=true`), `PLATFORM_FRONT_DOOR_PATH = '/'`. Task 4 sets that env var in the Dockerfile.

- [ ] **Step 1: Failing tests**

`src/runtime/frontDoor.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { platformFrontDoorEnabled } from './frontDoor'

describe('platformFrontDoorEnabled', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('is off unless the build opts in', () => {
    vi.stubEnv('VITE_PLATFORM_FRONT_DOOR', '')
    expect(platformFrontDoorEnabled()).toBe(false)
  })

  it('is on when built with VITE_PLATFORM_FRONT_DOOR=true', () => {
    vi.stubEnv('VITE_PLATFORM_FRONT_DOOR', 'true')
    expect(platformFrontDoorEnabled()).toBe(true)
  })
})
```

In `src/App.test.tsx`, add (follow the file's existing pattern for making `getMe` answer 401; read how the current "shows the sign-in card when signed out" test stubs the session and copy it):

```ts
it('sends a signed-out visitor to the front door when the platform has one', async () => {
  vi.stubEnv('VITE_PLATFORM_FRONT_DOOR', 'true')
  const assign = vi.fn()
  vi.stubGlobal('location', { ...window.location, assign, pathname: '/transelec/pendientes', search: '?q=1' })
  // arrange getMe() -> 401 exactly as the existing signed-out test does
  render(<App />)
  await waitFor(() => expect(assign).toHaveBeenCalledWith('/'))
  expect(screen.queryByText('Inicie sesión para continuar')).not.toBeInTheDocument()
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})
```

In `src/components/Chrome.test.tsx` (it renders `AppHeader`; reuse its render helper):

```ts
it('links back to the project picker only on the unified platform', () => {
  vi.stubEnv('VITE_PLATFORM_FRONT_DOOR', 'true')
  renderHeader()
  expect(screen.getByRole('link', { name: 'Cambiar proyecto' })).toHaveAttribute('href', '/')
  vi.unstubAllEnvs()
})

it('has no project picker link in a standalone build', () => {
  renderHeader()
  expect(screen.queryByRole('link', { name: 'Cambiar proyecto' })).not.toBeInTheDocument()
})
```

(`renderHeader` = the helper the file already uses to render `AppHeader`; if it has a different name, use that.)

For the router, add to the existing router test (search `src/**/router*.test.tsx`; if none exists, create `src/router.test.tsx`):

```tsx
it('treats /transelec/ like /transelec', () => {
  let seen = ''
  function Probe() {
    seen = useRouter().pathname
    return null
  }
  render(
    <RouterProvider initialPath="/transelec/">
      <Probe />
    </RouterProvider>,
  )
  expect(seen).toBe('/transelec')
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd products/transelect/dashboard && npx vitest run src/runtime/frontDoor.test.ts src/App.test.tsx src/components/Chrome.test.tsx src/router.test.tsx`
Expected: FAIL (module `./frontDoor` missing; no link; no redirect; pathname `/transelec/`).

- [ ] **Step 3: Implement**

`src/runtime/frontDoor.ts`:

```ts
/**
 * On the unified Campo Digital platform, sign-in and the project picker live
 * at the front door (`/`, apps/portal); Transelec is served under
 * `/transelec/`. Compiled in at build time (the Dockerfile sets
 * VITE_PLATFORM_FRONT_DOOR=true); a standalone or local build keeps its own
 * sign-in card.
 */
export const PLATFORM_FRONT_DOOR_PATH = '/'

export function platformFrontDoorEnabled(): boolean {
  return import.meta.env.VITE_PLATFORM_FRONT_DOOR === 'true'
}
```

`App.tsx` 401 branch:

```tsx
if (sessionFailure?.status === 401) {
  if (platformFrontDoorEnabled()) {
    window.location.assign(PLATFORM_FRONT_DOOR_PATH)
    return null
  }
  return <LoginCard demoAvailable={demoSignInAvailable()} onSignedIn={refreshSession} />
}
```

Update the comment above it: on the unified platform the signed-out state belongs to the front door.

`AppHeader.tsx`, right after the wordmark `</Link>`:

```tsx
{platformFrontDoorEnabled() && (
  <a className="project-switch" href={PLATFORM_FRONT_DOOR_PATH}>
    Cambiar proyecto
  </a>
)}
```

`components.css`, after `.wordmark-text`:

```css
.project-switch {
  flex-shrink: 0;
  padding: var(--s-2) var(--s-4);
  border: 1px solid rgb(255 255 255 / 0.28);
  border-radius: var(--r-control);
  color: var(--ink-inverse);
  font-size: var(--t-small);
  font-weight: 600;
  text-decoration: none;
  white-space: nowrap;
  transition: background-color var(--d-fast) var(--ease);
}

.project-switch:hover {
  background: rgb(255 255 255 / 0.1);
}
```

`router.tsx`: in `splitLocation`, strip one trailing slash from a pathname longer than `/`:

```ts
function splitLocation(value: string): { pathname: string; search: string } {
  const index = value.indexOf('?')
  const rawPath = index === -1 ? value : value.slice(0, index)
  const search = index === -1 ? '' : value.slice(index)
  const pathname = rawPath.length > 1 && rawPath.endsWith('/') ? rawPath.slice(0, -1) : rawPath
  return { pathname, search }
}
```

Also apply the same normalization where `RouterProvider` reads `window.location.pathname` (initial state and `popstate`): call `splitLocation(window.location.pathname + window.location.search)` instead of reading the two fields separately.

`vite.config.ts`: add `base: '/transelec/',` to the `defineConfig` object with a comment: "Served under /transelec/ on the unified platform (docs/superpowers/specs/2026-09-28-unified-platform-design.md)".

`scripts/transelec_dev.py`: change `f"http://127.0.0.1:{port}/"` (line ~153, the frontend wait) and `frontend_url = f"http://127.0.0.1:{frontend_port}/"` (line ~179) to end in `/transelec/`.

- [ ] **Step 4: Run all Transelec checks**

Run: `cd products/transelect/dashboard && npm run lint && npm run build && npx vitest run && npx playwright test`
Expected: all pass. `dist/index.html` references `/transelec/assets/...`. If a Playwright spec navigates to `/`, change it to `/transelec/`.

- [ ] **Step 5: Commit**

```bash
git add products/transelect/dashboard scripts/transelec_dev.py
git commit -m "feat(transelec): serve under /transelec/ with a link back to the project picker"
```

---

### Task 3: Portal production mode: sign-in and project picker

**Files:**
- Modify: `apps/portal/src/runtime/environment.ts` (add `'production'`)
- Modify: `apps/portal/src/App.tsx` (production renders `FrontDoor` only)
- Create: `apps/portal/src/pages/FrontDoor.tsx`, `apps/portal/src/pages/FrontDoor.test.tsx`, `apps/portal/src/styles/front-door.css`
- Create: `apps/portal/src/assets/campo-digital-logo.png` (copy of `products/transelect/dashboard/src/assets/campo-digital-logo.png`)
- Test: `apps/portal/src/runtime/environment.test.ts` (extend)

**Interfaces:**
- Consumes: `getMe(): Promise<ApiResult<Me>>`, `logout(): Promise<ApiResult<void>>`, `Me`, `ProductKey` from `apps/portal/src/lib/platformApi.ts` (existing).
- Produces: `CampoEnvironment = 'local' | 'staging' | 'production'`; `FrontDoor` component; `PRODUCT_CARDS` array (Task 3 of step 3 will set Rodales' `href` to `/rodales`).

- [ ] **Step 1: Failing tests**

Extend `environment.test.ts` (follow its existing `vi.stubEnv` style):

```ts
it('recognises the production build', () => {
  vi.stubEnv('VITE_CAMPO_ENV', 'production')
  expect(getCampoEnvironment()).toBe('production')
})
```

`FrontDoor.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../lib/platformApi'
import { FrontDoor } from './FrontDoor'

vi.mock('../lib/platformApi', async (importOriginal) => {
  const actual = await importOriginal<typeof api>()
  return { ...actual, getMe: vi.fn(), logout: vi.fn() }
})

const me = (grants: api.ProductGrant[]): api.ApiResult<api.Me> => ({
  ok: true,
  data: { identity_key: 'sub-1', display_name: 'Javier Soto', product_grants: grants },
})

describe('FrontDoor', () => {
  beforeEach(() => vi.mocked(api.getMe).mockReset())

  it('offers Google sign-in when signed out', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ok: false, status: 401, error: 'no session' })
    render(<FrontDoor />)
    const link = await screen.findByRole('link', { name: 'Iniciar sesión con Google' })
    expect(link).toHaveAttribute('href', '/api/auth/google/login')
  })

  it('shows only the projects the user can open', async () => {
    vi.mocked(api.getMe).mockResolvedValue(me([{ product_key: 'transelect', role: 'viewer' }]))
    render(<FrontDoor />)
    expect(await screen.findByText('Hola, Javier Soto')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Transelec/ })).toHaveAttribute('href', '/transelec/')
    expect(screen.queryByText('Rodales')).not.toBeInTheDocument()
  })

  it('shows a project that is not online yet as upcoming, without a link', async () => {
    vi.mocked(api.getMe).mockResolvedValue(
      me([
        { product_key: 'transelect', role: 'admin' },
        { product_key: 'forestry', role: 'admin' },
      ]),
    )
    render(<FrontDoor />)
    expect(await screen.findByText('Rodales')).toBeInTheDocument()
    expect(screen.getByText('Próximamente')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Rodales/ })).not.toBeInTheDocument()
  })

  it('explains an account with no projects', async () => {
    vi.mocked(api.getMe).mockResolvedValue(me([]))
    render(<FrontDoor />)
    expect(await screen.findByText(/no tiene proyectos asignados/)).toBeInTheDocument()
  })

  it('reports an unreachable platform instead of asking to sign in', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ok: false, status: 503, error: 'down' })
    render(<FrontDoor />)
    expect(await screen.findByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Iniciar sesión con Google' })).not.toBeInTheDocument()
  })

  it('signs out back to the sign-in view', async () => {
    vi.mocked(api.getMe).mockResolvedValue(me([{ product_key: 'transelect', role: 'viewer' }]))
    vi.mocked(api.logout).mockResolvedValue({ ok: true, data: undefined })
    render(<FrontDoor />)
    await userEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Iniciar sesión con Google' })).toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/portal && npx vitest run src/pages/FrontDoor.test.tsx src/runtime/environment.test.ts`
Expected: FAIL (`./FrontDoor` missing; environment returns `'local'`).

- [ ] **Step 3: Implement**

`environment.ts`:

```ts
export type CampoEnvironment = 'local' | 'staging' | 'production'

export function getCampoEnvironment(): CampoEnvironment {
  const value = import.meta.env.VITE_CAMPO_ENV
  return value === 'staging' || value === 'production' ? value : 'local'
}
```

Update its doc comment: `production` is the unified platform's front door, set by the Dockerfile. Run `npx tsc -b`; any `Record<CampoEnvironment, …>` or exhaustive switch now needs a `production` entry: give it the staging value (production never renders those pages, see `App.tsx`).

`App.tsx`: before the router, `if (getCampoEnvironment() === 'production') return <FrontDoor />` inside `App` (production has no module pages, no `/estado`, no `/archivos`).

`FrontDoor.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import logo from '../assets/campo-digital-logo.png'
import { getMe, logout, type Me, type ProductKey } from '../lib/platformApi'
import '../styles/front-door.css'

export interface ProductCard {
  key: ProductKey
  title: string
  description: string
  /** Where the product lives on this origin; null while it is not online. */
  href: string | null
}

export const PRODUCT_CARDS: readonly ProductCard[] = [
  {
    key: 'transelect',
    title: 'Transelec',
    description: 'Seguimiento de planes de manejo forestal y predios asociados.',
    href: '/transelec/',
  },
  {
    key: 'forestry',
    title: 'Rodales',
    description: 'Patrimonio Degenfeld: rodales, usos de suelo y superficies.',
    href: null,
  },
  {
    key: 'lidar',
    title: 'Cubicación LiDAR',
    description: 'Inspección de nubes de puntos de pilas de madera.',
    href: null,
  },
]

export const GOOGLE_LOGIN_PATH = '/api/auth/google/login'

type State =
  | { kind: 'loading' }
  | { kind: 'signed-out' }
  | { kind: 'unreachable' }
  | { kind: 'signed-in'; me: Me }

export function FrontDoor() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  const load = useCallback(async () => {
    setState({ kind: 'loading' })
    const result = await getMe()
    if (result.ok) setState({ kind: 'signed-in', me: result.data })
    else if (result.status === 401) setState({ kind: 'signed-out' })
    else setState({ kind: 'unreachable' })
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const signOut = async () => {
    const result = await logout()
    if (result.ok) setState({ kind: 'signed-out' })
  }

  return (
    <div className="door">
      <header className="door__bar">
        <img className="door__logo" src={logo} alt="Campo Digital" width={103} height={44} />
        {state.kind === 'signed-in' ? (
          <button type="button" className="door__signout" onClick={() => void signOut()}>
            Cerrar sesión
          </button>
        ) : null}
      </header>
      <main className="door__main">
        {state.kind === 'loading' ? <p className="door__muted">Verificando la sesión…</p> : null}
        {state.kind === 'signed-out' ? (
          <section className="door__panel" aria-labelledby="door-title">
            <h1 id="door-title">Plataforma Campo Digital</h1>
            <p className="door__muted">Ingresa con tu cuenta de Campo Digital para ver tus proyectos.</p>
            <a className="door__primary" href={GOOGLE_LOGIN_PATH}>
              Iniciar sesión con Google
            </a>
          </section>
        ) : null}
        {state.kind === 'unreachable' ? (
          <section className="door__panel" role="alert">
            <h1>No se pudo contactar la plataforma</h1>
            <p className="door__muted">Revisa tu conexión y vuelve a intentarlo.</p>
            <button type="button" className="door__primary" onClick={() => void load()}>
              Reintentar
            </button>
          </section>
        ) : null}
        {state.kind === 'signed-in' ? <Projects me={state.me} /> : null}
      </main>
    </div>
  )
}

function Projects({ me }: { me: Me }) {
  const granted = new Set(me.product_grants.map((grant) => grant.product_key))
  const cards = PRODUCT_CARDS.filter((card) => granted.has(card.key))

  return (
    <section aria-labelledby="door-hello">
      <h1 id="door-hello">Hola, {me.display_name}</h1>
      {cards.length === 0 ? (
        <p className="door__muted">
          Tu cuenta no tiene proyectos asignados. Pide acceso a un administrador de Campo Digital.
        </p>
      ) : (
        <>
          <p className="door__muted">Elige un proyecto.</p>
          <ul className="door__grid">
            {cards.map((card) => (
              <li key={card.key}>
                {card.href !== null ? (
                  <a className="door__card" href={card.href}>
                    <span className="door__card-title">{card.title}</span>
                    <span className="door__card-text">{card.description}</span>
                  </a>
                ) : (
                  <div className="door__card door__card--soon" aria-disabled="true">
                    <span className="door__card-title">{card.title}</span>
                    <span className="door__card-text">{card.description}</span>
                    <span className="door__soon">Próximamente</span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
```

`front-door.css`: the Campo Digital palette (same values as `products/transelect/dashboard/src/styles/tokens.css`: ink `#16211d`, ink-2 `#42524c`, ground `#f4f5f2`, surface `#fbfbfa`, line `#dde1db`, forest `#1e8055`, forest-deep `#15503a`, forest-dark `#0f3b2b`, focus `#0b6ea8`). Layout: 56px bar with `linear-gradient(100deg, #0f3b2b, #15503a)` and the 44px logo; main column `max-width: 960px; margin: 48px auto; padding: 0 16px`; cards in `grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px`, each card surface + 1px line + 8px radius + `0 1px 2px rgb(22 33 29 / 0.06)` shadow, hover lifts border to forest and `translateY(-1px)` (transform only, 120ms, disabled under `prefers-reduced-motion`); `:focus-visible` outline `2px solid #0b6ea8`; the soon card at 70% opacity with a pill "Próximamente"; primary button forest background, `#f2f6f3` text, 6px radius, min-height 40px. Define colors as custom properties on `.door`, no inline styles.

- [ ] **Step 4: Run portal checks**

Run: `cd apps/portal && npm run lint && npm run build && npx vitest run && VITE_CAMPO_ENV=production npm run build`
Expected: all pass; the production build contains no reference to `campo-runtime.json` fetching on load (grep `dist/assets/*.js` for `campo-runtime` finds only the dead-code-free result or none; at minimum `App` renders `FrontDoor` first).

- [ ] **Step 5: UI pass**

Take screenshots of the production build served by the API (Task 4 Step 3 does the serving; here use `npx vite --mode production` with `VITE_CAMPO_ENV=production` and the API running via `make platform-local`, signed in via dev login from another tab) for: signed out, signed in with one project, signed in with none. Check against design-taste-frontend's pre-flight (contrast, one accent, one radius system, no em-dash, no wrapped CTA) and run the web-design-guidelines review on `FrontDoor.tsx` and `front-door.css`; fix every finding.

- [ ] **Step 6: Commit**

```bash
git add apps/portal
git commit -m "feat(portal): production front door with Google sign-in and project picker"
```

---

### Task 4: Build both apps into the container and verify the URL layout

**Files:**
- Modify: `Dockerfile` (portal build stage; `VITE_PLATFORM_FRONT_DOOR=true` for Transelec; copy both dists)
- Modify: `.dockerignore` if it excludes `apps/portal` (check; it must not)

**Interfaces:**
- Consumes: `DEFAULT_PORTAL_DIST` = `/app/apps/portal/dist` and `DEFAULT_TRANSELEC_DIST` = `/app/products/transelect/dashboard/dist` in the image (Task 1), `VITE_PLATFORM_FRONT_DOOR` (Task 2), `VITE_CAMPO_ENV=production` (Task 3).

- [ ] **Step 1: Dockerfile**

In the Transelec build stage, before `RUN npm run build`: `ENV VITE_PLATFORM_FRONT_DOOR=true`. Add a stage after it:

```dockerfile
# ---- Stage 1b: build the Campo Digital front door (apps/portal) ------------
FROM node:24.19.0-slim AS portal-build

WORKDIR /portal

COPY apps/portal/package.json apps/portal/package-lock.json ./
RUN npm ci

COPY apps/portal/ ./
ENV VITE_CAMPO_ENV=production
RUN npm run build
```

In the runtime stage, next to the existing dashboard copy:

```dockerfile
COPY --from=portal-build /portal/dist ./apps/portal/dist
```

Update the Stage 1 comment to say the image serves the front door at `/` and Transelec at `/transelec/`.

- [ ] **Step 2: Build the image**

Run: `docker build -t campo-platform:front-door .`
Expected: success.

- [ ] **Step 3: Verify the URL layout without production secrets**

Run the API from the host against the two local builds (no DB needed for static routes):

```bash
(cd apps/portal && VITE_CAMPO_ENV=production npm run build)
(cd products/transelect/dashboard && VITE_PLATFORM_FRONT_DOOR=true npm run build)
APP_ENV=test uv run --extra api uvicorn app.main:app --app-dir apps/api --port 8765 &
for p in / /rodales /transelec /transelec/ /transelec/pendientes /transelec/does-not-exist /api/nope; do
  echo "$p $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765$p)"
done
curl -s http://127.0.0.1:8765/ | grep -o 'assets/index-[^"]*'
curl -s http://127.0.0.1:8765/transelec/ | grep -o '/transelec/assets/index-[^"]*'
kill %1
```

Expected: `/`, `/rodales`, `/transelec`, `/transelec/`, `/transelec/pendientes` answer 200; `/transelec/does-not-exist` and `/api/nope` answer 404; the portal page references `/assets/...` and Transelec's references `/transelec/assets/...`, and both asset URLs answer 200. Then open `/` and `/transelec/` in a browser (Playwright screenshot) and confirm no CSP violations in the console.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "build: ship the front door at / and Transelec under /transelec/"
```

---

### Task 5: Documentation

**Files:**
- Modify: `products/transelect/docs/deployment.md` (URL layout, two builds, env vars `CAMPO_PORTAL_DIST`, `VITE_PLATFORM_FRONT_DOOR`, `VITE_CAMPO_ENV=production`)
- Modify: `docs/platform/company-portal-v1.md` (new "Production mode" section: sign-in and picker, no iframes, why)
- Modify: `docs/superpowers/specs/2026-09-28-unified-platform-design.md` (Status: step 1 implemented on `feat/unified-platform`, not deployed)
- Create: `products/transelect/docs/es/2026-09-28-plataforma-unificada.md` (Spanish, for Campo Digital: what changes for Javier: open the main address, sign in, choose Transelec; bookmarks to `/transelec` still work and ask to sign in at the front door first)

- [ ] **Step 1: Write the four documents** (English canonical, Spanish summary; FACT / DECISION / OPEN QUESTION labels as in `docs/DOCUMENTATION_POLICY.md`; no workbook values).

- [ ] **Step 2: Check**

Run: `uv run python scripts/update_doc_nav.py && uv run python scripts/check_doc_links.py`
Expected: `Documentation links OK`.

- [ ] **Step 3: Commit**

```bash
git add docs products/transelect/docs
git commit -m "docs: unified platform front door (step 1)"
```

- [ ] **Step 4: Open the PR** to `main` with the test evidence from Tasks 1-4, and state that deploying it moves Transelec to `/transelec/` and puts the front door at `/`.
