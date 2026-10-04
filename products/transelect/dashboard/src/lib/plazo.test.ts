import { describe, expect, it } from 'vitest'
import { cruceText, indexPlazos, plazoBaseText, plazoDetail, plazoText } from './plazo'
import { ruleFor } from './rules'
import { makePlazoPmf, makePlazos } from '../test/factories'

describe('plazo_conaf_90_habiles_v1 wording', () => {
  it('says when the term ends and how many business days are left', () => {
    expect(plazoText(makePlazoPmf())).toBe('vence el 10-12-2026 · quedan 68 días hábiles')
    expect(plazoText(makePlazoPmf({ estado: 'por_vencer', remaining_business_days: 1 }))).toBe(
      'vence el 10-12-2026 · queda 1 día hábil',
    )
  })

  it('says «vence hoy» on the deadline day, never «quedan 0»', () => {
    expect(plazoText(makePlazoPmf({ estado: 'por_vencer', remaining_business_days: 0 }))).toBe(
      'vence hoy (10-12-2026)',
    )
  })

  it('counts business days since a passed deadline, and only when there are some', () => {
    const vencido = makePlazoPmf({ estado: 'vencido', deadline: '2026-07-10' })
    expect(plazoText({ ...vencido, remaining_business_days: -37 })).toBe(
      'venció el 10-07-2026 · hace 37 días hábiles',
    )
    // A Friday deadline seen on Saturday: past, with no business day elapsed since.
    expect(plazoText({ ...vencido, remaining_business_days: 0 })).toBe('venció el 10-07-2026')
  })

  it('names why there is no count', () => {
    expect(plazoText(makePlazoPmf({ estado: 'no_aplica' }))).toBe('Proceso cerrado')
    expect(plazoText(makePlazoPmf({ estado: 'sin_fecha', base_field: null }))).toBe(
      'Sin fecha de ingreso',
    )
    expect(
      plazoText(makePlazoPmf({ estado: 'sin_fecha_texto', base_field: 'fecha_ingreso_2' })),
    ).toBe('«Fecha de ingreso2» no se pudo leer como una fecha')
    expect(plazoText(makePlazoPmf({ estado: 'conflicto' }))).toBe(
      'Las filas del PMF tienen fechas de ingreso distintas',
    )
  })

  it('names the ingreso the clock started from', () => {
    expect(plazoBaseText(makePlazoPmf({ base_field: 'fecha_ingreso_2' }))).toBe(
      'Fecha de ingreso2 · 03-08-2026',
    )
    expect(plazoBaseText(makePlazoPmf({ base_field: null, base_date: null }))).toBe('—')
  })

  it('compares the planilla «90 dias» with the computed deadline', () => {
    expect(cruceText(makePlazoPmf())).toBe('Coincide con el cálculo')
    expect(
      cruceText(
        makePlazoPmf({ cruce: 'difiere', planilla_90_dias: '2026-07-01', diferencia_dias: -9 }),
      ),
    ).toBe('Difiere: la planilla dice 01-07-2026, 9 días antes del cálculo')
    expect(
      cruceText(
        makePlazoPmf({ cruce: 'difiere', planilla_90_dias: '2026-12-11', diferencia_dias: 1 }),
      ),
    ).toBe('Difiere: la planilla dice 11-12-2026, 1 día después del cálculo')
    expect(cruceText(makePlazoPmf({ cruce: 'sin_dato', planilla_90_dias: null }))).toBe(
      'La planilla no trae una fecha «90 dias» legible',
    )
    expect(cruceText(makePlazoPmf({ cruce: 'sin_calculo' }))).toBe('Sin cálculo con qué comparar')
  })

  it('indexes the plazos by PMF and builds the drawer detail', () => {
    const data = makePlazos()
    expect(indexPlazos(data).get('MP002')?.estado).toBe('vencido')
    expect(indexPlazos(null).size).toBe(0)
    expect(plazoDetail(data, 'MP002')).toEqual({
      entry: data.pmfs[1],
      observedOn: '2026-09-02',
      calendarVersion: '0.105',
    })
    expect(plazoDetail(data, 'NOPE')).toBeNull()
    expect(plazoDetail(null, 'MP002')).toBeNull()
  })

  it('explains both rules in «Cómo se calcula», provisional', () => {
    const rule = ruleFor('plazo_conaf_90_habiles_v1')
    expect(rule?.sourceColumns).toEqual([
      'PMF',
      'Fecha de ingreso2',
      'Fecha de ingreso1',
      '90 dias',
      'Estado resumido',
    ])
    expect(rule?.steps.join(' ')).toContain('provisional')
    expect(ruleFor('vencimiento_columna_90_dias_legacy')?.sourceColumns).toEqual([
      'Estado resumido',
      '90 dias',
    ])
  })
})
