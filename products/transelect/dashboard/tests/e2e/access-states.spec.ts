/**
 * The remaining required UI states: empty (nothing published), loading,
 * unauthorized per route, and platform-unavailable.
 */
import { expect, test } from '@playwright/test'
import { stubPlatform } from './stubs'

test('unauthenticated: every route asks the reader to sign in, and no data is fetched', async ({
  page,
}) => {
  const transelecCalls: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/transelec/')) transelecCalls.push(request.url())
  })

  await stubPlatform(page, { meStatus: 401 })
  await page.goto('/transelec')

  // A 401 is the signed-out state, not an error to report: it gets the
  // sign-in screen. (The assertion here used to expect the generic
  // "Sesión requerida" block; that block stopped being reachable when
  // sign-in moved into the dashboard itself, and this spec had not caught
  // up. `src/App.test.tsx` has asserted the sign-in screen all along.)
  await expect(page.getByTestId('login-card')).toBeVisible()
  await expect(page.getByText('Inicie sesión para continuar')).toBeVisible()
  await expect(page.getByTestId('kpi-row')).toBeHidden()
  expect(transelecCalls).toEqual([])
})

test('a viewer sees the dashboard but not the administration section', async ({ page }) => {
  await stubPlatform(page, {
    me: {
      identity_key: 'dev-viewer',
      display_name: 'Dev Viewer',
      product_grants: [{ product_key: 'transelect', role: 'viewer' }],
    },
  })

  await page.goto('/transelec')
  await expect(page.getByTestId('kpi-row')).toBeVisible()
  // The whole section, not merely its two old routes.
  await expect(
    page.getByRole('navigation', { name: 'Secciones de Transelec' }).getByRole('link', {
      name: 'Datos',
    }),
  ).toHaveCount(0)

  for (const path of ['/transelec/datos', '/transelec/importar', '/transelec/versiones']) {
    await page.goto(path)
    await expect(page.locator('[data-state-kind="forbidden"]')).toBeVisible()
    await expect(page.getByText('Sin autorización')).toBeVisible()
  }
})

test('a session without the Transelec grant sees the unauthorized state on the dashboard', async ({
  page,
}) => {
  await stubPlatform(page, {
    me: {
      identity_key: 'dev-operator',
      display_name: 'Dev Operator',
      product_grants: [{ product_key: 'forestry', role: 'operator' }],
    },
    readStatus: 403,
    readDetail: 'Not permitted for this product.',
  })

  await page.goto('/transelec')
  await expect(page.locator('[data-state-kind="forbidden"]')).toBeVisible()
  await expect(page.getByText('Sin autorización')).toBeVisible()
  // The generic backend string is never shown to the reader as-is.
  await expect(page.getByText('Not permitted for this product.')).toHaveCount(0)
})

test('empty: nothing published yet points an operator at the import page', async ({ page }) => {
  await stubPlatform(page, { readStatus: 404 })

  await page.goto('/transelec')
  await expect(page.locator('[data-state-kind="empty"]')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Sin versión publicada' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Importar planilla' }).last()).toBeVisible()
  await expect(page.getByTestId('kpi-row')).toBeHidden()
})

test('empty: the version history says so rather than showing an empty table', async ({ page }) => {
  await stubPlatform(page, {
    readStatus: undefined,
    extra: async (target) => {
      await target.route('**/api/transelec/imports', (route) =>
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
      )
      await target.route('**/api/transelec/imports/active', (route) =>
        route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'No hay una versión publicada de Transelec.' }),
        }),
      )
    },
  })

  await page.goto('/transelec/versiones')
  await expect(page.getByTestId('versions-empty')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Importe una planilla' })).toBeVisible()
})

test('unavailable: an unreachable platform is reported without blaming the data', async ({
  page,
}) => {
  await stubPlatform(page)
  await page.route('**/api/transelec/summary*', (route) => route.abort('failed'))
  await page.route('**/api/transelec/pending*', (route) => route.abort('failed'))
  await page.route('**/api/transelec/owner-status*', (route) => route.abort('failed'))
  await page.route('**/api/transelec/report*', (route) => route.abort('failed'))
  await page.route('**/api/transelec/pmfs?*', (route) => route.abort('failed'))

  await page.goto('/transelec')
  await expect(page.locator('[data-state-kind="unavailable"]')).toBeVisible()
  await expect(page.getByText('Plataforma no disponible')).toBeVisible()
  await expect(page.getByText(/los datos publicados no se han modificado/)).toBeVisible()
})

test('loading: a slow response shows a busy state before any numbers appear', async ({ page }) => {
  await stubPlatform(page)
  await page.route('**/api/transelec/summary*', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1200))
    await route.fallback()
  })

  await page.goto('/transelec')
  await expect(page.getByText('Cargando el alcance seleccionado…')).toBeVisible()
  // A skeleton shaped like the content it becomes, not a bare spinner.
  await expect(page.locator('.skeleton').first()).toBeVisible()
  await expect(page.getByTestId('kpi-row')).toBeVisible({ timeout: 15_000 })
})
