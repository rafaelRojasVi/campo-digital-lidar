/**
 * Failure classification for the required UI states.
 *
 * The design doc names the states this app must handle beyond the happy
 * path: empty (nothing published yet), loading, unauthorized (401/403 per
 * route), invalid upload, unavailable source, import failed, duplicate
 * upload and restore confirmation. The first four of those are decided
 * entirely by an HTTP status, so they are classified here once, in one
 * place, rather than re-derived at each call site.
 *
 * Copy is deliberately generic and stakeholder-safe. The API's own error
 * bodies are already generic Spanish strings (Task 3 asserts no traceback,
 * path, column name or row content ever reaches a client-facing body), so
 * where a detail is shown it is the API's own wording, never an exception.
 */

export type FailureKind =
  | 'unauthenticated'
  | 'forbidden'
  | 'empty'
  | 'unavailable'
  | 'invalid_upload'
  | 'import_failed'
  | 'too_large'
  | 'error'

export interface FailureView {
  kind: FailureKind
  title: string
  message: string
}

export interface ApiFailure {
  status: number
  error: string
}

const NOT_PUBLISHED = 'No hay una versión publicada de Transelec.'

export function classifyFailure(failure: ApiFailure): FailureView {
  switch (failure.status) {
    case 0:
      return {
        kind: 'unavailable',
        title: 'Plataforma no disponible',
        message:
          'No se pudo contactar la plataforma. Verifique su conexión e intente nuevamente; los datos publicados no se han modificado.',
      }
    case 401:
      return {
        kind: 'unauthenticated',
        title: 'Sesión requerida',
        message:
          'Debe iniciar sesión para consultar el seguimiento CONAF de Transelec. Ingrese desde el portal de Campo Digital y vuelva a esta página.',
      }
    case 403:
      return {
        kind: 'forbidden',
        title: 'Sin autorización',
        message:
          'Su cuenta no tiene permisos sobre el producto Transelec. Solicite el acceso al administrador de la plataforma.',
      }
    case 404:
      return {
        kind: 'empty',
        title: 'Sin versión publicada',
        message:
          'Todavía no hay una versión de la planilla publicada. Cargue y publique una planilla desde «Importar planilla» para ver el seguimiento.',
      }
    case 409:
      return {
        kind: 'unavailable',
        title: 'Archivo no disponible',
        message: failure.error,
      }
    case 413:
      return {
        kind: 'too_large',
        title: 'Archivo demasiado grande',
        message:
          'El archivo supera el tamaño máximo admitido por la plataforma. Verifique que corresponde a la planilla maestra.',
      }
    case 422:
      return {
        kind: 'invalid_upload',
        title: 'Planilla no válida',
        message: failure.error,
      }
    case 500:
      return {
        kind: 'import_failed',
        title: 'La importación no se completó',
        message: failure.error,
      }
    default:
      return {
        kind: 'error',
        title: 'No se pudo completar la operación',
        message: failure.error,
      }
  }
}

/** True when a 404 means "nothing published yet" rather than "not found". */
export function isNoActiveVersion(failure: ApiFailure): boolean {
  return failure.status === 404 && failure.error === NOT_PUBLISHED
}
