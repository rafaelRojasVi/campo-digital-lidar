/**
 * The navigation and interaction architecture the rearchitecture introduced.
 *
 * Four properties that did not exist before and that the product now depends
 * on:
 *
 *  1. the five sections are reachable, marked and role-gated;
 *  2. the filter state lives in the URL, so it is linkable, survives a
 *     reload, and is carried between sections;
 *  3. a row opens a detail drawer that is keyboard-operable and returns focus;
 *  4. the disclosure, the chips and the mobile navigation behave.
 */
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { stubPlatform } from './stubs'

const VIEWER = {
  identity_key: 'dev-viewer',
  display_name: 'Dev Viewer',
  product_grants: [{ product_key: 'transelect', role: 'viewer' }],
}

function nav(page: Page) {
  return page.getByRole('navigation', { name: 'Secciones de Transelec' })
}

test.describe('sections', () => {
  test.beforeEach(async ({ page }) => {
    await stubPlatform(page)
  })

  test('every section is reachable from the shell and marks itself as current', async ({
    page,
  }) => {
    await page.goto('/transelec')
    await expect(page.getByTestId('kpi-row')).toBeVisible()

    for (const [label, path, marker] of [
      ['Explorador', '/transelec/explorador', 'rows-body'],
      ['Pendientes', '/transelec/pendientes', 'pending-zone'],
      ['AEF', '/transelec/seguimiento-aef', 'aef-kpis'],
      ['Calidad', '/transelec/calidad', 'quality-panel'],
      ['Datos', '/transelec/datos', 'upload-submit'],
      ['Resumen', '/transelec', 'kpi-row'],
    ] as const) {
      await nav(page).getByRole('link', { name: label }).click()
      await expect(page).toHaveURL(new RegExp(`${path.replace(/\//g, '\\/')}$`))
      await expect(page.getByTestId(marker)).toBeVisible()
      await expect(nav(page).getByRole('link', { name: label })).toHaveAttribute(
        'aria-current',
        'page',
      )
    }
  })

  test('an AEF PMF row opens its detail by keyboard and returns focus when closed', async ({ page }) => {
    await page.goto('/transelec/seguimiento-aef')
    const row = page.getByTestId('aef-pmf-PMF-002')
    await expect(row).toBeVisible()
    await row.focus()
    await page.keyboard.press('Enter')

    const drawer = page.getByTestId('row-drawer')
    await expect(drawer).toBeVisible()
    await expect(drawer).toContainText('PMF-002')
    await expect(drawer).toContainText('Fila de origen 2')
    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
    await expect(row).toBeFocused()

    await row.click()
    await expect(drawer).toBeVisible()
  })

  test('the two legacy administration routes still resolve, into the Datos section', async ({
    page,
  }) => {
    await page.goto('/transelec/importar')
    await expect(page.getByTestId('upload-submit')).toBeVisible()
    await expect(nav(page).getByRole('link', { name: 'Datos' })).toHaveAttribute(
      'aria-current',
      'page',
    )

    await page.goto('/transelec/versiones')
    await expect(page.getByTestId('provenance-footer')).toBeVisible()
    await expect(nav(page).getByRole('link', { name: 'Datos' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  test('the section links are real anchors, so they can be opened in a new tab', async ({
    page,
  }) => {
    await page.goto('/transelec')
    await expect(page.getByTestId('kpi-row')).toBeVisible()
    await expect(nav(page).getByRole('link', { name: 'Explorador' })).toHaveAttribute(
      'href',
      '/transelec/explorador',
    )
  })
})

test.describe('the filter state lives in the URL', () => {
  test.beforeEach(async ({ page }) => {
    await stubPlatform(page)
  })

  test('typing a search writes it to the address bar and survives a reload', async ({ page }) => {
    await page.goto('/transelec/explorador')
    await expect(page.getByTestId('rows-body')).toBeVisible()

    await page.getByLabel('Búsqueda general').fill('rechaz')
    await expect(page).toHaveURL(/\?q=rechaz$/)
    await expect(page.getByTestId('rows-total')).toContainText('8 áreas de corta')

    await page.reload()
    await expect(page.getByLabel('Búsqueda general')).toHaveValue('rechaz')
    await expect(page.getByTestId('rows-total')).toContainText('8 áreas de corta')
  })

  test('a filtered link opens already filtered, in any section', async ({ page }) => {
    await page.goto('/transelec?q=rechaz')
    await expect(page.getByTestId('kpi-pmf')).toHaveText('4')
    await expect(page.getByText('Búsqueda: rechaz')).toBeVisible()

    await page.goto('/transelec/calidad?sector=Norte')
    await expect(page.getByText('Sector: Norte')).toBeVisible()
  })

  test('moving between sections carries the filter rather than silently dropping it', async ({
    page,
  }) => {
    await page.goto('/transelec/explorador')
    await page.getByLabel('Búsqueda general').fill('rechaz')
    await expect(page).toHaveURL(/q=rechaz/)

    await nav(page).getByRole('link', { name: 'Resumen' }).click()
    await expect(page).toHaveURL(/\/transelec\?q=rechaz/)
    await expect(page.getByTestId('kpi-pmf')).toHaveText('4')
  })

  test('a filter change replaces history rather than stacking an entry per keystroke', async ({
    page,
  }) => {
    await page.goto('/transelec')
    await expect(page.getByTestId('kpi-row')).toBeVisible()
    await nav(page).getByRole('link', { name: 'Explorador' }).click()
    await expect(page.getByTestId('rows-body')).toBeVisible()

    await page.getByLabel('Búsqueda general').fill('rechaz')
    await expect(page).toHaveURL(/q=rechaz/)

    // One Back press returns to the Resumen, not to five intermediate
    // half-typed filter states.
    await page.goBack()
    await expect(page).toHaveURL(/\/transelec$/)
    await expect(page.getByTestId('kpi-row')).toBeVisible()
  })

  test('a chip removes exactly its own filter and leaves the others alone', async ({ page }) => {
    await page.goto('/transelec/explorador?q=rechaz&sector=Norte')
    await expect(page.getByTestId('rows-body')).toBeVisible()

    const chips = page.getByTestId('active-filters')
    await expect(chips).toContainText('Búsqueda: rechaz')
    await expect(chips).toContainText('Sector: Norte')

    await page.getByRole('button', { name: 'Quitar el filtro Sector: Norte' }).click()
    await expect(chips).toContainText('Búsqueda: rechaz')
    await expect(chips).not.toContainText('Sector: Norte')
    await expect(page).toHaveURL(/\?q=rechaz$/)
  })

  test('an unfiltered view has a clean URL, with no empty parameters left behind', async ({
    page,
  }) => {
    await page.goto('/transelec/explorador?q=rechaz')
    await expect(page.getByTestId('rows-body')).toBeVisible()
    await page.getByRole('button', { name: 'Limpiar', exact: true }).click()
    await expect(page).toHaveURL(/\/transelec\/explorador$/)
  })
})

test.describe('the filter disclosure', () => {
  test.beforeEach(async ({ page }) => {
    await stubPlatform(page)
  })

  test('is closed by default, opens on demand, and counts what is active', async ({ page }) => {
    await page.goto('/transelec/explorador')
    await expect(page.getByTestId('rows-body')).toBeVisible()

    const toggle = page.getByRole('button', { name: /^Filtros/ })
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByRole('button', { name: 'Sector', exact: true })).toBeHidden()

    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await page.getByRole('button', { name: 'Sector', exact: true }).click()
    await page.getByLabel('Norte').check()

    // The badge reports the active count even once the panel is closed again.
    await expect(toggle).toContainText('1')
    await toggle.click()
    await expect(page.getByTestId('active-filters')).toContainText('Sector: Norte')
  })
})

test.describe('the row detail drawer', () => {
  test.beforeEach(async ({ page }) => {
    await stubPlatform(page, {
      extra: async (target) => {
        await target.route('**/api/transelec/pmfs/PMF-001', (route) =>
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              pmf: 'PMF-001',
              row_count: 2,
              basis_estado_resumido: 'estado_resumido_first_row',
              estado_resumido: 'En tramite',
              rows: [
                {
                  source_row_number: 1,
                  pmf: 'PMF-001',
                  rol: '101-1',
                  numero_area_corta: 'A1',
                  superficie_corta: 1.5,
                  estado_resumido: 'En tramite',
                },
                {
                  source_row_number: 99,
                  pmf: 'PMF-001',
                  rol: '101-2',
                  numero_area_corta: 'A2',
                  superficie_corta: 2.5,
                  estado_resumido: 'Aprobado',
                },
              ],
            }),
          }),
        )
      },
    })
  })

  test('opens from a row, shows the PMF’s other source rows, and closes on Escape', async ({
    page,
  }) => {
    await page.goto('/transelec/explorador')
    await expect(page.getByTestId('rows-body')).toBeVisible()

    await page.getByTestId('row-1').click()
    const drawer = page.getByTestId('row-drawer')
    await expect(drawer).toBeVisible()
    await expect(drawer).toContainText('PMF-001')
    await expect(drawer).toContainText('Fila de origen 1')
    await expect(page.getByTestId('drawer-sibling-count')).toContainText('2 filas en total')
    // The sibling row, which the flat table could never show.
    await expect(drawer).toContainText('101-2')

    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
  })

  test('is operable by keyboard alone and returns focus to the row it came from', async ({
    page,
  }) => {
    await page.goto('/transelec/explorador')
    await expect(page.getByTestId('rows-body')).toBeVisible()

    const row = page.getByTestId('row-1')
    await row.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('row-drawer')).toBeVisible()

    // Focus moved into the panel rather than being left behind the backdrop.
    await expect(page.getByTestId('row-drawer-close')).toBeFocused()

    await page.keyboard.press('Escape')
    await expect(page.getByTestId('row-drawer')).toBeHidden()
    await expect(row).toBeFocused()
  })

  test('covers the whole app, top bar included, and keeps the page from scrolling', async ({
    page,
  }) => {
    await page.goto('/transelec/explorador')
    await page.getByTestId('row-1').click()
    await expect(page.getByTestId('row-drawer')).toBeVisible()
    const topHit = await page.evaluate(() => {
      const element = document.elementFromPoint(40, 20)
      return element?.className ?? ''
    })
    expect(topHit).toContain('drawer-backdrop')
    expect(await page.evaluate(() => document.body.style.overflow)).toBe('hidden')
    await page.keyboard.press('Escape')
    expect(await page.evaluate(() => document.body.style.overflow)).toBe('')
  })

  test('switches to another row of the same PMF without closing', async ({ page }) => {
    await page.goto('/transelec/explorador')
    await page.getByTestId('row-1').click()
    const drawer = page.getByTestId('row-drawer')
    await expect(page.getByTestId('drawer-provenance')).toContainText('Fila de origen 1')
    await expect(page.getByTestId('drawer-row-1')).toHaveAttribute('aria-current', 'true')
    await drawer.getByRole('button', { name: /Ver la fila/ }).first().click()
    await expect(page.getByTestId('drawer-provenance')).toContainText('Fila de origen 99')
    await expect(page.getByTestId('drawer-row-99')).toHaveAttribute('aria-current', 'true')
    // Row 99 says «Aprobado»; the PMF is counted under its first row's value.
    await expect(page.getByTestId('drawer-counted-as')).toContainText('«En tramite»')
    await expect(drawer).toBeVisible()
  })

  test('marks the row whose detail is open', async ({ page }) => {
    await page.goto('/transelec/explorador')
    await page.getByTestId('row-2').click()
    await expect(page.getByTestId('row-2')).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('row-1')).toHaveAttribute('aria-selected', 'false')
  })
})

