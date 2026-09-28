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
