import { test, expect, webApi, WEB_URL } from '../fixtures/web'
import { ensureAtBuildSelect } from '../fixtures/mainSkillDps'
import type { Page, Route } from '@playwright/test'

// Hosted-account journeys through the REAL web UI, with the hosted service replaced by an in-test mock
// that follows docs/HOSTED_ACCOUNT_API_CONTRACT.md. This proves the app's behavior (status indicators,
// explicit actions, conflict screen, no silent overwrite). It does NOT prove the live service, Discord
// OAuth, or cookie/CORS behavior against the real origin: the mock "sign-in" is a redirect that flips a
// flag. Anonymous composition reporting is disabled under Playwright by design (navigator.webdriver),
// so it is covered by unit tests instead.

test.describe.configure({ mode: 'serial' })

const API = /api\.tlibuilder\.com/
const NAME = 'E2E Cloud Build'
const SIDEBAR_SAVE = /^Save( \*)?$/

interface CloudRow { id: string; name: string; revisions: { id: string; code: string }[]; link: null | { slug: string; listed: boolean; revisionId: string } }

class MockService {
  signedIn = false
  rows = new Map<string, CloudRow>()
  private counter = 0
  readonly writes: string[] = []

  private cors(origin: string): Record<string, string> {
    return {
      'Access-Control-Allow-Origin': origin,
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'content-type, x-csrf-token',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    }
  }

  private summary(r: CloudRow) {
    const current = r.revisions[r.revisions.length - 1]
    return {
      cloud_build_id: r.id, name: r.name, current_revision_id: current.id, semantic_hash: `mock:${current.code}`,
      updated_at: 1_700_000_000 + this.counter, data_version: 'e2e',
      named_link: r.link ? { url_path: `/u/tyra-4472/${r.link.slug}`, slug: r.link.slug, listed: r.link.listed, revision_id: r.link.revisionId } : null,
    }
  }

  /** Another device uploads a new revision behind the app's back. */
  bumpCloud(id: string, code: string): void {
    const r = this.rows.get(id)!
    r.revisions.push({ id: `rev${++this.counter}`, code })
  }

  async handle(route: Route, origin: string): Promise<void> {
    const req = route.request()
    const url = new URL(req.url())
    const method = req.method()
    const headers = { ...this.cors(origin), 'Content-Type': 'application/json' }
    const json = (status: number, body: unknown) => route.fulfill({ status, headers, body: JSON.stringify(body) })
    const err = (status: number, code: string) => json(status, { error: { code, message: code } })

    if (method === 'OPTIONS') return route.fulfill({ status: 204, headers: this.cors(origin) })
    if (url.pathname === '/auth/discord/start') {
      this.signedIn = true
      return route.fulfill({ status: 302, headers: { Location: WEB_URL } })
    }
    if (url.pathname === '/v1/csrf') return json(200, { csrf_token: 'mock-csrf' })
    if (url.pathname === '/v1/account/signup') return err(404, 'not_found')
    if (!this.signedIn) return err(401, 'unauthenticated')
    if (method !== 'GET' && req.headers()['x-csrf-token'] !== 'mock-csrf') return err(403, 'csrf_failed')

    if (url.pathname === '/v1/account' && method === 'GET') {
      return json(200, {
        user_id: 'usr_e2e', public_name: { name: 'Tyra', tag: '4472' },
        limits: { cloud_builds: 20, profile_builds: 10 }, usage: { cloud_builds: this.rows.size, profile_builds: 0 },
      })
    }
    if (url.pathname === '/v1/account/signout') { this.signedIn = false; return json(200, {}) }
    if (url.pathname === '/v1/cloud/builds' && method === 'GET') return json(200, { builds: [...this.rows.values()].map((r) => this.summary(r)) })

    if (url.pathname === '/v1/cloud/builds' && method === 'POST') {
      const body = JSON.parse(req.postData() ?? '{}') as { name: string; code: string; allow_duplicate?: boolean }
      const match = [...this.rows.values()].find((r) => r.revisions[r.revisions.length - 1].code === body.code)
      if (match && !body.allow_duplicate) return json(200, { match: { cloud_build_id: match.id, name: match.name } })
      if (this.rows.size >= 20) return err(409, 'cloud_quota_reached')
      const row: CloudRow = { id: `cb${++this.counter}`, name: body.name, revisions: [{ id: `rev${++this.counter}`, code: body.code }], link: null }
      this.rows.set(row.id, row)
      this.writes.push(`create ${row.id}`)
      return json(201, { summary: this.summary(row) })
    }

    const one = /^\/v1\/cloud\/builds\/([^/]+)$/.exec(url.pathname)
    if (one) {
      const row = this.rows.get(decodeURIComponent(one[1]))
      if (!row) return err(404, 'not_found')
      if (method === 'GET') return json(200, { summary: this.summary(row), code: row.revisions[row.revisions.length - 1].code })
      if (method === 'PUT') {
        const body = JSON.parse(req.postData() ?? '{}') as { base_revision_id: string; code: string; name: string }
        const current = row.revisions[row.revisions.length - 1]
        if (current.id !== body.base_revision_id) {
          return json(409, { error: { code: 'stale_revision', message: 'stale', current_revision_id: current.id } })
        }
        if (current.code !== body.code) { row.revisions.push({ id: `rev${++this.counter}`, code: body.code }); row.name = body.name }
        this.writes.push(`put ${row.id}`)
        return json(200, { summary: this.summary(row) })
      }
      if (method === 'DELETE') { this.rows.delete(row.id); return json(200, {}) }
    }
    return err(404, 'not_found')
  }
}

