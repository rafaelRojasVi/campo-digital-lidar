import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const port = Number(process.env.PORTAL_PORT ?? 5100)

const platformApiPort = Number(process.env.CAMPO_PLATFORM_API_PORT ?? 8000)

export default defineConfig({
  plugins: [react()],
  server: {
    port,
    strictPort: false,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${platformApiPort}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // Front door preview (VITE_CAMPO_ENV=production): the Transelec card
      // opens the build the API serves under /transelec/, on this origin.
      '/transelec': {
        target: `http://127.0.0.1:${platformApiPort}`,
        changeOrigin: true,
      },
    },
  },
  preview: {
    port,
    strictPort: false,
  },
})
