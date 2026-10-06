// Hosted-account API client. Contract: docs/HOSTED_ACCOUNT_API_CONTRACT.md.
//
// Two transports reach the same endpoints:
//  - web: cookie session + CSRF token, credentialed fetch to the exact API origin;
//  - desktop: requests go through the main process, which holds the bearer token in Electron
//    safeStorage. The renderer never sees the token.
// The user is always derived from the verified session on the service; this client never sends a
// user id.
import { getShareBase } from './share'

export interface TransportResult {
  ok: boolean
  status: number
  data: unknown
}

export interface AccountTransport {
  request(method: string, path: string, body?: unknown): Promise<TransportResult>
}

/** Plain-language text for an account-service failure. */
export function friendlyAccountError(error: unknown): string {
  if (!(error instanceof AccountApiError)) return error instanceof Error ? error.message : 'Something went wrong.'
  switch (error.code) {
    case 'signup_closed': return 'Sign-up is not open yet.'
    case 'name_unavailable': return 'That name is taken. Choose another.'
    case 'invalid_name': return 'Names use 2–24 letters, numbers, underscores, or dots.'
    case 'handle_limit_reached': return 'You have changed your public name too many times. Try a different name later.'
    case 'already_registered': return 'This Discord account already has an account.'
    case 'busy': return 'The service is busy. Try again in a moment.'
    case 'rate_limited': return 'You are making too many requests. Wait a moment and try again.'
    default: return error.message
  }
}

export class AccountApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'AccountApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

const REQUEST_TIMEOUT_MS = 15_000

// ── Transports ───────────────────────────────────────────────────────────────
export function webSignInUrl(base: string = getShareBase()): string {
  return `${base}/auth/discord/start?client=web`
}

