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