async function install(page: Page): Promise<MockService> {
  const mock = new MockService()
  const origin = new URL(page.url()).origin
  // Registered after the fixture's catch-all abort, so it takes precedence for this host.
  await page.route(API, (route) => mock.handle(route, origin))
  return mock
}

const DIALOG = (title: string) => (page: Page) => page.locator('.modal-card', { hasText: title })

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
  const guardModal = page.locator('.modal-card', { hasText: 'Unsaved Changes' })
  const newBuild = page.getByRole('button', { name: '+ New Build' })
  await expect(guardModal.or(newBuild).first()).toBeVisible()
  if (await guardModal.isVisible()) await guardModal.getByRole('button', { name: 'Discard' }).click()
  await expect(newBuild).toBeVisible()
}

async function deleteAllByName(page: Page, name: string): Promise<void> {
  const list = (await webApi(page, 'GET', '/api/builds')) as Array<{ id: string; name: string }>
  for (const b of list.filter((x) => x.name === name || x.name.startsWith(name))) await webApi(page, 'DELETE', `/api/builds/${b.id}`)
}

async function waitForEngine(page: Page): Promise<void> {
  await page.waitForFunction(() => (window as unknown as { __tliComputeReady?: boolean }).__tliComputeReady === true, undefined, { timeout: 240_000 })
}

async function encodeBuild(page: Page, build: Record<string, unknown>): Promise<string> {
  const out = (await webApi(page, 'POST', '/api/build-code/encode', { build })) as { code: string }
  return out.code
}

// Set TLI_EVIDENCE_DIR to save screenshots of the key states.
async function shot(page: Page, name: string): Promise<void> {
  const dir = process.env.TLI_EVIDENCE_DIR
  if (dir) await page.screenshot({ path: `${dir}/web-${name}.png` })
}

let mock: MockService

test.afterAll(async ({ webPage: page }) => {
  await page.unroute(API).catch(() => undefined)
  await deleteAllByName(page, NAME)
})

test('guest: sign-in is optional, no cloud controls, and the privacy switch works', async ({ webPage: page }) => {
  mock = await install(page)
  await ensureAtBuildSelect(page)
  await expect(page.locator('.build-card-cloud')).toHaveCount(0)

  // A device that never signed in never contacts the hosted service, not even to check for a session.
  const apiRequests: string[] = []
  const onRequest = (req: { url: () => string }) => { if (API.test(req.url())) apiRequests.push(req.url()) }
  page.on('request', onRequest)
  await page.getByRole('button', { name: '⚙ Settings' }).click()
  const settings = page.locator('.modal-card.settings-modal-card')
  await expect(settings.getByRole('button', { name: 'Continue with Discord' })).toHaveCount(0)
  page.off('request', onRequest)
  expect(apiRequests).toEqual([])
  await expect(settings).toContainText('Anonymous build statistics')
  await expect(settings.locator('details')).not.toHaveAttribute('open', '')
  await expect(settings.getByText(/A report contains only catalog/)).toBeHidden()
  await settings.locator('summary').click()
  await expect(settings.getByText(/A report contains only catalog/)).toBeVisible()
  await shot(page, '01-guest-settings')

  const readPref = () => page.evaluate(() => JSON.parse(localStorage.getItem('tli-ui-prefs') || '{}').state?.shareCompositionStats)
  const row = settings.locator('.settings-row', { hasText: 'Anonymous build statistics' })
  await row.getByRole('button', { name: 'Off', exact: true }).click()
  expect(await readPref()).toBe(false)
  await row.getByRole('button', { name: 'On', exact: true }).click()
  expect(await readPref()).toBe(true)
  await settings.getByRole('button', { name: 'Close' }).click()
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Sign in' })).toContainText('Signing in is optional')
  await page.getByRole('dialog', { name: 'Sign in' }).getByRole('button', { name: 'Close' }).click()
})

