/**
 * `/transelec/datos` — data administration, for operators and administrators.
 *
 * Two panes that were two top-level routes. They belong together: importing a
 * planilla and deciding which version is live are one job with two halves,
 * and separating them made "publish, then check what is now active" a
 * navigation instead of a glance.
 *
 * The old routes still resolve here, so `/transelec/importar` and
 * `/transelec/versiones` keep working as links and bookmarks — they simply
 * select a pane.
 *
 * The Accesos pane is administrators only: the tab is absent for operators,
 * and an operator who types its URL gets the unauthorized state here.
 *
 * Access is presentation only. The server re-enforces the same boundary on
 * every endpoint this section calls; a viewer who types the URL gets the
 * unauthorized state from the shell and a 403 from the API.
 */
import type { TranselecActiveImport } from '../api'
import { Link, ROUTES, type Route } from '../router'
import { StateBlock } from '../components/StateViews'
import { SectionHeader } from '../ui/Primitives'
import { AccesosPage } from './AccesosPage'
import { ImportarPage } from './ImportarPage'
import { VersionesPage } from './VersionesPage'

export function DatosPage({
  route,
  activeImport,
  onActiveVersionChanged,
  isAdmin,
}: {
  route: Route
  activeImport: TranselecActiveImport | null
  onActiveVersionChanged: () => void
  isAdmin: boolean
}) {
  const pane =
    route === ROUTES.versiones ? 'versiones' : route === ROUTES.accesos ? 'accesos' : 'importar'

  const content = () => {
    if (pane === 'importar') {
      return <ImportarPage onActiveVersionChanged={onActiveVersionChanged} />
    }
    if (pane === 'versiones') {
      return (
        <VersionesPage activeImport={activeImport} onActiveVersionChanged={onActiveVersionChanged} />
      )
    }
    if (!isAdmin) {
      return (
        <StateBlock
          view={{
            kind: 'forbidden',
            title: 'Sin autorización',
            message: 'Sólo los administradores de Transelec pueden gestionar accesos.',
          }}
        />
      )
    }
    return <AccesosPage />
  }

  return (
    <div className="page enter">
      <SectionHeader
        title="Administración de datos"
        meta="Sólo operadores y administradores de Transelec."
        actions={null}
      />

      <nav className="datos-tabs no-print" aria-label="Paneles de administración de datos">
        <Link to={ROUTES.importar} current={pane === 'importar'}>
          Importar planilla
        </Link>
        <Link to={ROUTES.versiones} current={pane === 'versiones'}>
          Versiones
        </Link>
        {isAdmin && (
          <Link to={ROUTES.accesos} current={pane === 'accesos'}>
            Accesos
          </Link>
        )}
      </nav>

      <div style={{ marginTop: 'var(--s-6)' }}>{content()}</div>
    </div>
  )
}
