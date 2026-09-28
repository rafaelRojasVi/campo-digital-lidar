/**
 * TR-FUNC-040 (redesigned) and the version/restore surface.
 *
 * The import pane now drives a three-step stepper rather than three static
 * boxes, and the versions pane a timeline rather than a ten-column table.
 * Neither changed the pipeline, its ordering or its guarantees, so every
 * assertion below is the one this suite has always made.
 *
 * The controller's ruling is that TR-FUNC-040's acceptance criteria are met
 * by Task 3's backend tests plus this file's UI-state coverage: upload,
 * validating, validation-failed, duplicate-upload, validated-but-unpublished,
 * publish-confirmation and publish-failed. The old client-side ZIP/XLSX
 * reader is superseded, not reproduced.
 */
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { stubPlatform } from './stubs'

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

const UPLOAD_OK = {
  source_snapshot_id: 195,
  sha256: '82ba5eaed0b1a110b5966b301ca4a0bcbd3588ad5b8db7ba50d911b320af1851',
  byte_size: 5710,
  validation_evidence: { sheet_names: ['Resumen'], resumen_row_count: 24, contract_error: null },
  job_id: 83,
}

const RUNS = [
  {
    ingestion_run_id: 41,
    source_snapshot_id: 195,
    filename: 'planilla-sintetica.xlsx',
    sha256: '82ba',
    requested_by_app_user_id: 3,
    created_at: '2026-09-02T21:08:00+00:00',
    import_id: null,
    is_active: false,
  },
]

const VALIDATED = {
  status: 'validated',
  import_id: 83,
  source_snapshot_id: 195,
  ingestion_run_id: 41,
  schema_contract_version: 'transelec-resumen-v1',
  parser_version: 'transelec_ingestion.xlsx_contract@1',
  business_rows: 24,
  distinct_pmf: 12,
  distinct_provisional_predio_ids: 20,
  surface_total: 48.75,
  validated_at: '2026-09-02T21:09:40+00:00',
  is_active: false,
}

interface FlowOptions {
  validate?: { status: number; body: unknown }
  publish?: { status: number; body: unknown }
  upload?: { status: number; body: unknown }
}

async function stubFlow(page: Page, options: FlowOptions = {}) {
  await stubPlatform(page, {
    extra: async (target) => {
      await target.route('**/api/transelec/uploads', (route) =>
        route.fulfill({
          status: options.upload?.status ?? 200,
          contentType: 'application/json',
          body: JSON.stringify(options.upload?.body ?? UPLOAD_OK),
        }),
      )
      await target.route('**/api/transelec/uploads/recent*', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(RUNS),
        }),
      )
      await target.route('**/api/transelec/imports/*/validate-and-project', (route) =>
        route.fulfill({
          status: options.validate?.status ?? 200,
          contentType: 'application/json',
          body: JSON.stringify(options.validate?.body ?? VALIDATED),
        }),
      )
      await target.route('**/api/transelec/imports/*/publish', (route) =>
        route.fulfill({
          status: options.publish?.status ?? 200,
          contentType: 'application/json',
          body: JSON.stringify(
            options.publish?.body ?? {
              status: 'published',
              event_type: 'publish',
              import_id: 83,
              previous_import_id: 7,
              publish_event_id: 29,
              occurred_at: '2026-09-02T21:10:00+00:00',
              active_import_id: 83,
            },
          ),
        }),
      )
    },
  })
}

async function uploadFixture(page: Page) {
  await page.goto('/transelec/importar')
  await expect(page.getByRole('heading', { name: 'Importar planilla' })).toBeVisible()
  await page.getByLabel('Planilla maestra (.xlsx)').setInputFiles({
    name: 'planilla-sintetica.xlsx',
    mimeType: XLSX_MIME,
    buffer: Buffer.from('synthetic workbook bytes'),
  })
  await page.getByTestId('upload-submit').click()
}

