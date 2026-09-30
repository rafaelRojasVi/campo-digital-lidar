import { defineConfig, type Connect, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// The Forestry read API already serves under the `/api/forestry` prefix, so
// the proxy forwards `/api` unrewritten. FORESTRY_API_PORT lets the local
// launcher point the proxy at a dynamically chosen backend port.
const apiPort = Number(process.env.FORESTRY_API_PORT ?? 8000)

// With base '/rodales/', Vite's own servers answer 404 for the bare
// '/rodales'. Production is served by the API, which accepts both
// (app.dashboard_static); this keeps dev and preview the same.
const BARE_BASE = /^\/rodales(\?|$)/

const acceptBareBase: Connect.NextHandleFunction = (req, _res, next) => {
  if (req.url !== undefined && BARE_BASE.test(req.url)) {
    req.url = req.url.replace('/rodales', '/rodales/')
  }
  next()
}

function bareBasePlugin(): Plugin {
  return {
    name: 'rodales-bare-base',
    configureServer(server) {
      server.middlewares.use(acceptBareBase)
    },
    configurePreviewServer(server) {
      server.middlewares.use(acceptBareBase)
    },
  }
}

export default defineConfig({
  // Served under /rodales/ on the unified platform, next to the Campo
  // Digital front door at / (docs/superpowers/specs/2026-09-28-unified-platform-design.md).
  base: '/rodales/',
  plugins: [react(), bareBasePlugin()],
  build: {
    // Never inline small assets (Leaflet's control icons) as data: URIs:
    // the production CSP allows images from 'self' and the tile origins only.
    assetsInlineLimit: 0,
  },
  server: {
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
})
