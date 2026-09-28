/**
 * One failed sign-in attempt, with the retry that repeats it.
 *
 * Shared by both sign-in panels so the wording, the alert role and the
 * retry affordance cannot drift apart between environments.
 */
export function SignInFailure({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="alert alert-error" role="alert">
      <strong>No se pudo iniciar la sesión</strong>
      <p className="login-failure-detail">{message}</p>
      <button type="button" className="btn-link" onClick={onRetry}>
        Reintentar
      </button>
    </div>
  )
}
