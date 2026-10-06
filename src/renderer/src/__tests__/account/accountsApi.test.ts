import { describe, it, expect, vi } from 'vitest'
import {
  AccountApiError,
  createAccountsApi,
  createWebTransport,
  createDesktopTransport,
  webSignInUrl,
  type AccountTransport,
} from '../../api/accounts'
import { createAnalyticsClient } from '../../api/analytics'

type FetchCall = { url: string; init: RequestInit }

function fakeFetch(handler: (call: FetchCall) => { status?: number; body?: unknown }) {
  const calls: FetchCall[] = []
  const impl = vi.fn(async (url: string, init: RequestInit) => {
    const call = { url, init }
    calls.push(call)
    const { status = 200, body = {} } = handler(call)
    return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  })
  return { impl: impl as unknown as typeof fetch, calls }
}

const BASE = 'https://api.example.test'

describe('web transport', () => {
  it('sends cookies and a CSRF token on writes but not on reads', async () => {
    const { impl, calls } = fakeFetch(({ url }) => (url.endsWith('/v1/csrf') ? { body: { csrf_token: 'tok-1' } } : { body: { ok: true } }))
    const t = createWebTransport({ base: BASE, fetchImpl: impl })
    await t.request('GET', '/v1/account')
    await t.request('POST', '/v1/account/signout')
    const read = calls.find((c) => c.url.endsWith('/v1/account'))!
    const write = calls.find((c) => c.url.endsWith('/v1/account/signout'))!
    expect(read.init.credentials).toBe('include')
    expect((read.init.headers as Record<string, string>)['X-CSRF-Token']).toBeUndefined()
    expect(write.init.credentials).toBe('include')
    expect((write.init.headers as Record<string, string>)['X-CSRF-Token']).toBe('tok-1')
  })

  it('refreshes the CSRF token once after csrf_failed and retries the write', async () => {
    let tokens = 0
    let writes = 0
    const { impl, calls } = fakeFetch(({ url, init }) => {
      if (url.endsWith('/v1/csrf')) return { body: { csrf_token: `tok-${++tokens}` } }
      writes++
      const sent = (init.headers as Record<string, string>)['X-CSRF-Token']
      return sent === 'tok-2' ? { body: { ok: true } } : { status: 403, body: { error: { code: 'csrf_failed', message: 'x' } } }
    })
    const t = createWebTransport({ base: BASE, fetchImpl: impl })
    const result = await t.request('POST', '/v1/cloud/builds', { name: 'a' })
    expect(result.ok).toBe(true)
    expect(writes).toBe(2)
    expect(calls.filter((c) => c.url.endsWith('/v1/csrf'))).toHaveLength(2)
  })

  it('never sends a client-supplied user id', async () => {
    const { impl, calls } = fakeFetch(() => ({ body: { csrf_token: 't' } }))
    const t = createWebTransport({ base: BASE, fetchImpl: impl })
    await t.request('POST', '/v1/cloud/builds', { name: 'a', code: 'tli1_x' })
    const body = JSON.parse(String(calls.find((c) => c.url.endsWith('/v1/cloud/builds'))!.init.body))
    expect(Object.keys(body)).not.toContain('user_id')
  })

  it('builds the sign-in navigation URL with only the web client parameter', () => {
    expect(webSignInUrl(BASE)).toBe(`${BASE}/auth/discord/start?client=web`)
  })
})

describe('desktop transport', () => {
  it('delegates to the main process so the renderer never holds the token', async () => {
    const accountRequest = vi.fn().mockResolvedValue({ ok: true, status: 200, data: { user_id: 'u' } })
    const t = createDesktopTransport({ accountRequest })
    const result = await t.request('GET', '/v1/account')
    expect(accountRequest).toHaveBeenCalledWith('GET', '/v1/account', undefined)
    expect(result.data).toEqual({ user_id: 'u' })
  })
})

const transportReturning = (status: number, data: unknown): AccountTransport => ({
  request: vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, data }),
})

