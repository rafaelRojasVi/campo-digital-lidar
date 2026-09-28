import type { GeoFeature } from '../types.ts'
import { aggregateByField } from './aggregate.ts'
import { codeFieldsDiffer, usoFieldsDiffer } from './filters.ts'

// Map color encoding. Colors mark factual categories only (source field
// values, literal field differences, quality evidence); they never encode
// business status, priority, or progress.
//
// The 8 categorical hues and their order are the validated default palette of
// the dataviz method (CVD-checked adjacent-pair ordering; see
// products/forestry/docs/dashboard-v1.md for the validator evidence and the
// >8-category fold rule). Categories beyond the first 8 by area fold into a
// neutral "Otros" gray; identity is always recoverable via hover, legend
// counts, and the table.

export const CATEGORICAL_COLORS: readonly string[] = [
  '#2a78d6', // blue
  '#eb6834', // orange
  '#1baf7a', // aqua
  '#eda100', // yellow
  '#e87ba4', // magenta
  '#008300', // green
  '#4a3aa7', // violet
  '#e34948', // red
]

export const OTHER_COLOR = '#9a9890'
export const BLANK_COLOR = '#c9c8c1'

/** Literal field difference highlight (no success/progress semantics). */
export const CHANGED_COLOR = '#2a78d6'
export const UNCHANGED_COLOR = '#d6d5ce'

/** Quality-evidence highlight (evidence, not error status). */
export const QUALITY_COLOR = '#eb6834'
export const NO_QUALITY_COLOR = '#d6d5ce'

export type ColorDimension = 'uso2026' | 'uso2024' | 'predio' | 'cambio' | 'calidad'

export const COLOR_DIMENSIONS: readonly { id: ColorDimension; label: string }[] = [
  { id: 'uso2026', label: 'Uso 2026' },
  { id: 'uso2024', label: 'Uso 2024' },
  { id: 'predio', label: 'Predio' },
  { id: 'cambio', label: 'Comparación 2024 → 2026' },
  { id: 'calidad', label: 'Evidencia de calidad' },
]

export interface LegendEntry {
  key: string
  label: string
  color: string
  featureCount: number
  supHaTotal: number
  /** Filter payload when the entry is clickable (categorical values only). */
  filterValue: string | null
  isFold: boolean
}

export interface ColorEncoding {
  dimension: ColorDimension
  legend: LegendEntry[]
  colorFor: (feature: GeoFeature) => string
}

const CATEGORICAL_FIELDS = {
  uso2026: 'uso_2026',
  uso2024: 'uso_2024',
  predio: 'nom_predio',
} as const

const MAX_DISTINCT_CATEGORIES = CATEGORICAL_COLORS.length

function categoricalEncoding(
  dimension: 'uso2026' | 'uso2024' | 'predio',
  features: GeoFeature[],
): ColorEncoding {
  const field = CATEGORICAL_FIELDS[dimension]
  const aggregates = aggregateByField(features, field)
  const named = aggregates.filter((entry) => entry.value !== null)
  const blank = aggregates.find((entry) => entry.value === null)

  // When exactly MAX+1 named categories exist, folding the last one into
  // "Otros" would hide a single class behind a gray of the same size; it is
  // clearer to fold only when at least two classes are grouped.
  const foldNeeded = named.length > MAX_DISTINCT_CATEGORIES + 1
  const distinctCount = foldNeeded ? MAX_DISTINCT_CATEGORIES : named.length

  const colorByValue = new Map<string, string>()
  const legend: LegendEntry[] = []

  named.slice(0, distinctCount).forEach((entry, index) => {
    const color = CATEGORICAL_COLORS[index] ?? OTHER_COLOR
    if (entry.value !== null) {
      colorByValue.set(entry.value, color)
      legend.push({
        key: entry.value,
        label: entry.value,
        color,
        featureCount: entry.featureCount,
        supHaTotal: entry.supHaTotal,
        filterValue: entry.value,
        isFold: false,
      })
    }
  })

  if (foldNeeded) {
    const folded = named.slice(distinctCount)
    legend.push({
      key: '__other__',
      label: `Otros (${folded.length} valores)`,
      color: OTHER_COLOR,
      featureCount: folded.reduce((sum, entry) => sum + entry.featureCount, 0),
      supHaTotal: folded.reduce((sum, entry) => sum + entry.supHaTotal, 0),
      filterValue: null,
      isFold: true,
    })
  }

  if (blank !== undefined) {
    legend.push({
      key: '__blank__',
      label: 'Sin valor en la fuente',
      color: BLANK_COLOR,
      featureCount: blank.featureCount,
      supHaTotal: blank.supHaTotal,
      filterValue: null,
      isFold: true,
    })
  }

  return {
    dimension,
    legend,
    colorFor: (feature) => {
      const raw = feature.properties[field]
      if (typeof raw !== 'string' || raw === '') {
        return BLANK_COLOR
      }
      return colorByValue.get(raw) ?? OTHER_COLOR
    },
  }
}

