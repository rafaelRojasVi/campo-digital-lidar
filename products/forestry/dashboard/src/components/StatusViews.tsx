import { DEV_IDENTITIES } from '../api.ts'
import { PLATFORM_FRONT_DOOR_PATH, platformFrontDoorEnabled } from '../runtime/frontDoor.ts'

interface RetryProps {
  onRetry: () => void
}

export function LoadingView({ step }: { step: string }) {
  return (
    <div className="status" role="status" aria-live="polite">
      <div className="status__card">
        <div className="status__spinner" aria-hidden="true" />
        <h1 className="status__title">Gestión Predial Forestal</h1>
        <p className="status__text">{step}</p>
      </div>
    </div>
  )
}

export function NoSnapshotView({ onRetry }: RetryProps) {
  return (
    <div className="status">
      <div className="status__card">
        <h1 className="status__title">Sin datos de origen</h1>
        <p className="status__text">
          Todavía no hay ninguna instantánea de Rodales cargada en la plataforma.
        </p>
        {platformFrontDoorEnabled() ? null : (
          <p className="status__text status__text--secondary">
            Para cargar la instantánea real desde la fuente externa, ejecute{' '}
            <code>make forestry-dev</code> en el repositorio.
          </p>
        )}
        <button type="button" className="button" onClick={onRetry}>
          Reintentar
        </button>
      </div>
    </div>
  )
}

export function ErrorView({ message, onRetry }: RetryProps & { message: string }) {
  return (
    <div className="status">
      <div className="status__card">
        <h1 className="status__title">API no disponible</h1>
        <p className="status__text">{message}</p>
        {platformFrontDoorEnabled() ? null : (
          <p className="status__text status__text--secondary">
            Verifique que el servicio backend esté activo (<code>make forestry-status</code>).
          </p>
        )}
        <button type="button" className="button" onClick={onRetry}>
          Reintentar
        </button>
      </div>
    </div>
  )
}

/**
 * No session. On the platform the app redirects to the front door before
 * this renders; a local build offers the development identities instead.
 */
export function SignedOutView({ onDevLogin }: { onDevLogin: (identityKey: string) => void }) {
  return (
    <div className="status">
      <div className="status__card">
        <h1 className="status__title">Inicie sesión</h1>
        {import.meta.env.DEV ? (
          <>
            <p className="status__text">
              Entorno de desarrollo: elija una identidad de prueba.
            </p>
            <div className="status__actions">
              {DEV_IDENTITIES.map((identity) => (
                <button
                  key={identity.identityKey}
                  type="button"
                  className="button"
                  onClick={() => onDevLogin(identity.identityKey)}
                >
                  {identity.label}
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            <p className="status__text">Para ver Rodales, inicie sesión en Campo Digital.</p>
            <a className="button" href={PLATFORM_FRONT_DOOR_PATH}>
              Ir al inicio de sesión
            </a>
          </>
        )}
      </div>
    </div>
  )
}

/** Signed in, but the account holds no Rodales grant. */
export function ForbiddenView() {
  return (
    <div className="status">
      <div className="status__card">
        <h1 className="status__title">Sin acceso a Rodales</h1>
        <p className="status__text">
          Su cuenta no tiene acceso a este proyecto. Solicite acceso a un administrador de
          Rodales.
        </p>
        <a className="button" href={PLATFORM_FRONT_DOOR_PATH}>
          Volver a Proyectos
        </a>
      </div>
    </div>
  )
}
