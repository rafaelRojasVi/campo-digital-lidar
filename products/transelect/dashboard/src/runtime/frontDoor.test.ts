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
