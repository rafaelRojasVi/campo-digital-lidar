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

// ---------------------------------------------------------------------------
// Upload → review → publish → restore (apps/api/app/routers/forestry_workflow.py)
// ---------------------------------------------------------------------------

export type VersionStatus = 'published' | 'pending' | 'previously_published'

export interface UploadRecord {
  snapshot_upload_id: number
  original_filename: string
  byte_size: number
  content_sha256: string
  uploaded_at: string
  uploaded_by_display_name: string
}

export interface ImportedSource {
  filename: string
  content_sha256: string
  byte_size: number
  observed_at: string
}

export interface Version {
  shapefile_snapshot_id: number
  status: VersionStatus
  layer_name: string
  family_fingerprint: string
  crs_name: string | null
  storage_srid: number
  feature_count: number
  total_sup_ha: number
  total_geometry_area_source_units: number
  geometry_invalid_count: number
  created_at: string
  uploads: UploadRecord[]
  imported_source: ImportedSource | null
}

export interface PublicationEvent {
  publication_event_id: number
  shapefile_snapshot_id: number
  event_type: 'initial' | 'publish' | 'restore'
  previous_snapshot_id: number | null
  occurred_at: string
  actor_display_name: string | null
}

export interface VersionsResponse {
  published_snapshot_id: number | null
  versions: Version[]
  events: PublicationEvent[]
}

export interface FeatureRef {
  feature_ordinal: number
  source_objectid: number | null
  cod_predial: string | null
  nom_predio: string | null
  n_rodal: string | null
  sup_ha: number | null
  geometry_area_source_units: number
}

export type ChangeKind = 'same_geometry' | 'geometry_changed' | 'uncertain' | 'added' | 'removed'

export interface ChangeItem {
  kind: ChangeKind
  published: FeatureRef[]
  pending: FeatureRef[]
  changed_fields: string[]
  overlaps: { published_ordinal: number; pending_ordinal: number; overlap_ratio_of_smaller: number }[]
  same_objectid: boolean | null
}

export interface Comparison {
  published_snapshot_id: number
  link_overlap_ratio: number
  counts: Record<ChangeKind, number>
  unchanged_count: number
  review_required_count: number
  items: ChangeItem[]
}

export interface InvalidGeometry {
  feature_ordinal: number
  source_objectid: number | null
  cod_predial: string | null
  nom_predio: string | null
  n_rodal: string | null
  reason: string
}

export interface Review {
  version: Version
  published_version: Version | null
  quality_flag_counts: Record<string, number>
  invalid_geometries: InvalidGeometry[]
  comparison: Comparison | null
  comparison_unavailable: boolean
  review_required: boolean
  can_publish: boolean
  can_restore: boolean
}

export interface UploadResult {
  status: 'uploaded' | 'already_uploaded'
  shapefile_snapshot_id: number
  version_status: VersionStatus
  layer_name: string
  feature_count: number
  content_sha256: string
  byte_size: number
}

export interface ActivationResult {
  status: 'published' | 'restored'
  shapefile_snapshot_id: number
  previous_snapshot_id: number | null
  publication_event_id: number
  occurred_at: string
}

export type ForestryRole = 'admin' | 'operator' | 'viewer'
