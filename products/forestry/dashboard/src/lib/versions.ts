import type { ChangeKind, PublicationEvent, Version, VersionStatus } from '../types.ts'

export const STATUS_LABELS: Record<VersionStatus, string> = {
  published: 'Publicada',
  pending: 'Pendiente de revisión',
  previously_published: 'Publicada anteriormente',
}

export const EVENT_LABELS: Record<PublicationEvent['event_type'], string> = {
  initial: 'Versión inicial',
  publish: 'Publicación',
  restore: 'Restauración',
}

// Plain descriptions of what the comparison can say. None of them claims an
// operation on the ground: a changed shape or attribute is only a change.
export const CHANGE_LABELS: Record<ChangeKind, string> = {
  uncertain: 'Correspondencia incierta',
  geometry_changed: 'Geometría modificada',
  removed: 'Sin correspondencia en la versión nueva',
  added: 'Nuevo en esta versión',
  same_geometry: 'Misma geometría, atributos distintos',
}

export const CHANGE_DESCRIPTIONS: Record<ChangeKind, string> = {
  uncertain:
    'Varios polígonos se superponen entre sí entre una versión y otra. Puede ser un redibujo, una división o una unión; la plataforma no decide cuál. Revíselo en el mapa.',
  geometry_changed:
    'Un polígono de la versión publicada se superpone con uno solo de la versión nueva, pero su forma cambió. Es una correspondencia probable, no segura.',
  removed: 'Este polígono de la versión publicada no se superpone con ninguno de la versión nueva.',
  added: 'Este polígono de la versión nueva no se superpone con ninguno de la versión publicada.',
  same_geometry:
    'La geometría es idéntica en ambas versiones; cambiaron los campos indicados.',
}

/** Where a version came from: the uploaded ZIP, or the controlled import. */
export function versionSource(version: Version): { filename: string; by: string; at: string } | null {
  const upload = version.uploads.at(-1)
  if (upload !== undefined) {
    return {
      filename: upload.original_filename,
      by: upload.uploaded_by_display_name,
      at: upload.uploaded_at,
    }
  }
  if (version.imported_source !== null) {
    return {
      filename: version.imported_source.filename,
      by: 'Importación controlada',
      at: version.imported_source.observed_at,
    }
  }
  return null
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${new Intl.NumberFormat('es-CL', { maximumFractionDigits: 0 }).format(bytes / 1024)} KB`
  }
  return `${new Intl.NumberFormat('es-CL', { maximumFractionDigits: 1 }).format(bytes / (1024 * 1024))} MB`
}

export function formatDateTime(isoTimestamp: string): string {
  const date = new Date(isoTimestamp)
  if (Number.isNaN(date.getTime())) return isoTimestamp
  return new Intl.DateTimeFormat('es-CL', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}
