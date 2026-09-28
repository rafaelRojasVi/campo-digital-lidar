/**
 * Presentation shapes derived from `GET /transelec/summary`.
 *
 * Nothing here computes a business value. Every number is already decided by
 * the API under a named legacy rule; this module only decides which of them a
 * reader should see first, and which should be quiet.
 *
 * That split is the point. The shipped interface rendered all eight KPI
 * values as eight identical cards, so "Roles" — a reference count nobody acts
 * on — shouted exactly as loudly as "Pendientes prioritarios", the number
 * that means somebody has work to do. Three groups replace the flat row:
 *
 *   scale      reference counts, quiet, in a rule-separated strip
 *   attention  numbers that imply work, with a route that resolves them
 *   composition part-to-whole, as stacked bars at both grains
 */

import type { TranselecSummary } from '../api'
import { formatInteger, formatNumber } from '../format'
import type { CompositionSegment } from '../ui/CompositionBar'
import type { StatItem } from '../ui/Primitives'

/**
 * The reference counts.
 *
 * Labels and sub-labels are the source dashboards' own, and the `id`s are the
 * shipped KPI ids, so a number that moved between groups can still be found
 * by the name it has always had.
 */
export function buildScaleStats(summary: TranselecSummary): StatItem[] {
  return [
    { id: 'pmf', label: 'PMF', value: formatInteger(summary.pmf_count), sub: 'planes únicos' },
    {
      id: 'predios',
      label: 'Predios',
      value: formatInteger(summary.predio_count),
      sub: 'identificadores únicos',
    },
    { id: 'roles', label: 'Roles', value: formatInteger(summary.rol_count), sub: 'roles distintos' },
    {
      id: 'superficie',
      label: 'Superficie',
      value: `${formatNumber(summary.surface_total)} ha`,
      sub: 'suma de áreas de corta',
    },
    {
      id: 'servidumbre',
      label: 'Con servidumbre',
      value: formatInteger(summary.con_servidumbre_predio_count),
      sub: 'predios únicos',
    },
  ]
}

export type AttentionTone = 'late' | 'progress' | 'calm'

export interface AttentionItem {
  id: string
  value: number
  label: string
  sub: string
  action: string
  /** Where the reader goes to resolve it. */
  href: string
  tone: AttentionTone
}

/**
 * The numbers that mean work.
 *
 * Tone is decided by the number itself: an indicator reading zero is calm, so
 * a healthy source never competes for attention with the day's real work.
 * Colour is never the only signal — each card states its own count, label and
 * next step in text.
 */
export function buildAttentionItems(
  summary: TranselecSummary,
  routes: { pendientes: string; calidad: string },
): AttentionItem[] {
  return [
    {
      id: 'pendientes',
      value: summary.pendientes_prioritarios_pmf_count,
      label: 'PMF pendientes prioritarios',
      sub: 'Sin N.º de ingreso, o con un rechazo en su «Estado».',
      action: 'Ver la cola de trabajo',
      href: routes.pendientes,
      tone: summary.pendientes_prioritarios_pmf_count > 0 ? 'late' : 'calm',
    },
    {
      id: 'sin-ingreso',
      value: summary.calidad_pmf_sin_numero_ingreso,
      label: 'PMF sin N.º de ingreso',
      sub: 'No es posible vincularlos a un expediente CONAF.',
      action: 'Revisar en Calidad',
      href: routes.calidad,
      tone: summary.calidad_pmf_sin_numero_ingreso > 0 ? 'progress' : 'calm',
    },
    {
      id: 'sin-id-predial',
      value: summary.calidad_filas_sin_id_predial_unico,
      label: 'Filas sin ID predial único',
      sub: 'La fila no puede atribuirse a un predio identificado.',
      action: 'Revisar en Calidad',
      href: routes.calidad,
      tone: summary.calidad_filas_sin_id_predial_unico > 0 ? 'progress' : 'calm',
    },
  ]
}

/**
 * Approval composition at one grain (TR-FUNC-009 predio, TR-FUNC-010 PMF).
 *
 * The API's own three-bucket split under `estado_resumido_first_row`. Each
 * bar's segments sum to its own grain's total, which is exactly why the two
 * bars can legitimately show different percentages, and why putting them on a
 * shared baseline is more useful than two separate rings.
 */
export function approvalSegments(counts: {
  aprobado: number
  en_tramite: number
  pendiente_o_tachado: number
}): CompositionSegment[] {
  return [
    { key: 'aprobados', label: 'Aprobado', value: counts.aprobado, tone: 'approved' },
    { key: 'en-tramite', label: 'En trámite', value: counts.en_tramite, tone: 'progress' },
    {
      key: 'resto',
      label: 'Pendiente o tachado',
      value: counts.pendiente_o_tachado,
      tone: 'struck',
    },
  ]
}

/**
 * The predio-grain `Estado resumido` breakdown (TR-FUNC-011).
 *
 * A different denominator from the PMF-grain figures, using the same field,
 * which is why the grain is always stated beside it. `sin_estado` is the
 * API's defensive bucket for a blank or unrecognised value: it is included
 * only when non-zero, so the visible segments still sum to the predio total
 * for the reviewed vocabulary while a future import carrying an unexpected
 * value cannot silently lose predios.
 */
export function estadoResumidoSegments(summary: TranselecSummary): CompositionSegment[] {
  const hero = summary.estado_resumido_hero_predio
  const segments: CompositionSegment[] = [
    { key: 'aprobado', label: 'Aprobado', value: hero.aprobado, tone: 'approved' },
    { key: 'en-tramite', label: 'En trámite', value: hero.en_tramite, tone: 'progress' },
    { key: 'pendiente', label: 'Pendiente', value: hero.pendiente, tone: 'late' },
    { key: 'tachado', label: 'Tachado', value: hero.tachado, tone: 'struck' },
  ]
  if (hero.sin_estado > 0) {
    segments.push({
      key: 'sin-estado',
      label: 'Sin estado',
      value: hero.sin_estado,
      tone: 'none',
    })
  }
  return segments
}
