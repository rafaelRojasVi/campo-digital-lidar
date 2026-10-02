import { describe, expect, it } from 'vitest'
import { ingreso2InSource } from './ingreso'

describe('ingreso2InSource', () => {
  it('is unknown until the active version is known', () => {
    expect(ingreso2InSource(null)).toBeNull()
    expect(ingreso2InSource(undefined)).toBeNull()
  })

  it('is false for a version whose source had no second ingreso columns', () => {
    expect(ingreso2InSource(['pmf', 'fecha_ingreso', 'numero_ingreso'])).toBe(false)
  })

  it('is true when either column was in the source', () => {
    expect(ingreso2InSource(['pmf', 'numero_ingreso_2'])).toBe(true)
    expect(ingreso2InSource(['pmf', 'fecha_ingreso_2', 'numero_ingreso_2'])).toBe(true)
  })
})
