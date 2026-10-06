// Desktop account sign-in and authenticated requests (main process).
//
// Flow (RFC 8252 + PKCE, see docs/HOSTED_ACCOUNT_PLATFORM_PLAN.md "Desktop sign-in"):
//   1. listen on 127.0.0.1 on a random port, make a PKCE verifier and S256 challenge;
//   2. open the SYSTEM browser at the service's /auth/discord/start (never an embedded window);
//   3. the service redirects the browser to http://127.0.0.1:<port>/callback?login_code=...;
//   4. exchange login_code + code_verifier at /auth/desktop/exchange for a session token;
//   5. keep the token with Electron safeStorage and send it as a bearer token. The renderer never
//      sees it: it only sends requests through `request`, which this module authenticates.
//
// Electron is injected, not imported, so the module is testable under plain Node.
import { createServer, type Server } from 'node:http'
import { createHash, randomBytes } from 'node:crypto'

// ── PKCE ─────────────────────────────────────────────────────────────────────
export function generatePkce(): { verifier: string; challenge: string } {
  const verifier = randomBytes(32).toString('base64url')
  const challenge = createHash('sha256').update(verifier).digest('base64url')
  return { verifier, challenge }
}

// ── Token vault ──────────────────────────────────────────────────────────────
export interface TokenVaultDeps {
  isEncryptionAvailable: () => boolean
  encryptString: (plain: string) => Buffer
  decryptString: (cipher: Buffer) => string
  readFile: (path: string) => Buffer
  writeFile: (path: string, data: Buffer) => void
  removeFile: (path: string) => void
  path: string
}

export interface TokenVault {
  isAvailable(): boolean
  save(token: string): void
  load(): string | null
  clear(): void
}

export function createTokenVault(deps: TokenVaultDeps): TokenVault {
  return {
    isAvailable: () => deps.isEncryptionAvailable(),
    save(token) {
      // No plaintext fallback: without OS-backed encryption the user stays signed out.
      if (!deps.isEncryptionAvailable()) throw new Error('OS encryption is unavailable, so the session cannot be stored safely.')
      deps.writeFile(deps.path, deps.encryptString(token))
    },
    load() {
      try {
        const token = deps.decryptString(deps.readFile(deps.path))
        return token || null
      } catch {
        return null
      }
    },
    clear() {
      try { deps.removeFile(deps.path) } catch { /* already gone */ }
    },
  }
}

// ── Loopback listener ────────────────────────────────────────────────────────
const LOGIN_CODE = /^[A-Za-z0-9_-]{8,256}$/
const CLOSE_PAGE = '<!doctype html><meta charset="utf-8"><title>TLI Builder</title>'
  + '<body style="font-family:system-ui;background:#111;color:#eee;padding:2rem">'
  + '<h1>Signed in</h1><p>You can close this tab and return to TLI Builder.</p></body>'

const FAILURE_REASON = /^[a-z_]{1,32}$/
const FAILURE_PAGE = '<!doctype html><meta charset="utf-8"><title>TLI Builder</title>'
  + '<body style="font-family:system-ui;background:#111;color:#eee;padding:2rem">'
  + '<h1>Sign-in did not complete</h1><p>You can close this tab and try again in TLI Builder.</p></body>'

export interface LoopbackListener {
  port: number
  code: Promise<string>
  close(): void
}

export function startLoopbackListener(opts: { timeoutMs: number }): Promise<LoopbackListener> {
  return new Promise((resolveStart, rejectStart) => {
    let settled = false
    let resolveCode!: (code: string) => void
    let rejectCode!: (error: Error) => void
    const code = new Promise<string>((res, rej) => { resolveCode = res; rejectCode = rej })
    code.catch(() => { /* surfaced to the awaiting caller */ })

    const server: Server = createServer((req, res) => {
      const reply = (status: number, body: string): void => {
        res.writeHead(status, {
          'Content-Type': 'text/html; charset=utf-8',
          'Cache-Control': 'no-store',
          'Referrer-Policy': 'no-referrer',
          'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'",
          Connection: 'close',
        })
        res.end(body)
      }
      let url: URL
      try { url = new URL(req.url ?? '/', 'http://127.0.0.1') } catch { reply(400, 'Bad request'); return }
      if (req.method !== 'GET' || url.pathname !== '/callback') { reply(404, 'Not found'); return }
      // The service reports a failed sign-in as ?error=<reason> instead of a login code.
      const failure = url.searchParams.get('error')
      if (failure !== null) {
        if (!FAILURE_REASON.test(failure)) { reply(400, 'Bad request'); return }
        if (settled) { reply(404, 'Not found'); return }
        settled = true
        res.once('finish', () => finish())
        reply(200, FAILURE_PAGE)
        rejectCode(new Error(`Sign-in did not complete (${failure}).`))
        return
      }
      const loginCode = url.searchParams.get('login_code') ?? ''
      if (!LOGIN_CODE.test(loginCode)) { reply(400, 'Bad request'); return }
      if (settled) { reply(404, 'Not found'); return }
      settled = true
      res.once('finish', () => finish())
      reply(200, CLOSE_PAGE)
      resolveCode(loginCode)
    })

    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      rejectCode(new Error('Sign-in timed out.'))
      finish()
    }, opts.timeoutMs)

    function finish(): void {
      clearTimeout(timer)
      server.close()
      server.closeAllConnections()
    }

    server.once('error', (error) => { clearTimeout(timer); rejectStart(error) })
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      if (!address || typeof address === 'string') { rejectStart(new Error('Could not open a loopback port.')); return }
      resolveStart({
        port: address.port,
        code,
        close() {
          if (!settled) { settled = true; rejectCode(new Error('Sign-in cancelled.')) }
          finish()
        },
      })
    })
  })
}

