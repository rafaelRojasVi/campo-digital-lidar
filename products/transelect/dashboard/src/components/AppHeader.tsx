/**
 * The persistent application shell (TR-FUNC-041 marca, TR-FUNC-046 vigencia).
 *
 * The shipped header spent 200 px of the first desktop screen — and 34 % of a
 * phone viewport — on a brand block, a client block, a subtitle, a four-line
 * stamp and a nav row, before a single number. This is one 56 px bar: who we
 * are, where you are, what you are looking at, and who you are signed in as.
 * The client's full name and the programme description move into the Resumen's
 * own context strip, where they belong to a page rather than to every page.
 *
 * The brand mark is Campo Digital's own logo, as published on
 * campodigital.cl (logo-campo-blanco-home-1-02.png), resized to a 2x asset
 * and served from this bundle rather than hotlinked. It is the white variant,
 * drawn for a dark ground, which is what this bar is. The image's alt text
 * carries the company name, and "Transelec" stays real text beside it, so
 * the link still reads "Campo Digital Transelec" without the picture.
 * The Transelec logo embedded in the source HTML is still not reused.
 *
 * The version stamp is still TR-FUNC-046's fix: it is the *active version's
 * own publish timestamp*, read from `GET /transelec/imports/active`, never a
 * live clock and never a literal.
 */
import { useCallback, useEffect, useState } from 'react'
import type { Me, TranselecActiveImport } from '../api'
import { logout, transelecRole } from '../api'
import { formatDateTime } from '../format'
import { Link, ROUTES, useRouter, type Route } from '../router'
import campoDigitalLogo from '../assets/campo-digital-logo.png'

const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  operator: 'Operador',
  viewer: 'Lectura',
}

interface NavItem {
  to: Route
  label: string
  /** Operator/administrator only; the server re-enforces the same boundary. */
  privileged?: boolean
  /** Other routes that should light this item up as the current section. */
  also?: readonly Route[]
  /**
   * Whether this section reads the shared filter state.
   *
   * The four reading sections carry the current filters across a section
   * change, so moving from a filtered Explorador to the Resumen keeps the
   * scope the reader chose instead of silently resetting it. Datos has no
   * filterable view, so it is deliberately not carried there.
   */
  filtered?: boolean
}

const NAV: readonly NavItem[] = [
  { to: ROUTES.resumen, label: 'Resumen', filtered: true },
  { to: ROUTES.explorador, label: 'Explorador', filtered: true },
  { to: ROUTES.pendientes, label: 'Pendientes', filtered: true },
  { to: ROUTES.aef, label: 'AEF', filtered: true },
  { to: ROUTES.calidad, label: 'Calidad', filtered: true },
  {
    to: ROUTES.datos,
    label: 'Datos',
    privileged: true,
    also: [ROUTES.importar, ROUTES.versiones],
  },
]

/**
 * Ends the current session from the shell.
 *
 * `POST /auth/logout` goes through the shared API client, so it carries the
 * session-bound CSRF token `GET /auth/csrf` issues, exactly like every other
 * state-changing call in this app. The caller is told only after the server
 * has actually cleared the session, so a failed sign-out never leaves the UI
 * claiming the user is signed out.
 */
function SessionControl({ label, onSignedOut }: { label: string; onSignedOut: () => void }) {
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  const endSession = useCallback(async () => {
    setBusy(true)
    setFailed(false)

    const result = await logout()
    if (result.ok) {
      onSignedOut()
      return
    }

    setFailed(true)
    setBusy(false)
  }, [onSignedOut])

  return (
    <div className="session-control no-print">
      <button
        type="button"
        className="btn alt small"
        disabled={busy}
        onClick={() => void endSession()}
      >
        {busy ? 'Cerrando sesión…' : label}
      </button>
      {failed && (
        <span className="session-control-error" role="alert">
          No se pudo cerrar la sesión. Intente nuevamente.
        </span>
      )}
    </div>
  )
}

export function AppHeader({
  me,
  activeImport,
  currentPath,
  canPublish,
  demoMode = false,
  onSignedOut,
}: {
  me: Me | null
  activeImport: TranselecActiveImport | null
  currentPath: string
  canPublish: boolean
  /**
   * Local development, where switching between seeded identities is the
   * point — it only changes the control's wording, never who may do what.
   */
  demoMode?: boolean
  /**
   * Optional: the shell also renders in states that have no session to end
   * (and in component tests that exercise the brand and navigation alone),
   * so the control appears only when a caller can actually handle the result.
   */
  onSignedOut?: () => void
}) {
  const role = transelecRole(me)
  const [navOpen, setNavOpen] = useState(false)
  const { search } = useRouter()

  // The mobile nav is a disclosure, so arriving at a new section must close
  // it — otherwise the reader lands behind the menu they just used.
  useEffect(() => setNavOpen(false), [currentPath])

  const items = NAV.filter((item) => !item.privileged || canPublish)

  // Signed out, there is nothing to navigate to and no version to stamp: the
  // whole application is one screen, the sign-in screen. Showing a section
  // bar and a "Sin versión publicada" chip there would offer a reader four
  // destinations they cannot open and blame the data for a session problem.
  const signedIn = me !== null

  return (
    <header className="topbar no-print">
      <div className="topbar-inner">
        <Link to={ROUTES.resumen} className="wordmark">
          <img
            className="wordmark-logo"
            src={campoDigitalLogo}
            alt="Campo Digital"
            width={103}
            height={44}
            fetchPriority="high"
            translate="no"
          />
          <span className="sr-only">{' · '}</span>
          <span className="wordmark-text" translate="no">
            Transelec
          </span>
        </Link>

        {signedIn && (
          <button
            type="button"
            className="topnav-toggle"
            aria-expanded={navOpen}
            aria-controls="secciones"
            onClick={() => setNavOpen((value) => !value)}
          >
            Secciones
          </button>
        )}

        {signedIn && (
          <nav
            id="secciones"
            className={`topnav${navOpen ? ' open' : ''}`}
            aria-label="Secciones de Transelec"
          >
            {items.map((item) => (
              <Link
                key={item.to}
                to={item.filtered ? `${item.to}${search}` : item.to}
                current={currentPath === item.to || item.also?.includes(currentPath as Route)}
                onNavigate={() => setNavOpen(false)}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        )}

        <div className="shell-side">
          {signedIn && activeImport ? (
            <span
              className="version-chip"
              title={`Publicada ${formatDateTime(activeImport.published_at)}`}
            >
              <b>Versión activa #{activeImport.import_id}</b>
              <span>Publicada {formatDateTime(activeImport.published_at)}</span>
            </span>
          ) : null}
          {signedIn && !activeImport && (
            <span className="version-chip none">
              <b>Sin versión publicada</b>
            </span>
          )}

          {me && (
            <span className="identity" data-testid="shell-identity">
              <span className="identity-name">{me.display_name}</span>
              {role && <span className="identity-role">{ROLE_LABELS[role] ?? role}</span>}
            </span>
          )}

          {me && onSignedOut && (
            <SessionControl
              label={demoMode ? 'Cambiar usuario' : 'Cerrar sesión'}
              onSignedOut={onSignedOut}
            />
          )}
        </div>
      </div>
    </header>
  )
}
