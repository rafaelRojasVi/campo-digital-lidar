/**
 * The local-development sign-in panel: one click per seeded identity.
 *
 * This module is the ONLY place in the application that names a seeded
 * identity or calls `POST /auth/dev-login`, and `LoginCard` reaches it
 * through a literal `import.meta.env.DEV` test. That is deliberate: in a
 * `vite build` artifact the bundler folds that test to `false`, this module
 * loses its last reference, and it is dropped from the output entirely —
 * so `dev-admin`, `dev-viewer` and the dev-login path are not merely hidden
 * in staging and production, they are absent from the shipped bundle.
 *
 * The server remains the authority regardless: `/auth/dev-login` is mounted
 * only under `APP_ENV == "development"` (apps/api/app/main.py).
 */
import { useCallback, useState } from 'react'
import { type DemoIdentityKey, devLogin } from '../api'
import { SignInFailure } from './SignInFailure'

interface DemoOption {
  identityKey: DemoIdentityKey
  label: string
  note: string
  className: string
}

/**
 * The two seeded identities worth demonstrating. The notes state what each
 * one can actually do — the server enforces exactly this, so the copy cannot
 * drift into promising access the grant does not carry.
 *
 * The identity keys are written as literals rather than read from a shared
 * constant on purpose. A top-level property read (`DEMO_IDENTITIES.admin`)
 * counts as a possible side effect, so Rollup preserves it even after the
 * component around it is eliminated — which would leave `dev-admin` and
 * `dev-viewer` sitting in the production bundle as the only survivors of
 * this module. With literals there is nothing left to preserve.
 */
const DEMO_OPTIONS: readonly DemoOption[] = [
  {
    identityKey: 'dev-admin',
    label: 'Entrar como administrador de demostración',
    note: 'Dev Admin · rol Administrador sobre Transelec: puede importar planillas y publicar o restaurar versiones.',
    className: 'btn',
  },
  {
    identityKey: 'dev-viewer',
    label: 'Ver como Javier — solo lectura',
    note: 'Dev Viewer · rol Lectura sobre Transelec: consulta el panel completo, sin importar ni cambiar la versión publicada.',
    className: 'btn alt',
  },
]

function failureMessage(status: number, error: string): string {
  // 404 is the fail-closed case: the dev-login route is not mounted outside
  // APP_ENV=development, so a dev server pointed at a hosted API lands here.
  // Say that plainly instead of showing a bare "Not Found".
  if (status === 404) {
    return 'El acceso de demostración no está disponible en este entorno. Sólo existe en el entorno de desarrollo local de Campo Digital.'
  }
  return error
}

export function DemoSignIn({ onSignedIn }: { onSignedIn: () => void | Promise<void> }) {
  const [pending, setPending] = useState<DemoIdentityKey | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [lastAttempt, setLastAttempt] = useState<DemoIdentityKey | null>(null)

  const signIn = useCallback(
    async (identityKey: DemoIdentityKey) => {
      setPending(identityKey)
      setLastAttempt(identityKey)
      setFailure(null)

      const result = await devLogin(identityKey)
      if (result.ok) {
        // Deliberately stays pending: the session refresh this triggers
        // replaces this card, and re-enabling the buttons first would let a
        // second click race the refresh.
        await onSignedIn()
        return
      }

      setFailure(failureMessage(result.status, result.error))
      setPending(null)
    },
    [onSignedIn],
  )

  const retry = useCallback(() => {
    if (lastAttempt !== null) void signIn(lastAttempt)
  }, [lastAttempt, signIn])

  return (
    <>
      {failure !== null && <SignInFailure message={failure} onRetry={retry} />}

      <div className="login-actions" data-testid="login-actions" aria-busy={pending !== null}>
        {DEMO_OPTIONS.map((option) => (
          <div className="login-action" key={option.identityKey}>
            <button
              type="button"
              className={option.className}
              disabled={pending !== null}
              onClick={() => void signIn(option.identityKey)}
            >
              {pending === option.identityKey ? 'Iniciando sesión…' : option.label}
            </button>
            <p className="login-action-note">{option.note}</p>
          </div>
        ))}
      </div>

      <p className="login-foot">
        Estas dos identidades son datos sembrados del entorno de desarrollo local y no existen en
        los entornos publicados de Campo Digital. Los permisos los sigue decidiendo el servidor:
        ocultar un botón no concede ni quita ningún acceso.
      </p>
    </>
  )
}
