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
