import { test, expect, E2E_PYTHON_PORT } from '../fixtures/electron'
import { readdirSync } from 'fs'
import path from 'path'

// The real desktop product: out/main/index.js under _electron.launch() — real preload, real IPC,
// real spawned Python backend, on an isolated port and an isolated copy of data/.

test('window opens and the spawned backend answers over IPC', async ({ electronApp, appWindow, e2eDirs }) => {
  await expect
    .poll(async () => appWindow.evaluate(() => (document.getElementById('root')?.children.length || 0)))
    .toBeGreaterThan(0)
  // appWindow fixture already waited for api-request GET /builds to succeed; assert the port too.
  const port = await appWindow.evaluate(() =>
    (window as { api?: { getPythonPort: () => Promise<number> } }).api!.getPythonPort(),
  )
  expect(port).toBe(E2E_PYTHON_PORT)
  // And that the userData redirect actually took — settings writes must land in the temp dir.
  const userDataPath = await electronApp.evaluate(({ app }) => app.getPath('userData'))
  expect(userDataPath).toBe(e2eDirs.userData)
})

test('backend runs on the isolated port with the isolated data dir', async ({ appWindow, e2eDirs }) => {
  // Straight to the spawned server from the test process — proves it is really listening there.
  const res = await fetch(`http://127.0.0.1:${E2E_PYTHON_PORT}/api/builds`)
  expect(res.ok).toBe(true)

  const buildsDir = path.join(e2eDirs.dataDir, 'builds')
  const before = new Set(readdirSync(buildsDir))
  const saved = await appWindow.evaluate(() =>
    (window as { api?: { apiRequest: (m: string, p: string, b?: unknown) => Promise<{ ok: boolean; data: unknown }> } })
      .api!.apiRequest('POST', '/builds', { name: 'E2E_ISOLATION', slots: [null, null, null, null] }),
  )
  expect(saved.ok).toBe(true)
  // The new build file must land in the temp copy of data/, not the repo's data/builds.
  const after = readdirSync(buildsDir).filter((f) => !before.has(f))
  expect(after.length).toBeGreaterThan(0)
})
