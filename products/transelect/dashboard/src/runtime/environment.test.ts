/**
 * The demo-sign-in boundary must fail CLOSED.
 *
 * The property under test is not "development shows the buttons" — it is
 * that nothing other than actually running the Vite dev server can turn
 * them on. A missing, blank or hostile `VITE_*` value must not be able to
 * re-enable the seeded identities on a hosted deployment.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { demoSignInAvailable } from './environment'

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('demoSignInAvailable', () => {
  it('is available while the module graph is served by the Vite dev server', () => {
    vi.stubEnv('DEV', true)
    expect(demoSignInAvailable()).toBe(true)
  })

  it('is unavailable in a built artifact — the staging and production case', () => {
    vi.stubEnv('DEV', false)
    expect(demoSignInAvailable()).toBe(false)
  })

  it('stays unavailable in a build no matter what the VITE_ variables say', () => {
    // Every one of these is either unset in the Docker build or outside this
    // repository's control. None of them may be able to open the demo path.
    vi.stubEnv('DEV', false)
    vi.stubEnv('MODE', 'development')
    vi.stubEnv('VITE_CAMPO_ENV', 'local')
    expect(demoSignInAvailable()).toBe(false)

    vi.stubEnv('VITE_CAMPO_ENV', '')
    expect(demoSignInAvailable()).toBe(false)
  })
})