test('upload → validate → publish, with an explicit confirmation before the mutation', async ({
  page,
}) => {
  await stubFlow(page)
  await uploadFixture(page)

  await expect(page.getByTestId('validation-result')).toBeVisible()
  await expect(page.getByText('Planilla validada')).toBeVisible()
  // The stepper reflects where the pipeline actually got to.
  await expect(page.locator('[data-step="upload"]')).toHaveAttribute('data-state', 'done')
  await expect(page.locator('[data-step="validate"]')).toHaveAttribute('data-state', 'done')
  await expect(page.locator('[data-step="publish"]')).toHaveAttribute('data-state', 'idle')
  await expect(page.getByText(/Todavía no está publicada/)).toBeVisible()
  await expect(page.getByTestId('upload-evidence')).toContainText('82ba5eaed0b1')

  await page.getByTestId('publish-open').click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('la importación #83 sea la versión activa')

  await page.getByTestId('confirm-accept').click()
  await expect(page.getByTestId('publish-result')).toBeVisible()
  await expect(page.getByText(/Reemplaza a la versión #7/)).toBeVisible()
})

test('the publish confirmation can be cancelled without firing the mutation', async ({ page }) => {
  let published = false
  await stubFlow(page)
  page.on('request', (request) => {
    if (request.url().includes('/publish')) published = true
  })

  await uploadFixture(page)
  await page.getByTestId('publish-open').click()
  await page.getByRole('button', { name: 'Cancelar' }).click()

  await expect(page.getByRole('dialog')).toBeHidden()
  expect(published).toBe(false)
})

test('a contract violation shows the generic invalid-upload state and no technical detail', async ({
  page,
}) => {
  await stubFlow(page, {
    validate: {
      status: 422,
      body: { detail: 'La planilla no cumple el contrato de origen esperado. Contacte a soporte.' },
    },
  })
  await uploadFixture(page)

  const failure = page.getByTestId('import-failure')
  await expect(failure).toBeVisible()
  await expect(failure).toContainText('Planilla no válida')
  // The step that failed says so, and the one after it never started.
  await expect(page.locator('[data-step="validate"]')).toHaveAttribute('data-state', 'failed')
  await expect(page.locator('[data-step="publish"]')).toHaveAttribute('data-state', 'idle')
  await expect(failure).toContainText('no cumple el contrato de origen esperado')
  await expect(failure).toContainText('La versión publicada actualmente no ha cambiado')
  await expect(page.getByTestId('validation-result')).toBeHidden()
  // Nothing resembling a traceback, a path or a column name reaches the page.
  await expect(failure).not.toContainText('Traceback')
  await expect(failure).not.toContainText('.py')
})

test('an invariant failure shows the import-failed state and says the active version is unchanged', async ({
  page,
}) => {
  await stubFlow(page, {
    validate: {
      status: 500,
      body: { detail: 'No se pudo verificar la importación. La versión activa no cambió.' },
    },
  })
  await uploadFixture(page)

  await expect(page.getByText('La importación no se completó')).toBeVisible()
  await expect(page.getByText(/La versión activa no cambió/)).toBeVisible()
})

test('an unavailable stored object shows the unavailable-source state', async ({ page }) => {
  await stubFlow(page, {
    validate: {
      status: 409,
      body: { detail: 'El archivo cargado ya no está disponible. Vuelva a cargarlo.' },
    },
  })
  await uploadFixture(page)

  await expect(page.getByText('Archivo no disponible')).toBeVisible()
  await expect(page.getByText('El archivo cargado ya no está disponible. Vuelva a cargarlo.')).toBeVisible()
})

test('a duplicate upload that is not active reports itself and still offers to publish', async ({
  page,
}) => {
  await stubFlow(page, {
    validate: { status: 200, body: { ...VALIDATED, status: 'already_imported' } },
  })
  await uploadFixture(page)

  await expect(page.getByText('Esta planilla ya había sido importada')).toBeVisible()
  await expect(page.getByTestId('publish-open')).toBeEnabled()
})

test('a duplicate upload that is already current offers no action', async ({ page }) => {
  await stubFlow(page, {
    validate: {
      status: 200,
      body: { ...VALIDATED, status: 'already_current', is_active: true },
    },
  })
  await uploadFixture(page)

  await expect(page.getByText('Esta planilla ya es la versión vigente')).toBeVisible()
  await expect(page.getByTestId('publish-open')).toBeDisabled()
})

test('a failed publish never claims the version changed', async ({ page }) => {
  await stubFlow(page, {
    publish: {
      status: 500,
      body: { detail: 'No se pudo publicar la versión. La versión activa no cambió.' },
    },
  })
  await uploadFixture(page)
  await page.getByTestId('publish-open').click()
  await page.getByTestId('confirm-accept').click()

  await expect(page.getByTestId('import-failure')).toBeVisible()
  await expect(page.getByTestId('publish-result')).toBeHidden()
})

test('mutations carry the runtime-issued CSRF token, never a compiled-in secret', async ({
  page,
}) => {
  await stubFlow(page)
  const mutationHeaders: Record<string, string>[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/api/transelec/')) {
      mutationHeaders.push(request.headers())
    }
  })

  await uploadFixture(page)
  await expect(page.getByTestId('validation-result')).toBeVisible()

  expect(mutationHeaders.length).toBeGreaterThan(0)
  for (const headers of mutationHeaders) {
    expect(headers['x-csrf-token']).toBe('nonce.signature')
  }

  // The token was fetched at runtime, not baked into the bundle.
  const bundle = await page.evaluate(async () => {
    const response = await fetch('/src/api.ts')
    return response.ok ? response.text() : ''
  })
  expect(bundle).not.toContain('nonce.signature')
})

