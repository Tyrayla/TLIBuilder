import { defineConfig } from '@playwright/test'
import { WEB_URL } from './fixtures/web'

// E2E harness — two targets, different jobs (docs/TEST_EXPANSION_PLAN.md Phase 3):
//   web      — dist-web served statically, same Python engine under Pyodide. CI-friendly (still
//              fetches catalogs from the live CDN — see the fixture note).
//   electron — the real desktop product via _electron.launch(): real preload/IPC/spawned backend.
// Both run with an isolated data dir / port so a run never touches real builds or a live dev backend.
// Scripts: npm run test:e2e / test:e2e:web / test:e2e:electron (each rebuilds its target first).
export default defineConfig({
  testDir: '.',
  // Pyodide worker boot alone is allowed up to 180s; journeys sharing the booted page are fast.
  timeout: 120_000,
  expect: { timeout: 15_000 },
  // One worker: the web target reuses a single booted Pyodide page; the electron target owns one
  // backend port. Parallel workers would fight over both.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  outputDir: 'test-results',
  reporter: [['list']],
  projects: [
    { name: 'web', testMatch: 'web/**/*.spec.ts' },
    { name: 'electron', testMatch: 'electron/**/*.spec.ts' },
  ],
  // webServer is config-global in Playwright, but only the web project needs it — electron-only
  // runs set PW_NO_WEBSERVER=1 (see test:e2e:electron) so they don't gate on dist-web existing.
  ...(process.env.PW_NO_WEBSERVER
    ? {}
    : {
        webServer: {
          command: 'node serve-dist-web.mjs',
          url: WEB_URL,
          reuseExistingServer: !process.env.CI,
          timeout: 30_000,
        },
      }),
})
