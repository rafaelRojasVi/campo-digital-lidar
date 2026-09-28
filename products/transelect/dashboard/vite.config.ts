import { defineConfig, type Connect, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// Same-origin-through-a-proxy convention as apps/portal and
// products/lidar/dashboard: the browser only ever calls /api/*, and the dev
// proxy (or the hosting rewrite in production) strips the /api prefix before
// forwarding to the platform API. There is no CORS surface and no API base
// URL compiled into the bundle.
const port = Number(process.env.TRANSELEC_DASHBOARD_PORT ?? 5200)
const platformApiPort = Number(process.env.CAMPO_PLATFORM_API_PORT ?? 8000)

// With base '/transelec/', Vite's own servers answer 404 for the bare
// '/transelec' (ROUTES.resumen). Production is served by the API, which
// accepts both (app.dashboard_static); this keeps dev and preview the same.
const BARE_BASE = /^\/transelec(\?|$)/

const acceptBareBase: Connect.NextHandleFunction = (req, _res, next) => {
  if (req.url !== undefined && BARE_BASE.test(req.url)) {
    req.url = req.url.replace('/transelec', '/transelec/')
  }
  next()
}

function bareBasePlugin(): Plugin {
  return {
    name: 'transelec-bare-base',
    configureServer(server) {
      server.middlewares.use(acceptBareBase)
    },
    configurePreviewServer(server) {
      server.middlewares.use(acceptBareBase)
    },
  }
}

export default defineConfig({
  // Served under /transelec/ on the unified platform, next to the Campo
  // Digital front door at / (docs/superpowers/specs/2026-09-28-unified-platform-design.md).
  base: '/transelec/',
  plugins: [react(), bareBasePlugin()],
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
