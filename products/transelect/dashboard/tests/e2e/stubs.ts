/**
 * Platform API stubs for the acceptance suite.
 *
 * Synthetic, hand-computed values only — never the reviewed snapshot's
 * counts, never real Transelec content. Each stub answers the same query
 * contract the real API does, so a filter change in the browser produces a
 * genuinely different response and every section has to re-read it.
 */
import type { Page, Route } from '@playwright/test'

export interface SummaryShape {
  pmf_count: number
  predio_count: number
  rol_count: number
  surface_total: number
  aprobados: number
  en_tramite: number
  pendiente_o_tachado: number
  hero: [number, number, number, number]
}

const UNFILTERED: SummaryShape = {
  pmf_count: 12,
  predio_count: 20,
  rol_count: 15,
  surface_total: 48.75,
  aprobados: 6,
  en_tramite: 3,
  pendiente_o_tachado: 3,
  hero: [10, 5, 3, 2],
}

const FILTERED: SummaryShape = {
  pmf_count: 4,
  predio_count: 5,
  rol_count: 4,
  surface_total: 12.25,
  aprobados: 3,
  en_tramite: 1,
  pendiente_o_tachado: 0,
  hero: [3, 1, 1, 0],
}

/** A filter state counts as "narrowed" when any filter parameter is present. */
export function isFiltered(url: URL): boolean {
  for (const key of ['q', 'estado_resumido', 'empresa', 'pas', 'sector', 'tipo_propietario']) {
    if (url.searchParams.getAll(key).length > 0) return true
  }
  return false
}

/** The unfiltered summary body, exported so a test can vary one field. */
export function summaryFixture(shape: SummaryShape = UNFILTERED) {
  return summaryBody(shape)
}

function summaryBody(shape: SummaryShape) {
  return {
    import_id: 7,
    row_count: shape.pmf_count * 2,
    pmf_count: shape.pmf_count,
    predio_count: shape.predio_count,
    rol_count: shape.rol_count,
    surface_total: shape.surface_total,
    basis_estado_resumido: 'estado_resumido_first_row',
    aprobados_pmf_count: shape.aprobados,
    en_tramite_pmf_count: shape.en_tramite,
    basis_pending_priority: 'pending_priority_legacy',
    pendientes_prioritarios_pmf_count: 5,
    con_servidumbre_predio_count: 4,
    avance_por_pmf: {
      aprobado: shape.aprobados,
      en_tramite: shape.en_tramite,
      pendiente_o_tachado: shape.pendiente_o_tachado,
    },
    avance_por_predio: {
      aprobado: shape.hero[0],
      en_tramite: shape.hero[1],
      pendiente_o_tachado: shape.hero[2] + shape.hero[3],
    },
    estado_resumido_hero_predio: {
      aprobado: shape.hero[0],
      en_tramite: shape.hero[1],
      pendiente: shape.hero[2],
      tachado: shape.hero[3],
      sin_estado: 0,
    },
    // PMF-grain headline. Hand-split so the four buckets sum to pmf_count
    // exactly — the invariant the acceptance suite checks on screen.
    estado_resumido_pmf: {
      aprobado: shape.aprobados,
      en_tramite: shape.en_tramite,
      pendiente: 0,
      tachado: shape.pendiente_o_tachado,
      sin_estado: 0,
    },
    estado_detalle_pmf: [
      { label: 'Aprobado', normalized: 'aprobado', count: shape.aprobados },
      { label: 'En Evaluacion', normalized: 'en evaluacion', count: shape.en_tramite },
      {
        label: 'Recurso reposicion rechazado',
        normalized: 'recurso reposicion rechazado',
        count: shape.pendiente_o_tachado,
      },
    ],
    estado_resumido_valores: {
      aprobado: ['Aprobado'],
      en_tramite: ['En tramite'],
      tachado: ['Tachado'],
    },
    por_empresa: [
      {
        empresa: 'Campo Sintético',
        pmf_count: shape.pmf_count,
        estado_resumido: {
          aprobado: shape.aprobados,
          en_tramite: shape.en_tramite,
          pendiente: 0,
          tachado: shape.pendiente_o_tachado,
          sin_estado: 0,
        },
      },
    ],
    reforestacion: {
      definicion:
        'Valores distintos y no vacíos de «Predio Ref», excluyendo el literal «Sin reforestacion».',
      predio_ref_labels: Array.from(
        { length: 13 },
        (_, index) => `Fundo Sintético ${index + 1}`,
      ),
      predio_ref_count: 13,
      rol_ref_count: 9,
      sentinel_label: 'Sin reforestacion',
      sentinel_row_count: 1,
      etiquetas_compuestas: ['Fundo Sintético 1 + Fundo Sintético 2'],
      propietarios: 'No disponible en el origen',
    },
    predios_reforestacion: Array.from({ length: 13 }, (_, index) => `Fundo Sintético ${index + 1}`),
    calidad_filas_sin_id_predial_unico: 2,
    calidad_pmf_sin_numero_ingreso: 3,
    calidad_numero_resolucion: 'No disponible',
    calidad_pmf_estado_resumido_conflictivo: [
      {
        pmf: 'PMF-002',
        valores: ['Aprobado', 'Tachado'],
        canonico: 'Aprobado',
        estado_detalle: 'Rechazado',
        source_row_number: 3,
      },
    ],
  }
}

