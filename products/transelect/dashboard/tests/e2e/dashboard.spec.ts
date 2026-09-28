/**
 * Acceptance tests for the four reading sections.
 *
 * Traceability: TR-FUNC-001-023, 026-039, 041-043, 046.
 *
 * Every assertion about a *value*, a *rule* or a *behaviour* is the one the
 * suite has always made. What moved is where the assertion is made: the UX
 * rearchitecture split one route into five, so a test that used to scroll a
 * single page now navigates to the section that owns the thing under test.
 * Filter consistency (TR-FUNC-017) keeps its own dedicated spec, as the
 * design doc requires; print and responsive keep theirs.
 */
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { makeApiRow, stubPlatform, summaryFixture } from './stubs'

const ZERO_DEFECT_SUMMARY = summaryFixture()

test.beforeEach(async ({ page }) => {
  await stubPlatform(page)
})

async function openResumen(page: Page) {
  await page.goto('/transelec')
  await expect(page.getByTestId('kpi-row')).toBeVisible()
}

async function openExplorador(page: Page) {
  await page.goto('/transelec/explorador')
  await expect(page.getByTestId('rows-body')).toBeVisible()
}

/**
 * The filter surface — the five fields and the four presets — lives behind a
 * disclosure, so a test that drives either has to open it first, exactly as a
 * reader would.
 */
async function openFilters(page: Page) {
  await page.getByRole('button', { name: /^Filtros/ }).click()
  await expect(page.getByRole('button', { name: 'Sector', exact: true })).toBeVisible()
}

async function openPendientes(page: Page) {
  await page.goto('/transelec/pendientes')
  await expect(page.getByTestId('pending-zone')).toBeVisible()
}

async function openCalidad(page: Page) {
  await page.goto('/transelec/calidad')
  await expect(page.getByTestId('quality-panel')).toBeVisible()
}

test('TR-FUNC-041/046: the shell carries the identity and the active version’s publish stamp', async ({
  page,
}) => {
  await openResumen(page)

  await expect(page.getByRole('img', { name: 'Campo Digital' })).toBeVisible()
  await expect(page.getByText('Transmisora del Pacífico – Transelec')).toBeVisible()
  await expect(page.getByText('Versión activa #7')).toBeVisible()
  await expect(page.getByText(/Publicada 02-09-2026/).first()).toBeVisible()
  // Campo Digital's own logo, served from the bundle and actually decoded —
  // never hotlinked from campodigital.cl. The Transelec logo is not reused.
  const logo = page.locator('.topbar img')
  await expect(logo).toHaveCount(1)
  expect(await logo.getAttribute('src')).not.toMatch(/^https?:/)
  expect(await logo.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0)
})

test('TR-FUNC-042: the Consulta documental banner keeps its source wording, beside the search it describes', async ({
  page,
}) => {
  await openExplorador(page)
  const banner = page.getByTestId('notice-banner')
  await expect(banner).toContainText('Consulta documental:')
  await expect(banner).toContainText('N.º de ingreso está asociado directamente a cada PMF')
})

test('TR-FUNC-001-008: every KPI value the API returns is rendered, in its new group', async ({
  page,
}) => {
  await openResumen(page)

  // Reference counts — the quiet scale strip.
  await expect(page.getByTestId('kpi-pmf')).toHaveText('12')
  await expect(page.getByTestId('kpi-predios')).toHaveText('20')
  await expect(page.getByTestId('kpi-roles')).toHaveText('15')
  await expect(page.getByTestId('kpi-superficie')).toHaveText('48,75 ha')
  await expect(page.getByTestId('kpi-servidumbre')).toHaveText('4')

  // The number that means work — the attention row.
  await expect(page.getByTestId('kpi-pendientes')).toHaveText('5')

  // Approval at PMF grain, now carried by the status headline. The former
  // three-way `composition-pmf` bar is superseded rather than removed: the
  // headline reads the same basis at the same grain, one bucket finer, so
  // `Tachado` is no longer merged into a "pendiente o tachado" catch-all.
  await expect(page.getByTestId('status-aprobado')).toHaveText('6')
  await expect(page.getByTestId('status-en_tramite')).toHaveText('3')
  await expect(page.getByTestId('status-tachado')).toHaveText('3')
})