describe('accounts api', () => {
  it('maps an account response', async () => {
    const api = createAccountsApi(transportReturning(200, {
      user_id: 'usr_1',
      public_name: { name: 'Tyra', tag: '4472' },
      limits: { cloud_builds: 20, profile_builds: 10 },
      usage: { cloud_builds: 3, profile_builds: 1 },
      needs_handle_confirmation: false,
    }))
    expect(await api.getAccount()).toEqual({
      userId: 'usr_1',
      publicName: { name: 'Tyra', tag: '4472' },
      limits: { cloudBuilds: 20, profileBuilds: 10 },
      usage: { cloudBuilds: 3, profileBuilds: 1 },
    })
  })

  it('returns null for a signed-out visitor instead of throwing', async () => {
    const api = createAccountsApi(transportReturning(401, { error: { code: 'unauthenticated', message: 'x' } }))
    expect(await api.getAccount()).toBeNull()
  })

  it('treats a pending signup (403 signup_required) as no account yet, not an error', async () => {
    const api = createAccountsApi(transportReturning(403, { error: { code: 'signup_required', message: 'x' } }))
    expect(await api.getAccount()).toBeNull()
  })

  it('maps the cloud list', async () => {
    const api = createAccountsApi(transportReturning(200, {
      builds: [{
        cloud_build_id: 'cb_1', name: 'Fire', current_revision_id: 'rev_1',
        semantic_hash: 'h', updated_at: 5, data_version: 'season-9',
        named_link: { url_path: '/u/tyra-4472/fire', slug: 'fire', listed: true, revision_id: 'rev_1' },
      }],
    }))
    const list = await api.listCloudBuilds()
    expect(list[0]).toMatchObject({
      cloudBuildId: 'cb_1', currentRevisionId: 'rev_1', semanticHash: 'h', dataVersion: 'season-9',
      namedLink: { urlPath: '/u/tyra-4472/fire', slug: 'fire', listed: true, revisionId: 'rev_1' },
    })
  })

  it('create returns a content match without a build', async () => {
    const api = createAccountsApi(transportReturning(200, { match: { cloud_build_id: 'cb_9', name: 'Existing' } }))
    expect(await api.createCloudBuild({ name: 'n', code: 'tli1_x', dataVersion: 's', appVersion: '1', allowDuplicate: false }))
      .toEqual({ kind: 'match', cloudBuildId: 'cb_9', name: 'Existing' })
  })

  it('create sends allow_duplicate and returns the created summary', async () => {
    const transport = transportReturning(201, {
      summary: { cloud_build_id: 'cb_2', name: 'n', current_revision_id: 'rev_2', semantic_hash: 'h', updated_at: 1, data_version: 's', named_link: null },
    })
    const api = createAccountsApi(transport)
    const result = await api.createCloudBuild({ name: 'n', code: 'tli1_x', dataVersion: 's', appVersion: '1', allowDuplicate: true })
    expect(result.kind).toBe('created')
    expect(transport.request).toHaveBeenCalledWith('POST', '/v1/cloud/builds', {
      name: 'n', code: 'tli1_x', data_version: 's', app_version: '1', allow_duplicate: true,
    })
  })

  it('upload is conditional on base_revision_id', async () => {
    const transport = transportReturning(200, {
      summary: { cloud_build_id: 'cb_1', name: 'n', current_revision_id: 'rev_3', semantic_hash: 'h', updated_at: 1, data_version: 's', named_link: null },
    })
    const api = createAccountsApi(transport)
    await api.uploadRevision('cb_1', { baseRevisionId: 'rev_2', name: 'n', code: 'tli1_x', dataVersion: 's', appVersion: '1' })
    expect(transport.request).toHaveBeenCalledWith('PUT', '/v1/cloud/builds/cb_1', {
      base_revision_id: 'rev_2', name: 'n', code: 'tli1_x', data_version: 's', app_version: '1',
    })
  })

  it('surfaces a stale write as a typed conflict that carries the current revision', async () => {
    const api = createAccountsApi(transportReturning(409, {
      error: { code: 'stale_revision', message: 'x', current_revision_id: 'rev_9' },
    }))
    const error = await api.uploadRevision('cb_1', { baseRevisionId: 'rev_2', name: 'n', code: 'c', dataVersion: 's', appVersion: '1' }).catch((e) => e)
    expect(error).toBeInstanceOf(AccountApiError)
    expect(error).toMatchObject({ status: 409, code: 'stale_revision', details: { currentRevisionId: 'rev_9' } })
  })

  it('encodes ids in paths', async () => {
    const transport = transportReturning(204, null)
    const api = createAccountsApi(transport)
    await api.deleteCloudBuild('a/b c')
    expect(transport.request).toHaveBeenCalledWith('DELETE', '/v1/cloud/builds/a%2Fb%20c', undefined)
  })

  it('moves a named link only when asked to with a revision id', async () => {
    const transport = transportReturning(200, { named_link: { url_path: '/u/t-1111/x', slug: 'x', listed: false, revision_id: 'rev_5' } })
    const api = createAccountsApi(transport)
    const link = await api.updateNamedLink('cb_1', { revisionId: 'rev_5' })
    expect(transport.request).toHaveBeenCalledWith('PUT', '/v1/cloud/builds/cb_1/link', { revision_id: 'rev_5' })
    expect(link.revisionId).toBe('rev_5')
  })

  it('reauth returns the authorize URL', async () => {
    const api = createAccountsApi(transportReturning(200, { authorize_url: 'https://api.example.test/auth/discord/start?x=1' }))
    expect(await api.startReauth()).toBe('https://api.example.test/auth/discord/start?x=1')
  })

  it('export and delete pass through reauth_required', async () => {
    const api = createAccountsApi(transportReturning(403, { error: { code: 'reauth_required', message: 'x' } }))
    await expect(api.exportAccount()).rejects.toMatchObject({ code: 'reauth_required', status: 403 })
    await expect(api.deleteAccount()).rejects.toMatchObject({ code: 'reauth_required', status: 403 })
  })

  it('reports a network failure as a typed error', async () => {
    const transport: AccountTransport = { request: vi.fn().mockRejectedValue(new TypeError('Failed to fetch')) }
    const api = createAccountsApi(transport)
    await expect(api.listCloudBuilds()).rejects.toMatchObject({ code: 'network_error' })
  })
})

