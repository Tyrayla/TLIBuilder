// Interactive mobile preview: opens a visible, touch-emulated phone-sized browser window on the
// local dist-web build. Close the window (or kill the process) to end it.
// Run with the static server up: node e2e/serve-dist-web.mjs  →  node e2e/mobile-preview.mjs
import { chromium } from '@playwright/test'

const browser = await chromium.launch({ headless: false, args: ['--window-size=410,900'] })
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
})
const page = await context.newPage()
const PORT = Number(process.env.TLI_E2E_WEB_PORT || 8800)
await page.goto(`http://127.0.0.1:${PORT}/index.html`)
console.log('Mobile preview open — 390x844, touch emulation. Close the window to exit.')
await new Promise((resolve) => browser.on('disconnected', resolve))