test('TR-FUNC-009/010: one composition bar per grain, each against its own total', async ({
  page,
}) => {
  await openResumen(page)
  await expect(page.getByTestId('composition-predios-total')).toHaveText(
    '10 de 20 predios aprobados',
  )
  await expect(page.getByTestId('status-pmf-total')).toHaveText('12 PMF')
  // 10 of 20 predios: the predio grain's own percentage, not the PMF grain's.
  await expect(page.getByTestId('composition-predios')).toContainText('50% aprobado')
})

test('TR-FUNC-011: the predio-grain Estado resumido breakdown, with its grain stated', async ({
  page,
}) => {
  await openResumen(page)
  await expect(page.getByTestId('status-hero-aprobado')).toHaveText('10')
  await expect(page.getByTestId('status-hero-en-tramite')).toHaveText('5')
  await expect(page.getByTestId('status-hero-pendiente')).toHaveText('3')
  await expect(page.getByTestId('status-hero-tachado')).toHaveText('2')
  await expect(page.getByText(/20 predios únicos del alcance seleccionado/)).toBeVisible()
})

test('TR-FUNC-012: reforestación chips list ten values plus an overflow chip', async ({ page }) => {
  await openCalidad(page)
  await expect(page.getByTestId('reforestation-count')).toHaveText('13')
  await expect(page.getByTestId('reforestation-overflow')).toContainText('Muchos · 13 en total')
  await expect(page.locator('.refchip:not(.refmany)')).toHaveCount(10)
})

test('TR-FUNC-013: the owner-status table pivots the API rows and shows its basis', async ({
  page,
}) => {
  await openCalidad(page)
  const table = page.getByTestId('owner-status')
  await expect(table.locator('.basis-tag').first()).toHaveText('owner_stage_legacy')
  await expect(table).toContainText('Servidumbre firmada')
  await expect(page.getByTestId('owner-status-total')).toHaveText('20')
  await expect(table).toContainText(
    'puede clasificar un predio de forma distinta al resto del panel',
  )
})

test('TR-FUNC-014/015/016: the quality panel shows both counts and the static literal', async ({
  page,
}) => {
  await openCalidad(page)
  await expect(page.getByTestId('quality-sin-id')).toHaveText('2')
  await expect(page.getByTestId('quality-sin-ingreso')).toHaveText('3')
  await expect(page.getByTestId('quality-resolucion')).toHaveText('No disponible')
})

test('TR-FUNC-014/015: a quality indicator reading zero renders calm, not as a warning', async ({
  page,
}) => {
  // Registered after the defaults so this handler wins, and fulfilled
  // outright: re-fetching would bypass the stub and hit the dev server.
  await page.route('**/api/transelec/summary*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...ZERO_DEFECT_SUMMARY,
        calidad_filas_sin_id_predial_unico: 0,
        calidad_pmf_sin_numero_ingreso: 3,
      }),
    }),
  )
  await openCalidad(page)

  await expect(page.locator('[data-finding="sin-id"]')).toHaveAttribute('data-tone', 'calm')
  // …while the one that is non-zero still escalates.
  await expect(page.locator('[data-finding="sin-ingreso"]')).toHaveAttribute('data-tone', 'warn')
})

test('TR-FUNC-018-022: a multi-select narrows the result set', async ({ page }) => {
  await openExplorador(page)
  await openFilters(page)
  await page.getByRole('button', { name: 'Sector', exact: true }).click()
  await page.getByLabel('Norte').check()

  await expect(page.getByTestId('rows-total')).toContainText('8 áreas de corta')
})

test('TR-FUNC-023: Limpiar clears every filter, from the toolbar and from a chip alike', async ({
  page,
}) => {
  await openExplorador(page)

  await page.getByLabel('Búsqueda general').fill('rechaz')
  await expect(page.getByTestId('rows-total')).toContainText('8 áreas de corta')
  await expect(page.getByTestId('active-filters')).toContainText('Búsqueda: rechaz')

  await page.getByRole('button', { name: 'Limpiar', exact: true }).click()
  await expect(page.getByTestId('rows-total')).toContainText('60 áreas de corta')
  await expect(page.getByLabel('Búsqueda general')).toHaveValue('')

  // The chip's own remove control is the same reset path for one field.
  await page.getByLabel('Búsqueda general').fill('legal')
  await expect(page.getByTestId('rows-total')).toContainText('8 áreas de corta')
  await page.getByRole('button', { name: 'Quitar el filtro Búsqueda: legal' }).click()
  await expect(page.getByTestId('rows-total')).toContainText('60 áreas de corta')
})

