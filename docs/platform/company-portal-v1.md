# Campo Digital — Company Portal V1

## Status

**FACT** — a local company portal V1 exists at `apps/portal/` and is
implemented (Phase 5 of the [platform roadmap](roadmap.md)).

**FACT** — local module navigation/composition (portal home, per-module
shells, iframe embedding, module switcher, back navigation) is implemented.

**FACT** — the portal is also deployed to a $0 Render STAGING blueprint
(`render.yaml`, `ADR-005`), explicitly LOCAL/STAGING-aware
([ADR-007](../adr/ADR-007-hosted-product-composition-v1.md)), with one
hosted product module (LiDAR) and an honest not-yet-hosted state for the
other two. This is still not production: STAGING has no real sign-in
mechanism (dev-auth is development-only per
[ADR-006](../adr/ADR-006-restrict-dev-auth-to-development.md), and Entra ID
sign-in remains externally blocked), no durable object storage, and no
multi-tenant access. See [Production platform V1](production-platform-v1.md)
and [Environments and infrastructure costs](environments-and-costs.md) for
what production would still require.

**OPEN QUESTION** — Entra ID sign-in, and therefore any real STAGING
authentication, remains externally blocked; Phase 6 (production deployment)
remains unstarted.

## Purpose

Campo Digital is one company platform with three bounded products (LiDAR /
Cubicación, Gestión Predial Forestal, Transelec — see
[product boundaries](product-boundaries.md)). Before this work, there was no
single entry point that made that coherent: each product had its own
standalone dev launcher and its own standalone dashboard.

The company portal is a thin, company-branded shell around the three
existing, independently owned product dashboards. It does not merge their
domain models, their persistence, or their frontends. It only gives them a
shared front door, shared branding, and a shared local demo launcher.

## Architecture decision

- The portal is its own application at `apps/portal/` (React + TypeScript +
  Vite), not inside any single product's folder. This matches
  [`ARCHITECTURE.md`](../../ARCHITECTURE.md): "Product applications must not
  directly import another product application." The portal does not import
  any product's frontend code; it treats each product dashboard as an
  external URL.
- **Composition strategy: iframe, in both LOCAL and STAGING.** Each product
  dashboard keeps running as its own independent origin — a local Vite dev
  server in LOCAL, or its own deployed Render static site in STAGING. The
  portal embeds it inside a thin Campo Digital header (`← Campo Digital`,
  current module name, a compact module switcher, "Abrir en pestaña nueva")
  using an `<iframe>` that fills the remaining viewport. This was chosen
  because it lets independently developed, independently versioned
  dashboards be composed from one URL without rewriting any of them —
  including once a dashboard becomes hosted, per
  [ADR-007](../adr/ADR-007-hosted-product-composition-v1.md).
- The portal never imports, reads, or renders another product's source code.
  It only knows: a module's id, its display copy/facts, and (at runtime) the
  URL and status a launcher (LOCAL) or build-time hosted-module registry
  (STAGING) told it about.
- **The portal is explicitly LOCAL/STAGING-aware**, not just "always assume
  local." `apps/portal/src/runtime/environment.ts` resolves a build-time
  `CampoEnvironment` from `VITE_CAMPO_ENV`; `/estado` and every module's
  unavailable-state copy branch on it, so a public STAGING visitor never
  sees local-only language like "Demo no iniciada" or "Iniciado por Campo
  Demo." See [ADR-007](../adr/ADR-007-hosted-product-composition-v1.md) for
  the full mechanism and the per-product hosting decision it records.

## Information architecture

The home screen (`/`) is stakeholder-facing, in Spanish, and shows only
evidence-backed facts:

- Cubicación LiDAR — capability description only (point-cloud inspection,
  geometry/QC, 3D preview); LiDAR does not yet have a stakeholder-safe
  volume/cubicación number to show, and none is invented here.
- Gestión Predial Forestal — 1.568 polígonos de origen, ≈10.422,61 ha
  derivadas de geometría (from the Degenfeld source evidence already
  established elsewhere in the repository).
- Transelec — 159 PMF, 272 identificadores provisionales de predio, 164,63
  ha de superficie de corta (from the Transelec source contract already
  established elsewhere in the repository).

Branch names, commit hashes, PIDs, ports, and stack traces are deliberately
never shown on this screen. `/estado` is a separate, unlinked-from-nav
developer diagnostics view that does show per-module port/URL/ownership —
useful when demoing, not meant for Javier.

Routes:

- `/` — company home, three product panels.
- `/modulo/lidar`, `/modulo/forestal`, `/modulo/transelec` — module shells.
- `/estado` — status diagnostics. LOCAL: ports, URLs, process ownership.
  STAGING: hosted availability, no process-ownership column.
- `/archivos` — the ingestion/access UI (upload, jobs, audit), first-class
  in the Home nav. LOCAL: local dev-identity sign-in. STAGING: an honest
  "sign-in not available yet" message, since dev-auth is
  development-only ([ADR-006](../adr/ADR-006-restrict-dev-auth-to-development.md))
  and no other sign-in exists yet.

## STAGING hosted composition

