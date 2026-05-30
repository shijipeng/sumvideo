import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const { dev } = JSON.parse(
  readFileSync(join(root, 'config/environments.json'), 'utf8'),
)

export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  define: {
    __SUMVIDEO_DEV_BACKEND_URL__: JSON.stringify(dev.backend.url),
    __SUMVIDEO_DEV_FRONTEND_URL__: JSON.stringify(dev.frontend.url),
  },
  server: {
    host: dev.frontend.host,
    port: dev.frontend.port,
    proxy: {
      '/api': {
        target: dev.backend.url,
        changeOrigin: true,
        timeout: 0,
      },
    },
  },
})
