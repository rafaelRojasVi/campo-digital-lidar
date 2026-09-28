import type { QualityFlag } from '../types.ts'

// Spanish labels for the established quality-evidence classes. These are
// descriptions of observed evidence in the source snapshot, never error or
// workflow statuses.

export const QUALITY_FLAG_LABELS: Record<QualityFlag, string> = {
  invalid_geometry: 'Geometría inválida (OGC)',
  duplicate_geometry: 'Geometría duplicada',
  blank_rodal: 'Rodal en blanco',
  duplicate_predio_rodal_key: 'Par predio/rodal repetido',
  predio_code_name_anomaly: 'Anomalía código/nombre de predio',
  truncated_use_code_2026: 'Código de uso 2026 truncado',
}

export const QUALITY_FLAG_DESCRIPTIONS: Record<QualityFlag, string> = {
  invalid_geometry:
    'El polígono no cumple validez OGC (anillos auto-intersectados) tal como viene en la fuente. Se almacena y dibuja sin reparar.',
  duplicate_geometry:
    'La geometría es byte-idéntica a la de otro polígono de la misma instantánea.',
  blank_rodal: 'El campo N_Rodal viene vacío en la fuente.',
  duplicate_predio_rodal_key:
    'El par (Cod_Predial, N_Rodal) no vacío se repite en más de un polígono.',
  predio_code_name_anomaly:
    'El par código/nombre de predio difiere del emparejamiento mayoritario observado en la instantánea.',
  truncated_use_code_2026:
    'El valor de CodUso_2026 termina en el artefacto «*» observado (truncado a 10 caracteres en la fuente).',
}

export function qualityFlagLabel(flag: string): string {
  return (QUALITY_FLAG_LABELS as Record<string, string>)[flag] ?? flag
}