function changeEncoding(features: GeoFeature[]): ColorEncoding {
  let changedCount = 0
  let changedSupHa = 0
  let unchangedCount = 0
  let unchangedSupHa = 0

  for (const feature of features) {
    const differs = usoFieldsDiffer(feature.properties) || codeFieldsDiffer(feature.properties)
    if (differs) {
      changedCount += 1
      changedSupHa += feature.properties.sup_ha ?? 0
    } else {
      unchangedCount += 1
      unchangedSupHa += feature.properties.sup_ha ?? 0
    }
  }

  return {
    dimension: 'cambio',
    legend: [
      {
        key: 'changed',
        label: 'Campos 2024/2026 distintos',
        color: CHANGED_COLOR,
        featureCount: changedCount,
        supHaTotal: changedSupHa,
        filterValue: 'changed',
        isFold: false,
      },
      {
        key: 'unchanged',
        label: 'Campos 2024/2026 iguales',
        color: UNCHANGED_COLOR,
        featureCount: unchangedCount,
        supHaTotal: unchangedSupHa,
        filterValue: 'unchanged',
        isFold: false,
      },
    ],
    colorFor: (feature) =>
      usoFieldsDiffer(feature.properties) || codeFieldsDiffer(feature.properties)
        ? CHANGED_COLOR
        : UNCHANGED_COLOR,
  }
}

function qualityEncoding(features: GeoFeature[]): ColorEncoding {
  let withEvidence = 0
  let withEvidenceSupHa = 0
  let without = 0
  let withoutSupHa = 0

  for (const feature of features) {
    if (feature.properties.quality_flags.length > 0) {
      withEvidence += 1
      withEvidenceSupHa += feature.properties.sup_ha ?? 0
    } else {
      without += 1
      withoutSupHa += feature.properties.sup_ha ?? 0
    }
  }

  return {
    dimension: 'calidad',
    legend: [
      {
        key: 'with-evidence',
        label: 'Con evidencia de calidad',
        color: QUALITY_COLOR,
        featureCount: withEvidence,
        supHaTotal: withEvidenceSupHa,
        filterValue: 'any',
        isFold: false,
      },
      {
        key: 'without-evidence',
        label: 'Sin evidencia registrada',
        color: NO_QUALITY_COLOR,
        featureCount: without,
        supHaTotal: withoutSupHa,
        filterValue: null,
        isFold: false,
      },
    ],
    colorFor: (feature) =>
      feature.properties.quality_flags.length > 0 ? QUALITY_COLOR : NO_QUALITY_COLOR,
  }
}

/**
 * Build the color encoding for one dimension over the FULL collection, so
 * colors stay stable while filters change (color follows the category, not
 * the filtered subset).
 */
export function buildColorEncoding(
  dimension: ColorDimension,
  allFeatures: GeoFeature[],
): ColorEncoding {
  switch (dimension) {
    case 'uso2026':
    case 'uso2024':
    case 'predio':
      return categoricalEncoding(dimension, allFeatures)
    case 'cambio':
      return changeEncoding(allFeatures)
    case 'calidad':
      return qualityEncoding(allFeatures)
  }
}
