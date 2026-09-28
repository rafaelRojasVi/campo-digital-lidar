import { useState } from 'react'
import { findModule } from '../data/modules'
import { ModuleHeader } from '../components/ModuleHeader'
import { Link } from '../router/Router'
import { isSafeIframeUrl } from '../lib/safeUrl'
import type { CampoEnvironment } from '../runtime/environment'
import { moduleStatusFor } from '../runtime/runtimeConfig'
import { useRuntimeConfig } from '../runtime/useRuntimeConfig'

export function ModulePage({ moduleId }: { moduleId: string }) {
  const module = findModule(moduleId)
  const { config, loading } = useRuntimeConfig()
  const [iframeFailed, setIframeFailed] = useState(false)

  if (!module) {
    return (
      <div className="module-shell module-shell--missing">
        <p>Módulo desconocido.</p>
        <Link to="/">Volver a Campo Digital</Link>
      </div>
    )
  }

  const runtimeStatus = moduleStatusFor(config, module.id)
  const safeUrl = isSafeIframeUrl(runtimeStatus.url, config.environment)
    ? runtimeStatus.url
    : undefined
  const isAvailable = runtimeStatus.status === 'available' && Boolean(safeUrl)

  return (
    <div className="module-shell">
      <ModuleHeader module={module} url={safeUrl} environment={config.environment} />

      <div className="module-shell__content">
        {loading ? (
          <div className="module-shell__state">Cargando estado del módulo…</div>
        ) : isAvailable && !iframeFailed ? (
          <iframe
            key={safeUrl}
            src={safeUrl}
            title={module.title}
            className="module-shell__frame"
            onError={() => setIframeFailed(true)}
          />
        ) : (
          <ModuleUnavailable moduleId={module.id} environment={config.environment} />
        )}
      </div>
    </div>
  )
}

const EXPECTED_BRANCH: Record<string, string> = {
  lidar: 'products/lidar (esta misma rama)',
  forestal: 'feat/forestry-dashboard-v1',
  transelec: 'products/transelect (esta misma rama)',
}

function ModuleUnavailable({
  moduleId,
  environment,
}: {
  moduleId: string
  environment: CampoEnvironment
}) {
  if (environment === 'staging') {
    return (
      <div className="module-shell__state module-shell__state--unavailable">
        <p>Este módulo aún no está disponible públicamente en este entorno.</p>
        <p className="module-shell__state-hint">
          No se publican datos reales de clientes sin sanear primero; este módulo se habilitará
          aquí cuando exista una versión hospedada segura.
        </p>
      </div>
    )
  }

  return (
    <div className="module-shell__state module-shell__state--unavailable">
      <p>Demo no iniciada.</p>
      <p className="module-shell__state-hint">
        Este módulo no está disponible en este entorno local.
      </p>
      <details className="module-shell__details">
        <summary>Detalles técnicos</summary>
        <p>
          Worktree/rama esperada: <code>{EXPECTED_BRANCH[moduleId] ?? moduleId}</code>
        </p>
        <p>
          Inicie la demo completa con <code>make campo-demo</code> desde este repositorio.
        </p>
      </details>
    </div>
  )
}
