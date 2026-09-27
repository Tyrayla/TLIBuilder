import { test, expect } from '../fixtures/web'
import { assignMainSkillAndReadDps, ensureAtBuildSelect, recordParitySample, MAIN_SKILL, DEFAULT_LEVEL } from '../fixtures/mainSkillDps'

// Promotes the app-harness journey (.agents/skills/app-harness/journeys/main-skill-dps.mjs) to a
// real Playwright spec on the web target. Ground rule: never assert an exact engine DPS number (a
// season change would break a literal pin) — assert a parsed, positive number, and that the slot
// reflects what was actually assigned. Also records this target's number so the electron spec (same
// invocation) can assert cross-target parity.

test('assigns a main skill and shows a non-zero Full DPS', async ({ webPage: page }, testInfo) => {
  const result = await assignMainSkillAndReadDps(page, testInfo)

  expect(result.skillName).toBe(MAIN_SKILL)
  expect(result.level).toBe(DEFAULT_LEVEL)
  expect(result.dps).toBeGreaterThan(0)

  recordParitySample(testInfo, 'web', result.dps)

  // Leave the scratch build cleanly (discard through the unsaved guard) so the next spec sharing
  // this worker's page starts from the build-select screen, same as journeys.spec.ts's specs do.
  await ensureAtBuildSelect(page)
})
