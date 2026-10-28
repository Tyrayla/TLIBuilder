import { test, expect, webApi } from '../fixtures/web'

const SHARE_ID = 'local-share-perf-fixture'
const PREVIEW = {
  hero: 'Harness Hero', trait: 'Harness Trait', level: 90, main_skill: 'Harness Skill',
  max_life: 1000, max_mana: 500, max_energy_shield: 0, total_dps: 1234,
  fire_resist: 75, cold_resist: 75, lightning_resist: 75, erosion_resist: 0, movement_speed: 0,
}

test('share overview exposes Open early and the link reaches the usable editor', async ({ webPage }, testInfo) => {
  test.setTimeout(240_000)
  const encoded = await webApi(webPage, 'POST', '/api/build-code/encode', {
    build: {
      v: 2, name: 'Share performance fixture', characterLevel: 90, slots: [null, null, null, null],
      gear: [{
        item_id: 'share-fixture-gear', name: 'Share Fixture Gear', slot: 'weapon1', is_crafted: true,
        affixes: [{ raw_text: 'Adds 1 to 2 Fire Damage', expression: 'Adds 1 to 2 Fire Damage',
          modifier_id: null, condition: null, affix_kind: 'numeric', numeric_values: [] }],
      }],
      skills: [],
    },
  }) as { code?: string }
  expect(encoded.code?.startsWith('tli1_')).toBe(true)

  const viewContext = await webPage.context().browser()!.newContext()
  const viewPage = await viewContext.newPage()
  await viewPage.route(/api\.tlibuilder\.com/, route => route.abort())
  await viewPage.route(`https://api.tlibuilder.com/b/${SHARE_ID}/preview`, async route => {
    await new Promise(resolve => setTimeout(resolve, 1200))
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PREVIEW) })
  })
  await viewPage.route(`https://api.tlibuilder.com/b/${SHARE_ID}`, route =>
    route.fulfill({ status: 200, contentType: 'text/plain', body: encoded.code! }),
  )
  await viewPage.addInitScript(id => {
    if (location.pathname.endsWith('/view.html')) history.replaceState(null, '', `/b/${id}`)
  }, SHARE_ID)

  const overviewStart = Date.now()
  await viewPage.goto(new URL('/view.html', webPage.url()).href, { waitUntil: 'domcontentloaded' })
  try {
    const openLink = viewPage.getByRole('link', { name: 'Open in TLI Builder (Web)' })
    const visibleBeforePreview = await openLink.isVisible().catch(() => false)
    expect.soft(visibleBeforePreview, 'Open action should be visible while the optional preview is pending').toBe(true)
    await openLink.waitFor({ state: 'visible', timeout: 15_000 })
    console.log(`[share-perf] overview open visible after ${Date.now() - overviewStart} ms`)
    await viewPage.waitForFunction(() => {
      const host = window as Window & { __tliStartupMetrics?: Array<{ name: string }> }
      return host.__tliStartupMetrics?.some(metric => metric.name === 'share.preview-fetch')
    }, null, { timeout: 15_000 })
    const overviewMetrics = await viewPage.evaluate(() => {
      const host = window as Window & { __tliStartupMetrics?: Array<{ name: string; durationMs: number }> }
      return (host.__tliStartupMetrics ?? []).filter(metric => metric.name.startsWith('share.'))
    })
    expect(overviewMetrics.map(metric => metric.name)).toEqual(expect.arrayContaining([
      'share.code-fetch', 'share.code-decode', 'share.catalog-resolution',
      'share.overview-render-commit', 'share.preview-fetch',
    ]))
    console.log(`[share-perf] overview stages ${JSON.stringify(overviewMetrics)}`)

    const clickStart = Date.now()
    await openLink.click()
    await expect(viewPage.getByRole('button', { name: /Hero Memory Inventory/ })).toBeVisible({ timeout: 180_000 })
    expect(viewPage.url()).not.toContain('share=')
    const importMetrics = await viewPage.evaluate(() => {
      const host = window as Window & { __tliStartupMetrics?: Array<{ name: string; durationMs: number }> }
      return host.__tliStartupMetrics ?? []
    })
    const measuredStages = importMetrics.filter(metric => metric.name.startsWith('share.'))
    const workerStages = importMetrics.filter(metric => metric.name.startsWith('worker.'))
    expect(measuredStages.map(metric => metric.name)).toEqual(expect.arrayContaining([
      'share.import-fetch', 'share.import-decode', 'share.open-build', 'share.editor-render-commit',
    ]))
    expect(measuredStages.find(metric => metric.name === 'share.import-decode')!.durationMs).toBeLessThan(1_000)
    expect(measuredStages.map(metric => metric.name)).toContain('share.session-draft-persist')
    console.log(`[share-perf] import stages ${JSON.stringify(measuredStages)}`)
    console.log(`[share-perf] worker stages ${JSON.stringify(workerStages)}`)
    console.log(`[share-perf] click to usable editor ${Date.now() - clickStart} ms`)
    await viewPage.screenshot({ path: testInfo.outputPath('share-editor.png') })
    await viewPage.reload({ waitUntil: 'domcontentloaded' })
    await expect(viewPage.getByRole('button', { name: /Hero Memory Inventory/ })).toBeVisible({ timeout: 30_000 })
    expect(viewPage.url()).not.toContain('share=')
    await viewPage.getByRole('button', { name: 'Gear', exact: true }).click()
    await expect(viewPage.getByRole('button', { name: 'Share Fixture Gear', exact: true }).first()).toBeVisible({ timeout: 30_000 })
  } finally {
    await viewContext.close()
  }
})

test('failed share imports show an error, keep the ID, and retry into the editor', async ({ webPage }) => {
  test.setTimeout(240_000)
  const encoded = await webApi(webPage, 'POST', '/api/build-code/encode', {
    build: { v: 2, name: 'Retry share fixture', characterLevel: 90, slots: [null, null, null, null], gear: [], skills: [] },
  }) as { code?: string }
  expect(encoded.code?.startsWith('tli1_')).toBe(true)

  const viewContext = await webPage.context().browser()!.newContext()
  const viewPage = await viewContext.newPage()
  let requests = 0
  await viewPage.route(/api\.tlibuilder\.com/, route => route.abort())
  await viewPage.route(`https://api.tlibuilder.com/b/${SHARE_ID}`, route => {
    requests += 1
    return requests === 1
      ? route.fulfill({ status: 503, contentType: 'text/plain', body: 'Temporary share read failure' })
      : route.fulfill({ status: 200, contentType: 'text/plain', body: encoded.code! })
  })

  try {
    await viewPage.goto(`${new URL('/', webPage.url()).href}?share=${SHARE_ID}`, { waitUntil: 'domcontentloaded' })
    await expect(viewPage.getByRole('alert')).toContainText('could not be loaded (503)', { timeout: 30_000 })
    expect(viewPage.url()).toContain(`share=${SHARE_ID}`)
    await viewPage.getByRole('button', { name: 'Retry import' }).click()
    await expect(viewPage.getByRole('button', { name: /Hero Memory Inventory/ })).toBeVisible({ timeout: 180_000 })
    expect(requests).toBe(2)
    expect(viewPage.url()).not.toContain('share=')
  } finally {
    await viewContext.close()
  }
})
