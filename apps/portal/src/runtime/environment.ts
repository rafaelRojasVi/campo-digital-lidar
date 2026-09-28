/**
 * Compiled in at Vite build time from VITE_CAMPO_ENV (see render.yaml for the
 * STAGING build's value, and the Dockerfile for `production`, the unified
 * platform's front door). Never fetched at runtime, so this is trustworthy
 * even though CampoRuntimeConfig's *contents* (module URLs) are not.
 */
export type CampoEnvironment = 'local' | 'staging' | 'production'

export function getCampoEnvironment(): CampoEnvironment {
  const value = import.meta.env.VITE_CAMPO_ENV
  return value === 'staging' || value === 'production' ? value : 'local'
}
