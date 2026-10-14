import { describe, it, expect, beforeAll } from 'vitest'
import zlib from 'node:zlib'
import { createHash, randomBytes } from 'node:crypto'
import {
  AccountApiError,
  createAccountsApi,
  type AccountTransport,
  type TransportResult,
} from '../../api/accounts'
import { createAnalyticsClient } from '../../api/analytics'
import { createCloudSync } from '../../utils/cloudSync'
import { createSyncRecordStore, type SyncRecordBackend } from '../../utils/syncRecords'
import { semanticBuildHash, type SyncRecord } from '../../utils/sync'

// App clients against the REAL local account service (its own PostgreSQL, sessions, CSRF, quotas), with the
// stand-in Discord page. Skipped unless TLI_LOCAL_SERVICE is set (for example http://localhost:8000).
// It proves the app's clients and the service agree. It does NOT prove live Discord OAuth or production
// cookie, CORS, or proxy behavior. Run from the repo root:
//   TLI_LOCAL_SERVICE=http://localhost:8000 npx vitest run src/renderer/src/__tests__/account/localService.integration.test.ts

const SERVICE = (process.env.TLI_LOCAL_SERVICE ?? '').replace(/\/+$/, '')
const ORIGIN = process.env.TLI_LOCAL_APP ?? 'http://localhost:5173'
const run = SERVICE ? describe : describe.skip

function codeOf(extra: Record<string, unknown>): string {
  const json = JSON.stringify({ v: 2, name: 'Integration', slots: [null, null, null, null], ...extra })
  const deflated = zlib.deflateSync(Buffer.from(json, 'utf-8'), { level: 9 })
  return `tli1_${deflated.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}`
}
const unique = () => Math.random().toString(36).slice(2, 10)
const upload = (name: string, code: string) => ({ name, code, dataVersion: 'SS13', appVersion: '0.6.9' })

/** The service rate-limits sign-in starts per address; wait and retry like a person would. */
async function patient(call: () => Promise<Response>): Promise<Response> {
  for (let attempt = 0; attempt < 40; attempt++) {
    const res = await call()
    if (res.status !== 429) return res
    const wait = Number(res.headers.get('retry-after')) || 3
    await new Promise((r) => setTimeout(r, Math.min(wait, 15) * 1000))
  }
  throw new Error('rate limit did not clear')
}

/** A browser-like device: a cookie jar plus the web transport rules (credentials, exact Origin, CSRF). */
class Device implements AccountTransport {
  private cookies = new Map<string, string>()
  private csrf: string | null = null

  private store(res: Response): void {
    for (const line of res.headers.getSetCookie()) {
      const [pair] = line.split(';')
      const index = pair.indexOf('=')
      const name = pair.slice(0, index).trim()
      const value = pair.slice(index + 1).trim()
      if (/max-age=0|expires=thu, 01 jan 1970/i.test(line) || value === '') this.cookies.delete(name)
      else this.cookies.set(name, value)
    }
  }

  private cookieHeader(): string {
    return [...this.cookies.entries()].map(([k, v]) => `${k}=${v}`).join('; ')
  }

