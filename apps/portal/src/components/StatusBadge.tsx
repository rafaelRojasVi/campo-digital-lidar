import type { CampoEnvironment } from '../runtime/environment'
import type { ModuleStatus } from '../runtime/runtimeConfig'

const LABELS: Record<CampoEnvironment, Record<ModuleStatus, string>> = {
  local: {
    available: 'Disponible',
    unavailable: 'Demo no iniciada',
  },
  staging: {
    available: 'Disponible',
    unavailable: 'No desplegado en este entorno',
  },
}

export function StatusBadge({
  status,
  environment,
}: {
  status: ModuleStatus
  environment: CampoEnvironment
}) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      <span className="status-badge__dot" aria-hidden="true" />
      {LABELS[environment][status]}
    </span>
  )
}
