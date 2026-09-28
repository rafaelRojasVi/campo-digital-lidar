/**
 * TR-FUNC-017's own acceptance criterion, called out by the design doc as a
 * mandatory test: one filter change must move every figure together, from one
 * filter state.
 *
 * This is the automated equivalent of the cross-check the forensic audit had
 * to perform by hand across two separate HTML files. It fails if any section
 * keeps a stale value, reads a different filter state, or is served from a
 * response the others did not see.
 *
 * The rearchitecture made the property stronger rather than weaker. It used
 * to hold *within* one page, because one component fetched five endpoints
 * together. It now holds across the whole application, because every section
 * derives its filters from the URL: there is one filter state, and it is
 * visible in the address bar. So the test asserts both halves — the sections
 * agree with each other, and they agree with the URL and with the requests
 * the API actually received.
 */
import { expect, test } from '@playwright/test'
import { isFiltered, stubPlatform } from './stubs'

test('one filter change moves every section, and every endpoint sees the same state', async ({
  page,
}) => {
  // Record the filter state every read endpoint is called with, so the test
  // can prove they all saw the same one — not merely that they all changed.
  const seen: Record<string, string[]> = {}
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (!url.pathname.startsWith('/api/transelec/')) return
    // The Explorador also walks `/pmfs` unfiltered, once per active version,
    // to build the multi-select option lists — those lists must offer every
    // distinct value in the version, not only the values that survive the
    // current filter. That walk uses `limit=200`; it is deliberately not part
    // of the filtered view, so it is excluded here rather than counted as a
    // section disagreeing.
    if (url.searchParams.get('limit') === '200') return
    const endpoint = url.pathname.replace('/api/transelec/', '')
    seen[endpoint] = seen[endpoint] ?? []
    seen[endpoint].push(url.searchParams.getAll('q').join(','))
  })

  await stubPlatform(page)
  await page.goto('/transelec')
  await expect(page.getByTestId('kpi-row')).toBeVisible()

  // Unfiltered baseline, hand-computed in stubs.ts.
  await expect(page.getByTestId('kpi-pmf')).toHaveText('12')
  await expect(page.getByTestId('kpi-predios')).toHaveText('20')
  await expect(page.getByTestId('kpi-pmf-total')).toHaveText('12')
  await expect(page.getByTestId('status-aprobado')).toHaveText('6')
  await expect(page.getByTestId('composition-predios-total')).toHaveText(
    '10 de 20 predios aprobados',
  )
  await expect(page.getByTestId('status-hero-aprobado')).toHaveText('10')

  // ONE filter change, made in the one place the filter state lives.
  await page.goto('/transelec?q=rechaz')
  await expect(page.getByTestId('kpi-pmf')).toHaveText('4')

  // Every figure on the Resumen moves, and moves to the narrowed values.
  await expect(page.getByTestId('kpi-predios')).toHaveText('5')
  await expect(page.getByTestId('kpi-roles')).toHaveText('4')
  await expect(page.getByTestId('kpi-superficie')).toHaveText('12,25 ha')
  await expect(page.getByTestId('kpi-pmf-total')).toHaveText('4')
  await expect(page.getByTestId('status-aprobado')).toHaveText('3')
  await expect(page.getByTestId('composition-predios-total')).toHaveText('3 de 5 predios aprobados')
  await expect(page.getByTestId('status-hero-aprobado')).toHaveText('3')
  await expect(page.getByTestId('status-hero-en-tramite')).toHaveText('1')

  // The predio-grain segments still sum to the predio KPI: 5 predios.
  const heroTotal = await page.evaluate(() =>
    ['aprobado', 'en-tramite', 'pendiente', 'tachado']
      .map((key) => document.querySelector(`[data-testid="status-hero-${key}"]`))
      .filter((node): node is Element => node !== null)
      .reduce(
      (sum, node) => sum + Number(node.textContent),
      0,
    ),
  )
  expect(heroTotal).toBe(5)

  // The other three sections read the same state, carried in the URL.
  await page.getByRole('navigation', { name: 'Secciones de Transelec' })
    .getByRole('link', { name: 'Explorador' })
    .click()
  await expect(page).toHaveURL(/q=rechaz/)
  await expect(page.getByTestId('rows-total')).toContainText('8 áreas de corta')
  await expect(page.getByTestId('rows-body').locator('tr')).toHaveCount(8)

  await page.goto('/transelec/calidad?q=rechaz')
  await expect(page.getByTestId('owner-status')).toBeVisible()
  await expect(page.getByTestId('report-text')).toBeVisible()

  // And every endpoint was asked for the same filter state.
  for (const endpoint of ['summary', 'pending', 'owner-status', 'report', 'pmfs']) {
    const states = seen[endpoint] ?? []
    expect(states.length, `${endpoint} was never called`).toBeGreaterThan(0)
    expect(states[states.length - 1], `${endpoint} saw a different filter state`).toBe('rechaz')
  }
})

test('clearing the filter returns every section to the unfiltered view together', async ({
  page,
}) => {
  await stubPlatform(page)
  await page.goto('/transelec/explorador?q=rechaz')
  await expect(page.getByTestId('rows-total')).toContainText('8 áreas de corta')

  await page.getByRole('button', { name: 'Limpiar', exact: true }).click()

  await expect(page.getByTestId('rows-total')).toContainText('60 áreas de corta')
  await page.goto('/transelec')
  await expect(page.getByTestId('kpi-pmf')).toHaveText('12')
  await expect(page.getByTestId('kpi-pmf-total')).toHaveText('12')
  await expect(page.getByTestId('status-hero-aprobado')).toHaveText('10')
})

test('the URL and the API request carry the same parameters, so the guarantee is inspectable', async ({
  page,
}) => {
  await stubPlatform(page)
  const summaryUrls: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/transelec/summary')) summaryUrls.push(request.url())
  })

  await page.goto('/transelec?q=legal&sector=Norte&sector=Sur')
  await expect(page.getByTestId('kpi-pmf')).toHaveText('4')

  const requested = new URL(summaryUrls[summaryUrls.length - 1])
  expect(requested.searchParams.get('q')).toBe('legal')
  expect(requested.searchParams.getAll('sector')).toEqual(['Norte', 'Sur'])
})

test('the stub itself distinguishes filtered from unfiltered states', () => {
  // Guard against a vacuous consistency test: if this helper ever returned a
  // constant, the assertions above would pass without proving anything.
  expect(isFiltered(new URL('http://x/api/transelec/summary'))).toBe(false)
  expect(isFiltered(new URL('http://x/api/transelec/summary?q=rechaz'))).toBe(true)
  expect(isFiltered(new URL('http://x/api/transelec/summary?sector=Norte'))).toBe(true)
})