test.describe('role differences', () => {
  test('a viewer never sees the administration section, and is refused at its routes', async ({
    page,
  }) => {
    await stubPlatform(page, { me: VIEWER })

    await page.goto('/transelec')
    await expect(page.getByTestId('kpi-row')).toBeVisible()
    for (const label of ['Resumen', 'Explorador', 'Pendientes', 'AEF', 'Calidad']) {
      await expect(nav(page).getByRole('link', { name: label })).toBeVisible()
    }
    await expect(nav(page).getByRole('link', { name: 'Datos' })).toHaveCount(0)

    for (const path of ['/transelec/datos', '/transelec/importar', '/transelec/versiones']) {
      await page.goto(path)
      await expect(page.locator('[data-state-kind="forbidden"]')).toBeVisible()
    }
  })
})

test.describe('the skip link', () => {
  test('is the first thing a keyboard reader reaches, and jumps to the content', async ({
    page,
  }) => {
    await stubPlatform(page)
    await page.goto('/transelec')
    await expect(page.getByTestId('kpi-row')).toBeVisible()

    await page.keyboard.press('Tab')
    const skip = page.getByRole('link', { name: 'Saltar al contenido' })
    await expect(skip).toBeFocused()
    await expect(skip).toHaveAttribute('href', '#contenido')
  })
})

test.describe('the signed-out shell', () => {
  test('offers no section navigation and no version stamp', async ({ page }) => {
    await stubPlatform(page, { meStatus: 401 })
    await page.goto('/transelec')

    await expect(page.getByTestId('login-card')).toBeVisible()
    // Four destinations a visitor cannot open, and a "Sin versión publicada"
    // chip blaming the data for a session problem, are both absent.
    await expect(
      page.getByRole('navigation', { name: 'Secciones de Transelec' }),
    ).toHaveCount(0)
    await expect(page.getByText('Sin versión publicada')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Secciones' })).toHaveCount(0)
  })
})
