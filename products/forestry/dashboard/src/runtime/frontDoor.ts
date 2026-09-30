/**
 * On the unified Campo Digital platform, sign-in and the project picker live
 * at the front door (`/`, apps/portal); Rodales is served under `/rodales/`.
 * Compiled in at build time (the Dockerfile sets
 * VITE_PLATFORM_FRONT_DOOR=true); a local `make forestry-dev` build keeps its
 * own development sign-in instead.
 */
export const PLATFORM_FRONT_DOOR_PATH = '/'

export function platformFrontDoorEnabled(): boolean {
  return import.meta.env.VITE_PLATFORM_FRONT_DOOR === 'true'
}