export function createWebTransport(opts: { base?: string; fetchImpl?: typeof fetch } = {}): AccountTransport {
  const base = (opts.base ?? getShareBase()).replace(/\/+$/, '')
  const doFetch = opts.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args))
  let csrfToken: string | null = null

  async function readJson(res: Response): Promise<unknown> {
    try { return await res.json() } catch { return null }
  }

  async function ensureCsrf(force: boolean): Promise<string> {
    if (csrfToken && !force) return csrfToken
    const res = await doFetch(`${base}/v1/csrf`, { method: 'GET', credentials: 'include', signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) })
    const data = (await readJson(res)) as { csrf_token?: string } | null
    if (res.status === 401) throw new AccountApiError(401, 'unauthenticated', 'Not signed in.')
    if (!res.ok || !data?.csrf_token) throw new AccountApiError(res.status, 'csrf_unavailable', 'Could not obtain a CSRF token.')
    csrfToken = data.csrf_token
    return csrfToken
  }

  async function send(method: string, path: string, body: unknown, forceCsrf: boolean): Promise<TransportResult> {
    const headers: Record<string, string> = {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (method !== 'GET') headers['X-CSRF-Token'] = await ensureCsrf(forceCsrf)
    const res = await doFetch(`${base}${path}`, {
      method,
      headers,
      credentials: 'include',
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
    return { ok: res.ok, status: res.status, data: await readJson(res) }
  }

  return {
    async request(method, path, body) {
      const first = await send(method, path, body, false)
      const code = (first.data as { error?: { code?: string } } | null)?.error?.code
      if (method !== 'GET' && first.status === 403 && code === 'csrf_failed') {
        return send(method, path, body, true)
      }
      return first
    },
  }
}

export function createDesktopTransport(bridge: {
  accountRequest: (method: string, path: string, body?: unknown) => Promise<TransportResult>
}): AccountTransport {
  return { request: (method, path, body) => bridge.accountRequest(method, path, body) }
}

/** The transport for the running shell: the main-process bridge on desktop, credentialed fetch on web. */
export function defaultAccountTransport(): AccountTransport {
  const bridge = typeof window !== 'undefined' ? window.api : undefined
  if (bridge?.accountRequest) return createDesktopTransport({ accountRequest: bridge.accountRequest })
  return createWebTransport()
}

// ── Types ────────────────────────────────────────────────────────────────────
export interface Account {
  userId: string
  publicName: { name: string; tag: string }
  limits: { cloudBuilds: number; profileBuilds: number }
  usage: { cloudBuilds: number; profileBuilds: number }
}

export interface NamedLink {
  urlPath: string
  slug: string
  listed: boolean
  revisionId: string
}

export interface CloudBuild {
  cloudBuildId: string
  name: string
  currentRevisionId: string
  semanticHash: string
  updatedAt: number
  dataVersion: string
  namedLink: NamedLink | null
}

export interface UploadInput {
  name: string
  code: string
  dataVersion: string
  appVersion: string
}

export type CreateResult =
  | { kind: 'created'; build: CloudBuild }
  | { kind: 'match'; cloudBuildId: string; name: string }

export interface SignupOffer {
  suggestedName: string
  preview: { name: string; tag: string } | null
}

// ── Mapping ──────────────────────────────────────────────────────────────────
type Raw = Record<string, unknown>

function asRaw(value: unknown): Raw {
  return value && typeof value === 'object' ? (value as Raw) : {}
}

function mapLink(raw: unknown): NamedLink | null {
  if (!raw) return null
  const r = asRaw(raw)
  return { urlPath: String(r.url_path), slug: String(r.slug), listed: Boolean(r.listed), revisionId: String(r.revision_id) }
}

function mapBuild(raw: unknown): CloudBuild {
  const r = asRaw(raw)
  return {
    cloudBuildId: String(r.cloud_build_id),
    name: String(r.name),
    currentRevisionId: String(r.current_revision_id),
    semanticHash: String(r.semantic_hash),
    updatedAt: Number(r.updated_at),
    dataVersion: String(r.data_version ?? ''),
    namedLink: mapLink(r.named_link),
  }
}

function toError(result: TransportResult): AccountApiError {
  const err = asRaw(asRaw(result.data).error)
  const code = typeof err.code === 'string' ? err.code : `http_${result.status}`
  const message = typeof err.message === 'string' ? err.message : `Request failed (${result.status}).`
  const details: Record<string, unknown> = {}
  if (typeof err.current_revision_id === 'string') details.currentRevisionId = err.current_revision_id
  return new AccountApiError(result.status, code, message, details)
}

// ── API ──────────────────────────────────────────────────────────────────────
export function createAccountsApi(transport: AccountTransport) {
  async function call(method: string, path: string, body?: unknown): Promise<TransportResult> {
    let result: TransportResult
    try {
      result = await transport.request(method, path, body)
    } catch (error) {
      if (error instanceof AccountApiError) throw error
      throw new AccountApiError(0, 'network_error', 'The account service could not be reached.')
    }
    return result
  }

  async function ok(method: string, path: string, body?: unknown): Promise<TransportResult> {
    const result = await call(method, path, body)
    if (!result.ok) throw toError(result)
    return result
  }

  const uploadBody = (input: UploadInput) => ({
    name: input.name, code: input.code, data_version: input.dataVersion, app_version: input.appVersion,
  })
  const id = (value: string) => encodeURIComponent(value)

  return {
    async getAccount(): Promise<Account | null> {
      const result = await call('GET', '/v1/account')
      if (result.status === 401) return null
      // A session whose sign-up has not been completed answers 403 signup_required on every /v1 route.
      if (result.status === 403 && toError(result).code === 'signup_required') return null
      if (!result.ok) throw toError(result)
      const r = asRaw(result.data)
      const name = asRaw(r.public_name)
      const limits = asRaw(r.limits)
      const usage = asRaw(r.usage)
      return {
        userId: String(r.user_id),
        publicName: { name: String(name.name), tag: String(name.tag) },
        limits: { cloudBuilds: Number(limits.cloud_builds), profileBuilds: Number(limits.profile_builds) },
        usage: { cloudBuilds: Number(usage.cloud_builds), profileBuilds: Number(usage.profile_builds) },
      }
    },

    async getSignupOffer(): Promise<SignupOffer | null> {
      const result = await call('GET', '/v1/account/signup')
      if (result.status === 404 || result.status === 401) return null
      if (!result.ok) throw toError(result)
      const r = asRaw(result.data)
      const preview = r.preview ? asRaw(r.preview) : null
      return {
        suggestedName: String(r.suggested_name),
        preview: preview ? { name: String(preview.name), tag: String(preview.tag) } : null,
      }
    },

    async completeSignup(name: string): Promise<void> {
      await ok('POST', '/v1/account/signup', { name })
    },

    async renameHandle(name: string): Promise<{ name: string; tag: string }> {
      const result = await ok('POST', '/v1/account/handle', { name })
      const r = asRaw(asRaw(result.data).public_name)
      return { name: String(r.name), tag: String(r.tag) }
    },

    async signOut(): Promise<void> {
      await ok('POST', '/v1/account/signout')
    },

    async signOutEverywhere(): Promise<void> {
      await ok('POST', '/v1/account/signout-everywhere')
    },

    async listCloudBuilds(): Promise<CloudBuild[]> {
      const result = await ok('GET', '/v1/cloud/builds')
      const builds = asRaw(result.data).builds
      return Array.isArray(builds) ? builds.map(mapBuild) : []
    },

    async getCloudBuild(cloudBuildId: string): Promise<{ build: CloudBuild; code: string }> {
      const result = await ok('GET', `/v1/cloud/builds/${id(cloudBuildId)}`)
      const r = asRaw(result.data)
      return { build: mapBuild(r.summary), code: String(r.code) }
    },

    async getRevision(cloudBuildId: string, revisionId: string): Promise<{ build: CloudBuild; code: string }> {
      const result = await ok('GET', `/v1/cloud/builds/${id(cloudBuildId)}/revisions/${id(revisionId)}`)
      const r = asRaw(result.data)
      return { build: mapBuild(r.summary), code: String(r.code) }
    },

    async createCloudBuild(input: UploadInput & { allowDuplicate: boolean }): Promise<CreateResult> {
      const result = await ok('POST', '/v1/cloud/builds', { ...uploadBody(input), allow_duplicate: input.allowDuplicate })
      const r = asRaw(result.data)
      if (r.match) {
        const m = asRaw(r.match)
        return { kind: 'match', cloudBuildId: String(m.cloud_build_id), name: String(m.name) }
      }
      return { kind: 'created', build: mapBuild(r.summary) }
    },

    async uploadRevision(cloudBuildId: string, input: UploadInput & { baseRevisionId: string }): Promise<CloudBuild> {
      const result = await ok('PUT', `/v1/cloud/builds/${id(cloudBuildId)}`, {
        base_revision_id: input.baseRevisionId, ...uploadBody(input),
      })
      return mapBuild(asRaw(result.data).summary)
    },

    async deleteCloudBuild(cloudBuildId: string): Promise<void> {
      await ok('DELETE', `/v1/cloud/builds/${id(cloudBuildId)}`)
    },

    async updateNamedLink(
      cloudBuildId: string,
      change: { slug?: string; listed?: boolean; revisionId?: string },
    ): Promise<NamedLink> {
      const body: Raw = {}
      if (change.slug !== undefined) body.slug = change.slug
      if (change.listed !== undefined) body.listed = change.listed
      if (change.revisionId !== undefined) body.revision_id = change.revisionId
      const result = await ok('PUT', `/v1/cloud/builds/${id(cloudBuildId)}/link`, body)
      const link = mapLink(asRaw(result.data).named_link)
      if (!link) throw new AccountApiError(result.status, 'invalid_response', 'The service returned no link.')
      return link
    },

    async deleteNamedLink(cloudBuildId: string): Promise<void> {
      await ok('DELETE', `/v1/cloud/builds/${id(cloudBuildId)}/link`)
    },

    async startReauth(): Promise<string> {
      const result = await ok('POST', '/v1/account/reauth')
      return String(asRaw(result.data).authorize_url)
    },

    async exportAccount(): Promise<unknown> {
      const result = await ok('GET', '/v1/account/export')
      return result.data
    },

    async deleteAccount(): Promise<void> {
      await ok('DELETE', '/v1/account')
    },
  }
}

export type AccountsApi = ReturnType<typeof createAccountsApi>

/** A public named link (/u/<handle>/<slug>). Anonymous read: no cookies, no session. */
export async function fetchNamedLink(
  handle: string,
  slug: string,
  opts: { base?: string; fetchImpl?: typeof fetch } = {},
): Promise<{ name: string; code: string; dataVersion: string | null }> {
  const base = (opts.base ?? getShareBase()).replace(/\/+$/, '')
  const doFetch = opts.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args))
  let res: Response
  try {
    res = await doFetch(`${base}/u/${encodeURIComponent(handle)}/${encodeURIComponent(slug)}`, {
      method: 'GET',
      credentials: 'omit',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch {
    throw new AccountApiError(0, 'network_error', 'The link could not be loaded. Check your connection and try again.')
  }
  let data: unknown = null
  try { data = await res.json() } catch { /* not JSON */ }
  if (res.status === 410) throw new AccountApiError(410, 'removed_by_owner', 'This build was removed by its owner.')
  if (!res.ok) throw toError({ ok: false, status: res.status, data })
  const r = asRaw(data)
  if (typeof r.code !== 'string' || !r.code.startsWith('tli1_')) {
    throw new AccountApiError(res.status, 'invalid_response', 'The link did not return a build code.')
  }
  return { name: String(r.name ?? ''), code: r.code, dataVersion: typeof r.data_version === 'string' && r.data_version ? r.data_version : null }
}

let defaultApi: AccountsApi | null = null

/** The shared accounts client for the running shell. */
export function getAccountsApi(): AccountsApi {
  if (!defaultApi) defaultApi = createAccountsApi(defaultAccountTransport())
  return defaultApi
}
