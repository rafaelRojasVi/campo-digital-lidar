import { describe, expect, it } from 'vitest'
import {
  OWNER_UNKNOWN_LABEL,
  buildOwnerStatusTable,
  ownerLabel,
  ownerStageBucket,
} from './ownerStatus'

describe('ownerStageBucket (TR-FUNC-013)', () => {
  it("maps ownerStage()'s four outputs onto the source table's four columns", () => {
    expect(ownerStageBucket('Aprobado')).toBe('approved')
    expect(ownerStageBucket('En tramite')).toBe('progress')
    expect(ownerStageBucket('En trámite')).toBe('progress')
    expect(ownerStageBucket('Rechazado')).toBe('rejected')
    expect(ownerStageBucket('Pendiente')).toBe('pending')
    expect(ownerStageBucket('Tachado')).toBe('pending')
    expect(ownerStageBucket(null)).toBe('pending')
  })
})

describe('ownerLabel', () => {
  it('falls back to "Sin información" for a blank or literal dash owner type', () => {
    expect(ownerLabel(null)).toBe(OWNER_UNKNOWN_LABEL)
    expect(ownerLabel('  ')).toBe(OWNER_UNKNOWN_LABEL)
    expect(ownerLabel('-')).toBe(OWNER_UNKNOWN_LABEL)
    expect(ownerLabel(' Servidumbre firmada ')).toBe('Servidumbre firmada')
  })
})

describe('buildOwnerStatusTable', () => {
  const response = {
    basis: 'owner_stage_legacy',
    rows: [
      { tipo_propietario: 'Particular', owner_stage: 'Aprobado', predio_count: 3 },
      { tipo_propietario: 'Particular', owner_stage: 'Rechazado', predio_count: 1 },
      { tipo_propietario: 'Particular', owner_stage: 'Tachado', predio_count: 1 },
      { tipo_propietario: 'Servidumbre firmada', owner_stage: 'Aprobado', predio_count: 5 },
      { tipo_propietario: 'Servidumbre firmada', owner_stage: 'En tramite', predio_count: 2 },
      { tipo_propietario: '-', owner_stage: 'Pendiente', predio_count: 2 },
    ],
  }

  it('pivots long-format API rows into the source table shape', () => {
    const table = buildOwnerStatusTable(response)
    const particular = table.rows.find((row) => row.tipoPropietario === 'Particular')

    expect(particular).toEqual({
      tipoPropietario: 'Particular',
      approved: 3,
      progress: 0,
      rejected: 1,
      pending: 1,
      total: 5,
      approvedPercentage: 60,
    })
  })

  it('sorts by approved count descending, then by owner name in Spanish', () => {
    const table = buildOwnerStatusTable(response)
    expect(table.rows.map((row) => row.tipoPropietario)).toEqual([
      'Servidumbre firmada',
      'Particular',
      OWNER_UNKNOWN_LABEL,
    ])
  })

  it('produces a TOTAL row whose columns sum every group', () => {
    const table = buildOwnerStatusTable(response)
    expect(table.total).toEqual({
      tipoPropietario: 'TOTAL',
      approved: 8,
      progress: 2,
      rejected: 1,
      pending: 3,
      total: 14,
      approvedPercentage: (8 / 14) * 100,
    })
  })

  it('carries the API basis identifier through so the UI can show it', () => {
    expect(buildOwnerStatusTable(response).basis).toBe('owner_stage_legacy')
  })

  it('returns an empty table with a zeroed TOTAL when the API returns no rows', () => {
    const table = buildOwnerStatusTable({ basis: 'owner_stage_legacy', rows: [] })
    expect(table.rows).toEqual([])
    expect(table.total.total).toBe(0)
    expect(table.total.approvedPercentage).toBe(0)
  })
})
