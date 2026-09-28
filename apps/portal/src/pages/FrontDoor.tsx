import { useEffect, useState } from 'react'
import logo from '../assets/campo-digital-logo.png'
import { GOOGLE_LOGIN_PATH, PRODUCT_CARDS } from '../data/productCards'
import { getMe, logout, type ApiResult, type Me } from '../lib/platformApi'
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

  const signOut = async () => {
    const result = await logout()
    if (result.ok) setState({ kind: 'signed-out' })
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
          <p className="door__muted">Elige un proyecto.</p>
          <ul className="door__grid">
            {cards.map((card) => (
              <li key={card.key}>
                {card.href !== null ? (
                  <a className="door__card" href={card.href}>
                    <span className="door__card-title">{card.title}</span>
                    <span className="door__card-text">{card.description}</span>
                  </a>
                ) : (
                  <div className="door__card door__card--soon" aria-disabled="true">
                    <span className="door__card-title">{card.title}</span>
                    <span className="door__card-text">{card.description}</span>
                    <span className="door__soon">Próximamente</span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
