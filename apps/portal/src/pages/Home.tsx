import { MODULES } from '../data/modules'
import { ProductPanel } from '../components/ProductPanel'
import { Link } from '../router/Router'
import { moduleStatusFor, type ModuleId } from '../runtime/runtimeConfig'
import { useRuntimeConfig } from '../runtime/useRuntimeConfig'

const LAYOUTS: Record<ModuleId, 'visual-left' | 'visual-right' | 'banner'> = {
  lidar: 'visual-right',
  forestal: 'visual-left',
  transelec: 'banner',
}

export function Home() {
  const { config } = useRuntimeConfig()

  return (
    <div className="home">
      <header className="home__hero">
        <span className="home__eyebrow">Campo Digital</span>
        <h1>Plataforma de inteligencia territorial y gestión operacional</h1>
        <p>
          Campo Digital integra tres módulos especializados bajo una misma plataforma,
          manteniendo la trazabilidad y las reglas propias de cada producto.
        </p>
      </header>

      <main className="home__modules">
        {MODULES.map((module) => (
          <ProductPanel
            key={module.id}
            module={module}
            status={moduleStatusFor(config, module.id).status}
            environment={config.environment}
            layout={LAYOUTS[module.id]}
          />
        ))}
      </main>

      <footer className="home__footer">
        <p>3 productos · fuentes trazables · evidencia preservada</p>
        <Link to="/estado" className="home__footer-link">
          {config.environment === 'staging'
            ? 'Estado del entorno de staging'
            : 'Estado del entorno local'}
        </Link>
        <Link to="/archivos" className="home__footer-link">
          Archivos
        </Link>
      </footer>
    </div>
  )
}
