/**
 * The banner for a failed `GET /transelec/plazos`, shared by Estado and
 * Calidad. A server error never shows the server's own text (an unhandled
 * FastAPI exception answers «Internal Server Error», in English); it says
 * what is missing and what still works, and offers «Reintentar».
 */
import type { ApiFailure, FailureView } from '../lib/apiState'
import { AlertBanner } from './StateViews'

export function PlazoFailureBanner({
  failure,
  rawFailure,
  loading,
  onRetry,
  scope,
}: {
  failure: FailureView
  rawFailure: ApiFailure | null
  loading: boolean
  onRetry: () => void
  /** What is unavailable and what still works, for a server error. */
  scope: string
}) {
  return (
    <AlertBanner title="No se pudo calcular el plazo CONAF">
      <p>{rawFailure && rawFailure.status >= 500 ? scope : failure.message}</p>
      <button type="button" className="btn-link" onClick={onRetry} disabled={loading}>
        {loading ? 'Reintentando…' : 'Reintentar'}
      </button>
    </AlertBanner>
  )
}
