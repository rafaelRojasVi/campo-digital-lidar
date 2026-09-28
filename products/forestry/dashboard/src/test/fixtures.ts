import type {
  FeatureCollection,
  ForestrySnapshot,
  GeoFeature,
  SnapshotSummary,
  SourceFeatureDetail,
  SourceFeatureProperties,
  SourceFieldComparison,
} from '../types.ts'

// Synthetic snapshot data for tests: same shapes as the read API, small
// coordinates inside the real UTM 18S envelope, no client data.

let squareOffset = 0

/** A 100 m × 100 m square MultiPolygon near the observed estate envelope. */
export function squareGeometry(): GeoFeature['geometry'] {
  const x = 620_000 + squareOffset * 200
  const y = 5_490_000
  squareOffset += 1

  return {
    type: 'MultiPolygon',
    coordinates: [
      [
        [
          [x, y],
          [x + 100, y],
          [x + 100, y + 100],
          [x, y + 100],
          [x, y],
        ],
      ],
    ],
  }
}

export function makeFeature(overrides: Partial<SourceFeatureProperties>): GeoFeature {
  const base: SourceFeatureProperties = {
    feature_ordinal: 1,
    source_objectid: 1,
    cod_predial: 'HT',
    nom_predio: 'Hacienda Trinidad',
    n_rodal: '10',
    cod_uso: 'Pi06',
    uso_2024: 'PLANTACION',
    desc_uso: 'Plantacion de P. radiata',
    uso_2026: 'PLANTACION',
    cod_uso_2026: 'Pi06',
    sup_ha: 12.5,
    geometry_is_valid: true,
    geometry_area_source_units: 125_000,
    quality_flags: [],
  }

  return {
    type: 'Feature',
    properties: { ...base, ...overrides },
    geometry: squareGeometry(),
  }
}

export function testFeatures(): GeoFeature[] {
  return [
    makeFeature({ feature_ordinal: 1, source_objectid: 101 }),
    makeFeature({
      feature_ordinal: 2,
      source_objectid: 102,
      n_rodal: '11',
      uso_2024: 'ENSAYO',
      uso_2026: 'PLANTACION',
      cod_uso: 'En11',
      cod_uso_2026: 'Pi26',
      desc_uso: 'Plantacion de P. radiata',
      sup_ha: 3.2,
      geometry_area_source_units: 32_000,
    }),
    makeFeature({
      feature_ordinal: 3,
      source_objectid: 103,
      cod_predial: 'SS',
      nom_predio: 'San Sebastian',
      n_rodal: '',
      uso_2024: 'BOSQUE NATIVO',
      uso_2026: 'BOSQUE NATIVO',
      cod_uso: 'BN',
      cod_uso_2026: 'BN',
      desc_uso: 'Bosque nativo',
      sup_ha: 8,
      geometry_area_source_units: 80_000,
      quality_flags: ['blank_rodal'],
    }),
    makeFeature({
      feature_ordinal: 4,
      source_objectid: 104,
      cod_predial: 'PU2',
      nom_predio: 'Purretrun',
      n_rodal: '5',
      uso_2024: 'VEGA',
      uso_2026: 'VEGA',
      cod_uso: 'Ve',
      cod_uso_2026: 'Ve',
      desc_uso: 'Vega',
      sup_ha: 0.3,
      geometry_area_source_units: 3_000,
      quality_flags: ['predio_code_name_anomaly'],
    }),
    makeFeature({
      feature_ordinal: 5,
      source_objectid: 105,
      n_rodal: '12',
      cod_uso: 'RaCoRo01Pi Rn',
      cod_uso_2026: 'RaCoRo01P*',
      sup_ha: 2,
      geometry_is_valid: false,
      geometry_area_source_units: 20_000,
      quality_flags: ['invalid_geometry', 'truncated_use_code_2026'],
    }),
    makeFeature({
      feature_ordinal: 6,
      source_objectid: 106,
      cod_predial: 'LUM',
      nom_predio: 'Lumaco',
      n_rodal: '0',
      uso_2024: 'VEGETACION NATIVA',
      uso_2026: 'VEGETACION NATIVA',
      cod_uso: 'VN',
      cod_uso_2026: 'VN',
      desc_uso: 'Vegetación nativa',
      sup_ha: 1.1,
      geometry_area_source_units: 11_000,
      quality_flags: ['duplicate_predio_rodal_key'],
    }),
  ]
}

