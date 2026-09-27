import { expect } from '@playwright/test'
import type { Page, TestInfo } from '@playwright/test'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import path from 'path'

// Shared by both e2e targets (web + electron, same renderer): assign a skill as Main Skill on a
// fresh build and read the result back through the real UI. This mirrors the agent-driven journey
// at .agents/skills/app-harness/journeys/main-skill-dps.mjs, but drives Playwright locators instead
// of the accessibility-snapshot harness, and is factored out so both projects share one assertion
// path plus the cross-target parity check below.
//
// Ground rule (owner, 2026-09-26): never assert a literal engine DPS number — a season change would
// break it, and no independent damage-math oracle is maintained here either. Every DPS assertion
// below is either "> 0" or "matches the other target's own number".

export const MAIN_SKILL = 'Chain Lightning'
// SkillsScreen.tsx's catalog-item click handler calls setPendingLevel(20) whenever the clicked item
// isn't already equipped in the focused slot — this is the renderer's own default, not an engine number.
export const DEFAULT_LEVEL = '20'

// Navigate to a guaranteed-empty build-select screen, discarding any unsaved build in the way.
// Electron's electronApp fixture is test-scoped (a fresh app per test), so this is normally a no-op
// there; web's page is worker-scoped and can carry state left by an earlier spec in the same worker
// (same normalization journeys.spec.ts uses).
export async function ensureAtBuildSelect(page: Page): Promise<void> {
  const newBuildBtn = page.getByRole('button', { name: '+ New Build' })
  // Inside a build the way out is "← Back to Builds"; the Reference & Verification screen uses "Main Menu".
  const exitBtn = page.getByRole('button', { name: /^(← Back to Builds|Main Menu)$/ })
  // Wait for the app to settle on SOME known screen first — a cold Electron start hasn't rendered
  // the build list yet, so a one-shot isVisible() (no wait) here would wrongly read "not on
  // build-select" and wait forever for an exit button that never appears (the cold-start race this
  // function was fixed for).
  await expect(newBuildBtn.or(exitBtn).first()).toBeVisible({ timeout: 60_000 })
  if (await newBuildBtn.isVisible()) return
  await exitBtn.click()
  const guardModal = page.locator('.modal-card', { hasText: 'Unsaved Changes' })
  await expect(guardModal.or(newBuildBtn).first()).toBeVisible()
  if (await guardModal.isVisible()) await guardModal.getByRole('button', { name: 'Discard' }).click()
  await expect(newBuildBtn).toBeVisible()
}

export interface MainSkillDpsResult {
  skillName: string
  level: string
  dpsText: string
  dps: number
}

// fmtDps (src/renderer/src/components/BuildSidebar.tsx) abbreviates above 100k with these suffixes.
// Parsed back out so a much larger future-season baseline still yields a comparable number without
// this file ever asserting what that baseline is.
const SUFFIX_MULT: Record<string, number> = { k: 1e3, M: 1e6, B: 1e9, T: 1e12, Q: 1e15 }

function parseDps(boxText: string): number {
  const m = boxText.match(/FULL DPS\s+([\d.,]+)([kMBTQ]?)/i)
  if (!m) return NaN
  return Number(m[1].replace(/,/g, '')) * (SUFFIX_MULT[m[2]] ?? 1)
}

