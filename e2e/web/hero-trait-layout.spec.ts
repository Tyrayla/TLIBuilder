import { test, expect } from '../fixtures/web'
import { ensureAtBuildSelect } from '../fixtures/mainSkillDps'

test.afterEach(async ({ webPage }) => {
  await ensureAtBuildSelect(webPage)
})

test('Youga 3 effects panel starts below the hero memory rail when expanded', async ({ webPage: page }) => {
  await ensureAtBuildSelect(page)
  await page.getByRole('button', { name: '+ New Build' }).click()
  await page.getByRole('button', { name: 'Hero Trait' }).click()

  await page.locator('.hero-trait-header .ht-dd-trigger').click()
  await page.getByRole('button', { name: /^The Ultimate One Youga 3/ }).click()

  const effects = page.locator('.hero-trait-alternate-effects')
  await expect(effects).toBeVisible()
  await effects.locator('summary').click({ position: { x: 16, y: 12 } })
  await expect(effects).toHaveAttribute('open', '')

  const memoryRail = page.locator('.htt-memory-rail')
  const railBox = await memoryRail.boundingBox()
  const effectsBox = await effects.boundingBox()
  expect(railBox).not.toBeNull()
  expect(effectsBox).not.toBeNull()
  expect(railBox!.y + railBox!.height).toBeLessThanOrEqual(effectsBox!.y)
})
