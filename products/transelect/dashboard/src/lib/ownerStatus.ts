/**
 * TR-FUNC-013 — "Estado por tipo de propietario" table, presentation layer.
 *
 * The status decision itself is NOT made here. `GET /transelec/owner-status`
 * already applies Javier's own `ownerStage()` rule server-side, under the
 * explicit basis identifier `owner_stage_legacy`, and returns one row per
 * `(tipo_propietario, owner_stage)` pair with a predio count. That basis is
 * one of three genuinely disagreeing legacy rules (TR-OPEN-01) and this
 * module neither reconciles it with the others nor re-derives it.
 *
 * What this module does is purely a pivot: the API's long-format rows are
 * turned into the source table's 4 fixed columns. The four column buckets
 * are `ownerStage()`'s own four outputs — "Rechazado" is the rule's
 * synthesized override label, "Aprobado"/"En tramite" pass through from
 * `Estado resumido`, and everything else (Pendiente, Tachado, blank) falls
 * into the source table's own "Pend./tach." column, exactly as
 * `ownerStage()`'s final `return 'pending'` branch does.
 */

import type { OwnerStatusRow, TranselecOwnerStatus } from '../api'

export type OwnerStageBucket = 'approved' | 'progress' | 'rejected' | 'pending'

export interface OwnerStatusTableRow {
  tipoPropietario: string
  approved: number
  progress: number
  rejected: number
  pending: number
  total: number
  approvedPercentage: number
}

/** The source's own fallback label for a blank or literal "-" owner type. */
export const OWNER_UNKNOWN_LABEL = 'Sin información'

export function ownerStageBucket(ownerStage: string | null): OwnerStageBucket {
  const normalized = (ownerStage ?? '').trim().toLowerCase()
  if (normalized === 'rechazado') return 'rejected'
  if (normalized === 'aprobado') return 'approved'
  if (normalized === 'en tramite' || normalized === 'en trámite') return 'progress'
  return 'pending'
}

export function ownerLabel(tipoPropietario: string | null): string {
  const raw = (tipoPropietario ?? '').trim()
  return raw === '' || raw === '-' ? OWNER_UNKNOWN_LABEL : raw
}

function emptyCounts(): Record<OwnerStageBucket, number> {
  return { approved: 0, progress: 0, rejected: 0, pending: 0 }
}

function toTableRow(
  tipoPropietario: string,
  counts: Record<OwnerStageBucket, number>,
): OwnerStatusTableRow {
  const total = counts.approved + counts.progress + counts.rejected + counts.pending
  return {
    tipoPropietario,
    ...counts,
    total,
    approvedPercentage: total ? (counts.approved / total) * 100 : 0,
  }
}

export interface OwnerStatusTable {
  rows: OwnerStatusTableRow[]
  total: OwnerStatusTableRow
  /** The named legacy rule the API applied — surfaced in the UI, not hidden. */
  basis: string
}

/**
 * Pivot the API response into the source table's row set.
 *
 * Ordering reproduces the source's own `sort`: most approved first, ties
 * broken by owner name using Spanish collation.
 */
export function buildOwnerStatusTable(
  response: Pick<TranselecOwnerStatus, 'basis' | 'rows'>,
): OwnerStatusTable {
  const groups = new Map<string, Record<OwnerStageBucket, number>>()

  for (const row of response.rows as OwnerStatusRow[]) {
    const label = ownerLabel(row.tipo_propietario)
    const counts = groups.get(label) ?? emptyCounts()
    counts[ownerStageBucket(row.owner_stage)] += row.predio_count
    groups.set(label, counts)
  }

  const rows = [...groups.entries()]
    .map(([label, counts]) => toTableRow(label, counts))
    .sort((a, b) => b.approved - a.approved || a.tipoPropietario.localeCompare(b.tipoPropietario, 'es'))

  const totals = emptyCounts()
  for (const row of rows) {
    totals.approved += row.approved
    totals.progress += row.progress
    totals.rejected += row.rejected
    totals.pending += row.pending
  }

  return { rows, total: toTableRow('TOTAL', totals), basis: response.basis }
}
