/**
 * TR-FUNC-038 / 044 / 045 — print stylesheet, responsive behaviour, keyboard
 * access and reduced motion.
 *
 * The design doc calls print and responsive mandatory rather than optional:
 * printing is a function Javier uses today, and the breakpoints plus a real
 * 390px phone viewport are confirmed requirements.
 *
 * The print assertions run on the Explorador, because that is where the
 * chrome they check (the filter panel, the presets, the notice, the
 * pagination) and the dataset worth printing now live. What is asserted is
 * unchanged: the chrome disappears and every table is un-clipped.
 */
import { expect, test } from '@playwright/test'
import { stubPlatform } from './stubs'

test.beforeEach(async ({ page }) => {
  await stubPlatform(page)
})

test('TR-FUNC-038/045: print emulation hides the chrome and un-clips every table', async ({
  page,
}) => {
  await page.goto('/transelec/explorador')
  await expect(page.getByTestId('rows-body')).toBeVisible()
  await page.getByRole('button', { name: /^Filtros/ }).click()

  // Everything is visible on screen first, so the assertions below prove the
  // print stylesheet did the hiding rather than the elements being absent.
  await expect(page.locator('.topbar')).toBeVisible()
  await expect(page.locator('.filters')).toBeVisible()
  await expect(page.locator('.questions')).toBeVisible()
  await expect(page.getByTestId('notice-banner')).toBeVisible()

  await page.emulateMedia({ media: 'print' })

  const state = await page.evaluate(() => {
    const display = (selector: string) => {
      const element = document.querySelector(selector)
      return element ? getComputedStyle(element).display : 'missing'
    }
    const wraps = [...document.querySelectorAll('.tablewrap')].map((node) => {
      const style = getComputedStyle(node)
      return { overflow: style.overflow, maxHeight: style.maxHeight }
    })
    const stickyHeaders = [...document.querySelectorAll('th')].map(
      (node) => getComputedStyle(node).position,
    )
    return {
      topbar: display('.topbar'),
      filters: display('.filters'),
      faq: display('.questions'),
      notice: display('.notice'),
      buttons: display('.btns'),
      pagination: display('.pagination'),
      wraps,
      stickyHeaders: [...new Set(stickyHeaders)],
    }
  })

  expect(state.topbar).toBe('none')
  expect(state.filters).toBe('none')
  expect(state.faq).toBe('none')
  expect(state.notice).toBe('none')
  expect(state.buttons).toBe('none')
  expect(state.pagination).toBe('none')
  // Tables are un-clipped: no scroll container, no max-height cut-off.
  expect(state.wraps.length).toBeGreaterThan(0)
  for (const wrap of state.wraps) {
    expect(wrap.overflow).toBe('visible')
    expect(wrap.maxHeight).toBe('none')
  }
  // A sticky header renders as a floating band on paper.
  expect(state.stickyHeaders).toEqual(['static'])

  // The content itself survives printing.
  await expect(page.getByTestId('rows-body')).toBeVisible()
})

test('TR-FUNC-038/045: the Resumen prints its figures without its shortcut chrome', async ({
  page,
}) => {
  await page.goto('/transelec')
  await expect(page.getByTestId('kpi-row')).toBeVisible()

  await page.emulateMedia({ media: 'print' })

  const state = await page.evaluate(() => ({
    topbar: getComputedStyle(document.querySelector('.topbar')!).display,
    grid: document.querySelector('.grid')
      ? getComputedStyle(document.querySelector('.grid')!).display
      : 'absent',
  }))
  expect(state.topbar).toBe('none')

  await expect(page.getByTestId('kpi-row')).toBeVisible()
  await expect(page.getByTestId('status-pmf')).toBeVisible()
  await expect(page.getByTestId('status-cards')).toBeVisible()
  await expect(page.getByTestId('work-queue')).toBeVisible()
})

for (const [label, width, height] of [
  ['desktop', 1440, 900],
  ['laptop', 1280, 800],
  ['tablet', 768, 1024],
  ['390px phone', 390, 844],
] as const) {
  for (const [section, path, marker] of [
    ['resumen', '/transelec', 'kpi-row'],
    ['explorador', '/transelec/explorador', 'rows-body'],
    ['pendientes', '/transelec/pendientes', 'pending-zone'],
    ['calidad', '/transelec/calidad', 'quality-panel'],
    ['datos', '/transelec/datos', 'upload-submit'],
  ] as const) {
    test(`TR-FUNC-044: ${section} at ${label} has no horizontal page scroll and no console errors`, async ({
      page,
    }) => {
      const problems: string[] = []
      page.on('console', (message) => {
        if (message.type() === 'error') problems.push(message.text())
      })
      page.on('pageerror', (error) => problems.push(error.message))

      await page.setViewportSize({ width, height })
      await page.goto(path)
      await expect(page.getByTestId(marker)).toBeVisible()

      const overflow = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }))
      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth)

      expect(problems).toEqual([])
    })
  }
}

