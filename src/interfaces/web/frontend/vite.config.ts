import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The FastAPI server serves the build from ../dist. No `changeOrigin` on the proxy: the
// backend's same-origin check compares Origin with Host, and both must stay 127.0.0.1:5173.
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: { outDir: '../dist', emptyOutDir: true, assetsDir: 'assets' },
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8765' } },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test-setup.ts'] },
})
