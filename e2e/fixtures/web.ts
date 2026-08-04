import { test as base, chromium, expect } from '@playwright/test'
import type { Browser, Page } from '@playwright/test'

// Single source of truth for the static server's port — playwright.config.ts and
// serve-dist-web.mjs (via TLI_E2E_WEB_PORT, which the config's webServer inherits) both use it.
export const WEB_PORT = Number(process.env.TLI_E2E_WEB_PORT || 8800)
export const WEB_URL = `http://127.0.0.1:${WEB_PORT}/index.html`

// Diagnostic globals exposed by src/renderer/src/web/pyodideCompute.ts. Used as readiness
// probes and state oracles only — assertions in journeys go through the real UI.
export interface TliWindow {
  __tliComputeReady?: boolean
  __tliComputeError?: string
  __tliWebApi?: (method: string, path: string, body?: unknown) => Promise<unknown>
}

interface WebWorkerFixtures {
  webBrowser: Browser
  // One page per worker: Pyodide boot costs up to ~3 minutes, so every spec in a worker
  // shares the booted page instead of paying that per test (TEST_EXPANSION_PLAN Phase 3, step 4).
  webPage: Page
}

// eslint-disable-next-line @typescript-eslint/no-empty-object-type -- {} is Playwright's "no test-scoped fixtures"
export const test = base.extend<{}, WebWorkerFixtures>({
  webBrowser: [
    async ({}, use) => {
      const browser = await chromium.launch()
      await use(browser)
      await browser.close()
    },
    { scope: 'worker' },
  ],
  webPage: [
    async ({ webBrowser }, use) => {
      const page = await webBrowser.newPage()
      // The share service is a live external API — no test may ever hit it. Only the share host is
      // blocked: the web build loads its catalogs + engine data from the live static CDN
      // (VITE_STATIC_DATA_BASE), so this target needs network. A local CDN mirror would make it
      // fully hermetic — tracked in docs/BACKLOG.md.
      await page.route(/api\.tlibuilder\.com/, (route) => route.abort())

      await page.goto(WEB_URL, { waitUntil: 'domcontentloaded', timeout: 60_000 })
      await page.waitForFunction(
        () => (document.getElementById('root')?.children.length || 0) > 0,
        { timeout: 30_000 },
      )
      await page.waitForFunction(
        () => {
          const w = window as TliWindow
          return w.__tliComputeReady === true || !!w.__tliComputeError
        },
        { timeout: 180_000 },
      )
      const computeError = await page.evaluate(() => (window as TliWindow).__tliComputeError || null)
      expect(computeError, 'Pyodide compute worker failed to boot').toBeNull()

      await use(page)
      await page.close()
    },
    { scope: 'worker', timeout: 240_000 },
  ],
})

export { expect }

// State oracle: call the in-browser backend directly (bypasses UI). Reads only in journeys.
export async function webApi(page: Page, method: string, path: string, body?: unknown): Promise<unknown> {
  return page.evaluate(
    ([m, p, b]) => (window as TliWindow).__tliWebApi!(m as string, p as string, b),
    [method, path, body],
  )
}
