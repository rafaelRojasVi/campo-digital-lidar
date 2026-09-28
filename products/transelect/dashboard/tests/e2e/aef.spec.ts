import { expect, test } from '@playwright/test'
import { stubPlatform } from './stubs'

test.beforeEach(async ({ page }) => {
  await stubPlatform(page)
})

test('the AEF section shows PMF values with their row and flags the inverted date', async ({
  page,
}) => {
  await page.goto('/transelec/seguimiento-aef')

  await expect(page.getByTestId('aef-kpis')).toBeVisible()
  await expect(page.getByText('Valores por PMF, con su fila de origen')).toBeVisible()
  const pmf = page.getByTestId('aef-pmf-PMF-002')
  await expect(pmf).toContainText('Presentado')
  await expect(pmf).toContainText('fila 2')
  await expect(pmf).toContainText('Fecha corta anterior a la solicitud')
  const row = page.getByTestId('aef-row-2')
  await expect(row).toContainText('Presentado')
  await expect(row).toContainText('19-08-2026')
  await expect(row).toContainText('Fecha corta anterior a la solicitud')
})

test('the explorer shows AEF per row and the drawer keeps blanks blank', async ({ page }) => {
  await page.goto('/transelec/explorador')

  await expect(page.getByTestId('row-2')).toContainText('Revisar fechas')
  await page.getByTestId('row-3').click()
  const aef = page.getByTestId('drawer-aef')
  await expect(aef).toContainText('Sin registro en esta fila')
})