  async raw(path: string, init: RequestInit & { origin?: string | null } = {}): Promise<Response> {
    const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) }
    if (this.cookies.size) headers.Cookie = this.cookieHeader()
    if (init.origin !== null) headers.Origin = init.origin ?? ORIGIN
    const res = await fetch(`${SERVICE}${path}`, { ...init, headers, redirect: 'manual' })
    this.store(res)
    return res
  }

  /** Stand-in Discord sign-in, exactly the browser's redirects. */
  async signIn(username: string, opts: { reauth?: boolean } = {}): Promise<string> {
    let authorize: URL
    if (opts.reauth) {
      const started = await this.request('POST', '/v1/account/reauth')
      expect(started.ok).toBe(true)
      authorize = new URL(String((started.data as { authorize_url: string }).authorize_url))
    } else {
      const start = await patient(() => this.raw('/auth/discord/start?client=web', { origin: null }))
      expect(start.status).toBe(302)
      authorize = new URL(start.headers.get('location')!)
    }
    const approve = await fetch(`${SERVICE}/dev/discord/approve?state=${encodeURIComponent(authorize.searchParams.get('state')!)}&username=${username}`, { redirect: 'manual' })
    const callback = new URL(approve.headers.get('location')!)
    const done = await patient(() => this.raw(`${callback.pathname}${callback.search}`, { origin: null }))
    expect(done.status).toBe(302)
    this.csrf = null
    return done.headers.get('location') ?? ''
  }

  async request(method: string, path: string, body?: unknown): Promise<TransportResult> {
    const headers: Record<string, string> = {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (method !== 'GET') {
      if (!this.csrf) {
        const t = await this.raw('/v1/csrf')
        this.csrf = ((await t.json()) as { csrf_token: string }).csrf_token
      }
      headers['X-CSRF-Token'] = this.csrf
    }
    const res = await this.raw(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
    let data: unknown = null
    try { data = await res.json() } catch { /* no body */ }
    return { ok: res.ok, status: res.status, data }
  }
}

/** Signed-in device for a new account (completes sign-up with the suggested name). */
async function newAccount(): Promise<{ device: Device; api: ReturnType<typeof createAccountsApi>; username: string }> {
  const username = `it_${unique()}`
  const device = new Device()
  await device.signIn(username)
  const api = createAccountsApi(device)
  expect(await api.getAccount()).toBeNull() // pending sign-up reads as no account yet
  const offer = await api.getSignupOffer()
  expect(offer?.suggestedName).toBe(username)
  await api.completeSignup(username)
  expect((await api.getAccount())?.publicName.name).toBe(username)
  return { device, api, username }
}

async function error(promise: Promise<unknown>): Promise<AccountApiError> {
  try { await promise } catch (e) { return e as AccountApiError }
  throw new Error('expected a rejection')
}

run('app clients against the real local account service', () => {
  beforeAll(async () => {
    const health = await fetch(`${SERVICE}/healthz`)
    expect(health.status).toBe(200)
  })

  it('guest: public routes work with no session; private routes answer 401', async () => {
    const guest = new Device()
    const api = createAccountsApi(guest)
    expect(await api.getAccount()).toBeNull()
    expect((await guest.request('GET', '/v1/cloud/builds')).status).toBe(401)
    expect((await guest.raw('/healthz', { origin: null })).status).toBe(200)
    const csrf = await guest.raw('/v1/csrf')
    expect(csrf.status).toBe(401)
  })

  it('unchanged upload creates no revision; changed upload does; stale write is refused with the current revision', async () => {
    const { api } = await newAccount()
    const code = codeOf({ notes: unique() })
    const created = await api.createCloudBuild({ ...upload('First', code), allowDuplicate: false })
    if (created.kind !== 'created') throw new Error('expected created')
    const first = created.build

    const same = await api.uploadRevision(first.cloudBuildId, { ...upload('First', code), baseRevisionId: first.currentRevisionId })
    expect(same.currentRevisionId).toBe(first.currentRevisionId) // no new revision for unchanged content

    const changed = await api.uploadRevision(first.cloudBuildId, { ...upload('First', codeOf({ notes: unique() })), baseRevisionId: first.currentRevisionId })
    expect(changed.currentRevisionId).not.toBe(first.currentRevisionId)

    const stale = await error(api.uploadRevision(first.cloudBuildId, { ...upload('First', codeOf({ notes: unique() })), baseRevisionId: first.currentRevisionId }))
    expect(stale).toMatchObject({ status: 409, code: 'stale_revision', details: { currentRevisionId: changed.currentRevisionId } })
    const after = (await api.listCloudBuilds())[0]
    expect(after.currentRevisionId).toBe(changed.currentRevisionId) // the refused write replaced nothing
  })

  it('an identical unlinked upload reports a match and creates nothing until allow_duplicate, which uses a slot', async () => {
    const { api } = await newAccount()
    const code = codeOf({ notes: unique() })
    await api.createCloudBuild({ ...upload('Original', code), allowDuplicate: false })
    const match = await api.createCloudBuild({ ...upload('Copy', code), allowDuplicate: false })
    expect(match).toMatchObject({ kind: 'match', name: 'Original' })
    expect((await api.listCloudBuilds())).toHaveLength(1)
    const dup = await api.createCloudBuild({ ...upload('Copy', code), allowDuplicate: true })
    expect(dup.kind).toBe('created')
    expect((await api.listCloudBuilds())).toHaveLength(2)
  })

  it('names over 50 characters are refused by the service and the cap holds', async () => {
    const { api } = await newAccount()
    const err = await error(api.createCloudBuild({ ...upload('n'.repeat(51), codeOf({ notes: unique() })), allowDuplicate: false }))
    expect(err).toMatchObject({ status: 422, code: 'name_too_long' })
    const ok = await api.createCloudBuild({ ...upload('n'.repeat(50), codeOf({ notes: unique() })), allowDuplicate: false })
    expect(ok.kind).toBe('created')
  })

  it('20 cloud builds at most, even when 25 are created at the same time', async () => {
    const { api } = await newAccount()
    const results = await Promise.allSettled(
      Array.from({ length: 25 }, (_, i) => api.createCloudBuild({ ...upload(`B${i}`, codeOf({ notes: `${i}-${unique()}` })), allowDuplicate: false })),
    )
    const created = results.filter((r) => r.status === 'fulfilled' && (r.value as { kind: string }).kind === 'created')
    const refused = results.filter((r) => r.status === 'rejected' && (r.reason as AccountApiError).code === 'cloud_quota_reached')
    expect(created).toHaveLength(20)
    expect(refused).toHaveLength(5)
    expect(await api.listCloudBuilds()).toHaveLength(20)
    const account = await api.getAccount()
    expect(account?.usage.cloudBuilds).toBe(20)
  })

  it('10 listed profile builds at most, even when 12 are listed at the same time', async () => {
    const { api } = await newAccount()
    const ids: string[] = []
    for (let i = 0; i < 12; i++) {
      const created = await api.createCloudBuild({ ...upload(`P${i}`, codeOf({ notes: `${i}-${unique()}` })), allowDuplicate: false })
      if (created.kind !== 'created') throw new Error('expected created')
      ids.push(created.build.cloudBuildId)
      await api.updateNamedLink(created.build.cloudBuildId, { slug: `link-${i}`, listed: false })
    }
    const results = await Promise.allSettled(ids.map((id) => api.updateNamedLink(id, { listed: true })))
    expect(results.filter((r) => r.status === 'fulfilled')).toHaveLength(10)
    const refused = results.filter((r) => r.status === 'rejected')
    expect(refused).toHaveLength(2)
    for (const r of refused) expect((r as PromiseRejectedResult).reason).toMatchObject({ status: 409, code: 'profile_quota_reached' })
    expect((await api.getAccount())?.usage.profileBuilds).toBe(10)
  })

  it('one account cannot read, change, link, or delete another account\'s builds, and its export holds only its own', async () => {
    const a = await newAccount()
    const b = await newAccount()
    const created = await a.api.createCloudBuild({ ...upload('Private A', codeOf({ notes: 'a-secret' })), allowDuplicate: false })
    if (created.kind !== 'created') throw new Error('expected created')
    const id = created.build.cloudBuildId
    await a.api.updateNamedLink(id, { slug: 'a-link', listed: false })

    expect(await error(b.api.getCloudBuild(id))).toMatchObject({ status: 404, code: 'not_found' })
    expect(await error(b.api.uploadRevision(id, { ...upload('x', codeOf({ notes: 'b' })), baseRevisionId: created.build.currentRevisionId }))).toMatchObject({ status: 404 })
    expect(await error(b.api.updateNamedLink(id, { listed: true }))).toMatchObject({ status: 404 })
    expect(await error(b.api.deleteCloudBuild(id))).toMatchObject({ status: 404 })
    expect(await b.api.listCloudBuilds()).toEqual([])
    // A client-supplied user id is never read: the owner still sees its build after B's attempts.
    expect((await a.api.listCloudBuilds())).toHaveLength(1)

    const bBuild = await b.api.createCloudBuild({ ...upload('Private B', codeOf({ notes: 'b-secret' })), allowDuplicate: false })
    if (bBuild.kind !== 'created') throw new Error('expected B build to be created')
    await b.device.signIn(b.username, { reauth: true })
    const exported = await b.api.exportAccount()
    const exportText = JSON.stringify(exported)
    expect(exportText).toContain('Private B')
    expect(exportText).toContain(bBuild.build.currentRevisionId)
    expect(exportText).not.toContain('Private A')
    expect(exportText).not.toContain(created.build.currentRevisionId)
  })

  it('a handle with the same name gets a different tag and a renamed handle redirects', async () => {
    const name = `same_${unique()}`
    const one = new Device(); await one.signIn(`${name}_1`)
    const two = new Device(); await two.signIn(`${name}_2`)
    const api1 = createAccountsApi(one); const api2 = createAccountsApi(two)
    await api1.getSignupOffer(); await api2.getSignupOffer()
    await api1.completeSignup(name)
    await api2.completeSignup(name)
    const [acc1, acc2] = [await api1.getAccount(), await api2.getAccount()]
    expect(acc1!.publicName.name).toBe(name)
    expect(acc2!.publicName.name).toBe(name)
    expect(acc1!.publicName.tag).not.toBe(acc2!.publicName.tag)

    const created = await api1.createCloudBuild({ ...upload('Linked', codeOf({ notes: unique() })), allowDuplicate: false })
    if (created.kind !== 'created') throw new Error('expected created')
    await api1.updateNamedLink(created.build.cloudBuildId, { slug: 'old-slug', listed: false })
    const oldHandle = `${name}-${acc1!.publicName.tag}`
    const renamed = await api1.renameHandle(`${name}x`)
    expect(renamed.name).toBe(`${name}x`)
    const redirect = await fetch(`${SERVICE}/u/${oldHandle}/old-slug`, { redirect: 'manual' })
    expect(redirect.status).toBe(301)
    expect(redirect.headers.get('location')).toContain(`${name}x-`.toLowerCase())
    // The previous handle can never be claimed by another account.
    const three = new Device(); await three.signIn(`${name}_3`)
    const api3 = createAccountsApi(three); await api3.getSignupOffer()
    await api3.completeSignup(name)
    expect(`${name}-${(await api3.getAccount())!.publicName.tag}`).not.toBe(oldHandle)
  })

  it('the cloud sync controller runs end to end on the real service, with sync records kept only locally', async () => {
    const { api } = await newAccount()
    const rows = new Map<string, SyncRecord>()
    const backend: SyncRecordBackend = {
      readAll: async () => [...rows.values()], put: async (r) => { rows.set(r.localBuildId, r) }, remove: async (id) => { rows.delete(id) },
    }
    const records = createSyncRecordStore(backend)
    const library = new Map<string, { name: string; code: string }>([['L1', { name: 'Sync One', code: codeOf({ notes: unique() }) }]])
    let counter = 0
    const sync = createCloudSync({
      accounts: api, records,
      activeUserId: () => 'user-under-test',
      dataVersion: () => 'SS13', appVersion: () => '0.6.9',
      hashOf: semanticBuildHash,
      local: {
        read: async (id) => { const b = library.get(id)!; return { name: b.name, code: b.code, hash: await semanticBuildHash(b.code) } },
        rename: async (id, name) => { library.get(id)!.name = name },
        createFromCloud: async (code, name) => { const id = `N${++counter}`; library.set(id, { name, code }); return id },
        replaceFromCloud: async (id, code, name) => { library.set(id, { name, code }) },
      },
    })
    expect((await sync.upload('L1')).kind).toBe('uploaded')
    expect((await sync.upload('L1')).kind).toBe('unchanged')
    // The app's local hash equals the service's hash for the same content (shared canonical form).
    const [cloud] = await api.listCloudBuilds()
    expect(cloud.semanticHash).toBe(await semanticBuildHash(library.get('L1')!.code))
    // A duplicate of the same content prompts instead of linking silently.
    library.set('COPY', { name: 'Copy', code: library.get('L1')!.code })
    expect((await sync.upload('COPY')).kind).toBe('link-prompt')
    expect(await api.listCloudBuilds()).toHaveLength(1)
    // The 5 sync fields are the only thing stored locally.
    expect(Object.keys([...rows.values()][0]).sort()).toEqual(['accountUserId', 'baseRevisionId', 'baseSemanticHash', 'cloudBuildId', 'localBuildId'])
  })

  it('cookie, CSRF, and CORS: exact origins only, credentials only for them, writes need the token', async () => {
    const { device } = await newAccount()
    // Credentialed CORS only for the exact web origin.
    const pre = await fetch(`${SERVICE}/v1/cloud/builds`, { method: 'OPTIONS', headers: { Origin: ORIGIN, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type,x-csrf-token' } })
    expect(pre.headers.get('access-control-allow-origin')).toBe(ORIGIN)
    expect(pre.headers.get('access-control-allow-credentials')).toBe('true')
    const evil = await fetch(`${SERVICE}/v1/cloud/builds`, { method: 'OPTIONS', headers: { Origin: 'https://evil.example', 'Access-Control-Request-Method': 'POST' } })
    expect(evil.headers.get('access-control-allow-origin')).toBeNull()
    // Anonymous routes never allow credentials.
    const share = await fetch(`${SERVICE}/healthz`, { headers: { Origin: 'https://anywhere.example' } })
    expect(share.headers.get('access-control-allow-credentials')).toBeNull()

    // A write without the CSRF token, or from another origin, is refused even with a valid cookie.
    const noToken = await device.raw('/v1/cloud/builds', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'x', code: codeOf({}), data_version: 'SS13', app_version: '1', allow_duplicate: false }) })
    expect(noToken.status).toBe(403)
    expect(((await noToken.json()) as { error: { code: string } }).error.code).toBe('csrf_failed')
    const csrf = ((await (await device.raw('/v1/csrf')).json()) as { csrf_token: string }).csrf_token
    const wrongOrigin = await device.raw('/v1/cloud/builds', { method: 'POST', origin: 'https://evil.example', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify({ name: 'x', code: codeOf({}), data_version: 'SS13', app_version: '1', allow_duplicate: false }) })
    expect(wrongOrigin.status).toBe(403)
    // Session cookie flags.
    const start = await fetch(`${SERVICE}/auth/discord/start?client=web`, { redirect: 'manual' })
    const stateCookie = start.headers.getSetCookie().join('\n')
    expect(stateCookie).toMatch(/HttpOnly/i)
    expect(stateCookie).toMatch(/SameSite=Lax/i)
  })

  it('sign out everywhere revokes every device; a rotated-out or unknown token is refused', async () => {
    const username = `so_${unique()}`
    const d1 = new Device(); await d1.signIn(username)
    const api1 = createAccountsApi(d1); await api1.getSignupOffer(); await api1.completeSignup(username)
    const d2 = new Device(); await d2.signIn(username)
    const api2 = createAccountsApi(d2)
    expect(await api2.getAccount()).not.toBeNull()
    await api1.signOutEverywhere()
    expect(await api1.getAccount()).toBeNull()
    expect(await api2.getAccount()).toBeNull()
    const bogus = await fetch(`${SERVICE}/v1/account`, { headers: { Authorization: 'Bearer not-a-real-token' } })
    expect(bogus.status).toBe(401)
  })

  it('export and delete are refused without a recent confirmation', async () => {
    const { api } = await newAccount()
    expect(await error(api.exportAccount())).toMatchObject({ status: 403, code: 'reauth_required' })
    expect(await error(api.deleteAccount())).toMatchObject({ status: 403, code: 'reauth_required' })
    expect((await api.getAccount())).not.toBeNull() // still there
  })

  it('desktop: PKCE exchange works once with the right verifier and a wrong verifier burns the code', async () => {
    const username = `dk_${unique()}`
    const verifier = randomBytes(32).toString('base64url')
    const challenge = createHash('sha256').update(verifier).digest('base64url')
    const flow = async () => {
      const start = await patient(() => fetch(`${SERVICE}/auth/discord/start?client=desktop&port=49152&code_challenge=${challenge}`, { redirect: 'manual' }))
      expect(start.status).toBe(302)
      const state = new URL(start.headers.get('location')!).searchParams.get('state')!
      const approve = await fetch(`${SERVICE}/dev/discord/approve?state=${encodeURIComponent(state)}&username=${username}`, { redirect: 'manual' })
      // The callback needs the state cookie from the start step, as the browser would send it.
      const cookie = start.headers.getSetCookie().map((c) => c.split(';')[0]).join('; ')
      const callbackUrl = new URL(approve.headers.get('location')!)
      const callback = await fetch(`${SERVICE}${callbackUrl.pathname}${callbackUrl.search}`, { headers: { Cookie: cookie }, redirect: 'manual' })
      expect(callback.status).toBe(302)
      const target = new URL(callback.headers.get('location')!)
      expect(target.hostname).toBe('127.0.0.1')
      expect(target.port).toBe('49152')
      return target.searchParams.get('login_code')!
    }
    const exchange = (loginCode: string, codeVerifier: string) => patient(() => fetch(`${SERVICE}/auth/desktop/exchange`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ login_code: loginCode, code_verifier: codeVerifier }),
    }))

    const intercepted = await flow()
    const wrong = await exchange(intercepted, randomBytes(32).toString('base64url'))
    expect(wrong.status).toBe(400)
    expect(((await wrong.json()) as { error: { code: string } }).error.code).toBe('invalid_grant')
    const retryRight = await exchange(intercepted, verifier) // the code was burned by the wrong attempt
    expect(retryRight.status).toBe(400)

    const good = await flow()
    const ok = await exchange(good, verifier)
    expect(ok.status).toBe(200)
    const { session_token } = (await ok.json()) as { session_token: string }
    const me = await fetch(`${SERVICE}/v1/account`, { headers: { Authorization: `Bearer ${session_token}` } })
    expect(me.status).toBe(403) // sign-up still pending: a bearer session is valid but incomplete
    expect(((await me.json()) as { error: { code: string } }).error.code).toBe('signup_required')
    const reuse = await exchange(good, verifier)
    expect(reuse.status).toBe(400)
  })

  it('desktop start refuses a privileged or malformed loopback port', async () => {
    const challenge = createHash('sha256').update('x').digest('base64url')
    for (const port of ['80', '1023', '70000', 'abc']) {
      const res = await fetch(`${SERVICE}/auth/discord/start?client=desktop&port=${port}&code_challenge=${challenge}`, { redirect: 'manual' })
      expect(res.status).toBeGreaterThanOrEqual(400)
    }
  })

  it('anonymous statistics: a valid report is accepted with no cookie; text, rolls, unknown mechanics and credentials are rejected', async () => {
    const client = createAnalyticsClient({ base: SERVICE })
    await client.sendComposition({
      dataVersion: 'SS13',
      entities: [{ type: 'support', id: 'support_a' }, { type: 'memory_base_stat', id: 'a65f0fbf-bc8f-5e90-a594-7b70b6fb7a63' }, { type: 'memory_revival', id: 'furious_roar' }],
      relations: [{ skillId: 'skill_x', supportId: 'support_a' }],
      mechanics: ['tangle', 'minion'],
    })
    const reject = (c: Parameters<typeof client.sendComposition>[0]) => expect(client.sendComposition(c)).rejects.toThrow(/400/)
    await reject({ dataVersion: 'SS13', entities: [{ type: 'support', id: '+93.5 Strength' }], relations: [], mechanics: [] })
    await reject({ dataVersion: 'SS13', entities: [{ type: 'memory_revival', id: 'Furious Roar!!' }], relations: [], mechanics: [] })
    await reject({ dataVersion: 'SS13', entities: [{ type: 'support', id: '93.5' }], relations: [], mechanics: [] })
    await reject({ dataVersion: 'SS13', entities: [{ type: 'not_a_type' as never, id: 'a' }], relations: [], mechanics: [] })
    await reject({ dataVersion: 'SS13', entities: [{ type: 'support', id: 'a' }], relations: [], mechanics: ['not_a_flag'] })

    // The raw route: no cookie is set, and an Authorization header is refused.
    const body = JSON.stringify({ data_version: 'SS13', entities: [{ type: 'support', id: 'support_b' }], relations: [], mechanics: [] })
    const plain = await fetch(`${SERVICE}/v1/stats/composition`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
    expect(plain.status).toBe(204)
    expect(plain.headers.getSetCookie()).toEqual([])
    const withAuth = await fetch(`${SERVICE}/v1/stats/composition`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer x' }, body })
    expect(withAuth.status).toBe(400)
  })

  it('a named link read needs no credentials, is not indexed, and a removed link says so', async () => {
    const { api, device } = await newAccount()
    const account = (await api.getAccount())!
    const created = await api.createCloudBuild({ ...upload('Public', codeOf({ notes: unique() })), allowDuplicate: false })
    if (created.kind !== 'created') throw new Error('expected created')
    const link = await api.updateNamedLink(created.build.cloudBuildId, { slug: 'public-one', listed: false })
    expect(link.urlPath).toBe(`/u/${account.publicName.name.toLowerCase()}-${account.publicName.tag}/public-one`)
    const read = await fetch(`${SERVICE}${link.urlPath}`)
    expect(read.status).toBe(200)
    expect(read.headers.get('x-robots-tag')).toContain('noindex')
    expect(((await read.json()) as { code: string }).code).toMatch(/^tli1_/)
    await api.deleteCloudBuild(created.build.cloudBuildId)
    const gone = await fetch(`${SERVICE}${link.urlPath}`)
    expect(gone.status).toBe(410)
    expect(((await gone.json()) as { error: { code: string } }).error.code).toBe('removed_by_owner')
    // A different build cannot reuse the retired slug.
    const second = await api.createCloudBuild({ ...upload('Other', codeOf({ notes: unique() })), allowDuplicate: false })
    if (second.kind !== 'created') throw new Error('expected created')
    expect(await error(api.updateNamedLink(second.build.cloudBuildId, { slug: 'public-one' }))).toMatchObject({ status: 409, code: 'slug_taken' })
    void device
  })
})
