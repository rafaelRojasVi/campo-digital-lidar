/**
 * TR-FUNC-031 — "¿Qué ingresos superaron 90 días?"
 *
 * The source dashboards implement this as
 * `Estado resumido != 'Aprobado' AND '90 dias' < new Date('2026-08-26')`.
 * The literal reference date is the matrix's one unambiguous, mechanically
 * fixable bug: it can never advance, so the filter silently rots. This
 * module keeps the predicate exactly as evidenced and replaces only the
 * frozen literal with a reference instant supplied by the caller.
 *
 * The caller passes the platform API's own observed clock (`api.ts`'s
 * `observedServerNow()`, read from the `Date` response header), so "today"
 * is the server's observation time rather than the viewer's device clock —
 * matching source-ingestion.md's rule that observation time is platform
 * infrastructure, never workbook data.
 *
 * What `90 dias` actually *means* stays TR-OPEN-03 and is not interpreted
 * here: the column is compared as the date the workbook asserts, nothing
 * more.
 */

import type { ResumenRow } from '../api'

export function isOverdueRow(row: Pick<ResumenRow, 'estado_resumido' | 'fecha_90_dias'>, reference: Date): boolean {
  const estado = (row.estado_resumido ?? '').trim()
  if (estado === 'Aprobado') return false

  const raw = (row.fecha_90_dias ?? '').trim()
  if (raw === '') return false

  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return false

  return parsed.getTime() < reference.getTime()
}

export function selectOverdueRows<T extends Pick<ResumenRow, 'estado_resumido' | 'fecha_90_dias'>>(
  rows: readonly T[],
  reference: Date,
): T[] {
  return rows.filter((row) => isOverdueRow(row, reference))
}
