import { useEffect, useState } from 'react'
import logo from '../assets/campo-digital-logo.png'
import { MODULE_VISUALS } from '../components/visuals'
import { GOOGLE_LOGIN_PATH, PRODUCT_CARDS, type ProductCard } from '../data/productCards'
import { devLogin, getMe, logout, type ApiResult, type Me } from '../lib/platformApi'
import '../styles/front-door.css'

type State =
  | { kind: 'loading' }
  | { kind: 'signed-out' }
  | { kind: 'unreachable' }
  | { kind: 'signed-in'; me: Me }

// 401 is the signed-out state; any other failure is an unreachable platform,
// never a request to sign in.
function sessionState(result: ApiResult<Me>): State {
  if (result.ok) return { kind: 'signed-in', me: result.data }
  return result.status === 401 ? { kind: 'signed-out' } : { kind: 'unreachable' }
}

/**
 * The unified platform's front door: sign in once with Google Workspace, then
 * open a project. It only shows what the session's grants allow; every
 * product still enforces its own access on the server.
 */
export function FrontDoor() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let active = true
    void getMe().then((result) => {
      if (active) setState(sessionState(result))
    })
    return () => {
      active = false
    }
  }, [])

  const retry = () => {
    setState({ kind: 'loading' })
    void getMe().then((result) => setState(sessionState(result)))
  }

  const [signOutFailed, setSignOutFailed] = useState(false)

  const signInAsDemo = async (identityKey: string) => {
    setState(sessionState(await devLogin(identityKey)))
  }

  // The front door is the only place to sign out, so a failure must be said
  // out loud: on a shared computer "nothing happened" reads as "signed out".
  const signOut = async () => {
    setSignOutFailed(false)
    const result = await logout()
    if (result.ok) setState({ kind: 'signed-out' })
    else setSignOutFailed(true)
  }

  return (
    <div className="door">
      <header className="door__bar">
        <img className="door__logo" src={logo} alt="Campo Digital" width={103} height={44} />
        {state.kind === 'signed-in' ? (
          <button type="button" className="door__signout" onClick={() => void signOut()}>
            Cerrar sesión
          </button>
        ) : null}
      </header>
      <main className="door__main">
        {signOutFailed && state.kind === 'signed-in' ? (
          <p className="door__error" role="alert">
            No se pudo cerrar la sesión. Vuelve a intentarlo o cierra el navegador.
          </p>
        ) : null}
        {state.kind === 'loading' ? (
          <p className="door__muted" aria-live="polite">
            Verificando la sesión…
          </p>
        ) : null}
        {state.kind === 'signed-out' ? (
          <section className="door__panel" aria-labelledby="door-title">
            <h1 id="door-title">Plataforma Campo Digital</h1>
            <p className="door__muted">
              Ingresa con tu cuenta de Campo Digital para ver tus proyectos.
            </p>
            <a className="door__primary" href={GOOGLE_LOGIN_PATH}>
              Iniciar sesión con Google
            </a>
            {/* Vite replaces import.meta.env.DEV with false in every build, so
                these seeded identities exist only in the local dev server;
                the API also mounts /auth/dev-login only in development. */}
            {import.meta.env.DEV ? (
              <div className="door__demo">
                <p className="door__muted">Solo en desarrollo local:</p>
                <button
                  type="button"
                  className="door__secondary"
                  onClick={() => void signInAsDemo('dev-admin')}
                >
                  Entrar como administrador de demostración
                </button>
                <button
                  type="button"
                  className="door__secondary"
                  onClick={() => void signInAsDemo('dev-viewer')}
                >
                  Ver como Javier (solo lectura)
                </button>
              </div>
            ) : null}
          </section>
        ) : null}
        {state.kind === 'unreachable' ? (
          <section className="door__panel" role="alert">
            <h1>No se pudo contactar la plataforma</h1>
            <p className="door__muted">Revisa tu conexión y vuelve a intentarlo.</p>
            <button type="button" className="door__primary" onClick={retry}>
              Reintentar
            </button>
          </section>
        ) : null}
        {state.kind === 'signed-in' ? <Projects me={state.me} /> : null}
      </main>
    </div>
  )
}

function Projects({ me }: { me: Me }) {
  const granted = new Set(me.product_grants.map((grant) => grant.product_key))
  const cards = PRODUCT_CARDS.filter((card) => granted.has(card.key))

  return (
    <section aria-labelledby="door-hello">
      <h1 id="door-hello" className="door__hello">
        Hola, {me.display_name}
      </h1>
      {cards.length === 0 ? (
        <p className="door__muted">
          Tu cuenta no tiene proyectos asignados. Pide acceso a un administrador de Campo Digital.
        </p>
      ) : (
        <>
          <p className="door__muted">Elige un proyecto para continuar.</p>
          <ul className="door__grid">
            {cards.map((card) => (
              <li key={card.key}>
                <ProjectCard card={card} />
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function ProjectCard({ card }: { card: ProductCard }) {
  const Visual = MODULE_VISUALS[card.accent]
  const body = (
    <>
      {/* Identity mark only: the title and description carry the meaning. */}
      <span className="door__card-visual" aria-hidden="true">
        <Visual />
      </span>
      <span className="door__card-body">
        <span className="door__card-title">{card.title}</span>
        <span className="door__card-text">{card.description}</span>
        {card.href !== null ? (
          <span className="door__card-cta">
            Abrir <span aria-hidden="true">→</span>
          </span>
        ) : (
          <span className="door__soon">Próximamente</span>
        )}
      </span>
    </>
  )

  const className = `door__card door__card--${card.accent}`
  return card.href !== null ? (
    <a className={className} href={card.href}>
      {body}
    </a>
  ) : (
    <div className={`${className} door__card--soon`} aria-disabled="true">
      {body}
    </div>
  )
}
