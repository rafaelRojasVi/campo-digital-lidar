import { describe, expect, it } from 'vitest'
import {
  LIFECYCLE_GROUP_LABELS,
  lifecycleGroupSegments,
  lifecycleStepSegments,
  lifecycleStepText,
  needsReview,
} from './lifecycle'
import { ruleFor } from './rules'
import { makeLifecycle, makeLifecycleRow } from '../test/factories'

describe('lifecycle_pmf_v1 labels and bars', () => {
  it('orders the groups approved first, each with its own tone', () => {
    const segments = lifecycleGroupSegments(makeLifecycle())
    expect(segments.map((segment) => segment.key)).toEqual([
      'aprobado',
      'en_tramite',
      'descartado',
      'desistido',
      'sin_clasificar',
    ])
    expect(segments.map((segment) => segment.tone)).toEqual([
      'approved',
      'progress',
      'struck',
      'struck',
      'none',
    ])
    expect(segments.map((segment) => segment.value)).toEqual([1, 2, 0, 0, 1])
  })

  it('reserves the attention tone for a rejection waiting for its recurso', () => {
    const late = lifecycleStepSegments(makeLifecycle()).filter((segment) => segment.tone === 'late')
    expect(late.map((segment) => segment.key)).toEqual(['rechazado_esperando_recurso'])
  })

  it('shows Descartado and Desistido with their own words, never merged', () => {
    expect(LIFECYCLE_GROUP_LABELS.descartado).toBe('Descartado')
    expect(LIFECYCLE_GROUP_LABELS.desistido).toBe('Desistido')
  })

  it('describes a PMF by its step, or by why it could not be placed', () => {
    expect(
      lifecycleStepText(makeLifecycleRow({ lifecycle_step: 'rechazado_esperando_recurso' })),
    ).toBe('Rechazado, esperando recurso')
    expect(
      lifecycleStepText(makeLifecycleRow({ lifecycle_group: 'aprobado', lifecycle_step: null })),
    ).toBe('—')
    expect(
      lifecycleStepText(
        makeLifecycleRow({
          lifecycle_group: 'sin_clasificar',
          lifecycle_step: null,
          lifecycle_reason: 'estado_desconocido',
        }),
      ),
    ).toBe('«Estado» con un valor que esta regla no reconoce')
  })

  it('marks for review an unclassified PMF and one whose rows disagree', () => {
    expect(needsReview(makeLifecycleRow())).toBe(false)
    expect(needsReview(makeLifecycleRow({ lifecycle_flags: ['filas_no_coinciden'] }))).toBe(true)
    expect(
      needsReview(
        makeLifecycleRow({
          lifecycle_group: 'sin_clasificar',
          lifecycle_step: null,
          lifecycle_reason: 'resumido_desconocido',
        }),
      ),
    ).toBe(true)
  })

  it('explains the rule in «Cómo se calcula», provisional', () => {
    const rule = ruleFor('lifecycle_pmf_v1')
    expect(rule?.sourceColumns).toEqual([
      'PMF',
      'Estado resumido',
      'Estado',
      'N Ingreso',
      'N Ingreso2',
      'Tipo de rechazo',
    ])
    expect(rule?.steps.join(' ')).toContain('provisional')
  })
})
