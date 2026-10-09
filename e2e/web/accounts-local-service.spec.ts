import { test, expect, chromium } from '@playwright/test'
import type { Browser, BrowserContext, Page } from '@playwright/test'

// Real app + REAL account service, run locally. Skipped unless TLI_LOCAL_SERVICE is set.
//
// Needs: the service's dev server (tools/dev_server.py, with its stand-in Discord page) on
// http://localhost:8000, and the web build made with VITE_SHARE_BASE_URL=http://localhost:8000 and its CSP
// allowing that origin, served at http://localhost:5173 (TLI_E2E_WEB_HOST=localhost TLI_E2E_WEB_PORT=5173
// node e2e/serve-dist-web.mjs). The stand-in Discord replaces the real one: this proves the app against the
// service's own sessions, CSRF, cross-origin cookies, quotas, conditional writes, links, export and delete.
// It does NOT prove live Discord OAuth, production CORS/cookies, or safeStorage.

const SERVICE = process.env.TLI_LOCAL_SERVICE ?? ''
const APP = process.env.TLI_LOCAL_APP ?? 'http://localhost:5173'
const SIDEBAR_SAVE = /^Save( \*)?$/

test.skip(!SERVICE, 'set TLI_LOCAL_SERVICE=http://localhost:8000 to run against the local account service')
test.describe.configure({ mode: 'serial' })

const evidence = async (page: Page, name: string) => {
  const dir = process.env.TLI_EVIDENCE_DIR
  if (dir) await page.screenshot({ path: `${dir}/local-${name}.png` })
}

let browser: Browser
const username = `e2e_${Math.random().toString(36).slice(2, 8)}`
let publicName = ''
let handle = ''

async function openApp(context: BrowserContext): Promise<Page> {
  const page = await context.newPage()
  await page.goto(`${APP}/index.html`, { waitUntil: 'domcontentloaded' })
  await waitForEngine(page)
  return page
}

async function waitForEngine(page: Page): Promise<void> {
  await page.waitForFunction(() => (window as unknown as { __tliComputeReady?: boolean }).__tliComputeReady === true, undefined, { timeout: 240_000 })
  await expect(page.getByRole('button', { name: '+ New Build' })).toBeVisible({ timeout: 60_000 })
}

const profileCard = (page: Page) => page.getByRole('dialog').filter({ has: page.locator('#profile-dialog-title') })

async function openProfile(page: Page): Promise<void> {
  if (await profileCard(page).isVisible()) return
  const guest = page.getByRole('button', { name: /^(Sign in|Finish signup)$/ })
  if (await guest.isVisible()) await guest.click()
  else {
    await page.locator('.account-menu > button').click()
    await page.getByRole('menuitem', { name: 'Profile settings' }).click()
  }
  await expect(profileCard(page)).toBeVisible()
}

/** The stand-in Discord page: type a username and authorize. Lands back on the app. */
async function approveStandInDiscord(page: Page, name: string): Promise<void> {
  await page.waitForURL(/\/dev\/discord\/authorize/)
  await page.locator('input[name="username"]').fill(name)
  await page.getByRole('button', { name: 'Authorize' }).click()
  await page.waitForURL(`${APP}/**`)
  await waitForEngine(page)
}

async function signIn(page: Page, name: string): Promise<void> {
  await openProfile(page)
  await profileCard(page).getByRole('button', { name: 'Continue with Discord' }).click()
  await approveStandInDiscord(page, name)
}

async function createAndSaveBuild(page: Page, name: string): Promise<void> {
  await page.getByRole('button', { name: '+ New Build' }).click()
  await expect(page.getByRole('button', { name: '← Back to Builds' })).toBeVisible()
  await page.getByRole('button', { name: SIDEBAR_SAVE }).click()
  const saveModal = page.locator('.modal-card', { hasText: 'Save Build' })
  await saveModal.getByPlaceholder('Build name…').fill(name)
  await saveModal.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(saveModal).toBeHidden()
}