test('version history lists activations and restore asks for an explicit confirmation', async ({
  page,
}) => {
  let restored = false
  await stubPlatform(page, {
    extra: async (target) => {
      await target.route('**/api/transelec/imports', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              publish_event_id: 9,
              import_id: 7,
              event_type: 'publish',
              occurred_at: '2026-09-02T21:00:00+00:00',
              actor_app_user_id: 3,
              actor_display_name: 'Dev Admin',
              filename: 'planilla-sintetica.xlsx',
              sha256: '82ba5eaed0b1a110b5966b301ca4a0bc',
              business_rows: 24,
              distinct_pmf: 12,
              distinct_provisional_predio_ids: 20,
              surface_total: 48.75,
              is_active: true,
            },
            {
              publish_event_id: 4,
              import_id: 3,
              event_type: 'restore',
              occurred_at: '2026-08-20T10:00:00+00:00',
              actor_app_user_id: 3,
              actor_display_name: 'Dev Admin',
              filename: 'planilla-anterior.xlsx',
              sha256: 'aaaabbbbccccdddd',
              business_rows: 18,
              distinct_pmf: 9,
              distinct_provisional_predio_ids: 15,
              surface_total: 30.5,
              is_active: false,
            },
          ]),
        }),
      )
      await target.route('**/api/transelec/imports/*/restore', (route) => {
        restored = true
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'restored',
            event_type: 'restore',
            import_id: 3,
            previous_import_id: 7,
            publish_event_id: 30,
            occurred_at: '2026-09-02T22:00:00+00:00',
            active_import_id: 3,
          }),
        })
      })
    },
  })

  await page.goto('/transelec/versiones')
  await expect(page.getByTestId('version-9')).toBeVisible()
  await expect(page.getByTestId('version-9')).toHaveClass(/active/)
  await expect(page.getByTestId('version-4').getByText('Restauración')).toBeVisible()
  await expect(page.getByTestId('restore-7')).toBeDisabled()
  // The active entry is distinguishable from the previous one without
  // reading the disabled button: it is the only one badged as active.
  await expect(page.getByTestId('version-9').locator('.version-badge.active')).toBeVisible()
  await expect(page.getByTestId('version-4').locator('.version-badge.active')).toHaveCount(0)

  // Cancelling fires nothing.
  await page.getByTestId('restore-3').click()
  await expect(page.getByTestId('restore-confirm-message')).toContainText(
    'Está a punto de volver a activar la importación #3',
  )
  await page.getByRole('button', { name: 'Cancelar' }).click()
  expect(restored).toBe(false)

  // Confirming does.
  await page.getByTestId('restore-3').click()
  await page.getByTestId('confirm-accept').click()
  await expect(page.getByText('Versión restaurada')).toBeVisible()
  expect(restored).toBe(true)
})
