import type { CampoEnvironment } from './environment'
import { hostedModuleUrls } from './hostedModules'

export type ModuleId = 'lidar' | 'forestal' | 'transelec'

export type ModuleStatus = 'available' | 'unavailable'

export interface ModuleRuntimeStatus {
  status: ModuleStatus
  url?: string
  owned?: boolean
  measurementCount?: number
}

export interface CampoRuntimeConfig {
  environment: CampoEnvironment
  generatedAt?: string
  portal?: { port?: number }
  modules: Partial<Record<ModuleId, ModuleRuntimeStatus>>
}

const EMPTY_CONFIG: CampoRuntimeConfig = { environment: 'local', modules: {} }

function isModuleStatus(value: unknown): value is ModuleStatus {
  return value === 'available' || value === 'unavailable'
}

function normalizeModule(value: unknown): ModuleRuntimeStatus | undefined {
  if (typeof value !== 'object' || value === null) {
    return undefined
  }

  const record = value as Record<string, unknown>

  if (!isModuleStatus(record.status)) {
    return undefined
  }

  return {
    status: record.status,
    url: typeof record.url === 'string' ? record.url : undefined,
    owned: typeof record.owned === 'boolean' ? record.owned : undefined,
    measurementCount:
      typeof record.measurementCount === 'number' ? record.measurementCount : undefined,
  }
}

/**
 * Parses the launcher-generated runtime config. Never throws: any malformed
 * or missing field is treated as "unavailable" rather than crashing the
 * stakeholder-facing home screen.
 */
export function parseRuntimeConfig(raw: unknown): CampoRuntimeConfig {
  if (typeof raw !== 'object' || raw === null) {
    return EMPTY_CONFIG
  }

  const record = raw as Record<string, unknown>
  const modulesRaw = record.modules

  const modules: CampoRuntimeConfig['modules'] = {}

  if (typeof modulesRaw === 'object' && modulesRaw !== null) {
    for (const key of ['lidar', 'forestal', 'transelec'] as const) {
      const normalized = normalizeModule((modulesRaw as Record<string, unknown>)[key])
      if (normalized) {
        modules[key] = normalized
      }
    }
  }

  return {
    environment: 'local',
    generatedAt: typeof record.generatedAt === 'string' ? record.generatedAt : undefined,
    portal:
      typeof record.portal === 'object' && record.portal !== null
        ? { port: (record.portal as Record<string, unknown>).port as number | undefined }
        : undefined,
    modules,
  }
}

export async function fetchRuntimeConfig(
  signal?: AbortSignal,
): Promise<CampoRuntimeConfig> {
  try {
    const response = await fetch('/campo-runtime.json', {
      signal,
      cache: 'no-store',
    })

    if (!response.ok) {
      return EMPTY_CONFIG
    }

    const raw = (await response.json()) as unknown
    return parseRuntimeConfig(raw)
  } catch {
    return EMPTY_CONFIG
  }
}

/**
 * STAGING's runtime config: no fetch, no dynamic file (Render's static
 * hosting has no server to generate one) — everything is already compiled
 * into this bundle from hostedModuleUrls(). Synchronous by design so
 * useRuntimeConfig never shows a loading flicker in STAGING.
 */
export function buildStagingRuntimeConfig(): CampoRuntimeConfig {
  const hosted = hostedModuleUrls()
  const modules: CampoRuntimeConfig['modules'] = {}

  for (const moduleId of ['lidar', 'forestal', 'transelec'] as const) {
    const url = hosted[moduleId]
    modules[moduleId] = url ? { status: 'available', url } : { status: 'unavailable' }
  }

  return { environment: 'staging', modules }
}

export function moduleStatusFor(
  config: CampoRuntimeConfig,
  moduleId: ModuleId,
): ModuleRuntimeStatus {
  return config.modules[moduleId] ?? { status: 'unavailable' }
}
