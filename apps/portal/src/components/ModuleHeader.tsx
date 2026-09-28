import type { ModuleDefinition } from '../data/modules'
import { MODULES } from '../data/modules'
import { Link, useRouter } from '../router/Router'
import { isSafeIframeUrl } from '../lib/safeUrl'
import type { CampoEnvironment } from '../runtime/environment'

interface ModuleHeaderProps {
  module: ModuleDefinition
  url: string | undefined
  environment: CampoEnvironment
}

export function ModuleHeader({ module, url, environment }: ModuleHeaderProps) {
  const { pathname } = useRouter()
  const canOpenExternally = isSafeIframeUrl(url, environment)

  return (
    <header className="module-header">
      <div className="module-header__left">
        <Link to="/" className="module-header__home">
          ← Campo Digital
        </Link>
        <span className="module-header__separator" aria-hidden="true">
          /
        </span>
        <span className="module-header__title">{module.title}</span>
      </div>

      <nav className="module-switcher" aria-label="Cambiar de módulo">
        {MODULES.map((candidate) => (
          <Link
            key={candidate.id}
            to={candidate.path}
            className={
              candidate.path === pathname
                ? 'module-switcher__item module-switcher__item--active'
                : 'module-switcher__item'
            }
          >
            {candidate.title.replace('Cubicación ', '').replace('Gestión Predial ', '')}
          </Link>
        ))}
      </nav>

      <div className="module-header__right">
        {canOpenExternally ? (
          <a
            className="module-header__new-tab"
            href={url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Abrir en pestaña nueva
          </a>
        ) : null}
      </div>
    </header>
  )
}
