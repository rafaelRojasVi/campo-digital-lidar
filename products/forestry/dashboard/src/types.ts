// Typed mirror of the read-only Forestry API (apps/api/app/routers/forestry.py).
// Every value is a literal source-field projection; nothing here carries
// workflow, approval, or canonical-identity semantics.

export type QualityFlag =
  | 'blank_rodal'
  | 'duplicate_geometry'
  | 'duplicate_predio_rodal_key'
  | 'invalid_geometry'
  | 'predio_code_name_anomaly'
  | 'truncated_use_code_2026'

export const KNOWN_QUALITY_FLAGS: readonly QualityFlag[] = [
  'invalid_geometry',
  'duplicate_geometry',
  'blank_rodal',
  'duplicate_predio_rodal_key',
  'predio_code_name_anomaly',
  'truncated_use_code_2026',
]

export interface ForestrySnapshot {
  shapefile_snapshot_id: number
  layer_name: string
  family_fingerprint: string
  storage_srid: number
  feature_count: number
  created_at: string
}

export interface SnapshotSummary {
  shapefile_snapshot_id: number
  layer_name: string
  family_fingerprint: string
  storage_srid: number
  bbox: [number, number, number, number]
  feature_count: number
  total_geometry_area_source_units: number
  total_sup_ha: number
  geometry_valid_count: number
  geometry_invalid_count: number
  quality_flag_counts: Record<string, number>
  n_rodal_te_non_blank_count: number
  created_at: string
}

export interface SourceFeatureProperties {
  feature_ordinal: number
  source_objectid: number | null
  cod_predial: string | null
  nom_predio: string | null
  n_rodal: string | null
  cod_uso: string | null
  uso_2024: string | null
  desc_uso: string | null
  uso_2026: string | null
  cod_uso_2026: string | null
  sup_ha: number | null
  geometry_is_valid: boolean
  geometry_area_source_units: number
  quality_flags: string[]
}

export interface MultiPolygonGeometry {
  type: 'MultiPolygon'
  coordinates: number[][][][]
}

export interface GeoFeature {
  type: 'Feature'
  properties: SourceFeatureProperties
  geometry: MultiPolygonGeometry
}

export interface FeatureCollection {
  type: 'FeatureCollection'
  shapefile_snapshot_id: number
  storage_srid: number
  feature_count: number
  features: GeoFeature[]
}

export interface SourceFieldChange {
  feature_ordinal: number
  source_objectid: number | null
  before: string | null
  after: string | null
}

export interface SourceFieldComparisonSide {
  changed_feature_count: number
  changes: SourceFieldChange[]
}

export interface SourceFieldComparison {
  shapefile_snapshot_id: number
  semantics: string
  uso_2024_vs_uso_2026: SourceFieldComparisonSide
  cod_uso_vs_cod_uso_2026: SourceFieldComparisonSide
}

export interface SourceFeatureDetail extends SourceFeatureProperties {
  shapefile_snapshot_id: number
  storage_srid: number
  shape_area: number | null
  geometry_invalid_reason: string | null
  source_attributes: Record<string, unknown>
  geometry: MultiPolygonGeometry
}
