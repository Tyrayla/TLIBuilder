import { test, expect, webApi } from '../fixtures/web'
import type { TliWindow } from '../fixtures/web'

// Promoted from spike/browser/smoke.mjs: the web build boots the real Python engine under Pyodide,
// serves catalogs, and persists builds across a full page reload (main-thread IndexedDB).
// __tliWebApi is the state oracle here; UI-driven journeys live in the journey specs.

test('app renders and the compute worker reaches ready', async ({ webPage }) => {
  // The worker fixture already gated on #root populating and __tliComputeReady — re-assert visibly.
  const state = await webPage.evaluate(() => {
    const w = window as TliWindow
    return { ready: w.__tliComputeReady === true, err: w.__tliComputeError || null }
  })
  expect(state.err).toBeNull()
  expect(state.ready).toBe(true)
})

test('a talent tree loads through the in-browser engine', async ({ webPage }) => {
  const tree = (await webApi(webPage, 'GET', '/api/tree/God of War')) as { nodes?: unknown[] }
  expect(Array.isArray(tree.nodes)).toBe(true)
  expect(tree.nodes!.length).toBeGreaterThan(0)
})

// The reload re-boots the Pyodide worker for the shared page; the test re-waits for readiness
// before finishing, so later specs in the worker still get a booted page.
test('a saved build survives a page reload', async ({ webPage }) => {
  const saved = (await webApi(webPage, 'POST', '/api/builds', {
    name: 'E2E_PERSIST',
    slots: [null, null, null, null],
  })) as { id?: string }
  expect(saved.id).toBeTruthy()

  await webPage.reload({ waitUntil: 'domcontentloaded', timeout: 60_000 })
  await webPage.waitForFunction(
    () => {
      const w = window as TliWindow
      return w.__tliComputeReady === true || !!w.__tliComputeError
    },
    { timeout: 180_000 },
  )

  const list = (await webApi(webPage, 'GET', '/api/builds')) as Array<{ id: string }>
  expect(list.some((b) => b.id === saved.id)).toBe(true)
  await webApi(webPage, 'DELETE', `/api/builds/${saved.id}`)
})