// ── Authenticated requests ───────────────────────────────────────────────────
const ALLOWED_METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
const ALLOWED_PATH = /^\/v1\/[A-Za-z0-9_\-./%?=&]*$/

/** The renderer may only reach the service's /v1 API: never an arbitrary URL, host, or traversal path. */
export function isAllowedAccountPath(path: string): boolean {
  return typeof path === 'string' && ALLOWED_PATH.test(path)
    && !path.includes('..') && !path.includes('//') && !/%2e/i.test(path)
}

export interface BridgeResult {
  ok: boolean
  status: number
  data: unknown
}

const REQUEST_TIMEOUT_MS = 20_000

const unauthenticated: BridgeResult = {
  ok: false, status: 401, data: { error: { code: 'unauthenticated', message: 'Not signed in.' } },
}

export function createAccountAuth(deps: {
  apiBase: string
  vault: TokenVault
  fetchImpl: typeof fetch
  openBrowser: (url: string) => Promise<void>
  callbackTimeoutMs?: number
}) {
  const apiBase = deps.apiBase.replace(/\/+$/, '')
  const apiOrigin = new URL(apiBase).origin

  async function readJson(res: Response): Promise<unknown> {
    try { return await res.json() } catch { return null }
  }

  async function signIn(): Promise<{ ok: boolean; error?: string }> {
    if (!deps.vault.isAvailable()) {
      return { ok: false, error: 'This computer cannot encrypt the sign-in session, so TLI Builder will not store it.' }
    }
    let listener: LoopbackListener | null = null
    try {
      listener = await startLoopbackListener({ timeoutMs: deps.callbackTimeoutMs ?? 300_000 })
      const { verifier, challenge } = generatePkce()
      const start = new URL(`${apiBase}/auth/discord/start`)
      start.searchParams.set('client', 'desktop')
      start.searchParams.set('port', String(listener.port))
      start.searchParams.set('code_challenge', challenge)
      await deps.openBrowser(start.toString())
      const loginCode = await listener.code
      const res = await deps.fetchImpl(`${apiBase}/auth/desktop/exchange`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'omit',
        body: JSON.stringify({ login_code: loginCode, code_verifier: verifier }),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      })
      const data = (await readJson(res)) as { session_token?: unknown } | null
      if (!res.ok || typeof data?.session_token !== 'string' || !data.session_token) {
        return { ok: false, error: 'Sign-in could not be completed.' }
      }
      deps.vault.save(data.session_token)
      return { ok: true }
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : 'Sign-in failed.' }
    } finally {
      listener?.close()
    }
  }

  async function request(method: string, path: string, body?: unknown): Promise<BridgeResult> {
    const verb = String(method).toUpperCase()
    if (!ALLOWED_METHODS.has(verb) || !isAllowedAccountPath(path)) {
      return { ok: false, status: 400, data: { error: { code: 'invalid_request', message: 'Request not allowed.' } } }
    }
    const token = deps.vault.load()
    if (!token) return unauthenticated
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` }
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    try {
      const res = await deps.fetchImpl(`${apiBase}${path}`, {
        method: verb,
        headers,
        credentials: 'omit',
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      })
      if (res.status === 401) deps.vault.clear()
      const rotated = res.headers.get('X-TLI-Session-Token')
      if (rotated && res.ok) {
        try { deps.vault.save(rotated) } catch { /* keep the still-valid previous token */ }
      }
      return { ok: res.ok, status: res.status, data: await readJson(res) }
    } catch {
      return { ok: false, status: 0, data: { error: { code: 'network_error', message: 'The account service could not be reached.' } } }
    }
  }

  async function signOut(): Promise<void> {
    if (deps.vault.load()) await request('POST', '/v1/account/signout').catch(() => undefined)
    deps.vault.clear()
  }

  async function reauth(authorizeUrl: string): Promise<{ ok: boolean; error?: string }> {
    let parsed: URL
    try { parsed = new URL(authorizeUrl) } catch { return { ok: false, error: 'Invalid sign-in address.' } }
    if (parsed.origin !== apiOrigin) return { ok: false, error: 'Sign-in address is not the TLI Builder service.' }
    await deps.openBrowser(parsed.toString())
    return { ok: true }
  }

  return { signIn, request, signOut, reauth }
}

export type AccountAuth = ReturnType<typeof createAccountAuth>
