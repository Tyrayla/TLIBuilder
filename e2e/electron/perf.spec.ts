import { test, expect, waitForBackendReady } from '../fixtures/electron'

// Keep-alive render-overhead measurement (real desktop app).
//
// GOAL: quantify how much extra React render time the HIDDEN keep-alive screens add per edit, by
// comparing the `screens` <PerfProfiler> commit cost between two mount configs that differ ONLY in how
// many keep-alive screens are mounted:
//   Arm A — only the active editing screen (Gear) mounted        (== pre-keep-alive unmount behavior)
//   Arm B — all keep-alive screens mounted, Gear active, rest hidden
// Delta = the cost the hidden screens add per edit (frame budget 16.7ms).
//
// FIXME — two things block this from running today; both are scoped to the "expand E2E" effort:
//   1. Enable mechanism: PerfProfiler.PERF_ENABLED must be true before the bundle loads. The renderer's
//      reload path can't be relied on to re-enable (and this test must not need a temp force-on build);
//      the clean fix is main-process support for a `?perf=1` / env flag on the initial load.
//   2. Computing-build fixture: an empty build with no active season makes engineStats error, so
//      computedStats never updates and edits produce no re-renders to time. Needs a fixture that opens a
//      build with a season + a skill/gear so recompute actually completes.
// The A/B driver below (via App's window.__perf* hooks + window.__perf) is the intended shape once those land.

const KEEPALIVE = [
  'gear', 'skills', 'hero-traits', 'pact-spirits', 'slate-board', 'notes', 'import-export', 'build-overview',
]
const N = 30

test.fixme('keep-alive render overhead: only-active vs all-mounted', async ({ electronApp }) => {
  const win = await electronApp.firstWindow()
  await waitForBackendReady(win)

  // Open a fresh build via the stable landing-screen primary button, then wait for the drivers.
  await win.getByRole('button', { name: '+ New Build' }).click()
  await win.waitForFunction(() => window.__perfNav !== undefined, null, { timeout: 15_000 })

  // Fixed settle covers the 150ms recompute debounce + engine + render commit; the Profiler captures
  // that commit regardless. (Once the computing-build fixture lands, this can wait on computedVersion.)
  const settle = () => win.waitForTimeout(450)

  async function measure(n: number) {
    await settle()
    await win.evaluate(() => window.__perf!.reset())
    for (let i = 0; i < n; i++) {
      await win.evaluate(() => window.__perfEdit!())
      await settle()
    }
    return win.evaluate(() => window.__perf!.stats('screens'))
  }

  // Arm A — only Gear mounted.
  await win.evaluate(() => window.__perfNav!('gear'))
  await settle()
  const armA = await measure(N)

  // Visit every keep-alive screen (mounting them), then return to Gear.
  for (const s of KEEPALIVE) {
    await win.evaluate((sc) => window.__perfNav!(sc), s)
    await win.waitForTimeout(120)
  }
  await win.evaluate(() => window.__perfNav!('gear'))
  await settle()
  const armB = await measure(N)

  const dMedian = armB.median - armA.median
  console.log('[perf] arm A (only gear):', JSON.stringify(armA))
  console.log('[perf] arm B (all mounted):', JSON.stringify(armB))
  console.log(`[perf] DELTA per edit — median ${dMedian.toFixed(2)}ms (frame budget 16.7ms)`)

  expect(armA.count).toBeGreaterThan(0)
  expect(armB.count).toBeGreaterThan(0)
  expect(dMedian).toBeLessThan(16.7)
})

// The renderer's PerfProfiler augments Window with these (src/renderer/src/components/PerfProfiler.tsx +
// App.tsx). The e2e project compiles under its own tsconfig, so mirror the shape for the browser callbacks.
declare global {
  interface Window {
    __perf?: {
      reset: () => void
      stats: (id?: string) => { count: number; mean: number; median: number; p95: number; max: number }
    }
    __perfNav?: (screen: string) => void
    __perfEdit?: () => void
    __perfBuildState?: () => { buildVersion: number; computedVersion: number; statsLoading: boolean }
  }
}
