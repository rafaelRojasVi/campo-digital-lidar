/**
 * TEST-ONLY response builders.
 *
 * These construct API-shaped objects for component tests. They are not a
 * fixture data module for the application: nothing under `src/` outside a
 * `*.test.tsx`/`*.test.ts` file imports this, and the running app has no
 * code path that can reach it. Values are deliberately small, synthetic and
 * unlike the reviewed snapshot's counts.
 */
import type {
  ResumenRow,
  TranselecActiveImport,
  TranselecImportHistoryRow,
  TranselecOwnerStatus,
  TranselecPending,
  TranselecReport,
  TranselecSummary,
} from '../api'

export function makeSummary(overrides: Partial<TranselecSummary> = {}): TranselecSummary {
  return {
    import_id: 12,
    row_count: 7,
    pmf_count: 6,
    predio_count: 6,
    rol_count: 5,
    surface_total: 32.5,
    basis_estado_resumido: 'estado_resumido_first_row',
    aprobados_pmf_count: 3,
    en_tramite_pmf_count: 1,
    basis_pending_priority: 'pending_priority_legacy',
    pendientes_prioritarios_pmf_count: 2,
    con_servidumbre_predio_count: 1,
    avance_por_predio: { aprobado: 3, en_tramite: 1, pendiente_o_tachado: 2 },
    avance_por_pmf: { aprobado: 3, en_tramite: 1, pendiente_o_tachado: 2 },
    estado_resumido_hero_predio: {
      aprobado: 3,
      en_tramite: 1,
      pendiente: 1,
      tachado: 1,
      sin_estado: 0,
    },
    estado_resumido_pmf: {
      aprobado: 3,
      en_tramite: 1,
      pendiente: 1,
      tachado: 1,
      sin_estado: 0,
    },
    estado_detalle_pmf: [
      { label: 'Aprobado', normalized: 'aprobado', count: 3 },
      { label: 'En Evaluacion', normalized: 'en evaluacion', count: 2 },
      { label: 'Rechazado', normalized: 'rechazado', count: 1 },
    ],
    estado_resumido_valores: {
      aprobado: ['Aprobado'],
      en_tramite: ['En tramite'],
      pendiente: ['Pendiente'],
      tachado: ['Tachado'],
    },
    por_empresa: [
      {
        empresa: 'Forestal Sur',
        pmf_count: 4,
        estado_resumido: { aprobado: 2, en_tramite: 1, pendiente: 1, tachado: 0, sin_estado: 0 },
      },
      {
        empresa: 'Forestal Norte',
        pmf_count: 2,
        estado_resumido: { aprobado: 1, en_tramite: 0, pendiente: 0, tachado: 1, sin_estado: 0 },
      },
    ],
    reforestacion: {
      definicion:
        'Valores distintos y no vacíos de «Predio Ref», excluyendo el literal «Sin reforestacion».',
      predio_ref_labels: ['Fundo Dos', 'Fundo Uno'],
      predio_ref_count: 2,
      rol_ref_count: 3,
      sentinel_label: 'Sin reforestacion',
      sentinel_row_count: 1,
      etiquetas_compuestas: [],
      propietarios: 'No disponible en el origen',
    },
    predios_reforestacion: ['Fundo Dos', 'Fundo Uno'],
    calidad_filas_sin_id_predial_unico: 6,
    calidad_pmf_sin_numero_ingreso: 2,
    calidad_numero_resolucion: 'No disponible',
    calidad_pmf_estado_resumido_conflictivo: [],
    ...overrides,
  }
}

export function makeRow(overrides: Partial<ResumenRow> = {}): ResumenRow {
  return {
    source_row_number: 2,
    predio_ref: 'Fundo Uno',
    rol_ref: null,
    area_ref: null,
    pmf: 'MP001',
    carpeta_source: 'CARP-E-01',
    carpeta_normalizada: 'CARP-AC-01',
    pas: 'PAS 148',
    estado: 'En evaluacion',
    estado_resumido: 'En tramite',
    tipo_rechazo: null,
    reingreso_tec: null,
    reingreso_legal: null,
    reingreso_recrep: null,
    tipo_propietario: 'Servidumbre firmada',
    id_transelec: null,
    rol: '123-4',
    numero_predio: '7',
    numero_area_corta: 'A1',
    superficie_corta: 4.25,
    superficie_total_corta: 9.5,
    fecha_ingreso: '2026-03-04',
    numero_ingreso: 'ING-900',
    fecha_90_dias: '2026-06-02',
    hoy_raw: null,
    empresa: 'Forestal Austral',
    id_predio_unico_ii: null,
    id_pmf: null,
    id_predio_unico: 'MP001-123-4-7',
    predio_group_key: 'MP001-123-4-7',
    tramite: null,
    sector: 'Norte',
    aef: null,
    quien_solicita: null,
    fecha_solicitud: null,
    fecha_corta: null,
    fecha_termino: null,
    chronology_flags: [],
    ...overrides,
  }
}

