import { test, expect } from '../fixtures/electron'
import { existsSync, readFileSync } from 'fs'
import path from 'path'

// The real desktop product: preload bridge, main-process account module, and sync-record file.
// Signed out, no request leaves the machine: the main process answers 401 itself. The test never
// starts the Discord sign-in (it would open the system browser) and never talks to the live service,
// so this does NOT prove OAuth; it proves the IPC surface and that a guest keeps working.

type Bridge = {
  accountRequest: (m: string, p: string, b?: unknown) => Promise<{ ok: boolean; status: number; data: unknown }>
  syncRecordsRead: () => Promise<Array<Record<string, string>>>
  syncRecordsPut: (r: unknown) => Promise<void>
  syncRecordsRemove: (id: string) => Promise<void>
}

const rec = (id: string) => ({
  localBuildId: id, accountUserId: 'user-A', cloudBuildId: 'cb-1', baseRevisionId: 'r1', baseSemanticHash: 'h1',
})

test('signed out: the bridge answers 401 locally and refuses paths outside /v1', async ({ appWindow }) => {
  const unauthenticated = await appWindow.evaluate(() => (window as unknown as { api: Bridge }).api.accountRequest('GET', '/v1/account'))
  expect(unauthenticated.status).toBe(401)
  expect(unauthenticated.ok).toBe(false)

  const outside = await appWindow.evaluate(() => (window as unknown as { api: Bridge }).api.accountRequest('GET', 'https://evil.test/v1/account'))
  expect(outside.status).toBe(400)
  const traversal = await appWindow.evaluate(() => (window as unknown as { api: Bridge }).api.accountRequest('GET', '/v1/%2e%2e/admin'))
  expect(traversal.status).toBe(400)
  const badMethod = await appWindow.evaluate(() => (window as unknown as { api: Bridge }).api.accountRequest('TRACE', '/v1/account'))
  expect(badMethod.status).toBe(400)
})

test('guest account entry opens Profile while Settings keeps the collapsed privacy disclosure', async ({ appWindow }) => {
  await appWindow.getByRole('button', { name: 'Sign in', exact: true }).click()
  const profile = appWindow.getByRole('dialog', { name: 'Sign in' })
  await expect(profile).toContainText('Discord sign-in is optional')
  await expect(profile.getByRole('button', { name: 'Continue with Discord' })).toBeVisible()
  await profile.getByRole('button', { name: 'Close' }).click()
  await appWindow.getByRole('button', { name: '⚙ Settings' }).click()
  const settings = appWindow.locator('.modal-card.settings-modal-card')
  await expect(settings.getByRole('button', { name: 'Continue with Discord' })).toHaveCount(0)
  await expect(settings).toContainText('Anonymous build statistics')
  await expect(settings.getByText(/A report contains only catalog/)).toBeHidden()
  await settings.locator('summary').click()
  await expect(settings.getByText(/A report contains only catalog/)).toBeVisible()
  if (process.env.TLI_EVIDENCE_DIR) await appWindow.screenshot({ path: `${process.env.TLI_EVIDENCE_DIR}/electron-01-guest-settings.png` })
  await settings.getByRole('button', { name: 'Close' }).click()
  await expect(appWindow.getByRole('button', { name: '+ New Build' })).toBeVisible()
  await expect(appWindow.locator('.build-card-cloud')).toHaveCount(0)
})

test('sync records persist in the userData file with only the five sync fields', async ({ appWindow, e2eDirs }) => {
  await appWindow.evaluate((r) => (window as unknown as { api: Bridge }).api.syncRecordsPut({ ...r, buildName: 'must not be stored' }), rec('L1'))
  await appWindow.evaluate((r) => (window as unknown as { api: Bridge }).api.syncRecordsPut(r), rec('L2'))

  const read = await appWindow.evaluate(() => (window as unknown as { api: Bridge }).api.syncRecordsRead())
  expect(read.map((r) => r.localBuildId).sort()).toEqual(['L1', 'L2'])

  const file = path.join(e2eDirs.userData, 'sync-records.json')
  expect(existsSync(file)).toBe(true)
  const raw = readFileSync(file, 'utf-8')
  expect(raw).not.toContain('must not be stored')
  expect(Object.keys(JSON.parse(raw).records[0]).sort()).toEqual(
    ['accountUserId', 'baseRevisionId', 'baseSemanticHash', 'cloudBuildId', 'localBuildId'],
  )

  const rejected = await appWindow.evaluate(async () => {
    try { await (window as unknown as { api: Bridge }).api.syncRecordsPut({ localBuildId: 'bad' }); return 'accepted' } catch { return 'rejected' }
  })
  expect(rejected).toBe('rejected')

  await appWindow.evaluate(() => (window as unknown as { api: Bridge }).api.syncRecordsRemove('L1'))
  await appWindow.evaluate(() => (window as unknown as { api: Bridge }).api.syncRecordsRemove('L2'))
  expect(await appWindow.evaluate(() => (window as unknown as { api: Bridge }).api.syncRecordsRead())).toEqual([])
})

test('no session token file exists for a guest', async ({ e2eDirs }) => {
  expect(existsSync(path.join(e2eDirs.userData, 'account-session.bin'))).toBe(false)
})
