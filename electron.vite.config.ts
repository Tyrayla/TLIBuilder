import { resolve } from 'path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'

// Per-worktree dev slot (scripts/dev-slot.mjs): pin the renderer dev server to the slot's port and
// fail loudly if it's taken, instead of silently drifting onto another worktree's port. Unset → the
// normal `npm run dev` behavior.
const slotVitePort = Number(process.env.TLI_DEV_VITE_PORT) || undefined

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()]
  },
  preload: {
    plugins: [externalizeDepsPlugin()]
  },
  renderer: {
    // public/ holds web-build-only assets (backend-py.zip, _headers) — without this the desktop
    // build copies them into out/renderer and they ride into app.asar for nothing.
    publicDir: false,
    ...(slotVitePort ? { server: { port: slotVitePort, strictPort: true } } : {}),
    resolve: {
      alias: {
        '@renderer': resolve('src/renderer/src')
      }
    },
    plugins: [react()]
  }
})
