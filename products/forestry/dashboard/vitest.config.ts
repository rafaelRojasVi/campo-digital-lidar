import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // Globals let @testing-library/react register its afterEach cleanup.
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