export function testCollection(): FeatureCollection {
  const features = testFeatures()

  return {
    type: 'FeatureCollection',
    shapefile_snapshot_id: 1,
    storage_srid: 32718,
    feature_count: features.length,
    features,
  }
}

export function testSnapshot(): ForestrySnapshot {
  return {
    shapefile_snapshot_id: 1,
    layer_name: 'Gdb_Test_mv',
    family_fingerprint: 'ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12',
    storage_srid: 32718,
    feature_count: 6,
    created_at: '2026-08-29T12:00:00Z',
  }
}

export function testSummary(): SnapshotSummary {
  return {
    shapefile_snapshot_id: 1,
    layer_name: 'Gdb_Test_mv',
    family_fingerprint: 'ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12',
    storage_srid: 32718,
    bbox: [620_000, 5_490_000, 621_100, 5_490_100],
    feature_count: 6,
    total_geometry_area_source_units: 271_000,
    total_sup_ha: 27.1,
    geometry_valid_count: 5,
    geometry_invalid_count: 1,
    quality_flag_counts: {
      blank_rodal: 1,
      duplicate_geometry: 0,
      duplicate_predio_rodal_key: 1,
      invalid_geometry: 1,
      predio_code_name_anomaly: 1,
      truncated_use_code_2026: 1,
    },
    n_rodal_te_non_blank_count: 0,
    created_at: '2026-08-29T12:00:00Z',
  }
}

export function testComparison(): SourceFieldComparison {
  return {
    shapefile_snapshot_id: 1,
    semantics:
      'literal source-field differences within one snapshot; not workflow transitions',
    uso_2024_vs_uso_2026: {
      changed_feature_count: 1,
      changes: [
        {
          feature_ordinal: 2,
          source_objectid: 102,
          before: 'ENSAYO',
          after: 'PLANTACION',
        },
      ],
    },
    cod_uso_vs_cod_uso_2026: {
      changed_feature_count: 2,
      changes: [
        { feature_ordinal: 2, source_objectid: 102, before: 'En11', after: 'Pi26' },
        {
          feature_ordinal: 5,
          source_objectid: 105,
          before: 'RaCoRo01Pi Rn',
          after: 'RaCoRo01P*',
        },
      ],
    },
  }
}

export function testDetail(featureOrdinal: number): SourceFeatureDetail {
  const feature = testFeatures().find(
    (candidate) => candidate.properties.feature_ordinal === featureOrdinal,
  )

  if (feature === undefined) {
    throw new Error(`no test feature ${featureOrdinal}`)
  }

  return {
    ...feature.properties,
    shapefile_snapshot_id: 1,
    storage_srid: 32718,
    shape_area: feature.properties.geometry_area_source_units,
    geometry_invalid_reason: feature.properties.geometry_is_valid
      ? null
      : 'Self-intersection[620000 5490000]',
    source_attributes: {
      OBJECTID: feature.properties.source_objectid,
      Nom_Predio: feature.properties.nom_predio,
      N_Rodal: feature.properties.n_rodal,
      Sup_ha: feature.properties.sup_ha,
      Cod_Uso: feature.properties.cod_uso,
      Editada: 'mv',
      Uso2024: feature.properties.uso_2024,
      DescUso: feature.properties.desc_uso,
      Cod_Predial: feature.properties.cod_predial,
      N_Rodal_te: '',
      Uso2026: feature.properties.uso_2026,
      CodUso_2026: feature.properties.cod_uso_2026,
      Shape_Leng: 400,
      Shape_Area: feature.properties.geometry_area_source_units,
    },
    geometry: feature.geometry,
  }
}
