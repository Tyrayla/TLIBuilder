import { test, expect } from '../fixtures/electron'
import { assignMainSkillAndReadDps, readParitySample, MAIN_SKILL, DEFAULT_LEVEL } from '../fixtures/mainSkillDps'

// Same journey as e2e/web/main-skill-dps.spec.ts, driven against the real desktop app (real
// preload/IPC/spawned backend). Adds the cross-target parity check: both targets run the SAME
// renderer, so a fresh build with the same Main Skill assigned must show the same Full DPS.

test('assigns a main skill and shows a non-zero Full DPS, matching web', async ({ appWindow }, testInfo) => {
  const result = await assignMainSkillAndReadDps(appWindow, testInfo)

  expect(result.skillName).toBe(MAIN_SKILL)
  expect(result.level).toBe(DEFAULT_LEVEL)
  expect(result.dps).toBeGreaterThan(0)

  const web = readParitySample(testInfo)
  if (!web) {
    // Standalone electron-only run (e.g. test:e2e:electron in isolation) — the web spec never ran in
    // this invocation, so there's nothing to compare against. Not a failure.
    testInfo.annotations.push({ type: 'parity skipped', description: 'web not run' })
    return
  }
  // Exact equality, not toBeCloseTo: both targets run the same Python engine source (native CPython
  // here, Pyodide/WASM on web), Chain Lightning's rate math rounds deterministically, and the sidebar
  // value is already string-formatted (fmtDps/dec) before either side parses it — so both sides
  // compare the same displayed value. Future float drift here would be a real parity bug, not noise.
  expect(result.dps).toBe(web.dps)
})
