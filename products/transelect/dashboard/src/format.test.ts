import { describe, expect, it } from 'vitest'
import { cell, formatBytes, formatDate, formatNumber, formatPercent, shortHash } from './format'

describe('formatNumber', () => {
  it("matches the source dashboards' es-CL fmt() shape", () => {
    expect(formatNumber(164.6288)).toBe('164,63')
    expect(formatNumber(0)).toBe('0')
    expect(formatNumber(null)).toBe('0')
  })
})

describe('formatPercent', () => {
  it('appends a percent sign to the same es-CL number shape', () => {
    expect(formatPercent((108 / 159) * 100)).toBe('67,92%')
  })
})

describe('cell', () => {
  it('never renders a null or whitespace-only workbook value', () => {
    expect(cell(null)).toBe('')
    expect(cell('  ')).toBe('')
    expect(cell(null, 'Sin información')).toBe('Sin información')
    expect(cell(' Fundo Uno ')).toBe('Fundo Uno')
  })
})

describe('formatDate', () => {
  it('renders an ISO date as DD-MM-YYYY and leaves anything else verbatim', () => {
    expect(formatDate('2026-08-14')).toBe('14-08-2026')
    expect(formatDate('2026-08-14T10:00:00Z')).toBe('14-08-2026')
    expect(formatDate('08 de octubre de 2024')).toBe('08 de octubre de 2024')
    expect(formatDate(null)).toBe('')
  })
})

describe('shortHash / formatBytes', () => {
  it('shortens a content hash to a citable prefix', () => {
    expect(shortHash('82ba5eaed0b1a110b5966b301ca4a0bc')).toBe('82ba5eaed0b1')
    expect(shortHash(null)).toBe('')
  })

  it('renders byte sizes in binary units', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(5710)).toBe('5,58 KiB')
    expect(formatBytes(15716792)).toBe('14,99 MiB')
  })
})