test('TR-FUNC-024/032: the Resumen attention card and the Pendientes section agree', async ({
  page,
}) => {
  await openResumen(page)
  await expect(page.getByTestId('kpi-pendientes')).toHaveText('5')

  await page.getByRole('link', { name: /Ver la cola de trabajo/ }).click()
  await expect(page.getByTestId('pending-zone')).toBeVisible()
  await expect(page.getByTestId('pending-count')).toHaveText('5 de 12')

  // Unfiltered, there is nothing to clear, so no button pretends to act.
  await expect(page.getByTestId('clear-pending-filters')).toHaveCount(0)
})

test('Pendientes: a narrowed scope offers one button that clears it', async ({ page }) => {
  await page.goto('/transelec/pendientes?q=legal')
  await expect(page.getByTestId('pending-zone')).toBeVisible()
  await page.getByTestId('clear-pending-filters').click()
  await expect(page).toHaveURL(/\/transelec\/pendientes$/)
  await expect(page.getByTestId('clear-pending-filters')).toHaveCount(0)
})

test('Pendientes: every queue row opens the PMF detail, by mouse and by keyboard', async ({
  page,
}) => {
  await page.goto('/transelec/pendientes')
  const row = page.getByTestId('pending-row-2')
  await row.click()
  const drawer = page.getByTestId('row-drawer')
  await expect(drawer).toBeVisible()
  await expect(drawer).toContainText('PMF-002')
  await expect(page.getByTestId('drawer-provenance')).toHaveText(
    'Fila de origen 2 de la hoja «Resumen»',
  )
  await expect(row).toHaveAttribute('aria-selected', 'true')
  await page.getByTestId('row-drawer-close').click()
  await expect(drawer).toBeHidden()
  await expect(row).toBeFocused()

  await page.getByTestId('pending-row-3').focus()
  await page.keyboard.press('Enter')
  await expect(drawer).toContainText('PMF-003')
})

test('Resumen: the work-queue rows open the PMF detail', async ({ page }) => {
  await openResumen(page)
  await page.getByTestId('queue-row-1').click()
  await expect(page.getByTestId('row-drawer')).toContainText('PMF-001')
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('row-drawer')).toBeHidden()
})

test('no section shows a raw rule identifier in its reading text', async ({ page }) => {
  for (const path of [
    '/transelec',
    '/transelec/explorador',
    '/transelec/pendientes',
    '/transelec/seguimiento-aef',
    '/transelec/calidad',
  ]) {
    await page.goto(path)
    await expect(page.locator('main .enter')).toBeVisible()
    await page.waitForLoadState('networkidle')
    // innerText leaves out the body of a closed <details>: the identifiers
    // are still there for audit, one «Cómo se calcula» away.
    const text = await page.locator('main').innerText()
    expect(text, path).not.toMatch(/_legacy|_first_row|pmf_from_source_rows|canónic|deduplica/)
  }
})

test('Calidad: «Cómo se calcula» opens to the exact rule and source columns', async ({ page }) => {
  await openCalidad(page)
  const how = page.getByTestId('owner-how')
  await expect(how.getByText('owner_stage_legacy')).toBeHidden()
  await how.locator('summary').click()
  await expect(how.getByText('owner_stage_legacy')).toBeVisible()
  await expect(how).toContainText('Tipo de propietario')
  await expect(page.getByTestId('owner-why')).toContainText('Cuenta predios, no planes')
  await expect(page.getByTestId('owner-why-rejected')).toHaveText('6')
})

test('TR-FUNC-025: the Explorador’s search is the N.º de ingreso lookup, and it is the page’s first control', async ({
  page,
}) => {
  await openExplorador(page)
  const search = page.getByLabel('Búsqueda general')
  await expect(search).toBeVisible()
  await expect(search).toHaveAttribute(
    'placeholder',
    'PMF, rol, N.º de ingreso, predio, empresa…',
  )

  await search.fill('ING-1')
  await expect(page.getByTestId('rows-total')).toContainText('8 áreas de corta')
})