async function backToBuilds(page: Page): Promise<void> {
  await page.getByRole('button', { name: '← Back to Builds' }).click()
  const guard = page.locator('.modal-card', { hasText: 'Unsaved Changes' })
  const newBuild = page.getByRole('button', { name: '+ New Build' })
  await expect(guard.or(newBuild).first()).toBeVisible()
  if (await guard.isVisible()) await guard.getByRole('button', { name: 'Discard' }).click()
  await expect(newBuild).toBeVisible()
}

async function editNotesAndSave(page: Page, text: string): Promise<void> {
  await page.getByRole('button', { name: 'Notes', exact: true }).click()
  await page.locator('[contenteditable="true"]').first().click()
  await page.keyboard.type(text)
  await page.getByRole('button', { name: SIDEBAR_SAVE }).click()
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible()
}

test.beforeAll(async () => { browser = await chromium.launch() })
test.afterAll(async () => { await browser.close() })

const BUILD = `Local Svc ${username}`

test('sign in through the real service, create the account, upload, and link', async () => {
  test.setTimeout(480_000)
  const context = await browser.newContext()
  const page = await openApp(context)

  // Guest first: no cloud controls, nothing contacted.
  await expect(page.locator('.build-card-cloud')).toHaveCount(0)

  await signIn(page, username)
  await openProfile(page)
  await expect(profileCard(page)).toContainText('Choose your public name')
  await expect(profileCard(page)).toContainText('public')
  await evidence(page, '01-signup')
  await profileCard(page).getByRole('button', { name: 'Create account' }).click()
  await expect(profileCard(page)).toContainText(/#\d{4}/)
  const text = (await profileCard(page).textContent()) ?? ''
  // The suggested public name is the Discord username; the service assigns the four-digit tag.
  const match = new RegExp(`${username}#(\\d{4})`).exec(text)
  expect(match).not.toBeNull()
  publicName = `${username}#${match![1]}`
  handle = `${username.toLowerCase()}-${match![1]}`
  await evidence(page, '02-signed-in')
  await profileCard(page).getByRole('button', { name: 'Close' }).click()

  await createAndSaveBuild(page, BUILD)
  await backToBuilds(page)
  const card = page.locator('.build-card', { hasText: BUILD }).first()
  await expect(card.locator('.build-card-cloud')).toContainText('Not uploaded')
  await card.getByRole('button', { name: 'Upload to cloud' }).click()
  await expect(page.locator('.modal-card', { hasText: 'Uploaded' })).toBeVisible()
  await page.locator('.modal-card', { hasText: 'Uploaded' }).getByRole('button', { name: 'Close' }).click()
  await expect(card.locator('.build-card-cloud')).toContainText('Synced')

  // Reload: the session cookie carries across, the status survives, and the data stays.
  await page.reload({ waitUntil: 'domcontentloaded' })
  await waitForEngine(page)
  await expect(page.locator('.build-card', { hasText: BUILD }).first().locator('.build-card-cloud')).toContainText('Synced')

  // Named link, unlisted by default; then listed on the profile.
  await openProfile(page)
  await profileCard(page).getByRole('button', { name: 'Cloud library' }).click()
  const library = page.locator('.modal-card', { hasText: 'Cloud library' })
  await expect(library).toContainText('1 of 20')
  await library.getByLabel(`Link name for ${BUILD}`).fill('e2e-link')
  await library.getByRole('button', { name: 'Create link' }).click()
  await expect(library).toContainText(`/u/${handle}/e2e-link`)
  await expect(library).toContainText('Unlisted')
  await library.getByRole('button', { name: 'Show on profile' }).click()
  await expect(library).toContainText('Shown on profile')
  await evidence(page, '03-cloud-library-link')

  // The public read works with no credentials and is not indexed.
  const pub = await context.request.get(`${SERVICE}/u/${handle}/e2e-link`, { headers: {} })
  expect(pub.status()).toBe(200)
  expect(pub.headers()['x-robots-tag']).toContain('noindex')
  const pubBody = await pub.json()
  expect(pubBody.code).toMatch(/^tli1_/)
  expect(pubBody.owner.name.toLowerCase()).toBe(handle.split('-')[0])

  await library.getByRole('button', { name: 'Close' }).click()
  await context.close()
})

test('a second device: download, edit, upload, then a real conflict on the first device', async () => {
  test.setTimeout(480_000)
  // Device A: the build exists locally from the previous test only in that (closed) context, so recreate it by
  // signing in fresh and downloading from the cloud, as a real second device would.
  const ctxA = await browser.newContext()
  const a = await openApp(ctxA)
  await signIn(a, username)
  await openProfile(a)
  await profileCard(a).getByRole('button', { name: 'Cloud library' }).click()
  const libA = a.locator('.modal-card', { hasText: 'Cloud library' })
  await libA.getByRole('button', { name: 'Save to this device' }).click()
  await expect(libA).toContainText('Saved to this device.')
  await libA.getByRole('button', { name: 'Close' }).click()
  const cardA = () => a.locator('.build-card', { hasText: BUILD }).first()
  await expect(cardA().locator('.build-card-cloud')).toContainText('Synced')

  // Device B downloads the same build and uploads an edit.
  const ctxB = await browser.newContext()
  const b = await openApp(ctxB)
  await signIn(b, username)
  await openProfile(b)
  await profileCard(b).getByRole('button', { name: 'Cloud library' }).click()
  const libB = b.locator('.modal-card', { hasText: 'Cloud library' })
  await libB.getByRole('button', { name: 'Save to this device' }).click()
  await expect(libB).toContainText('Saved to this device.')
  await libB.getByRole('button', { name: 'Close' }).click()
  const cardB = () => b.locator('.build-card', { hasText: BUILD }).first()
  await cardB().click()
  await editNotesAndSave(b, 'edit from device B')
  await backToBuilds(b)
  await expect(cardB().locator('.build-card-cloud')).toContainText('Local changes')
  await cardB().getByRole('button', { name: 'Upload to cloud' }).click()
  await expect(b.locator('.modal-card', { hasText: 'Uploaded' })).toBeVisible()
  await b.locator('.modal-card', { hasText: 'Uploaded' }).getByRole('button', { name: 'Close' }).click()
  await expect(cardB().locator('.build-card-cloud')).toContainText('Synced')

  // Device A edits too, then reloads its library: Diverged. No prompt appeared on the way.
  await cardA().click()
  await editNotesAndSave(a, 'edit from device A')
  await backToBuilds(a)
  await expect(cardA().locator('.build-card-cloud')).toContainText('Diverged')
  await expect(a.locator('.modal-card', { hasText: 'changed in two places' })).toHaveCount(0)

  // Explicit upload opens the conflict screen; the service's conditional write protects the cloud copy.
  await cardA().getByRole('button', { name: 'Upload to cloud' }).click()
  const conflict = a.locator('.modal-card', { hasText: 'This build changed in two places' })
  await expect(conflict).toBeVisible()
  await expect(conflict.getByRole('button', { name: 'Keep both' })).toHaveClass(/btn-primary/)
  await evidence(a, '04-conflict')
  await conflict.getByRole('button', { name: 'Keep local' }).click()
  await expect(conflict).toContainText('replaces the cloud version')
  await conflict.getByRole('button', { name: 'Replace cloud version' }).click()
  await expect(a.locator('.modal-card', { hasText: 'Uploaded' })).toBeVisible()
  await a.locator('.modal-card', { hasText: 'Uploaded' }).getByRole('button', { name: 'Close' }).click()
  await expect(cardA().locator('.build-card-cloud')).toContainText('Synced')

  // Device B is now behind: it is told, and nothing was replaced silently.
  await b.reload({ waitUntil: 'domcontentloaded' })
  await waitForEngine(b)
  await expect(cardB().locator('.build-card-cloud')).toContainText('Newer version in cloud')
  await cardB().getByRole('button', { name: 'Download from cloud' }).click()
  await expect(b.locator('.modal-card', { hasText: 'Downloaded' })).toBeVisible()
  await b.locator('.modal-card', { hasText: 'Downloaded' }).getByRole('button', { name: 'Close' }).click()
  await expect(cardB().locator('.build-card-cloud')).toContainText('Synced')

  await ctxB.close()
  await ctxA.close()
})

test('export and delete need a fresh Discord confirmation, then work; a deleted account\'s link is removed', async () => {
  test.setTimeout(480_000)
  const ctx = await browser.newContext({ acceptDownloads: true })
  const page = await openApp(ctx)
  await signIn(page, username)
  // This browser is a fresh device: keep a local copy so we can prove deletion leaves local builds alone.
  await openProfile(page)
  await profileCard(page).getByRole('button', { name: 'Cloud library' }).click()
  const lib = page.locator('.modal-card', { hasText: 'Cloud library' })
  await lib.getByRole('button', { name: 'Save to this device' }).click()
  await expect(lib).toContainText('Saved to this device.')
  await lib.getByRole('button', { name: 'Close' }).click()
  await openProfile(page)

  // Export is refused until the user confirms with Discord again.
  await profileCard(page).getByRole('button', { name: 'Export my data' }).click()
  await expect(profileCard(page)).toContainText('confirm with Discord again')
  await evidence(page, '05-reauth-needed')
  await profileCard(page).getByRole('button', { name: 'Confirm with Discord' }).click()
  await approveStandInDiscord(page, username)
  expect(new URL(page.url()).searchParams.has('reauth')).toBe(false) // the app cleans the return parameter

  await openProfile(page)
  const downloadPromise = page.waitForEvent('download')
  await profileCard(page).getByRole('button', { name: 'Export my data' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('tli-builder-account-export.json')
  const stream = await download.createReadStream()
  const chunks: Buffer[] = []
  for await (const chunk of stream) chunks.push(chunk as Buffer)
  const exported = JSON.parse(Buffer.concat(chunks).toString('utf-8'))
  expect(JSON.stringify(exported)).toContain(BUILD)
  expect(JSON.stringify(exported)).not.toMatch(/session_token|token_hash/)

  // Delete: consequences first, typed confirmation, then it goes through (reauth is still fresh).
  await profileCard(page).getByRole('button', { name: 'Delete account' }).click()
  await expect(profileCard(page)).toContainText('6 months')
  const confirm = profileCard(page).getByRole('button', { name: 'Permanently delete' })
  await expect(confirm).toBeDisabled()
  await profileCard(page).getByLabel('Type DELETE to confirm').fill('DELETE')
  await evidence(page, '06-delete-confirm')
  await confirm.click()
  await expect(profileCard(page).getByRole('button', { name: 'Continue with Discord' })).toBeVisible()

  // The account's named link now answers "removed by its owner" and the slug cannot be claimed.
  const res = await ctx.request.get(`${SERVICE}/u/${handle}/e2e-link`)
  expect(res.status()).toBe(410)
  expect((await res.json()).error.code).toBe('removed_by_owner')

  // Importing that link in the app says so in plain words.
  await profileCard(page).getByRole('button', { name: 'Close' }).click()
  await page.getByRole('button', { name: 'Import Code' }).click()
  const importModal = page.locator('.modal-card').filter({ has: page.getByPlaceholder('Paste a tli1_… code or share link…') })
  await importModal.getByPlaceholder('Paste a tli1_… code or share link…').fill(`${SERVICE}/u/${handle}/e2e-link`)
  await importModal.getByRole('button', { name: 'Import', exact: true }).click()
  await expect(importModal).toContainText('This build was removed by its owner.')
  await evidence(page, '07-removed-link')

  // Local builds are untouched by account deletion.
  await importModal.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.locator('.build-card', { hasText: BUILD }).first()).toBeVisible()
  await ctx.close()
  void publicName
})
