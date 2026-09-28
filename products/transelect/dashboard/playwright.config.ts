import { defineConfig, devices } from '@playwright/test'

const PORT = Number(process.env.TRANSELEC_E2E_PORT ?? 5299)
const BASE_URL = `http://127.0.0.1:${PORT}`

/**
 * Acceptance tests drive the real application in a real browser. Platform API
 * responses are stubbed per test (see tests/e2e/stubs.ts) so the suite is
 * hermetic and deterministic — it needs no database, no session and no
 * published import — while every rendering, filtering, pagination, print and
 * responsive behaviour under test is the application's own.
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'line' : 'list',
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: `npx vite --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `${BASE_URL}/transelec`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})