export function makeApiRow(index: number, overrides: Record<string, unknown> = {}) {
  return {
    source_row_number: index,
    predio_ref: `Fundo Sintético ${index}`,
    rol_ref: null,
    area_ref: null,
    pmf: `PMF-${String(index).padStart(3, '0')}`,
    carpeta_source: `CARP-E-${index}`,
    carpeta_normalizada: `CARP-AC-${index}`,
    pas: 'PAS 148',
    estado: 'En evaluacion',
    estado_resumido: 'En tramite',
    tipo_rechazo: null,
    reingreso_tec: null,
    reingreso_legal: null,
    reingreso_recrep: null,
    tipo_propietario: 'Particular',
    id_transelec: null,
    rol: `10${index}-1`,
    numero_predio: '10',
    numero_area_corta: 'A1',
    superficie_corta: 1.5,
    superficie_total_corta: 3,
    fecha_ingreso: '2026-02-10',
    numero_ingreso: `ING-${index}`,
    fecha_90_dias: '2026-05-10',
    hoy_raw: null,
    empresa: 'Forestal Austral',
    id_predio_unico_ii: null,
    id_pmf: null,
    id_predio_unico: `PMF-${index}-10`,
    predio_group_key: `PMF-${index}-10`,
    tramite: null,
    sector: 'Norte',
    // Contract V2's AEF block: sparse and row-level, as in the source. Row 2
    // carries a full record with an inverted date; every other row is blank.
    aef: index === 2 ? 'Presentado' : null,
    quien_solicita: index === 2 ? 'Persona Sintética' : null,
    fecha_solicitud: index === 2 ? '2026-08-20' : null,
    fecha_corta: index === 2 ? '2026-08-19' : null,
    fecha_termino: index === 2 ? '2026-09-01' : null,
    chronology_flags: index === 2 ? ['cronologia_corta_antes_de_solicitud'] : [],
    ...overrides,
  }
}

export interface StubOptions {
  /** Force a status on every Transelec read (401/403/404 state tests). */
  readStatus?: number
  readDetail?: string
  /** Rows returned when a filter is active vs. not. */
  totalRows?: number
  filteredRows?: number
  /** Extra route handlers applied before the defaults. */
  extra?: (page: Page) => Promise<void>
  me?: Record<string, unknown> | null
  meStatus?: number
}

const DEFAULT_ME = {
  identity_key: 'dev-admin',
  display_name: 'Dev Admin',
  product_grants: [{ product_key: 'transelect', role: 'admin' }],
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: { date: 'Wed, 02 Sep 2026 21:10:00 GMT' },
    body: JSON.stringify(body),
  })
}

