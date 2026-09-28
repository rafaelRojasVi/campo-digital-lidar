import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Same-origin-through-a-proxy convention as apps/portal and
// products/lidar/dashboard: the browser only ever calls /api/*, and the dev
// proxy (or the hosting rewrite in production) strips the /api prefix before
// forwarding to the platform API. There is no CORS surface and no API base
// URL compiled into the bundle.
const port = Number(process.env.TRANSELEC_DASHBOARD_PORT ?? 5200)
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
    },
  },
  preview: {
    port,
    strictPort: false,
  },
})
