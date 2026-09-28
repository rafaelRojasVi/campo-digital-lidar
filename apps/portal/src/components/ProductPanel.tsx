import type { ModuleDefinition } from '../data/modules'
import type { CampoEnvironment } from '../runtime/environment'
import type { ModuleStatus } from '../runtime/runtimeConfig'
import { Link } from '../router/Router'
import { StatusBadge } from './StatusBadge'
import { MODULE_VISUALS } from './visuals'

interface ProductPanelProps {
  module: ModuleDefinition
  status: ModuleStatus
  environment: CampoEnvironment
  layout: 'visual-left' | 'visual-right' | 'banner'
}

export function ProductPanel({ module, status, environment, layout }: ProductPanelProps) {
  const Visual = MODULE_VISUALS[module.accent]

  return (
    <section
      className={`product-panel product-panel--${layout}`}
      style={{ ['--panel-accent' as string]: `var(--cd-${module.accent})` }}
      aria-labelledby={`${module.id}-heading`}
    >
      <div className="product-panel__visual">
        <Visual />
      </div>
      <div className="product-panel__body">
        <div className="product-panel__heading-row">
          <h2 id={`${module.id}-heading`}>{module.title}</h2>
          <StatusBadge status={status} environment={environment} />
        </div>
        <p className="product-panel__tagline">{module.tagline}</p>
        <p className="product-panel__description">{module.description}</p>
        <ul className="product-panel__facts">
          {module.facts.map((fact) => (
            <li key={fact}>{fact}</li>
          ))}
        </ul>
        <Link to={module.path} className="product-panel__cta">
          Abrir módulo
        </Link>
      </div>
    </section>
  )
}
