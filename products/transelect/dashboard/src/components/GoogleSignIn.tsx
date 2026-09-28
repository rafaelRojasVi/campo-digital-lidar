/**
 * The sign-in panel every deployed Transelec build ships: Google Workspace,
 * this product's identity provider (ADR-010).
 *
 * There is deliberately no fallback here. If Google sign-in is not
 * configured in this environment the panel says so and stops; it never
 * degrades to a demo identity, because outside development no such identity
 * exists on the server either.
 *
 * Nothing Google-issued reaches this bundle. The whole OpenID Connect flow
 * runs server-side (app/routers/google_auth.py); the browser is handed one
 * HttpOnly session cookie and never an id_token, access token or client
 * secret.
 */
import { GOOGLE_LOGIN_PATH, checkGoogleSignIn } from '../api'
import { SignInFailure } from './SignInFailure'
import { useCallback, useState } from 'react'

function failureMessage(status: number, error: string): string {
  if (status === 503) {
    return 'El inicio de sesión con Google no está configurado en este entorno. Avise al administrador de la plataforma de Campo Digital; no existe otra forma de acceder.'
  }
  return error
}

export function GoogleSignIn() {
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  const signIn = useCallback(async () => {
    setPending(true)
    setFailure(null)

    const result = await checkGoogleSignIn()
    if (result.ok) {
      // A full top-level navigation, not a fetch: the OpenID Connect flow has
      // to run in the browser's own address bar so Google can show its
      // account chooser and redirect back to /auth/google/callback.
      window.location.assign(GOOGLE_LOGIN_PATH)
      return
    }

    setFailure(failureMessage(result.status, result.error))
    setPending(false)
  }, [])

  return (
    <>
      {failure !== null && <SignInFailure message={failure} onRetry={() => void signIn()} />}

      <div className="login-actions" data-testid="login-actions" aria-busy={pending}>
        <div className="login-action">
          <button type="button" className="btn" disabled={pending} onClick={() => void signIn()}>
            {pending ? 'Redirigiendo a Google…' : 'Continuar con Google'}
          </button>
          <p className="login-action-note">
            Se abrirá el inicio de sesión de Google de su organización. Al volver, esta página
            mostrará el seguimiento correspondiente a su cuenta.
          </p>
        </div>
      </div>

      <p className="login-foot">
        El acceso a Transelec se administra con las cuentas corporativas de Google Workspace de
        Campo Digital. Iniciar sesión no concede acceso por sí solo: si su cuenta no tiene permisos
        sobre este producto, solicítelos al administrador de la plataforma de Campo Digital.
      </p>
    </>
  )
}
