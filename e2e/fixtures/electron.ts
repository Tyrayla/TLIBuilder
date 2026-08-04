import { test as base, expect, _electron as electron } from '@playwright/test'
import type { ElectronApplication, Page } from '@playwright/test'
import { mkdtempSync, cpSync, rmSync, mkdirSync, existsSync } from 'fs'
import { tmpdir } from 'os'
import path from 'path'

const REPO_ROOT = path.resolve(__dirname, '..', '..')
// Dedicated port, far from 8765 (packaged) / 8766 (dev) — main kills whatever holds its port on
// startup, so pointing E2E at its own port is what keeps a test run from killing a live dev backend.
export const E2E_PYTHON_PORT = 8801

export interface E2eDirs {
  root: string
  userData: string
  dataDir: string
}

interface ElectronWorkerFixtures {
  // One seeded copy of data/ per worker; builds written by tests stay in the temp copy, never in
  // the repo's data/builds. Shared across the worker's launches, so state persists app-to-app —
  // which is what a future persistence-across-restart journey needs.
  e2eDirs: E2eDirs
}

interface ElectronTestFixtures {
  electronApp: ElectronApplication
  appWindow: Page
}

export async function launchApp(dirs: E2eDirs): Promise<ElectronApplication> {
  // The unpackaged main spawns venv/Scripts/python.exe — fail fast with a real message instead of
  // an opaque firstWindow()/readiness timeout when the venv isn't provisioned.
  const venvPython = path.join(REPO_ROOT, 'venv', 'Scripts', 'python.exe')
  if (!existsSync(venvPython)) {
    throw new Error(`E2E needs the backend venv: ${venvPython} not found — run python -m venv venv && venv\\Scripts\\pip install -r backend\\requirements.txt`)
  }
  const app = await electron.launch({
    args: [path.join(REPO_ROOT, 'out', 'main', 'index.js')],
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      TLI_E2E_USERDATA: dirs.userData,
      TLI_E2E_PYTHON_PORT: String(E2E_PYTHON_PORT),
      TLI_DATA_DIR: dirs.dataDir,
    },
  })
  // Block the live share service at the session level, for every window, as early as possible.
  await app.evaluate(({ session }) => {
    session.defaultSession.webRequest.onBeforeRequest(
      { urls: ['https://api.tlibuilder.com/*', 'http://api.tlibuilder.com/*'] },
      (_details, callback) => callback({ cancel: true }),
    )
  })
  return app
}

// The renderer boots into a "Starting backend…" state; ready means the preload bridge is up and
// the spawned Python answers through the real IPC proxy. NOTE: this must poll via evaluate —
// waitForFunction with an async predicate resolves on the pending (truthy) Promise, not its value.
export async function waitForBackendReady(window: Page): Promise<void> {
  await window.waitForFunction(() => 'api' in window, { timeout: 30_000 })
  await expect
    .poll(
      () =>
        window.evaluate(async () => {
          const api = (window as { api?: { apiRequest: (m: string, p: string) => Promise<{ ok: boolean }> } }).api
          try { return (await api!.apiRequest('GET', '/builds')).ok } catch { return false }
        }),
      { timeout: 60_000, intervals: [500] },
    )
    .toBe(true)
}

// Bypass the unsaved-changes close dialog (native, unreachable from Playwright) by destroying
// windows before close. The unsaved-guard journey exercises the renderer-side guard instead.
export async function closeApp(app: ElectronApplication): Promise<void> {
  await app.evaluate(({ BrowserWindow }) => {
    for (const w of BrowserWindow.getAllWindows()) w.destroy()
  })
  await app.close()
}

export const test = base.extend<ElectronTestFixtures, ElectronWorkerFixtures>({
  e2eDirs: [
    async ({}, use) => {
      const root = mkdtempSync(path.join(tmpdir(), 'tli-e2e-'))
      const userData = path.join(root, 'userData')
      const dataDir = path.join(root, 'data')
      mkdirSync(userData, { recursive: true })
      // Seed app-managed data but NOT the owner's saved builds/save.json — tests start empty.
      const src = path.join(REPO_ROOT, 'data')
      cpSync(src, dataDir, {
        recursive: true,
        filter: (p) => {
          const rel = path.relative(src, p)
          if (!rel || rel === 'builds') return true
          const top = rel.split(path.sep)[0]
          return top !== 'builds' && rel !== 'save.json'
        },
      })
      await use({ root, userData, dataDir })
      try { rmSync(root, { recursive: true, force: true }) } catch { /* temp dir; OS cleans up */ }
    },
    { scope: 'worker', timeout: 120_000 },
  ],
  electronApp: async ({ e2eDirs }, use) => {
    const app = await launchApp(e2eDirs)
    await use(app)
    await closeApp(app)
  },
  appWindow: async ({ electronApp }, use) => {
    const window = await electronApp.firstWindow()
    await waitForBackendReady(window)
    await use(window)
  },
})

export { expect }
