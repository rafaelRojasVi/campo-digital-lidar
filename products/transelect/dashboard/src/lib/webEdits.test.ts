import { describe, expect, it } from 'vitest'
import type { TranselecOverride } from '../api'
import { canEdit, overrideConflictCode } from '../api'
import { makeRow } from '../test/factories'
import {
  EDITABLE_FIELDS,
  displayValue,
  isWebField,
  overrideFor,
  specFor,
  suggestionsFrom,
  webFieldsDescription,
  webTooltip,
} from './webEdits'

const override: TranselecOverride = {
  id: 31,
  field: 'estado_resumido',
  field_label: 'Estado resumido',
  status: 'aplicada',
  pmf: 'MP001',
  rol: '101',
  numero_predio: '1',
  numero_area_corta: 'A1',
  source_row_number: 2,
  web_value: 'Aprobado',
  planilla_value_at_edit: 'En tramite',
  planilla_value_now: 'En tramite',
  created_by_display_name: 'Ana Pérez',
  created_at: '2026-10-04T15:00:00+00:00',
}

describe('web edit helpers', () => {
  it('lists the eleven editable fields', () => {
    expect(EDITABLE_FIELDS.map((spec) => spec.name).sort()).toEqual(
      [
        'estado',
        'estado_resumido',
        'fecha_90_dias',
        'fecha_ingreso',
        'fecha_ingreso_2',
        'numero_ingreso',
        'numero_ingreso_2',
        'reingreso_legal',
        'reingreso_recrep',
        'reingreso_tec',
        'tipo_rechazo',
      ].sort(),
    )
  })

  it('knows which fields of a row came from the web', () => {
    expect(isWebField(makeRow({ web_fields: ['estado'] }), 'estado')).toBe(true)
    expect(isWebField(makeRow(), 'estado')).toBe(false)
  })

  it('formats dates and builds the tooltip', () => {
    expect(displayValue(specFor('fecha_ingreso'), '2026-03-12')).toBe('12-03-2026')
    expect(displayValue(specFor('estado'), null)).toBe('')
    expect(webTooltip(override, specFor('estado_resumido'))).toBe(
      'Editado en la web por Ana Pérez · 04-10-2026 · en la planilla: En tramite',
    )
  })

  it('finds the applied override of a row and field', () => {
    const row = makeRow({ source_row_number: 2 })
    expect(overrideFor([override], row, 'estado_resumido')?.id).toBe(31)
    expect(overrideFor([override], row, 'estado')).toBeUndefined()
  })

  it('collects distinct suggestions, sorted', () => {
    const rows = [
      makeRow({ estado_resumido: 'En tramite' }),
      makeRow({ estado_resumido: 'Aprobado' }),
      makeRow({ estado_resumido: 'Aprobado' }),
      makeRow({ estado_resumido: null }),
    ]
    expect(suggestionsFrom(rows, 'estado_resumido')).toEqual(['Aprobado', 'En tramite'])
  })

  it('reads the conflict code and the edit permission', () => {
    expect(overrideConflictCode({ detail: 'x', code: 'value_changed' })).toBe('value_changed')
    expect(overrideConflictCode({ detail: 'x' })).toBeNull()
    const grant = (role: 'admin' | 'operator' | 'viewer') => ({
      identity_key: 'k',
      display_name: 'K',
      product_grants: [{ product_key: 'transelect', role }],
    })
    expect(canEdit(grant('operator'))).toBe(true)
    expect(canEdit(grant('viewer'))).toBe(false)
  })
})

describe('webFieldsDescription', () => {
  it('names the edited fields, joined with «y»', () => {
    expect(webFieldsDescription(['numero_ingreso_2'])).toBe('N.º ingreso 2 editado en la web')
    expect(webFieldsDescription(['reingreso_tec', 'reingreso_legal'])).toBe(
      'Reingreso técnico y Reingreso legal editados en la web',
    )
    expect(webFieldsDescription(['fecha_ingreso', 'fecha_ingreso_2', 'fecha_90_dias'])).toBe(
      'Fecha ingreso, Fecha ingreso 2 y 90 días editados en la web',
    )
  })
})
