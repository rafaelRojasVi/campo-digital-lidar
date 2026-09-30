import type { ChangeItem, FeatureRef, Review, Version, VersionsResponse } from '../types.ts'

// Synthetic versions for the upload/review/publish pages; no client data.

export function testVersion(overrides: Partial<Version> = {}): Version {
  return {
    shapefile_snapshot_id: 2,
    status: 'pending',
    layer_name: 'Capa_Sintetica',
    family_fingerprint: 'a'.repeat(64),
    crs_name: 'WGS_1984_UTM_Zone_18S',
    storage_srid: 32718,
    feature_count: 6,
    total_sup_ha: 12.5,
    total_geometry_area_source_units: 125_000,
    geometry_invalid_count: 1,
    created_at: '2026-09-30T12:00:00Z',
    uploads: [
      {
        snapshot_upload_id: 1,
        original_filename: 'entrega_octubre.zip',
        byte_size: 2_600_000,
        content_sha256: 'b'.repeat(64),
        uploaded_at: '2026-09-30T12:00:00Z',
        uploaded_by_display_name: 'Operadora Sintética',
      },
    ],
    imported_source: null,
    ...overrides,
  }
}

function ref(ordinal: number, rodal: string): FeatureRef {
  return {
    feature_ordinal: ordinal,
    source_objectid: ordinal + 100,
    cod_predial: 'PS',
    nom_predio: 'Predio Sintético',
    n_rodal: rodal,
    sup_ha: 1,
    geometry_area_source_units: 10_000,
  }
}

const split: ChangeItem = {
  kind: 'uncertain',
  published: [ref(4, '4')],
  pending: [ref(4, '4'), ref(5, '4')],
  changed_fields: [],
  overlaps: [
    { published_ordinal: 4, pending_ordinal: 4, overlap_ratio_of_smaller: 1 },
    { published_ordinal: 4, pending_ordinal: 5, overlap_ratio_of_smaller: 1 },
  ],
  same_objectid: null,
}

const renumbered: ChangeItem = {
  kind: 'same_geometry',
  published: [ref(1, '1')],
  pending: [ref(1, '1')],
  changed_fields: ['objectid'],
  overlaps: [],
  same_objectid: false,
}

export function testReview(overrides: Partial<Review> = {}): Review {
  return {
    version: testVersion(),
    published_version: testVersion({
      shapefile_snapshot_id: 1,
      status: 'published',
      feature_count: 5,
      total_sup_ha: 10,
      geometry_invalid_count: 0,
    }),
    quality_flag_counts: { invalid_geometry: 1, blank_rodal: 0 },
    invalid_geometries: [
      {
        feature_ordinal: 3,
        source_objectid: 3,
        cod_predial: 'PS',
        nom_predio: 'Predio Sintético',
        n_rodal: '3',
        reason: 'Self-intersection[45 5]',
      },
    ],
    comparison: {
      published_snapshot_id: 1,
      link_overlap_ratio: 0.05,
      counts: { uncertain: 1, geometry_changed: 0, removed: 0, added: 0, same_geometry: 1 },
      unchanged_count: 3,
      review_required_count: 1,
      items: [split, renumbered],
    },
    comparison_unavailable: false,
    review_required: true,
    can_publish: true,
    can_restore: false,
    ...overrides,
  }
}

export function testVersions(): VersionsResponse {
  return {
    published_snapshot_id: 1,
    versions: [
      testVersion(),
      testVersion({
        shapefile_snapshot_id: 1,
        status: 'published',
        uploads: [],
        imported_source: {
          filename: 'origen.zip',
          content_sha256: 'c'.repeat(64),
          byte_size: 2_600_000,
          observed_at: '2026-09-29T12:00:00Z',
        },
      }),
    ],
    events: [
      {
        publication_event_id: 1,
        shapefile_snapshot_id: 1,
        event_type: 'initial',
        previous_snapshot_id: null,
        occurred_at: '2026-09-29T12:00:00Z',
        actor_display_name: null,
      },
    ],
  }
}
