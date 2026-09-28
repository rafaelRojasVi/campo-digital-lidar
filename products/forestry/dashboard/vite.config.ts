import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The Forestry read API already serves under the `/api/forestry` prefix, so
// the proxy forwards `/api` unrewritten. FORESTRY_API_PORT lets the local
// launcher point the proxy at a dynamically chosen backend port.
const apiPort = Number(process.env.FORESTRY_API_PORT ?? 8000)

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
})
