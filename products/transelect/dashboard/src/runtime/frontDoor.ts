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
