import type { GeoFeature, SourceFeatureProperties } from './../types.ts'
import { codeFieldsDiffer, usoFieldsDiffer } from './filters.ts'

// Factual arithmetic over the loaded source features. Sums of source fields
// and geometry-derived areas only; no business interpretation.

export interface SelectionStats {
  featureCount: number
  supHaTotal: number
  geometryAreaSourceUnitsTotal: number
  invalidGeometryCount: number
  withQualityEvidenceCount: number
  usoFieldDifferenceCount: number
  codeFieldDifferenceCount: number
}

export function selectionStats(features: GeoFeature[]): SelectionStats {
  let supHaTotal = 0
  let geometryAreaTotal = 0
  let invalidCount = 0
  let qualityCount = 0
  let usoDiffers = 0
  let codeDiffers = 0

  for (const feature of features) {
    const properties = feature.properties
    supHaTotal += properties.sup_ha ?? 0
    geometryAreaTotal += properties.geometry_area_source_units
    if (!properties.geometry_is_valid) invalidCount += 1
    if (properties.quality_flags.length > 0) qualityCount += 1
    if (usoFieldsDiffer(properties)) usoDiffers += 1
    if (codeFieldsDiffer(properties)) codeDiffers += 1
  }

  return {
    featureCount: features.length,
    supHaTotal,
    geometryAreaSourceUnitsTotal: geometryAreaTotal,
    invalidGeometryCount: invalidCount,
    withQualityEvidenceCount: qualityCount,
    usoFieldDifferenceCount: usoDiffers,
    codeFieldDifferenceCount: codeDiffers,
  }
}

export interface CategoryAggregate {
  /** Source value; `null` groups blank/absent source values. */
  value: string | null
  featureCount: number
  supHaTotal: number
}

/** Aggregate feature count and `Sup_ha` sums by one source field. */
export function aggregateByField(
  features: GeoFeature[],
  field: keyof SourceFeatureProperties,
): CategoryAggregate[] {
  const groups = new Map<string | null, { featureCount: number; supHaTotal: number }>()

  for (const feature of features) {
    const raw = feature.properties[field]
    const value = typeof raw === 'string' && raw !== '' ? raw : null
    const group = groups.get(value) ?? { featureCount: 0, supHaTotal: 0 }
    group.featureCount += 1
    group.supHaTotal += feature.properties.sup_ha ?? 0
    groups.set(value, group)
  }

  return [...groups.entries()]
    .map(([value, group]) => ({ value, ...group }))
    .sort(
      (a, b) =>
        b.supHaTotal - a.supHaTotal ||
        b.featureCount - a.featureCount ||
        (a.value ?? '').localeCompare(b.value ?? '', 'es'),
    )
}