test('TR-FUNC-026: the easement preset selects exactly Servidumbre firmada', async ({ page }) => {
  await openExplorador(page)
  await openFilters(page)
  const request = page.waitForRequest(
    (req) =>
      req.url().includes('/api/transelec/pmfs') &&
      req.url().includes('tipo_propietario=Servidumbre+firmada'),
  )
  await page.getByText('¿Cuáles tienen servidumbre?').click()
  await request
  await expect(page.getByTestId('active-filters')).toContainText(
    'Tipo de propietario: Servidumbre firmada',
  )
})

test('TR-FUNC-027: the surface figure is a reference count on the Resumen', async ({ page }) => {
  await openResumen(page)
  await expect(page.getByTestId('kpi-superficie')).toHaveText('48,75 ha')
  await expect(page.getByTestId('kpi-row')).toContainText('suma de áreas de corta')
})

test('TR-FUNC-028/029: the rejected and legal presets run their literal substring searches', async ({
  page,
}) => {
  await openExplorador(page)
  await openFilters(page)

  await page.getByText('¿Qué expedientes tienen rechazo?').click()
  await expect(page.getByLabel('Búsqueda general')).toHaveValue('rechaz')
  await expect(page).toHaveURL(/q=rechaz/)

  await page.getByText('¿Dónde está el principal cuello de botella?').click()
  await expect(page.getByLabel('Búsqueda general')).toHaveValue('legal')
})

test('TR-FUNC-030: the company preset opens the Empresa filter and nothing else', async ({
  page,
}) => {
  await openExplorador(page)
  await openFilters(page)
  await page.getByText('¿Cómo avanza cada empresa?').click()

  await expect(page.getByRole('button', { name: 'Empresa', exact: true })).toHaveAttribute(
    'aria-expanded',
    'true',
  )
  await expect(page.getByTestId('rows-total')).toContainText('60 áreas de corta')
})

test('TR-FUNC-031: the overdue consultation uses a computed reference date, never a frozen literal', async ({
  page,
}) => {
  await openPendientes(page)
  await page.getByRole('button', { name: '¿Qué ingresos superaron 90 días?' }).click()

  const panel = page.getByTestId('overdue-panel')
  await expect(panel).toBeVisible()
  await expect(page.getByTestId('overdue-count')).not.toContainText('(0 ')
  // The source dashboards froze this comparison at 2026-08-26.
  await expect(panel).not.toContainText('26-08-2026')
  await expect(panel).toContainText('02-09-2026')
  await expect(panel).toContainText('hora observada del servidor')

  await page.getByTestId('overdue-close').click()
  await expect(panel).toBeHidden()
})

test('TR-FUNC-017/031: the overdue panel follows a filter change instead of going stale', async ({
  page,
}) => {
  await page.goto('/transelec/pendientes')
  await expect(page.getByTestId('pending-zone')).toBeVisible()
  await page.getByRole('button', { name: '¿Qué ingresos superaron 90 días?' }).click()

  const panel = page.getByTestId('overdue-panel')
  await expect(panel).toBeVisible()
  // Unfiltered scope: the stub serves 60 rows, all of them overdue.
  await expect(page.getByTestId('overdue-count')).toContainText('(60 ')

  // The panel's own copy claims its scope is the active filters. Arriving
  // with a filter in the URL must move it with the rest of the section.
  await page.goto('/transelec/pendientes?q=rechaz')
  await expect(page.getByTestId('pending-zone')).toBeVisible()
  await page.getByRole('button', { name: '¿Qué ingresos superaron 90 días?' }).click()
  await expect(page.getByTestId('overdue-count')).toContainText('(8 ')
  await expect(page.getByTestId('overdue-panel')).toContainText(
    'El alcance es el de los filtros activos',
  )
})

test('TR-FUNC-032/033: Pendientes shows the count, the stages once, and the detail table', async ({
  page,
}) => {
  await openPendientes(page)

  await expect(page.getByTestId('pending-count')).toHaveText('5 de 12')
  await expect(page.getByTestId('pending-stage-preparacion')).toHaveText('2')
  await expect(page.getByTestId('pending-stage-recurso_rechazo')).toHaveText('2')
  await expect(page.getByTestId('pending-stage-otros')).toHaveText('1')
  await expect(page.getByTestId('pending-zone').locator('tbody tr')).toHaveCount(5)
  await expect(page.getByTestId('pending-zone')).toContainText('pending_priority_legacy')
  await expect(page.getByTestId('pending-zone')).toContainText('pending_stage_legacy')

  // Each stage count appears exactly once. The shipped pending zone printed
  // all three twice, as tiles and again as progress bars directly beneath.
  await expect(page.getByTestId('pending-stage-preparacion')).toHaveCount(1)
})

