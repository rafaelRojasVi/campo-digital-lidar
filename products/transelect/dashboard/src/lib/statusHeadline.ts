/**
 * "Estado de los planes de manejo" — the question the dashboard exists for.
 *
 * Marianne produces Javier's recurring summary from the workbook's `Estado
 * resumido` column, and the question he asks of it is always the same one:
 * what state are the management plans in? The shipped Resumen answered a
 * neighbouring question first — an approval *percentage*, at two grains, with
 * the plan counts themselves demoted to a reference strip — so a reader had
 * to reconstruct "how many are approved" from a percentage and a denominator.
 *
 * This module builds the counts that answer it directly, at PMF grain, each
 * one carrying the filter that reproduces it in the Explorador.
 *
 * Nothing here computes a business number. The counts, and the raw source
 * spellings behind each of them, come from `GET /transelec/summary`.
 */

import type { HeroStateCounts, TranselecFilterState, TranselecSummary } from '../api'
import type { CompositionSegment, SegmentTone } from '../ui/CompositionBar'

/** The API's own hero-state keys, in the order a reader should meet them. */
export const STATUS_ORDER = [
  'aprobado',
  'en_tramite',
  'pendiente',
  'tachado',
  'sin_estado',
] as const

export type StatusKey = (typeof STATUS_ORDER)[number]

const STATUS_LABELS: Record<StatusKey, string> = {
  aprobado: 'Aprobado',
  en_tramite: 'En trámite',
  pendiente: 'Pendiente',
  tachado: 'Tachado',
  sin_estado: 'Sin estado resumido',
}

/**
 * Semantic colour, used consistently and never as the only signal.
 *
 * `Tachado` is neutral grey rather than red: a struck-out plan is a closed
 * record, not an alarm. Red is reserved for the detailed states that actually
 * warrant it, which live in the drill-down below the headline.
 */
const STATUS_TONES: Record<StatusKey, SegmentTone> = {
  aprobado: 'approved',
  en_tramite: 'progress',
  pendiente: 'late',
  tachado: 'struck',
  sin_estado: 'none',
}

export interface StatusBucket {
  key: StatusKey
  label: string
  count: number
  tone: SegmentTone
  /** The percentage of the same PMF population this bucket represents. */
  percentage: number
  /**
   * The literal `Estado resumido` values that reproduce this bucket, or an
   * empty list when no equality filter can (`sin_estado`). A bucket with no
   * filter values is rendered as plain text rather than as a dead link.
   */
  filterValues: string[]
}

/**
 * The headline buckets, at PMF grain.
 *
 * Every bucket the population contains is returned, including the ones
 * reading zero for the known vocabulary, so the row's shape does not change
 * as the filter narrows. `sin_estado` is the exception: it is the API's
 * defensive bucket for an unrecognised value, so it appears only when it has
 * something in it — and when it does, it is counted, never dropped, which is
 * what keeps the buckets summing to the total.
 */
export function statusBuckets(summary: TranselecSummary): StatusBucket[] {
  const counts: HeroStateCounts = summary.estado_resumido_pmf
  const total = summary.pmf_count

  return STATUS_ORDER.filter((key) => key !== 'sin_estado' || counts.sin_estado > 0).map((key) => ({
    key,
    label: STATUS_LABELS[key],
    count: counts[key],
    tone: STATUS_TONES[key],
    percentage: total ? (counts[key] / total) * 100 : 0,
    filterValues: summary.estado_resumido_valores[key] ?? [],
  }))
}

/** The same buckets as a composition bar's segments. */
export function statusSegments(buckets: StatusBucket[]): CompositionSegment[] {
  return buckets.map((bucket) => ({
    key: bucket.key,
    label: bucket.label,
    value: bucket.count,
    tone: bucket.tone,
  }))
}

/**
 * True when the buckets account for every plan in the population.
 *
 * Asserted in the interface rather than only in a test: if a future import
 * ever breaks it, the reader is told the total is unreliable instead of
 * being shown buckets that quietly do not add up — which is exactly the
 * failure mode of the Power BI summary this replaces (101 + 56 + 3 = 160
 * against a stated 159).
 */
export function bucketsReconcile(buckets: StatusBucket[], pmfCount: number): boolean {
  return buckets.reduce((sum, bucket) => sum + bucket.count, 0) === pmfCount
}

/**
 * The filter state that reproduces one bucket in the Explorador.
 *
 * The current filter is preserved and `estado_resumido` replaced, so a
 * reader who narrowed to one company before clicking a status lands in that
 * company's plans of that status — not in every plan of that status.
 */
export function bucketFilters(
  filters: TranselecFilterState,
  bucket: StatusBucket,
): TranselecFilterState {
  return { ...filters, estado_resumido: bucket.filterValues }
}

/**
 * The detailed `Estado` drill-down, as display rows.
 *
 * Deliberately a table, not a second chart: thirteen source spellings
 * collapse to eleven states here, several of them differing by one word
 * ("Recurso reposicion aprobado" against "Recurso reposicion rechazado"),
 * and a reader comparing those needs to read them, not to match hues to a
 * legend.
 */
export interface DetalleRow {
  key: string
  label: string
  count: number
  percentage: number
  /** Red only where the detailed state genuinely warrants it. */
  attention: boolean
}

export function detalleRows(summary: TranselecSummary): DetalleRow[] {
  const total = summary.pmf_count
  return summary.estado_detalle_pmf.map((item, index) => ({
    key: item.normalized ?? `sin-estado-${index}`,
    label: item.label ?? 'Sin estado informado',
    count: item.count,
    percentage: total ? (item.count / total) * 100 : 0,
    attention: (item.normalized ?? '').includes('rechaz'),
  }))
}
