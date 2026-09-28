/**
 * The headline's arithmetic, and the filter each bucket links to.
 *
 * These are the guarantees the 29-Jul Power BI summary does not hold: its
 * 101 + 56 + 3 buckets sum to 160 against a stated total of 159, because one
 * PMF appears under two summarized states.
 */
import { describe, expect, it } from 'vitest'
import { makeSummary } from '../test/factories'
import {
  bucketFilters,
  bucketsReconcile,
  detalleRows,
  statusBuckets,
  statusSegments,
} from './statusHeadline'
import { EMPTY_FILTERS } from '../api'
import { searchFromFilters } from './filterUrl'

describe('statusBuckets', () => {
  it('sums exactly to the PMF total of the filtered population', () => {
    const summary = makeSummary()
    const buckets = statusBuckets(summary)

    expect(buckets.reduce((sum, bucket) => sum + bucket.count, 0)).toBe(summary.pmf_count)
    expect(bucketsReconcile(buckets, summary.pmf_count)).toBe(true)
  })

  it('reports every count against the same population it is a part of', () => {
    const summary = makeSummary({
      pmf_count: 10,
      estado_resumido_pmf: {
        aprobado: 5,
        en_tramite: 3,
        pendiente: 1,
        tachado: 1,
        sin_estado: 0,
      },
    })

    const aprobado = statusBuckets(summary).find((bucket) => bucket.key === 'aprobado')

    expect(aprobado?.count).toBe(5)
    expect(aprobado?.percentage).toBe(50)
  })

  it('hides the defensive sin_estado bucket only while it is empty', () => {
    const empty = statusBuckets(makeSummary())
    expect(empty.map((bucket) => bucket.key)).not.toContain('sin_estado')

    const withUnknown = statusBuckets(
      makeSummary({
        pmf_count: 7,
        estado_resumido_pmf: {
          aprobado: 3,
          en_tramite: 1,
          pendiente: 1,
          tachado: 1,
          sin_estado: 1,
        },
      }),
    )
    expect(withUnknown.map((bucket) => bucket.key)).toContain('sin_estado')
    expect(bucketsReconcile(withUnknown, 7)).toBe(true)
  })

  it('flags a population whose buckets do not account for every plan', () => {
    const broken = makeSummary({ pmf_count: 99 })
    expect(bucketsReconcile(statusBuckets(broken), 99)).toBe(false)
  })

  it('uses tone for meaning: tachado is neutral, not an alarm', () => {
    const tones = Object.fromEntries(
      statusBuckets(makeSummary()).map((bucket) => [bucket.key, bucket.tone]),
    )
    expect(tones).toMatchObject({
      aprobado: 'approved',
      en_tramite: 'progress',
      tachado: 'struck',
    })
  })

  it('keeps the segments and the cards describing the same numbers', () => {
    const buckets = statusBuckets(makeSummary())
    expect(statusSegments(buckets).map((segment) => segment.value)).toEqual(
      buckets.map((bucket) => bucket.count),
    )
  })
})

describe('bucketFilters', () => {
  it('produces the Explorer filter that reproduces the bucket', () => {
    const summary = makeSummary({
      estado_resumido_valores: { aprobado: ['Aprobado'], en_tramite: ['En tramite'] },
    })
    const aprobado = statusBuckets(summary).find((bucket) => bucket.key === 'aprobado')!

    expect(searchFromFilters(bucketFilters(EMPTY_FILTERS, aprobado))).toBe(
      '?estado_resumido=Aprobado',
    )
  })

  it('carries every source spelling of one state into the filter', () => {
    const summary = makeSummary({
      estado_resumido_valores: { en_tramite: ['En tramite', 'En trámite'] },
    })
    const enTramite = statusBuckets(summary).find((bucket) => bucket.key === 'en_tramite')!

    expect(bucketFilters(EMPTY_FILTERS, enTramite).estado_resumido).toEqual([
      'En tramite',
      'En trámite',
    ])
  })

  it('preserves the filters the reader already had, replacing only the status', () => {
    const summary = makeSummary({ estado_resumido_valores: { aprobado: ['Aprobado'] } })
    const aprobado = statusBuckets(summary).find((bucket) => bucket.key === 'aprobado')!

    const next = bucketFilters(
      { ...EMPTY_FILTERS, empresa: ['Ecores'], estado_resumido: ['Tachado'] },
      aprobado,
    )

    expect(next.empresa).toEqual(['Ecores'])
    expect(next.estado_resumido).toEqual(['Aprobado'])
  })

  it('offers no filter for a bucket no equality filter can reproduce', () => {
    const summary = makeSummary({
      pmf_count: 7,
      estado_resumido_pmf: { aprobado: 3, en_tramite: 1, pendiente: 1, tachado: 1, sin_estado: 1 },
      estado_resumido_valores: { aprobado: ['Aprobado'] },
    })
    const sinEstado = statusBuckets(summary).find((bucket) => bucket.key === 'sin_estado')!

    expect(sinEstado.filterValues).toEqual([])
  })
})

describe('detalleRows', () => {
  it('sums to the same PMF population as the headline', () => {
    const summary = makeSummary()
    expect(detalleRows(summary).reduce((sum, row) => sum + row.count, 0)).toBe(
      summary.estado_detalle_pmf.reduce((sum, item) => sum + item.count, 0),
    )
  })

  it('keeps the source spelling rather than a normalized rewrite', () => {
    const summary = makeSummary({
      estado_detalle_pmf: [{ label: 'En Evaluacion', normalized: 'en evaluacion', count: 2 }],
    })
    expect(detalleRows(summary)[0].label).toBe('En Evaluacion')
  })

  it('marks only the states that genuinely warrant attention', () => {
    const summary = makeSummary({
      estado_detalle_pmf: [
        { label: 'Aprobado', normalized: 'aprobado', count: 2 },
        { label: 'Recurso reposicion rechazado', normalized: 'recurso reposicion rechazado', count: 1 },
      ],
    })
    expect(detalleRows(summary).map((row) => row.attention)).toEqual([false, true])
  })

  it('names a missing detailed state rather than dropping it', () => {
    const summary = makeSummary({
      estado_detalle_pmf: [{ label: null, normalized: null, count: 3 }],
    })
    expect(detalleRows(summary)[0].label).toBe('Sin estado informado')
  })
})
