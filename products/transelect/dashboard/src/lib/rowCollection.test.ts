import { describe, expect, it, vi } from 'vitest'
import { EMPTY_FILTERS, type ResumenRow } from '../api'
import { collectAllRows, deriveFilterOptions } from './rowCollection'

function row(overrides: Partial<ResumenRow> & { source_row_number: number }): ResumenRow {
  return {
    predio_ref: null,
    rol_ref: null,
    area_ref: null,
    pmf: `PMF-${overrides.source_row_number}`,
    carpeta_source: null,
    carpeta_normalizada: null,
    pas: null,
    estado: null,
    estado_resumido: null,
    tipo_rechazo: null,
    reingreso_tec: null,
    reingreso_legal: null,
    reingreso_recrep: null,
    tipo_propietario: null,
    id_transelec: null,
    rol: null,
    numero_predio: null,
    numero_area_corta: null,
    superficie_corta: null,
    superficie_total_corta: null,
    fecha_ingreso: null,
    numero_ingreso: null,
    fecha_90_dias: null,
    hoy_raw: null,
    empresa: null,
    id_predio_unico_ii: null,
    id_pmf: null,
    id_predio_unico: null,
    predio_group_key: `k-${overrides.source_row_number}`,
    tramite: null,
    sector: null,
    aef: null,
    quien_solicita: null,
    fecha_solicitud: null,
    fecha_corta: null,
    fecha_termino: null,
    chronology_flags: [],
    ...overrides,
  }
}

describe('collectAllRows', () => {
  it('follows the cursor to the end and concatenates every page', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        data: {
          items: [row({ source_row_number: 1 })],
          next_cursor: 'c1',
          has_more: true,
          total_count: 3,
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        data: {
          items: [row({ source_row_number: 2 })],
          next_cursor: 'c2',
          has_more: true,
          total_count: 3,
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        data: {
          items: [row({ source_row_number: 3 })],
          next_cursor: null,
          has_more: false,
          total_count: 3,
        },
      })

    const result = await collectAllRows(EMPTY_FILTERS, { fetchPage, limit: 1 })

    expect(result).toMatchObject({ ok: true, truncated: false })
    expect(result.ok && result.rows.map((entry) => entry.source_row_number)).toEqual([1, 2, 3])
    expect(fetchPage.mock.calls.map((call) => call[1].cursor)).toEqual([null, 'c1', 'c2'])
  })

  it('propagates a failure instead of returning a partial row set as success', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        data: {
          items: [row({ source_row_number: 1 })],
          next_cursor: 'c1',
          has_more: true,
          total_count: 2,
        },
      })
      .mockResolvedValueOnce({ ok: false, status: 401, error: 'Not authenticated.' })

    await expect(collectAllRows(EMPTY_FILTERS, { fetchPage, limit: 1 })).resolves.toEqual({
      ok: false,
      status: 401,
      error: 'Not authenticated.',
    })
  })

  it('reports truncation rather than looping forever on an endless cursor', async () => {
    const fetchPage = vi.fn().mockResolvedValue({
      ok: true,
      data: {
        items: [row({ source_row_number: 1 })],
        next_cursor: 'always',
        has_more: true,
        total_count: 999999,
      },
    })

    const result = await collectAllRows(EMPTY_FILTERS, { fetchPage, limit: 1, maxPages: 4 })

    expect(result).toMatchObject({ ok: true, truncated: true })
    expect(fetchPage).toHaveBeenCalledTimes(4)
  })
})

describe('deriveFilterOptions', () => {
  it('collects distinct, non-blank values per filterable field, collated in Spanish', () => {
    const options = deriveFilterOptions([
      row({
        source_row_number: 1,
        estado_resumido: 'En tramite',
        empresa: 'Ñuble Forestal',
        pas: ' PAS 148 ',
        sector: 'Norte',
        tipo_propietario: 'Servidumbre firmada',
      }),
      row({
        source_row_number: 2,
        estado_resumido: 'Aprobado',
        empresa: 'Austral',
        pas: 'PAS 148',
        sector: '   ',
        tipo_propietario: null,
      }),
      row({ source_row_number: 3, estado_resumido: 'Aprobado', empresa: 'Zapallar' }),
    ])

    expect(options.estado_resumido).toEqual(['Aprobado', 'En tramite'])
    expect(options.empresa).toEqual(['Austral', 'Ñuble Forestal', 'Zapallar'])
    expect(options.pas).toEqual(['PAS 148'])
    expect(options.sector).toEqual(['Norte'])
    expect(options.tipo_propietario).toEqual(['Servidumbre firmada'])
  })

  it('returns empty lists for an empty row set', () => {
    expect(deriveFilterOptions([])).toEqual({
      estado_resumido: [],
      empresa: [],
      pas: [],
      sector: [],
      tipo_propietario: [],
      aef: [],
      quien_solicita: [],
    })
  })
})