// Create a fresh build, assign `skill` as the Main Skill through the real catalog UI (search →
// select → Assign), and read the sidebar's Full DPS box once the engine has actually produced a
// number. The box shows "…" (computing) or "—" (nothing to show) in between — `expect.poll` waits
// past both (BuildSidebar.tsx's DpsBox). `testInfo` is only used to attach failure diagnostics
// (screenshot + the box's own text) if the poll below times out — pass `test.info()` from the spec.
export async function assignMainSkillAndReadDps(page: Page, testInfo: TestInfo, skill = MAIN_SKILL): Promise<MainSkillDpsResult> {
  await ensureAtBuildSelect(page)
  await page.getByRole('button', { name: '+ New Build' }).click()
  await page.getByRole('button', { name: 'Skills' }).click()

  // The slot row is a div (not an ARIA button), so this is a class locator rather than getByRole —
  // matches how the app-harness journey has to fall back to a `generic "Main Skill` ref match.
  const mainSlot = page.locator('.skill-slot-row', { hasText: 'Main Skill' })
  await mainSlot.click()
  await page.getByPlaceholder('Search by name, tag, or effect…').fill(skill)
  await page.locator('.skill-catalog-item', { hasText: skill }).first().click()
  await page.getByRole('button', { name: `Assign ${skill} to Main Skill` }).click()

  // Assigning switches the center panel to the detail view (SkillsScreen's assignSkill): the level
  // spinbutton there reflects pendingLevel directly — renderer state, not gated on compute freshness
  // the way the slot row's "Lv.N …" badge is (skillLevelText, SkillsScreen.tsx) — that badge is
  // checked separately below, once compute is fresh.
  const levelInput = page.locator('.skill-level-input')
  await expect(levelInput).toHaveValue(DEFAULT_LEVEL)
  const level = await levelInput.inputValue()

  // The slot row in the left list should also now name the assigned skill.
  const slotName = mainSlot.locator('.skill-slot-skill-name-text')
  await expect(slotName).toHaveText(skill)
  const skillName = (await slotName.textContent())!.trim()

  const dpsBox = page.locator('.sidebar-dps-box')
  await expect(dpsBox).toBeVisible()
  try {
    await expect
      // 60s, not the original 20s: a cold Electron backend's FIRST compute (real spawned Python,
      // not the warm-worker web target) can be slow on a loaded machine — the test timeout is 120s,
      // so this still leaves headroom rather than masking a real hang.
      .poll(async () => parseDps((await dpsBox.innerText()).trim()), { timeout: 60_000, intervals: [250] })
      .toBeGreaterThan(0)
  } catch (e) {
    // expect.poll's own failure message doesn't include a snapshot of what was on screen — attach
    // one plus the box's raw text so a timeout here is diagnosable after the fact, not just "NaN".
    // Attach by `path` (a real file under testInfo.outputPath()), not `body`: a `body` attachment is
    // only ever persisted to disk if the configured reporter chooses to flush it (html/blob do; our
    // `list` reporter doesn't), so it would silently vanish here without landing in test-results/.
    const shotPath = testInfo.outputPath('dps-poll-timeout.png')
    await page.screenshot({ path: shotPath })
    await testInfo.attach('dps-poll-timeout.png', { path: shotPath, contentType: 'image/png' })

    const textPath = testInfo.outputPath('dps-box-text.txt')
    writeFileSync(textPath, await dpsBox.innerText().catch(() => '<box unreadable>'))
    await testInfo.attach('dps-box-text.txt', { path: textPath, contentType: 'text/plain' })
    throw e
  }

  // The slot row's own level badge (skillLevelText, SkillsScreen.tsx) is gated on compute freshness —
  // it shows "Lv.20 …" until the just-triggered recompute lands, then "Lv.20" or "Lv.20 (+N)"/"(-N)"
  // once a level bonus applies. The DPS poll above already waited for that recompute, so by now the
  // badge should have settled; anchor the regex so neither the stale "…" suffix nor a different level
  // (e.g. "Lv.200") can slip through, without hardcoding whether a bonus is present.
  const levelBadge = mainSlot.locator('.skill-slot-level-badge')
  await expect(levelBadge).toHaveText(new RegExp(`^Lv\\.${DEFAULT_LEVEL}(?: \\([+-]\\d+\\))?$`))

  const dpsText = (await dpsBox.innerText()).trim()
  return { skillName, level, dpsText, dps: parseDps(dpsText) }
}

// ---- cross-target parity file ------------------------------------------------------------------
// playwright.config.ts lists `web` before `electron` in `projects`, and neither project overrides
// `outputDir`, so both resolve to the exact same absolute folder (testInfo.project.outputDir).
// Playwright's runner clears every FILTERED project's outputDir once, in a single pass, before any
// project's tests start (node_modules/playwright/lib/runner/index.js's createRemoveOutputDirsTask
// unions project.outputDir across testRun.filteredProjects, then removes each folder once) — not
// per-project after each project finishes. So within one `playwright test` invocation that runs both
// projects, the web spec's file survives for the electron spec to read; an electron-only invocation
// never sees a stale file, because its own (shared) outputDir was wiped at the start of that run too.
function parityFile(testInfo: TestInfo): string {
  return path.join(testInfo.project.outputDir, 'main-skill-dps-parity.json')
}

export function recordParitySample(testInfo: TestInfo, target: 'web' | 'electron', dps: number): void {
  const file = parityFile(testInfo)
  mkdirSync(path.dirname(file), { recursive: true })
  writeFileSync(file, JSON.stringify({ target, dps }, null, 2))
}

export function readParitySample(testInfo: TestInfo): { target: string; dps: number } | null {
  const file = parityFile(testInfo)
  if (!existsSync(file)) return null
  try { return JSON.parse(readFileSync(file, 'utf8')) } catch { return null }
}
