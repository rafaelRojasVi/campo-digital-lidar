/**
 * The unauthenticated screen.
 *
 * Visually this is now the entrance to the same product rather than a card
 * floating in grey: a two-column composition on the page's own ground, where
 * the left column says what this is and what the reader will get, and the
 * right column holds the single decision they have to make.
 *
 * It adds no authentication mechanism of its own. Every button here drives an
 * endpoint the platform already exposes, and the session it produces is the
 * same HttpOnly `campo_session` cookie every other caller uses. Nothing is
 * written to localStorage, sessionStorage, a readable cookie or this bundle.
 *
 * The two panels are chosen by TWO independent conditions, and both must hold
 * before a demo identity is offered:
 *
 *  1. `import.meta.env.DEV`, written as a literal here so the bundler can see
 *     it. In a `vite build` artifact it folds to `false`, which drops the
 *     entire `DemoSignIn` module — and with it every seeded identity key —
 *     out of the shipped output.
 *  2. `demoAvailable`, the same boundary read through
 *     `src/runtime/environment.ts`, which keeps the decision testable and
 *     keeps the reason for it documented in one place.
 *
 * Neither is the security control. The server is: `POST /auth/dev-login` is
 * mounted only under `APP_ENV == "development"` (apps/api/app/main.py).
 */
import { DemoSignIn } from './DemoSignIn'
import { GoogleSignIn } from './GoogleSignIn'

export function LoginCard({
  demoAvailable,
  onSignedIn,
}: {
  demoAvailable: boolean
  /** Re-reads the session so the app advances without a browser refresh. */
  onSignedIn: () => void | Promise<void>
}) {
  return (
    <div className="signin" data-testid="login-card">
      <div className="signin-copy">
        <p className="eyebrow">Campo Digital · Transelec</p>
        <h1>Seguimiento de Planes de Manejo Forestal</h1>
        <p className="signin-lead">
          Ingresos CONAF, superficies de corta y situación predial de Transmisora del Pacífico –
          Transelec, sobre la versión de la planilla maestra publicada en la plataforma.
        </p>
        <div className="signin-facts">
          <div>
            <i aria-hidden="true" />
            <span>
              Cada cifra proviene de la versión activa, con su huella, su fecha de publicación y
              quién la publicó.
            </span>
          </div>
          <div>
            <i aria-hidden="true" />
            <span>
              El acceso lo decide el servidor a partir de los permisos de su cuenta sobre el
              producto Transelec.
            </span>
          </div>
        </div>
      </div>

      <section className="signin-panel" aria-labelledby="login-card-title">
        <div className="stack-tight">
          <h2 id="login-card-title">Inicie sesión para continuar</h2>
          <p className="hint">
            El seguimiento sólo se muestra a cuentas autorizadas. Elija cómo desea acceder.
          </p>
        </div>

        {import.meta.env.DEV && demoAvailable ? (
          <DemoSignIn onSignedIn={onSignedIn} />
        ) : (
          <GoogleSignIn />
        )}
      </section>
    </div>
  )
}