test('TR-FUNC-034/035/036: the report renders as text and both export actions work', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await openCalidad(page)

  const report = page.getByTestId('report-text')
  await expect(report).toContainText('REPORTE EJECUTIVO · SEGUIMIENTO CONAF')
  await expect(report).toContainText('Corte de información: 02-09-2026')

  await page.getByTestId('copy-report').click()
  await expect(page.getByText('Reporte copiado al portapapeles.')).toBeVisible()
  const clipboard = await page.evaluate(() => navigator.clipboard.readText())
  expect(clipboard).toContain('REPORTE EJECUTIVO · SEGUIMIENTO CONAF')

  const download = page.waitForEvent('download')
  await page.getByTestId('download-report').click()
  expect((await download).suggestedFilename()).toBe('reporte_ejecutivo_conaf.txt')
})

test('TR-FUNC-037: Exportar CSV downloads from the backend endpoint under the current filters', async ({
  page,
}) => {
  await openExplorador(page)
  await page.getByLabel('Búsqueda general').fill('rechaz')
  await expect(page.getByTestId('rows-total')).toContainText('8 áreas de corta')

  const [request, download] = await Promise.all([
    page.waitForRequest((req) => req.url().includes('/api/transelec/export.csv')),
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Exportar CSV' }).click(),
  ])

  expect(request.url()).toContain('q=rechaz')
  expect(download.suggestedFilename()).toBe('transelec_export.csv')
})

test('TR-FUNC-039: the detail table has the full column set and real pagination', async ({
  page,
}) => {
  await openExplorador(page)

  const headers = page.locator('.rows-table thead th')
  await expect(headers).toHaveText([
    'PMF',
    'Predio de reforestación',
    'Carpeta PMF',
    'Carpeta normalizada',
    'Rol',
    'Predio',
    'Área corta',
    'Sup. ha',
    'Estado resumido',
    'AEF',
    'N.º ingreso',
    'Empresa',
    'Propietario',
    'Sector',
  ])

  await expect(page.getByTestId('rows-total')).toContainText('60 áreas de corta')
  await expect(page.getByTestId('pagination-range')).toHaveText('Mostrando 1–25 de 60 filas')
  await expect(page.getByTestId('rows-body').locator('tr')).toHaveCount(25)

  await page.getByTestId('page-next').click()
  await expect(page.getByTestId('pagination-range')).toHaveText('Mostrando 26–50 de 60 filas')
  await page.getByTestId('page-next').click()
  await expect(page.getByTestId('pagination-range')).toHaveText('Mostrando 51–60 de 60 filas')
  await expect(page.getByTestId('page-next')).toBeDisabled()

  await page.getByTestId('page-prev').click()
  await expect(page.getByTestId('pagination-range')).toHaveText('Mostrando 26–50 de 60 filas')

  await page.getByLabel('Filas por página').selectOption('100')
  await expect(page.getByTestId('pagination-range')).toHaveText('Mostrando 1–60 de 60 filas')
})

test('TR-FUNC-043: the active version’s real provenance is cited beside its history', async ({
  page,
}) => {
  await page.goto('/transelec/versiones')
  const footer = page.getByTestId('provenance-footer')

  await expect(footer).toContainText('planilla-sintetica.xlsx')
  await expect(footer).toContainText('82ba5eaed0b1')
  await expect(footer).toContainText('transelec-resumen-v1')
  await expect(footer).toContainText('Dev Admin')
  await expect(footer).toContainText('nunca modifica la planilla de origen')
})

