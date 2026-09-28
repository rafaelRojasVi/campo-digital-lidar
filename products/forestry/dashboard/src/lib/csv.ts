import type { GeoFeature } from '../types.ts'

// Client-side CSV export of the filtered table. Column set = the persisted
// source projection fields (plus validity/quality evidence); no generated
// file is ever committed, this is a browser download only.

export const CSV_COLUMNS = [
  'feature_ordinal',
  'source_objectid',
  'cod_predial',
  'nom_predio',
  'n_rodal',
  'uso_2024',
  'uso_2026',
  'cod_uso',
  'cod_uso_2026',
  'desc_uso',
  'sup_ha',
  'geometry_area_ha',
  'geometry_is_valid',
  'quality_flags',
] as const

function csvCell(value: string | number | boolean | null): string {
  if (value === null) {
    return ''
  }

  const text = typeof value === 'boolean' ? (value ? 'true' : 'false') : String(value)

  if (/[",\n\r;]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }

  return text
}

export function buildCsv(features: GeoFeature[]): string {
  const lines: string[] = [CSV_COLUMNS.join(',')]

  for (const feature of features) {
    const p = feature.properties
    lines.push(
      [
        csvCell(p.feature_ordinal),
        csvCell(p.source_objectid),
        csvCell(p.cod_predial),
        csvCell(p.nom_predio),
        csvCell(p.n_rodal),
        csvCell(p.uso_2024),
        csvCell(p.uso_2026),
        csvCell(p.cod_uso),
        csvCell(p.cod_uso_2026),
        csvCell(p.desc_uso),
        csvCell(p.sup_ha),
        csvCell(p.geometry_area_source_units / 10_000),
        csvCell(p.geometry_is_valid),
        csvCell(p.quality_flags.join('|')),
      ].join(','),
    )
  }

  return `${lines.join('\r\n')}\r\n`
}

export function csvFilename(snapshotId: number): string {
  const stamp = new Date().toISOString().slice(0, 10)
  return `forestry-snapshot-${snapshotId}-filtrado-${stamp}.csv`
}

/** Trigger a browser download of the CSV (UTF-8 with BOM so Excel reads it). */
export function downloadCsv(features: GeoFeature[], snapshotId: number): void {
  const blob = new Blob(['\uFEFF', buildCsv(features)], {
    type: 'text/csv;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = csvFilename(snapshotId)
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
