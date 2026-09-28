import type { CampoEnvironment } from '../runtime/environment'

/**
 * Runtime module URLs come from a launcher-generated JSON file, not from
 * user input, but they are still an external input to this app. Only
 * http(s) URLs pointing at loopback hosts are ever used as an iframe `src`
 * or a new-tab target, so a corrupted or hand-edited runtime file cannot
 * turn into an open redirect or a `javascript:`/`data:` injection.
 */
const ALLOWED_HOSTNAMES = new Set(['127.0.0.1', 'localhost', '[::1]', '::1'])

export function isSafeLocalUrl(candidate: string | undefined | null): candidate is string {
  if (!candidate) {
    return false
  }

  let parsed: URL
  try {
    parsed = new URL(candidate)
  } catch {
    return false
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return false
  }

  return ALLOWED_HOSTNAMES.has(parsed.hostname)
}

/**
 * The one real STAGING hosted origin this build knows about. Deliberately a
 * closed exact-hostname set, not a `*.onrender.com` wildcard: the runtime
 * config that supplies a candidate URL is build-time-trusted (see
 * runtime/hostedModules.ts), but this check stays defense-in-depth against a
 * future config bug pointing an iframe at an arbitrary onrender.com app we
 * don't own.
 */
const ALLOWED_STAGING_HOSTNAMES = new Set(['campo-digital-lidar-staging.onrender.com'])

export function isSafeIframeUrl(
  candidate: string | undefined | null,
  environment: CampoEnvironment,
): candidate is string {
  if (environment === 'local') {
    return isSafeLocalUrl(candidate)
  }

  if (!candidate) {
    return false
  }

  let parsed: URL
  try {
    parsed = new URL(candidate)
  } catch {
    return false
  }

  return parsed.protocol === 'https:' && ALLOWED_STAGING_HOSTNAMES.has(parsed.hostname)
}
