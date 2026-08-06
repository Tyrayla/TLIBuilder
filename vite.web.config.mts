import { resolve } from 'path'
import { readFileSync, existsSync } from 'fs'
import { createHash } from 'crypto'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// App version baked in at build time so the web app can show it (desktop reads it via IPC; web has no IPC).
const pkgVersion = JSON.parse(readFileSync(resolve(__dirname, 'package.json'), 'utf-8')).version

// Content hash of backend-py.zip, baked in as a ?v= cache-buster (build:web runs export_backend_bundle first).
// The zip keeps a fixed filename in public/, so without this some browsers (Brave) served a stale copy to
// worker fetches after a deploy; the old workaround (cache:'reload') re-downloaded 600KB on every visit.
const zipPath = resolve(__dirname, 'src/renderer/public/backend-py.zip')
const zipHash = existsSync(zipPath)
  ? createHash('sha1').update(readFileSync(zipPath)).digest('hex').slice(0, 12)
  : 'dev'

// Standalone web build of the renderer (no Electron) for Cloudflare Pages. Reuses src/renderer as-is; the app
// detects web at runtime (no window.api) and routes catalogs to the CDN + compute to the Pyodide worker.
// Build with:  npm run build:web   (loads .env.web for VITE_STATIC_DATA_BASE)
export default defineConfig({
  root: resolve(__dirname, 'src/renderer'),
  base: '/',
  envDir: __dirname, // load .env.web from the repo root
  publicDir: resolve(__dirname, 'src/renderer/public'), // serves backend-py.zip
  define: {
    __APP_VERSION__: JSON.stringify(pkgVersion),
    __BACKEND_ZIP_VERSION__: JSON.stringify(zipHash),
  },
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
