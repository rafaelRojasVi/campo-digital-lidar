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
          La API responde, pero todavía no hay ninguna instantánea Forestal ingerida en la base
          de datos.
        </p>
        <p className="status__text status__text--secondary">
          Para cargar la instantánea real desde la fuente externa, ejecute{' '}
          <code>make forestry-dev</code> en el repositorio.
        </p>
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
        <p className="status__text status__text--secondary">
          Verifique que el servicio backend esté activo (<code>make forestry-status</code>).
        </p>
        <button type="button" className="button" onClick={onRetry}>
          Reintentar
        </button>
      </div>
    </div>
  )
}