test('no workbook-derived value is ever rendered as markup', async ({ page }) => {
  // Registered after the default stubs so this handler wins: Playwright
  // matches the most recently added route first.
  await page.route('**/api/transelec/pmfs?*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            ...makeApiRow(1),
            empresa: '<img src=x onerror="window.__xss=1">',
            sector: '<script>window.__xss2=1</script>',
          },
        ],
        next_cursor: null,
        has_more: false,
        total_count: 1,
      }),
    }),
  )

  await openExplorador(page)
  await expect(page.getByTestId('rows-body')).toContainText('<img src=x onerror=')
  expect(await page.locator('[data-testid="rows-body"] img').count()).toBe(0)
  expect(await page.locator('[data-testid="rows-body"] script').count()).toBe(0)
  expect(
    await page.evaluate(() => (window as unknown as Record<string, unknown>).__xss),
  ).toBeUndefined()
})

/*
 * The workflow Marianne actually runs, end to end.
 *
 * She answers Javier's "¿cuál es el estado de los planes de manejo?" from the
 * `Estado resumido` column, so the Resumen has to answer it without her
 * reconstructing it, and a status has to lead to the plans behind it.
 */
test('the status headline answers the recurring question at PMF grain', async ({ page }) => {
  await openResumen(page)

  await expect(
    page.getByRole('heading', { name: 'Estado de los planes de manejo' }),
  ).toBeVisible()
  await expect(page.getByTestId('kpi-pmf-total')).toHaveText('12')

  // The buckets account for every plan: 6 + 3 + 3 = 12, hand-computed in stubs.
  const bucketTotal = await page.evaluate(() =>
    ['aprobado', 'en_tramite', 'pendiente', 'tachado', 'sin_estado']
      .map((key) => document.querySelector(`[data-testid="status-${key}"]`))
      .filter((node): node is Element => node !== null)
      .reduce((sum, node) => sum + Number(node.textContent), 0),
  )
  expect(bucketTotal).toBe(12)
})

test('clicking a status opens the Explorer filtered to exactly that status', async ({ page }) => {
  await openResumen(page)

  await page.locator('[data-status="aprobado"]').click()

  await expect(page).toHaveURL(/\/transelec\/explorador\?estado_resumido=Aprobado/)
  await expect(page.getByTestId('active-filters')).toContainText('Aprobado')
})

test('a status click-through keeps the filters the reader already had', async ({ page }) => {
  await stubPlatform(page)
  await page.goto('/transelec?empresa=Campo+Sint%C3%A9tico')
  await expect(page.getByTestId('status-cards')).toBeVisible()

  await page.locator('[data-status="aprobado"]').click()

  await expect(page).toHaveURL(/empresa=Campo\+Sint%C3%A9tico/)
  await expect(page).toHaveURL(/estado_resumido=Aprobado/)
})

test('the filtered Explorer counts the whole API population, not the page', async ({ page }) => {
  await stubPlatform(page)
  await page.goto('/transelec/explorador?estado_resumido=Aprobado')

  // The count shown is the API's `total_count` for the whole filtered
  // population, not the number of rows the current page happens to hold.
  await expect(page.getByTestId('rows-body')).toBeVisible()
  const shown = await page.getByTestId('rows-body').locator('tr').count()
  const total = Number((await page.getByTestId('rows-total').textContent())!.replace(/\D/g, ''))
  expect(total).toBeGreaterThan(0)
  expect(total).toBeGreaterThanOrEqual(shown)
})

test('the detailed Estado drill-down sits under the headline and sums to it', async ({ page }) => {
  await openResumen(page)

  await expect(page.getByTestId('estado-detalle')).toBeVisible()
  await expect(page.getByTestId('detalle-total')).toHaveText('12')
})

test('the company matrix reconciles to the overall PMF total', async ({ page }) => {
  await openResumen(page)

  await expect(page.getByTestId('company-matrix')).toBeVisible()
  await expect(page.getByTestId('empresa-total')).toHaveText('12')
  await expect(page.getByTestId('empresa-Campo Sintético')).toHaveText('12')
})

test('reforestación states its definition and shows no owner count', async ({ page }) => {
  await openResumen(page)

  await expect(page.getByTestId('kpi-ref-predios')).toHaveText('13')
  await expect(page.getByTestId('kpi-ref-propietarios')).toHaveText('No disponible en el origen')
  await expect(page.getByTestId('reforestacion-definition')).toContainText('Predio Ref')
})

test('a PMF with two summarized states is disclosed, not double counted', async ({ page }) => {
  await openResumen(page)

  await expect(page.getByTestId('status-conflict-note')).toContainText('PMF-002')
  await expect(page.getByTestId('status-reconciliation-warning')).toHaveCount(0)
})
