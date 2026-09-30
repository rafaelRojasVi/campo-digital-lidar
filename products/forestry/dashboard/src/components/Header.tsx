import campoDigitalLogo from '../assets/campo-digital-logo.png'
import { canUpload } from '../api.ts'
import { formatDate, shortFingerprint } from '../lib/format.ts'
import { ROUTES, mapPath, onLinkClick } from '../router.ts'
import type { Route } from '../router.ts'
import { PLATFORM_FRONT_DOOR_PATH, platformFrontDoorEnabled } from '../runtime/frontDoor.ts'
import type { ForestryRole, ForestrySnapshot, SnapshotSummary } from '../types.ts'

interface HeaderProps {
  active: Route
  role: ForestryRole | null
  /** The version on the map, when the page shows one. */
  snapshot?: ForestrySnapshot
  summary?: SnapshotSummary
  /** True when the map shows a version other than the published one. */
  preview?: boolean
}

const NAV: { route: Route; href: string; label: string; uploadersOnly: boolean }[] = [
  { route: ROUTES.mapa, href: mapPath(), label: 'Mapa', uploadersOnly: false },
  { route: ROUTES.versiones, href: ROUTES.versiones, label: 'Versiones', uploadersOnly: false },
  { route: ROUTES.importar, href: ROUTES.importar, label: 'Cargar versión', uploadersOnly: true },
]

// The brand mark is Campo Digital's own white logo (the same asset the
// Transelec panel bundles, from campodigital.cl), drawn for this dark bar.
// Its alt text carries the company name; the product and estate stay real
// text beside it.
//
// The map shows the *published* version: the one an operator or admin chose
// with «Publicar» or «Restaurar». Publication is a decision about what the
// panel shows, not a claim that the source is the official estate state.
export function Header({ active, role, snapshot, summary, preview = false }: HeaderProps) {
  return (
    <header className="header">
      <div className="header__brand">
        <img
          className="header__logo"
          src={campoDigitalLogo}
          alt="Campo Digital"
          width={93}
          height={40}
        />
        <div className="header__context">
          <p className="header__product">Gestión Predial Forestal</p>
          <h1 className="header__title">Patrimonio Degenfeld</h1>
        </div>
        <nav className="header__nav" aria-label="Secciones de Rodales">
          {NAV.filter((item) => !item.uploadersOnly || canUpload(role)).map((item) => (
            <a
              key={item.route}
              className="header__nav-link"
              href={item.href}
              aria-current={item.route === active ? 'page' : undefined}
              onClick={(event) => onLinkClick(event, item.href)}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </div>

      <div className="header__end">
        {snapshot !== undefined && summary !== undefined ? (
          <dl
            className="header__provenance"
            title="Versión que muestra el mapa. Publicar una versión no la convierte en el estado oficial del patrimonio."
          >
            <div>
              <dt>{preview ? 'Vista previa' : 'Versión publicada'}</dt>
              <dd>
                N.º {snapshot.shapefile_snapshot_id} · cargada el {formatDate(snapshot.created_at)}
              </dd>
            </div>
            <div>
              <dt>Capa de origen</dt>
              <dd>{snapshot.layer_name}</dd>
            </div>
            <div>
              <dt>CRS almacenado</dt>
              <dd>EPSG:{summary.storage_srid}</dd>
            </div>
            <div>
              <dt>Huella de familia</dt>
              <dd>
                <code>{shortFingerprint(snapshot.family_fingerprint)}</code>
              </dd>
            </div>
          </dl>
        ) : null}
        {/* On the platform, the front door owns sign-in, sign-out and the
            project picker; this is the way back to it. */}
        {platformFrontDoorEnabled() ? (
          <a className="header__projects" href={PLATFORM_FRONT_DOOR_PATH}>
            Proyectos
          </a>
        ) : null}
      </div>
    </header>
  )
}
