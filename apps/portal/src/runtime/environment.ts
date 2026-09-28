/**
 * Compiled in at Vite build time from VITE_CAMPO_ENV (see render.yaml for the
 * STAGING build's value). Never fetched at runtime, so this is trustworthy
 * even though CampoRuntimeConfig's *contents* (module URLs) are not.
 */
export type CampoEnvironment = 'local' | 'staging'

export function getCampoEnvironment(): CampoEnvironment {
  return import.meta.env.VITE_CAMPO_ENV === 'staging' ? 'staging' : 'local'
}
