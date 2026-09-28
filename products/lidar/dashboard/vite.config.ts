import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// LIDAR_API_PORT lets a local multi-product demo (see scripts/lidar_dev.py)
// point the viewer at a dynamically chosen API port. Manual development is
// unaffected: the default remains 127.0.0.1:8000.
const apiPort = process.env.LIDAR_API_PORT ?? '8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
