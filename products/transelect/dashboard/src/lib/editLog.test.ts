import { describe, expect, it } from 'vitest'
import { makeHistory, makeHistoryEntry } from '../test/factories'
import {
  entryHref,
  formatEditWhen,
  isMuted,
  logValue,
  pillLabel,
  pillVisible,
  stateLabel,
} from './editLog'

// 12:00 in Santiago (UTC-3 in October 2026).
const NOW = new Date('2026-10-05T15:00:00Z')

describe('the pill', () => {
  it('counts edits in force, singular and plural, and adds what needs review', () => {
    expect(pillLabel({ in_force_count: 1, needs_review_count: 0 })).toBe('1 edición web')
    expect(pillLabel({ in_force_count: 5, needs_review_count: 0 })).toBe('5 ediciones web')
    expect(pillLabel({ in_force_count: 5, needs_review_count: 2 })).toBe(
      '5 ediciones web · 2 por revisar',
    )
  })

  it('exists only after a load with something in force or to review', () => {
    expect(pillVisible(null)).toBe(false)
    expect(pillVisible(makeHistory({ in_force_count: 0, needs_review_count: 0 }))).toBe(false)
    expect(pillVisible(makeHistory({ in_force_count: 0, needs_review_count: 1 }))).toBe(true)
    expect(pillVisible(makeHistory({ in_force_count: 3 }))).toBe(true)
  })
})

describe('state labels', () => {
  it.each([
    ['aplicada', null, null, false],
    ['en_conflicto', null, 'en conflicto: la planilla cambió', false],
    ['huerfana', null, 'sin fila en la versión activa', false],
    ['incorporada', null, 'ya está en la planilla', true],
    ['incorporated', 'Ana', 'se incorporó a la planilla', true],
    ['superseded', 'Ana', 'reemplazada por una edición posterior', true],
    ['discarded', 'Ana', 'revertida al valor de la planilla · Ana', true],
    ['kept', 'Luis', 'conservada al resolver un conflicto · Luis', true],
  ] as const)('%s', (state, who, label, muted) => {
    expect(stateLabel(makeHistoryEntry({ state, ended_by_display_name: who }))).toBe(label)
    expect(isMuted(state)).toBe(muted)
  })
})

describe('dates in Chile time', () => {
  it('reads «hoy», «ayer» or the date', () => {
    expect(formatEditWhen('2026-10-05T12:41:00Z', NOW)).toBe('hoy 09:41')
    expect(formatEditWhen('2026-10-04T20:02:00Z', NOW)).toBe('ayer 17:02')
    expect(formatEditWhen('2026-10-03T15:00:00Z', NOW)).toBe('03-10-2026')
  })

  it('uses the Santiago day, not the UTC day', () => {
    // 02:30 UTC on the 5th is 23:30 on the 4th in Santiago.
    expect(formatEditWhen('2026-10-05T02:30:00Z', NOW)).toBe('ayer 23:30')
  })
})

describe('values and links', () => {
  it('writes an empty value as «(vacío)» and dates as dd-mm-aaaa', () => {
    expect(logValue('estado', null)).toBe('(vacío)')
    expect(logValue('estado', '  ')).toBe('(vacío)')
    expect(logValue('fecha_ingreso', '2026-03-12')).toBe('12-03-2026')
    expect(logValue('estado', 'Aprobado')).toBe('Aprobado')
  })

  it('links an entry with a row to the Explorador, filtered to its PMF with the row open', () => {
    expect(entryHref(makeHistoryEntry({ pmf: 'MP 001', source_row_number: 7 }))).toBe(
      '/transelec/explorador?q=MP+001&fila=7',
    )
    expect(entryHref(makeHistoryEntry({ source_row_number: null }))).toBeNull()
  })
})
