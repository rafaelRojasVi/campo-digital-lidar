/**
 * TR-FUNC-032 — labels for `pendingStage()`'s three buckets.
 *
 * The classification itself is computed server-side (`stage_basis:
 * "pending_stage_legacy"`); this module only maps the API's stage keys back
 * to the wording the source dashboard shows. The matrix flags the heuristic
 * itself as INFERENCE-quality — not a confirmed CONAF taxonomy — which is
 * why the UI states the basis next to these labels rather than presenting
 * them as settled categories.
 */

import type { PendingStage } from '../api'

export const PENDING_STAGE_ORDER: PendingStage[] = ['preparacion', 'recurso_rechazo', 'otros']

export const PENDING_STAGE_LABELS: Record<PendingStage, string> = {
  preparacion: 'En preparación / no presentado',
  recurso_rechazo: 'Recurso rechazado',
  otros: 'Rechazado',
}

export function pendingStageLabel(stage: PendingStage): string {
  return PENDING_STAGE_LABELS[stage]
}
