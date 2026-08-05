// Mobile audit sweep: screenshot every screen at a phone viewport. Run with serve-dist-web running.
// Post-M0: navigation goes through the drawer (floating toggle opens it, nav click auto-closes it).
// Output dir via argv: node e2e/mobile-audit.mjs mobile-audit-after
import { chromium } from '@playwright/test'
import { mkdirSync } from 'fs'

const OUT = process.argv[2] || 'mobile-audit'
mkdirSync(`e2e/${OUT}`, { recursive: true })
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
await page.goto('http://127.0.0.1:8800/index.html', { waitUntil: 'domcontentloaded' })
await page.waitForFunction(() => window.__tliComputeReady === true || !!window.__tliComputeError, { timeout: 180000 })

const shot = (name) => page.screenshot({ path: `e2e/${OUT}/${name}.png` })
await shot('01-build-select')

await page.getByRole('button', { name: '+ New Build' }).click()
await page.waitForSelector('.sidebar-hero', { state: 'attached' })
await page.waitForTimeout(600)
await shot('02-config')

// One extra frame with the drawer open, to show the drawer itself.
const toggle = page.locator('.sidebar-mobile-toggle')
if (await toggle.isVisible()) {
  await toggle.click()
  await page.waitForTimeout(400)
  await shot('02b-drawer-open')
  await page.mouse.click(340, 420)   // tap the backdrop right of the 250px drawer
  await page.waitForTimeout(300)
}

const screens = [
  ['Calcs', '03-calcs'], ['Notes', '04-notes'], ['Talent Tree', '05-tree-selector'],
  ['Slates', '06-slates'], ['Gear', '07-gear'], ['Skills', '08-skills'],
  ['Hero Trait', '09-hero-trait'], ['Pact Spirits', '10-pact-spirits'], ['Import / Export', '11-import-export'],
]
for (const [label, name] of screens) {
  if (await toggle.isVisible()) { await toggle.click(); await page.waitForTimeout(350) }
  await page.getByRole('button', { name: label, exact: true }).click()
  await page.waitForTimeout(1200)
  await shot(name)
}
await browser.close()
console.log(`screenshots in e2e/${OUT}/`)