export function makePending(overrides: Partial<TranselecPending> = {}): TranselecPending {
  return {
    basis: 'pending_priority_legacy',
    pending_pmf_count: 2,
    total_pmf_count: 6,
    pending_pmf_percentage: 33.33,
    stage_basis: 'pending_stage_legacy',
    stages: { preparacion: 1, recurso_rechazo: 1, otros: 0 },
    rows: [
      { ...makeRow({ source_row_number: 3, pmf: 'MP002' }), pending_stage: 'preparacion' },
      { ...makeRow({ source_row_number: 5, pmf: 'MP005' }), pending_stage: 'recurso_rechazo' },
    ],
    ...overrides,
  }
}

export function makeOwnerStatus(
  overrides: Partial<TranselecOwnerStatus> = {},
): TranselecOwnerStatus {
  return {
    basis: 'owner_stage_legacy',
    total_predio_count: 6,
    rows: [
      { tipo_propietario: 'Servidumbre firmada', owner_stage: 'Aprobado', predio_count: 3 },
      { tipo_propietario: 'Particular', owner_stage: 'Rechazado', predio_count: 2 },
      { tipo_propietario: 'Particular', owner_stage: 'En tramite', predio_count: 1 },
    ],
    ...overrides,
  }
}

export function makeReport(overrides: Partial<TranselecReport> = {}): TranselecReport {
  return {
    generated_at: '2026-09-02T21:10:00+00:00',
    basis_estado_resumido: 'estado_resumido_first_row',
    basis_pending_priority: 'pending_priority_legacy',
    text:
      'REPORTE EJECUTIVO · SEGUIMIENTO CONAF\nCorte de información: 02-09-2026\n\n' +
      'El alcance seleccionado comprende 6 PMF, 6 predios identificados y 5 roles, con 32,50 ha de superficie de corta.',
    ...overrides,
  }
}

export function makeActiveImport(
  overrides: Partial<TranselecActiveImport> = {},
): TranselecActiveImport {
  return {
    import_id: 12,
    sha256: '82ba5eaed0b1a110b5966b301ca4a0bcbd3588ad5b8db7ba50d911b320af1851',
    byte_size: 5710,
    filename: 'resumen.xlsx',
    schema_contract_version: 'transelec-resumen-v1',
    parser_version: 'transelec_ingestion.xlsx_contract@1',
    business_rows: 7,
    distinct_pmf: 6,
    distinct_provisional_predio_ids: 1,
    surface_total: 32.5,
    validated_at: '2026-09-02T21:09:40+00:00',
    published_event_type: 'publish',
    published_at: '2026-09-02T21:10:00+00:00',
    published_by_app_user_id: 3,
    published_by_display_name: 'Dev Admin',
    warning_count: 0,
    source_fields: [
      'aef',
      'quien_solicita',
      'fecha_solicitud',
      'fecha_corta',
      'fecha_termino',
      'pmf',
      'estado_resumido',
    ],
    ...overrides,
  }
}

export function makeHistoryRow(
  overrides: Partial<TranselecImportHistoryRow> = {},
): TranselecImportHistoryRow {
  return {
    publish_event_id: 5,
    import_id: 12,
    event_type: 'publish',
    occurred_at: '2026-09-02T21:10:00+00:00',
    actor_app_user_id: 3,
    actor_display_name: 'Dev Admin',
    filename: 'resumen.xlsx',
    sha256: '82ba5eaed0b1a110b5966b301ca4a0bcbd3588ad5b8db7ba50d911b320af1851',
    business_rows: 7,
    distinct_pmf: 6,
    distinct_provisional_predio_ids: 1,
    surface_total: 32.5,
    is_active: true,
    ...overrides,
  }
}
