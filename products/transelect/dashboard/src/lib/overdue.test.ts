import { describe, expect, it } from 'vitest'
import { isOverdueRow, selectOverdueRows } from './overdue'

const reference = new Date('2026-09-02T21:10:00Z')

function row(estado_resumido: string | null, fecha_90_dias: string | null) {
  return { estado_resumido, fecha_90_dias }
}

describe('isOverdueRow (TR-FUNC-031)', () => {
  it('selects a non-approved row whose 90-day date is before the reference instant', () => {
    expect(isOverdueRow(row('En tramite', '2026-06-01'), reference)).toBe(true)
  })

  it('never selects an approved row, however old its 90-day date', () => {
    expect(isOverdueRow(row('Aprobado', '2020-01-01'), reference)).toBe(false)
  })

  it('never selects a row whose 90-day date is blank or missing', () => {
    expect(isOverdueRow(row('Pendiente', null), reference)).toBe(false)
    expect(isOverdueRow(row('Pendiente', '   '), reference)).toBe(false)
  })

  it('never selects a row whose 90-day date is unparseable', () => {
    expect(isOverdueRow(row('Pendiente', 'no informado'), reference)).toBe(false)
  })

  it('excludes a date that is not yet before the reference instant', () => {
    expect(isOverdueRow(row('Pendiente', '2026-12-31'), reference)).toBe(false)
  })

  it('advances with the reference date — the bug fix the matrix asks for', () => {
    const target = row('Pendiente', '2026-08-27')
    // The source dashboards froze this comparison at new Date('2026-08-26'),
    // so this row could never become overdue there.
    expect(isOverdueRow(target, new Date('2026-08-26T00:00:00Z'))).toBe(false)
    expect(isOverdueRow(target, new Date('2026-09-02T00:00:00Z'))).toBe(true)
  })

  it('filters a row list without mutating it', () => {
    const rows = [row('Aprobado', '2020-01-01'), row('Pendiente', '2020-01-01')]
    expect(selectOverdueRows(rows, reference)).toHaveLength(1)
    expect(rows).toHaveLength(2)
  })
})
