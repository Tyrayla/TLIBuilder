import { test, expect, webApi } from '../fixtures/web'
import type { Page } from '@playwright/test'

// Real click-driven user journeys (TEST_EXPANSION_PLAN Phase 3). Ground rule: assert structure
// and stability, never exact engine numbers. The __tliWebApi oracle is used for cleanup only.
//
// NOTE: a freshly-created build is already dirty ("Save *") before any user edit — the condition
// bootstrap bumps buildVersion past the loaded snapshot. Journeys therefore treat the unsaved
// guard as always armed on unsaved builds.

test.describe.configure({ mode: 'serial' })

// Sidebar save button reads "Save" when clean, "Save *" when dirty.
const SIDEBAR_SAVE = /^Save( \*)?$/

async function deleteBuildByName(page: Page, name: string): Promise<void> {
  const list = (await webApi(page, 'GET', '/api/builds')) as Array<{ id: string; name: string }>
  for (const b of list.filter((b) => b.name === name)) {
    await webApi(page, 'DELETE', `/api/builds/${b.id}`)
  }
}

// Journeys share one booted page across the whole worker — normalize to the build-select screen
// no matter what state an earlier spec left the page in.
async function ensureAtBuildSelect(page: Page): Promise<void> {
  const inBuild = await page.getByRole('button', { name: '← Back to Builds' }).isVisible().catch(() => false)
  if (inBuild) await backToBuilds(page)
  await expect(page.getByRole('button', { name: '+ New Build' })).toBeVisible()
}

// Navigate back to the build-select screen, discarding through the unsaved guard if it fires.
async function backToBuilds(page: Page): Promise<void> {
  await page.getByRole('button', { name: '← Back to Builds' }).click()
  const guardModal = page.locator('.modal-card', { hasText: 'Unsaved Changes' })
  const newBuild = page.getByRole('button', { name: '+ New Build' })
  await expect(guardModal.or(newBuild).first()).toBeVisible()
  if (await guardModal.isVisible()) await guardModal.getByRole('button', { name: 'Discard' }).click()
  await expect(newBuild).toBeVisible()
}

test('build-code round trip: create → save → export → reimport', async ({ webPage: page }) => {
  const NAME = 'E2E Round Trip'
  await ensureAtBuildSelect(page)

  // Create an empty build; we land on the Config (overview) screen with the sidebar up.
  await page.getByRole('button', { name: '+ New Build' }).click()
  await expect(page.getByRole('button', { name: '← Back to Builds' })).toBeVisible()

  // Save it (no buildId yet → the Save Build modal opens and asks for a name).
  await page.getByRole('button', { name: SIDEBAR_SAVE }).click()
  const saveModal = page.locator('.modal-card', { hasText: 'Save Build' })
  await saveModal.getByPlaceholder('Build name…').fill(NAME)
  await saveModal.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(saveModal).toBeHidden()
  await expect(page.locator('.build-sidebar')).toContainText(NAME)

  // Export: generate the tli1_ code.
  await page.getByRole('button', { name: 'Import / Export' }).click()
  await page.getByRole('button', { name: 'Generate Code' }).click()
  const codeArea = page.locator('textarea.share-code-area').first()
  await expect(codeArea).toBeVisible()
  const code = await codeArea.inputValue()
  expect(code).toMatch(/^tli1_/)

  // Back out, and the build shows on the select screen.
  await backToBuilds(page)
  await expect(page.locator('.build-card', { hasText: NAME })).toBeVisible()

  // Reimport through the Import Code modal — crosses the frozen codec + resolver + store.
  await page.getByRole('button', { name: 'Import Code' }).click()
  const importModal = page.locator('.modal-card', { hasText: 'Import Build Code' })
  await importModal.getByPlaceholder('Paste a tli1_… code or share link…').fill(code)
  await importModal.getByRole('button', { name: 'Import', exact: true }).click()
  // An empty build trips the compat warning ("no tree slots selected") — confirm through it.
  const importAnyway = importModal.getByRole('button', { name: 'Import Anyway' })
  const backBtn = page.getByRole('button', { name: '← Back to Builds' })
  await expect(importAnyway.or(backBtn).first()).toBeVisible()
  if (await importAnyway.isVisible()) await importAnyway.click()

  // The imported build opens as an unnamed copy — the tli1_ code carries build STATE, not the
  // name/id (by codec design), so the sidebar shows the "New Build" placeholder.
  await expect(backBtn).toBeVisible()
  await expect(page.locator('.build-sidebar')).toContainText('New Build')

  // Round-trip integrity: the reimported build exports to a code that DECODES to the same build.
  // (Byte-equality is deliberately not asserted — re-encoding materializes migration defaults.)
  await page.getByRole('button', { name: 'Import / Export' }).click()
  await page.getByRole('button', { name: 'Generate Code' }).click()
  await expect(page.locator('textarea.share-code-area').first()).toBeVisible()
  const code2 = await page.locator('textarea.share-code-area').first().inputValue()
  expect(code2).toMatch(/^tli1_/)
  const d1 = (await webApi(page, 'POST', '/api/build-code/decode', { code })) as { build: Record<string, unknown> }
  const d2 = (await webApi(page, 'POST', '/api/build-code/decode', { code: code2 })) as { build: Record<string, unknown> }
  for (const b of [d1.build, d2.build]) { delete b.name; delete b.id }
  expect(d2.build).toEqual(d1.build)

  // Cleanup: leave the imported build and delete the saved one.
  await backToBuilds(page)
  await deleteBuildByName(page, NAME)
})