describe('analytics client', () => {
  it('posts the composition with no credentials, no auth header, and snake_case fields', async () => {
    const { impl, calls } = fakeFetch(() => ({ status: 204 }))
    const client = createAnalyticsClient({ base: BASE, fetchImpl: impl })
    await client.sendComposition({
      dataVersion: 'season-9',
      entities: [{ type: 'support', id: 'support_a' }],
      relations: [{ skillId: 'skill_x', supportId: 'support_a' }],
      mechanics: ['minion'],
    })
    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe(`${BASE}/v1/stats/composition`)
    expect(calls[0].init.credentials).toBe('omit')
    expect(Object.keys(calls[0].init.headers as Record<string, string>).map((k) => k.toLowerCase()).sort()).toEqual(['content-type'])
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      data_version: 'season-9',
      entities: [{ type: 'support', id: 'support_a' }],
      relations: [{ skill_id: 'skill_x', support_id: 'support_a' }],
      mechanics: ['minion'],
    })
    expect(calls[0].init.referrerPolicy).toBe('no-referrer')
    expect(calls[0].init.keepalive).toBeUndefined()
  })

  it('rejects when the service answers an error so the reporter can retry later', async () => {
    const { impl } = fakeFetch(() => ({ status: 500, body: {} }))
    const client = createAnalyticsClient({ base: BASE, fetchImpl: impl })
    await expect(client.sendComposition({ dataVersion: 's', entities: [], relations: [], mechanics: [] })).rejects.toThrow()
  })
})