test('TR-FUNC-044: the shell navigation collapses to a disclosure at phone width', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/transelec')
  await expect(page.getByTestId('kpi-row')).toBeVisible()

  const toggle = page.getByRole('button', { name: 'Secciones' })
  await expect(toggle).toBeVisible()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(
    page.getByRole('navigation', { name: 'Secciones de Transelec' }),
  ).toBeHidden()

  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  const menu = page.getByRole('navigation', { name: 'Secciones de Transelec' })
  await expect(menu).toBeVisible()

  // Choosing a section navigates and closes the menu behind the reader.
  await menu.getByRole('link', { name: 'Pendientes' }).click()
  await expect(page.getByTestId('pending-zone')).toBeVisible()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
})

test('TR-FUNC-044: the Explorador stays usable at phone width', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/transelec/explorador')
  await expect(page.getByTestId('rows-body')).toBeVisible()

  await page.getByLabel('Búsqueda general').fill('rechaz')
  await expect(page.getByTestId('rows-total')).toContainText('8 áreas de corta')

  await page.getByRole('button', { name: /^Filtros/ }).click()
  await page.getByRole('button', { name: 'Sector', exact: true }).click()
  await expect(page.getByLabel('Norte')).toBeVisible()
})

test('TR-FUNC-044: the row drawer becomes a bottom sheet at phone width', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/transelec/explorador')
  await expect(page.getByTestId('rows-body')).toBeVisible()

  await page.getByTestId('row-1').click()
  const drawer = page.getByTestId('row-drawer')
  await expect(drawer).toBeVisible()

  const box = await drawer.boundingBox()
  expect(box!.width).toBeLessThanOrEqual(390)
  // Anchored to the bottom of the viewport rather than to the right edge.
  expect(box!.y + box!.height).toBeGreaterThan(700)
})

test('keyboard focus reaches the navigation, the search and the primary actions in order', async ({
  page,
}) => {
  // Arrive already filtered, so `Limpiar` is enabled and therefore in the
  // tab order — a disabled control is correctly unreachable.
  await page.goto('/transelec/explorador?q=rechaz')
  await expect(page.getByTestId('rows-body')).toBeVisible()

  const order: string[] = []
  for (let step = 0; step < 12; step += 1) {
    await page.keyboard.press('Tab')
    order.push(
      await page.evaluate(() => {
        const element = document.activeElement
        if (!element) return 'none'
        const label =
          element.getAttribute('aria-label') ??
          element.getAttribute('placeholder') ??
          element.textContent ??
          ''
        return `${element.tagName}:${label.trim().slice(0, 24)}`
      }),
    )
  }

  // The skip link is first, which is what makes the rest of this order
  // skippable for anyone who does not want to tab through the shell.
  expect(order[0]).toContain('Saltar al contenido')
  expect(order.some((entry) => entry.includes('Resumen'))).toBe(true)
  expect(order.some((entry) => entry.startsWith('INPUT'))).toBe(true)
  expect(order).toContain('BUTTON:Limpiar')
})

test('every interactive element shows a visible focus ring', async ({ page }) => {
  await page.goto('/transelec/explorador')
  await expect(page.getByTestId('rows-body')).toBeVisible()

  const outlines = await page.evaluate(() => {
    const results: string[] = []
    for (const selector of [
      '.filter-toggle',
      '.btn.alt:not([disabled])',
      'input[type="search"]',
      '.topnav a',
    ]) {
      const element = document.querySelector<HTMLElement>(selector)
      if (!element) continue
      element.focus()
      const style = getComputedStyle(element)
      results.push(`${selector}:${style.outlineStyle}:${style.outlineWidth}`)
    }
    return results
  })

  expect(outlines.length).toBeGreaterThan(0)
  for (const entry of outlines) {
    expect(entry, `no focus ring on ${entry}`).not.toContain(':none:')
  }
})

test('reduced motion removes every transition without removing any content', async ({
  browser,
}) => {
  const context = await browser.newContext({ reducedMotion: 'reduce' })
  const page = await context.newPage()
  await stubPlatform(page)

  await page.goto('/transelec/explorador')
  await expect(page.getByTestId('rows-body')).toBeVisible()

  // The drawer still opens, still shows its content, and still closes; it
  // simply does not animate.
  await page.getByTestId('row-1').click()
  await expect(page.getByTestId('row-drawer')).toBeVisible()

  const durations = await page.evaluate(() => {
    const nodes = ['.drawer', '.composition-seg', '.btn', '.disclosure-panel']
      .map((selector) => document.querySelector(selector))
      .filter((node): node is Element => node !== null)
    return nodes.map((node) => {
      const style = getComputedStyle(node)
      return `${style.transitionDuration}|${style.animationDuration}`
    })
  })

  expect(durations.length).toBeGreaterThan(0)
  for (const entry of durations) {
    for (const value of entry.split('|')[0].split(', ')) {
      expect(Number.parseFloat(value)).toBeLessThanOrEqual(0.01)
    }
  }

  await page.keyboard.press('Escape')
  await expect(page.getByTestId('row-drawer')).toBeHidden()
  await context.close()
})