test('unsaved-changes guard: cancel keeps editing, discard drops, save persists', async ({ webPage: page }) => {
  const NAME = 'E2E Guard Save'
  await ensureAtBuildSelect(page)
  // Count from the backend, not the DOM — the mounted list can be stale after API-level cleanup.
  const buildsBefore = ((await webApi(page, 'GET', '/api/builds')) as unknown[]).length

  // New build, then a real edit for good measure (typing into Notes).
  await page.getByRole('button', { name: '+ New Build' }).click()
  await page.getByRole('button', { name: 'Notes', exact: true }).click()
  await page.locator('[contenteditable="true"]').first().click()
  await page.keyboard.type('e2e guard note')
  await expect(page.getByRole('button', { name: 'Save *' })).toBeVisible()

  // Navigating back must raise the renderer's Unsaved Changes prompt.
  await page.getByRole('button', { name: '← Back to Builds' }).click()
  const guardModal = page.locator('.modal-card', { hasText: 'Unsaved Changes' })
  await expect(guardModal).toBeVisible()

  // Cancel: stay in the build, nothing lost.
  await guardModal.getByRole('button', { name: 'Cancel' }).click()
  await expect(guardModal).toBeHidden()
  await expect(page.getByRole('button', { name: '← Back to Builds' })).toBeVisible()

  // Discard: back to the select screen and the discarded build left nothing behind.
  await page.getByRole('button', { name: '← Back to Builds' }).click()
  await guardModal.getByRole('button', { name: 'Discard' }).click()
  await expect(page.getByRole('button', { name: '+ New Build' })).toBeVisible()
  await expect(page.locator('.build-card')).toHaveCount(buildsBefore)

  // Save path: same flow, but name it in the guard prompt and save.
  await page.getByRole('button', { name: '+ New Build' }).click()
  await page.getByRole('button', { name: 'Notes', exact: true }).click()
  await page.locator('[contenteditable="true"]').first().click()
  await page.keyboard.type('e2e guard note')
  await page.getByRole('button', { name: '← Back to Builds' }).click()
  await guardModal.getByPlaceholder('Build name…').fill(NAME)
  await guardModal.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.locator('.build-card', { hasText: NAME })).toBeVisible()

  await deleteBuildByName(page, NAME)
})
