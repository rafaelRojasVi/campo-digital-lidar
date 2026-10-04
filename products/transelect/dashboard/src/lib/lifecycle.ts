/**
 * `lifecycle_pmf_v1` in Spanish, for the «Estado» section.
 *
 * The classification is the server's (`transelec_ingestion/lifecycle_view.py`);
 * this module only names its keys and orders them. All of this wording is
 * provisional until Campo Digital confirms the vocabulary (spec 2026-10-04,
 * open questions). «Descartado» and «Desistido» keep the source's own words
 * and are never merged.
 */
import type {
  LifecycleFlag,
  LifecycleGroup,
  LifecycleReason,
  LifecycleRow,
  LifecycleStep,
  TranselecLifecycle,
} from '../api'
import type { CompositionSegment, SegmentTone } from '../ui/CompositionBar'

export const LIFECYCLE_GROUP_ORDER: LifecycleGroup[] = [
  'aprobado',
  'en_tramite',
  'descartado',
  'desistido',
  'sin_clasificar',
]

/** Attention first: a rejection waiting for its recurso is the work to do. */
export const LIFECYCLE_STEP_ORDER: LifecycleStep[] = [
  'rechazado_esperando_recurso',
  'en_recurso_reposicion',
  'en_recurso_jerarquico',
  'en_evaluacion',
  'sin_ingreso',
]

export const LIFECYCLE_GROUP_LABELS: Record<LifecycleGroup, string> = {
  aprobado: 'Aprobado',
  en_tramite: 'En trámite',
  descartado: 'Descartado',
  desistido: 'Desistido',
  sin_clasificar: 'Sin clasificar',
}

export const LIFECYCLE_STEP_LABELS: Record<LifecycleStep, string> = {
  sin_ingreso: 'Sin ingreso a CONAF',
  en_evaluacion: 'En evaluación',
  rechazado_esperando_recurso: 'Rechazado, esperando recurso',
  en_recurso_reposicion: 'En recurso de reposición',
  en_recurso_jerarquico: 'En recurso jerárquico',
}

export const LIFECYCLE_REASON_LABELS: Record<LifecycleReason, string> = {
  resumido_desconocido: '«Estado resumido» con un valor que esta regla no reconoce',
  estado_desconocido: '«Estado» con un valor que esta regla no reconoce',
  estado_y_resumido_no_coinciden: '«Estado» y «Estado resumido» no coinciden',
}

export const LIFECYCLE_FLAG_LABELS: Record<LifecycleFlag, string> = {
  filas_no_coinciden:
    'Sus filas no tienen el mismo «Estado» o «Estado resumido»; se usa la primera',
}

/** The existing `.pill-*` tones; closed-without-approval reads as struck. */
export const LIFECYCLE_GROUP_PILL: Record<LifecycleGroup, string> = {
  aprobado: 'pill-aprobado',
  en_tramite: 'pill-en-tramite',
  descartado: 'pill-tachado',
  desistido: 'pill-tachado',
  sin_clasificar: 'pill-otro',
}

const GROUP_TONES: Record<LifecycleGroup, SegmentTone> = {
  aprobado: 'approved',
  en_tramite: 'progress',
  descartado: 'struck',
  desistido: 'struck',
  sin_clasificar: 'none',
}

// Attention red is reserved for one step (spec 2026-10-04).
const STEP_TONES: Record<LifecycleStep, SegmentTone> = {
  rechazado_esperando_recurso: 'late',
  en_recurso_reposicion: 'progress',
  en_recurso_jerarquico: 'progress',
  en_evaluacion: 'progress',
  sin_ingreso: 'none',
}

export function lifecycleGroupSegments(data: TranselecLifecycle): CompositionSegment[] {
  return LIFECYCLE_GROUP_ORDER.map((group) => ({
    key: group,
    label: LIFECYCLE_GROUP_LABELS[group],
    value: data.groups[group],
    tone: GROUP_TONES[group],
  }))
}

export function lifecycleStepSegments(data: TranselecLifecycle): CompositionSegment[] {
  return LIFECYCLE_STEP_ORDER.map((step) => ({
    key: step,
    label: LIFECYCLE_STEP_LABELS[step],
    value: data.steps[step],
    tone: STEP_TONES[step],
  }))
}

/** The step inside «En trámite», why a PMF is unclassified, or a dash. */
export function lifecycleStepText(row: LifecycleRow): string {
  if (row.lifecycle_step) return LIFECYCLE_STEP_LABELS[row.lifecycle_step]
  if (row.lifecycle_reason) return LIFECYCLE_REASON_LABELS[row.lifecycle_reason]
  return '—'
}

/** Listed in Calidad: a PMF the rule could not place, or whose rows disagree. */
export function needsReview(row: LifecycleRow): boolean {
  return row.lifecycle_group === 'sin_clasificar' || row.lifecycle_flags.length > 0
}