See [ADR-007](../adr/ADR-007-hosted-product-composition-v1.md) for the full
decision record. Summary:

- **LiDAR is hosted.** `campo-digital-lidar-staging` is a new Render free
  static site (`render.yaml`) serving `products/lidar/dashboard` unmodified,
  talking to the already-deployed `campo-digital-api-staging` service via
  the same same-origin `/api/*` rewrite the portal itself uses. No new
  backend, no new database, no synthetic or real data shipped — the hosted
  state is a genuinely empty `GET /runs` response, verified against a local
  API instance configured the same way Render's fresh checkout will be.
- **Forestry and Transelec are not hosted this slice.** The portal shows an
  honest "not yet available publicly" state for both — never a fake green
  status — because hosting either safely would require either fabricating
  synthetic business data (Forestry) or standing up durable storage this
  free tier does not support for a design that was never meant to be public
  (Transelec). See ADR-007's classification for the evidence behind both.

## Local demo orchestrator

```
make campo-demo      # start (or adopt) all three products + the portal
make campo-status     # read-only status, refreshes the portal's runtime config
make campo-stop       # stop only what campo-demo itself started
```

`scripts/campo_demo.py` is a composition shell over three independently
owned launchers:

- **LiDAR** — `make lidar-dev` / `make lidar-status` / `make lidar-stop` in
  *this* worktree (`scripts/lidar_dev.py`, new in this change — LiDAR had no
  single-command launcher before). It starts the existing FastAPI app and
  the existing Vite viewer on free ports. It does not ingest anything and
  does not change scientific/measurement behavior. The viewer's own
  readiness is checked against `/health` (dependency-free), not `/ready`
  (which requires PostgreSQL), so the *viewer* never depends on the
  database — but the shared API it starts alongside it now also serves the
  platform ingestion/access routers, so starting it brings up the local
  `postgres` service and applies migrations first (`scripts/_platform_db.py`;
  see [source ingestion](source-ingestion.md) and
  [production platform V1](production-platform-v1.md)).
- **Forestry** — `make forestry-dev` / `-status` / `-stop`, unchanged,
  invoked in the sibling worktree checked out at
  `feat/forestry-dashboard-v1`.
- **Transelec** — `make transelec-dev` / `-status` / `-stop`, unchanged,
  invoked in the sibling worktree checked out at
  `feat/transelec-ui-reference-parity-v1`.

`campo_demo.py` does not reimplement any product's process management. It
only decides *whether* to invoke a product's own launcher, and reads that
launcher's own on-disk process record to check status.

### Worktree discovery

Sibling worktrees are discovered with `git worktree list --porcelain` and
matched by branch name (`scripts/campo_demo.py:parse_worktree_porcelain`,
`find_worktree_for_branch`). No absolute path is hard-coded. Sibling
worktrees are read-only from this script's perspective: it never clones,
resets, merges, or writes into them, beyond invoking their own `make
<product>-dev` / `make <product>-stop` targets exactly as a developer would
by hand.

If a worktree for a required branch is not present locally, the
corresponding module is reported unavailable — nothing is cloned, and the
portal still starts normally with that one module showing "Demo no
iniciada."

### Process ownership

A product is only ever stopped by `make campo-stop` if `campo-demo` itself
started it in the current session:

1. Before starting anything, `campo_demo.py` does a read-only probe of each
   product's own on-disk process state (LiDAR's `.lidar-dev/`, Forestry's
   `.forestry-dev/`, Transelec's temp-dir state file — the same files their
   own launchers already maintain).
2. If a product is already running and responding, it is **adopted**: shown
   as available in the portal, but recorded as *not* owned by this session.
3. Only modules this script actually started are recorded as owned
   (`.campo-demo/state.json`), and only owned modules are stopped by `make
   campo-stop`. The portal's own dev server is always owned (nothing else
   starts it).

This was verified against a real pre-existing Forestry dev server: `make
campo-demo` correctly adopted it without restarting it, and `make
campo-stop` left it running while stopping the LiDAR and Transelec
instances this session had started.

### Runtime config

`campo_demo.py` writes `apps/portal/public/campo-runtime.json` (git-ignored,
machine-specific) with each module's `status` (`available` /
`unavailable`), `url`, and `owned` flag, plus the portal's own port and a
generation timestamp. The portal fetches this at runtime (not build time),
so a browser refresh picks up a fresh launcher run without rebuilding the
portal. Only loopback (`127.0.0.1` / `localhost`) `http(s)` URLs are ever
used as an iframe `src` or an "open in new tab" target
(`apps/portal/src/lib/safeUrl.ts`); a malformed or hand-edited runtime file
degrades to "unavailable" rather than being trusted.

## What remains before production

- Authentication/session entry point (none exists).
- A real decision on production routing/composition — the local iframe
  strategy is explicitly not that decision.
- Deployment, TLS, and a real domain (Phase 6, still unstarted).
- A LiDAR stakeholder-safe cubicación figure, if one is ever established —
  none is shown today, and none should be invented.

## Related documentation

[Platform documentation](README.md) ·
[Platform roadmap](roadmap.md) ·
[Product boundaries](product-boundaries.md) ·
[Production platform V1](production-platform-v1.md)
