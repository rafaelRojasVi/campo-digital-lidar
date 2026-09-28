/**
 * The production case, proven against the artifact that actually ships.
 *
 * Every other test in this suite runs under the Vite dev server's semantics,
 * where `import.meta.env.DEV` is true. That can show the demo branch is
 * hidden when the boundary is closed; it cannot show what a real deployment
 * contains. This test builds the bundle the Dockerfile's `dashboard-build`
 * stage builds (`vite build`, the same command `npm run build` runs) and
 * asserts the demo sign-in path is absent from the output.
 *
 * Absent, not merely unreachable: no seeded identity key, no dev-login path,
 * no demo copy. A reviewer reading only the source could be convinced a
 * conditional is correct; this reads the shipped bytes instead. It is the
 * frontend half of the same guarantee
 * apps/api/tests/test_main_dev_auth_gate.py enforces on the server, where
 * `/auth/dev-login` is not mounted outside APP_ENV=development at all.
 */
import { execFileSync } from 'node:child_process'
import { readFileSync, readdirSync, rmSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { beforeAll, describe, expect, it } from 'vitest'

const DASHBOARD_ROOT = resolve(import.meta.dirname, '../..')
const OUT_DIR = join(DASHBOARD_ROOT, 'node_modules/.tmp/production-bundle-guard')

let bundle = ''

/** Every string that must not survive into a deployable artifact. */
const FORBIDDEN = [
  'dev-login',
  'dev-admin',
  'dev-viewer',
  'Entrar como administrador de demostración',
  'Ver como Javier — solo lectura',
]

/** …and the sign-in that must be there instead. */
const REQUIRED = ['Continuar con Google', '/api/auth/google/login']

/**
 * Transelec signs in with Google Workspace (ADR-010). Microsoft Entra is
 * still the platform's provider for the other products and is still mounted
 * server-side, but this bundle must not offer it: two entrances would make
 * the shipped artifact contradict the one the client is told to use.
 */
const FORBIDDEN_PROVIDERS = ['Continuar con Microsoft', '/api/auth/entra/login']

describe('production bundle', () => {
  beforeAll(() => {
    rmSync(OUT_DIR, { recursive: true, force: true })
    execFileSync(
      join(DASHBOARD_ROOT, 'node_modules/.bin/vite'),
      ['build', '--mode', 'production', '--outDir', OUT_DIR, '--emptyOutDir', '--logLevel', 'silent'],
      {
        cwd: DASHBOARD_ROOT,
        stdio: 'pipe',
        // Vitest exports NODE_ENV=test into this process, and Vite reads it
        // in preference to the build's own mode — inheriting it would produce
        // a development bundle here and quietly make this whole guard
        // vacuous. `npm run build` and the Dockerfile both run with NODE_ENV
        // unset, where `vite build` defaults to production; say so outright.
        env: { ...process.env, NODE_ENV: 'production' },
      },
    )

    const assets = join(OUT_DIR, 'assets')
    bundle = readdirSync(assets)
      .filter((name) => name.endsWith('.js'))
      .map((name) => readFileSync(join(assets, name), 'utf-8'))
      .join('\n')

    expect(bundle.length).toBeGreaterThan(1000)
  }, 180_000)

  it.each(FORBIDDEN)('contains no trace of %j', (needle) => {
    expect(bundle).not.toContain(needle)
  })

  it.each(REQUIRED)('still ships the real identity provider: %j', (needle) => {
    expect(bundle).toContain(needle)
  })

  it.each(FORBIDDEN_PROVIDERS)('offers no second identity provider: %j', (needle) => {
    expect(bundle).not.toContain(needle)
  })
})