test('signed in: upload, passive status, no prompt while editing, conflict only on an explicit action', async ({ webPage: page }) => {
  test.setTimeout(480_000)
  await ensureAtBuildSelect(page)
  await createAndSaveBuild(page, NAME)
  await backToBuilds(page)
  const card = () => page.locator('.build-card', { hasText: NAME }).first()
  await expect(card()).toBeVisible()
  // Guest: still no cloud controls on the card.
  await expect(card().locator('.build-card-cloud')).toHaveCount(0)

  // Sign in through the mock (a redirect that flips a flag), which reloads the app.
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('dialog', { name: 'Sign in' }).getByRole('button', { name: 'Continue with Discord' }).click()
  await page.waitForURL(WEB_URL)
  await waitForEngine(page)
  await page.locator('.account-menu > button').click()
  await page.getByRole('menuitem', { name: 'Profile settings' }).click()
  await expect(page.getByRole('dialog', { name: 'Profile settings' })).toContainText('Tyra#4472')
  await page.getByRole('dialog', { name: 'Profile settings' }).getByRole('button', { name: 'Close' }).click()

  // Passive status: not uploaded; nothing was uploaded by merely opening the library.
  await expect(card().locator('.build-card-cloud')).toContainText('Not uploaded')
  expect(mock.rows.size).toBe(0)

  // Explicit upload.
  await card().getByRole('button', { name: 'Upload to cloud' }).click()
  await expect(DIALOG('Uploaded')(page)).toBeVisible()
  await DIALOG('Uploaded')(page).getByRole('button', { name: 'Close' }).click()
  expect(mock.rows.size).toBe(1)
  await expect(card().locator('.build-card-cloud')).toContainText('Synced')
  await shot(page, '02-synced')

  // Uploading again with nothing changed creates no new revision.
  await expect(card().getByRole('button', { name: 'Upload to cloud' })).toHaveCount(0)
  const cloudId = [...mock.rows.keys()][0]
  expect(mock.rows.get(cloudId)!.revisions).toHaveLength(1)

  // Edit and save locally: only an indicator, never a prompt, even though the cloud moves meanwhile.
  await card().click()
  await expect(page.getByRole('button', { name: '← Back to Builds' })).toBeVisible()
  await page.getByRole('button', { name: 'Notes', exact: true }).click()
  await page.locator('[contenteditable="true"]').first().click()
  await page.keyboard.type('local edit')
  const cloudCode = await encodeBuild(page, { name: NAME, slots: [null, null, null, null], notes: 'edited in the cloud' })
  mock.bumpCloud(cloudId, cloudCode)
  await page.getByRole('button', { name: SIDEBAR_SAVE }).click()
  await expect(page.locator('.modal-card', { hasText: 'changed in two places' })).toHaveCount(0)
  await backToBuilds(page)
  await expect(card().locator('.build-card-cloud')).toContainText('Diverged')
  await expect(page.locator('.modal-card', { hasText: 'changed in two places' })).toHaveCount(0)

  // Explicit upload on a diverged build opens the conflict screen with Keep both highlighted.
  await card().getByRole('button', { name: 'Upload to cloud' }).click()
  const conflict = DIALOG('This build changed in two places')(page)
  await expect(conflict).toBeVisible()
  await expect(conflict.getByRole('button', { name: 'Keep both' })).toHaveClass(/btn-primary/)
  await shot(page, '03-conflict')

  // Keep local needs a second confirmation that names what is replaced, and Back replaces nothing.
  await conflict.getByRole('button', { name: 'Keep local' }).click()
  await expect(conflict).toContainText('replaces the cloud version')
  await shot(page, '04-keep-local-confirm')
  await conflict.getByRole('button', { name: 'Back' }).click()
  expect(mock.rows.get(cloudId)!.revisions).toHaveLength(2)
  expect(mock.writes.filter((w) => w.startsWith('put'))).toHaveLength(0)

  // Keep both: the cloud version becomes a separate local build; the original keeps its edit and its link.
  const before = await page.locator('.build-card').count()
  await conflict.getByRole('button', { name: 'Keep both' }).click()
  await expect(DIALOG('Saved as a new local build')(page)).toBeVisible()
  await DIALOG('Saved as a new local build')(page).getByRole('button', { name: 'Close' }).click()
  await expect(page.locator('.build-card')).toHaveCount(before + 1)
  await shot(page, '05-kept-both')
  expect(mock.rows.get(cloudId)!.revisions).toHaveLength(2)
  expect(mock.writes.filter((w) => w.startsWith('put'))).toHaveLength(0)
  await expect(page.locator('.build-card', { hasText: NAME }).first().locator('.build-card-cloud')).toBeVisible()

  // Sign out: cloud controls disappear but every local build stays.
  await page.locator('.account-menu > button').click()
  await page.getByRole('menuitem', { name: 'Sign out', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible()
  await expect(page.locator('.build-card-cloud')).toHaveCount(0)
  await expect(page.locator('.build-card', { hasText: NAME }).first()).toBeVisible()
})
