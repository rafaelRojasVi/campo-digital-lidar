import { describe, expect, it } from 'vitest'
import { CSV_COLUMNS, buildCsv, csvFilename } from './csv.ts'
import { makeFeature, testFeatures } from '../test/fixtures.ts'

describe('buildCsv', () => {
  it('emits the source-projection column header first', () => {
    const csv = buildCsv([])
    expect(csv.split('\r\n')[0]).toBe(CSV_COLUMNS.join(','))
  })

  it('emits one row per feature with quality flags joined by |', () => {
    const csv = buildCsv(testFeatures())
    const lines = csv.trim().split('\r\n')

    expect(lines).toHaveLength(1 + 6)
    expect(lines[5]).toContain('invalid_geometry|truncated_use_code_2026')
    expect(lines[5]).toContain('false')
  })

  it('quotes values containing commas or quotes', () => {
    const feature = makeFeature({ desc_uso: 'Plantacion, "mixta"' })
    const csv = buildCsv([feature])

    expect(csv).toContain('"Plantacion, ""mixta"""')
  })

  it('derives geometry hectares from source units', () => {
    const feature = makeFeature({ geometry_area_source_units: 125_000 })
    const csv = buildCsv([feature])
    const row = csv.trim().split('\r\n')[1]

    expect(row).toContain('12.5')
  })
})

describe('csvFilename', () => {
  it('names the file by snapshot and date', () => {
    expect(csvFilename(3)).toMatch(/^forestry-snapshot-3-filtrado-\d{4}-\d{2}-\d{2}\.csv$/)
  })
})