export async function stubPlatform(page: Page, options: StubOptions = {}): Promise<void> {
  const totalRows = options.totalRows ?? 60
  const filteredRows = options.filteredRows ?? 8

  await page.route('**/api/auth/me', (route) =>
    options.meStatus && options.meStatus !== 200
      ? json(route, { detail: 'Not authenticated.' }, options.meStatus)
      : json(route, options.me ?? DEFAULT_ME),
  )
  await page.route('**/api/auth/csrf', (route) =>
    json(route, { csrf_token: 'nonce.signature', header_name: 'X-CSRF-Token' }),
  )

  const fail = options.readStatus
  const failBody = { detail: options.readDetail ?? 'No hay una versión publicada de Transelec.' }

  // One synthetic activation event, so the Datos section's versions pane has
  // a history to render. Registered BEFORE `options.extra`: Playwright matches
  // the most recently added route first, so a test that supplies its own
  // `/imports` handler must still win over this default.
  await page.route('**/api/transelec/imports', (route) => {
    if (fail) return json(route, failBody, fail)
    return json(route, [
      {
        publish_event_id: 11,
        import_id: 7,
        event_type: 'publish',
        occurred_at: '2026-09-02T21:00:00+00:00',
        actor_app_user_id: 3,
        actor_display_name: 'Dev Admin',
        filename: 'planilla-sintetica.xlsx',
        sha256: '82ba5eaed0b1a110b5966b301ca4a0bcbd3588ad5b8db7ba50d911b320af1851',
        business_rows: 24,
        distinct_pmf: 12,
        distinct_provisional_predio_ids: 20,
        surface_total: 48.75,
        is_active: true,
      },
    ])
  })

  // One PMF's detail, for the row drawer: the clicked row plus one synthetic
  // sibling. Registered before `options.extra` so a test's own handler wins.
  await page.route('**/api/transelec/pmfs/*', (route) => {
    if (fail) return json(route, failBody, fail)
    const pmf = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop() ?? '')
    const index = Number(pmf.replace(/\D/g, '')) || 1
    return json(route, {
      pmf,
      row_count: 2,
      basis_estado_resumido: 'estado_resumido_first_row',
      estado_resumido: 'En tramite',
      rows: [
        makeApiRow(index),
        makeApiRow(index + 100, {
          pmf,
          rol: `10${index}-2`,
          numero_area_corta: 'A2',
          superficie_corta: 1.5,
          estado_resumido: 'En tramite',
          aef: null,
          quien_solicita: null,
          fecha_solicitud: null,
          fecha_corta: null,
          fecha_termino: null,
          chronology_flags: [],
        }),
      ],
    })
  })

  if (options.extra) await options.extra(page)

  await page.route('**/api/transelec/summary*', (route) => {
    if (fail) return json(route, failBody, fail)
    const url = new URL(route.request().url())
    return json(route, summaryBody(isFiltered(url) ? FILTERED : UNFILTERED))
  })

  await page.route('**/api/transelec/pending*', (route) => {
    if (fail) return json(route, failBody, fail)
    return json(route, {
      basis: 'pending_priority_legacy',
      pending_pmf_count: 5,
      total_pmf_count: 12,
      pending_pmf_percentage: 41.67,
      stage_basis: 'pending_stage_legacy',
      stages: { preparacion: 2, recurso_rechazo: 2, otros: 1 },
      rows: [1, 2, 3, 4, 5].map((index) => ({
        ...makeApiRow(index),
        pending_stage: index % 2 ? 'preparacion' : 'recurso_rechazo',
      })),
    })
  })

  await page.route('**/api/transelec/owner-status*', (route) => {
    if (fail) return json(route, failBody, fail)
    return json(route, {
      basis: 'owner_stage_legacy',
      total_predio_count: 20,
      rows: [
        { tipo_propietario: 'Servidumbre firmada', owner_stage: 'Aprobado', predio_count: 8 },
        { tipo_propietario: 'Particular', owner_stage: 'Rechazado', predio_count: 6 },
        { tipo_propietario: 'Particular', owner_stage: 'En tramite', predio_count: 4 },
        { tipo_propietario: '-', owner_stage: 'Tachado', predio_count: 2 },
      ],
    })
  })

  await page.route('**/api/transelec/report*', (route) => {
    if (fail) return json(route, failBody, fail)
    return json(route, {
      generated_at: '2026-09-02T21:10:00+00:00',
      basis_estado_resumido: 'estado_resumido_first_row',
      basis_pending_priority: 'pending_priority_legacy',
      text:
        'REPORTE EJECUTIVO · SEGUIMIENTO CONAF\nCorte de información: 02-09-2026\n\n' +
        'El alcance seleccionado comprende 12 PMF, 20 predios identificados y 15 roles, con 48,75 ha de superficie de corta.',
    })
  })

  await page.route('**/api/transelec/pmfs?*', (route) => {
    if (fail) return json(route, failBody, fail)
    const url = new URL(route.request().url())
    const limit = Number(url.searchParams.get('limit') ?? 25)
    const cursor = Number(url.searchParams.get('cursor') ?? 0)
    const total = isFiltered(url) ? filteredRows : totalRows
    const remaining = Math.max(0, total - cursor)
    const size = Math.min(limit, remaining)
    return json(route, {
      items: Array.from({ length: size }, (_, offset) => makeApiRow(cursor + offset + 1)),
      next_cursor: cursor + size < total ? String(cursor + size) : null,
      has_more: cursor + size < total,
      total_count: total,
    })
  })

  await page.route('**/api/transelec/imports/active', (route) => {
    if (fail) return json(route, failBody, fail)
    return json(route, {
      import_id: 7,
      sha256: '82ba5eaed0b1a110b5966b301ca4a0bcbd3588ad5b8db7ba50d911b320af1851',
      byte_size: 5710,
      filename: 'planilla-sintetica.xlsx',
      schema_contract_version: 'transelec-resumen-v1',
      parser_version: 'transelec_ingestion.xlsx_contract@1',
      business_rows: 24,
      distinct_pmf: 12,
      distinct_provisional_predio_ids: 20,
      surface_total: 48.75,
      validated_at: '2026-09-02T20:00:00+00:00',
      published_event_type: 'publish',
      published_at: '2026-09-02T21:00:00+00:00',
      published_by_app_user_id: 3,
      published_by_display_name: 'Dev Admin',
      warning_count: 1,
      source_fields: [
        'aef',
        'quien_solicita',
        'fecha_solicitud',
        'fecha_corta',
        'fecha_termino',
        'pmf',
        'estado_resumido',
      ],
    })
  })

  await page.route('**/api/transelec/aef*', (route) => {
    if (fail) return json(route, failBody, fail)
    return json(route, {
      basis: 'pmf_from_source_rows',
      source_fields: ['aef', 'quien_solicita', 'fecha_solicitud', 'fecha_corta', 'fecha_termino'],
      row_count: totalRows,
      pmf_count: 12,
      rows_with_any_tracking: 1,
      rows_with_aef: 1,
      rows_with_quien_solicita: 1,
      rows_with_fecha_solicitud: 1,
      rows_with_fecha_corta: 1,
      rows_with_fecha_termino: 1,
      rows_with_chronology_warning: 1,
      pmf_with_tracking: 1,
      pmf_with_aef: 1,
      pmf_with_conflict: 0,
      pmf_conflicts_by_field: {},
      pmf_with_chronology_warning: 1,
      por_aef: [{ label: 'Presentado', count: 1 }],
      por_solicitante: [{ label: 'Persona Sintética', count: 1 }],
      pmf_por_aef: [{ label: 'Presentado', count: 1 }],
      pmf_por_solicitante: [{ label: 'Persona Sintética', count: 1 }],
      pmfs: [
        {
          pmf: 'PMF-002',
          total_rows: 1,
          rows_with_any_tracking: 1,
          rows_with_aef: 1,
          source_row_numbers: [2],
          has_conflict: false,
          chronology_flags: ['cronologia_corta_antes_de_solicitud'],
          fields: Object.fromEntries(
            (
              [
                ['aef', 'Presentado', 'text'],
                ['quien_solicita', 'Persona Sintética', 'text'],
                ['fecha_solicitud', '2026-08-20', 'date'],
                ['fecha_corta', '2026-08-19', 'date'],
                ['fecha_termino', '2026-09-01', 'date'],
              ] as const
            ).map(([field, value, kind]) => [
              field,
              {
                status: 'value',
                value,
                value_kind: kind,
                source_rows: [2],
                variants: [{ value, source_rows: [2] }],
              },
            ]),
          ),
        },
      ],
      rows: [makeApiRow(2)],
    })
  })

  await page.route('**/api/transelec/export.csv*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/csv; charset=utf-8',
      headers: { 'content-disposition': 'attachment; filename="transelec_export.csv"' },
      body: '﻿PMF;Sector\nPMF-001;Norte\n',
    }),
  )
}
