import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Playwright specs live under tests/e2e and are driven by
    // `npm run test:e2e`, never by vitest. tests/bundle is the exception in
    // the other direction: it is a vitest suite that lives outside src/
    // because it uses Node APIs, which tsconfig.app.json's vite/client-only
    // types (correctly) do not provide to application code.
    include: ['src/**/*.test.{ts,tsx}', 'tests/bundle/*.test.ts'],
  },
})
