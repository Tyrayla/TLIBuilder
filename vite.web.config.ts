import { resolve } from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Standalone web build of the renderer (no Electron) for Cloudflare Pages. Reuses src/renderer as-is; the app
// detects web at runtime (no window.api) and routes catalogs to the CDN + compute to the Pyodide worker.
// Build with:  npm run build:web   (loads .env.web for VITE_STATIC_DATA_BASE)
export default defineConfig({
  root: resolve(__dirname, 'src/renderer'),
  base: '/',
  envDir: __dirname, // load .env.web from the repo root
  publicDir: resolve(__dirname, 'src/renderer/public'), // serves backend-py.zip
  resolve: {
    alias: { '@renderer': resolve(__dirname, 'src/renderer/src') },
  },
  plugins: [react()],
  worker: { format: 'es' },
  build: {
    outDir: resolve(__dirname, 'dist-web'),
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, 'src/renderer/index.web.html'),
    },
  },
})
