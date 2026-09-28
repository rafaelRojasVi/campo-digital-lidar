import { describe, expect, it } from 'vitest'
import { classifyFailure, isNoActiveVersion } from './apiState'

describe('classifyFailure', () => {
  it('maps every required UI state to its own kind', () => {
    expect(classifyFailure({ status: 0, error: 'x' }).kind).toBe('unavailable')
    expect(classifyFailure({ status: 401, error: 'Not authenticated.' }).kind).toBe(
      'unauthenticated',
    )
    expect(classifyFailure({ status: 403, error: 'Not permitted for this product.' }).kind).toBe(
      'forbidden',
    )
    expect(classifyFailure({ status: 404, error: 'x' }).kind).toBe('empty')
    expect(classifyFailure({ status: 409, error: 'x' }).kind).toBe('unavailable')
    expect(classifyFailure({ status: 413, error: 'x' }).kind).toBe('too_large')
    expect(classifyFailure({ status: 422, error: 'x' }).kind).toBe('invalid_upload')
    expect(classifyFailure({ status: 500, error: 'x' }).kind).toBe('import_failed')
    expect(classifyFailure({ status: 418, error: 'x' }).kind).toBe('error')
  })

  it('shows the API’s own generic Spanish copy for a contract violation', () => {
    const detail = 'La planilla no cumple el contrato de origen esperado. Contacte a soporte.'
    expect(classifyFailure({ status: 422, error: detail }).message).toBe(detail)
  })

  it('states that the active version is unchanged when an import fails', () => {
    const detail = 'No se pudo verificar la importación. La versión activa no cambió.'
    const view = classifyFailure({ status: 500, error: detail })
    expect(view.title).toBe('La importación no se completó')
    expect(view.message).toContain('La versión activa no cambió.')
  })

  it('never echoes a raw English backend string as the unauthorized message', () => {
    const view = classifyFailure({ status: 401, error: 'Not authenticated.' })
    expect(view.message).not.toContain('Not authenticated')
    expect(view.message).toContain('iniciar sesión')
  })
})

describe('isNoActiveVersion', () => {
  it('recognises the API’s own "nothing published yet" 404', () => {
    expect(
      isNoActiveVersion({ status: 404, error: 'No hay una versión publicada de Transelec.' }),
    ).toBe(true)
    expect(
      isNoActiveVersion({
        status: 404,
        error: 'No se encontró el PMF solicitado en la versión activa.',
      }),
    ).toBe(false)
    expect(isNoActiveVersion({ status: 403, error: 'x' })).toBe(false)
  })
})
