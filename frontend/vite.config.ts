import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

// The build is written into the Python package (interfaces/web/dist), which FastAPI serves. The proxy must set `changeOrigin: false`
// explicitly: Vite 8 otherwise rewrites Host to the target, and the backend's same-origin check
// (Origin netloc == Host) would reject every write from the dev server.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/',
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: { outDir: '../src/kinolog/interfaces/web/dist', emptyOutDir: true, assetsDir: 'assets' },
  server: {
    host: '127.0.0.1',
    proxy: { '/api': { target: 'http://127.0.0.1:8765', changeOrigin: false } },
  },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test-setup.ts'] },
})
