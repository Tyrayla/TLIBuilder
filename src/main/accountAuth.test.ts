import { describe, it, expect, vi } from 'vitest'
import { createHash } from 'node:crypto'
import {
  generatePkce,
  startLoopbackListener,
  createTokenVault,
  createAccountAuth,
  isAllowedAccountPath,
  type TokenVaultDeps,
} from './accountAuth'

function memoryVault(available = true) {
  const files = new Map<string, Buffer>()
  const deps: TokenVaultDeps = {
    isEncryptionAvailable: () => available,
    encryptString: (s) => Buffer.from([...s].reverse().join('')),
    decryptString: (b) => [...b.toString()].reverse().join(''),
    readFile: (p) => { const f = files.get(p); if (!f) throw new Error('ENOENT'); return f },
    writeFile: (p, d) => { files.set(p, d) },
    removeFile: (p) => { files.delete(p) },
    path: 'token.bin',
  }
  return { vault: createTokenVault(deps), files }
}

const BASE = 'https://api.example.test'

describe('pkce', () => {
  it('derives an S256 challenge from a high-entropy verifier', () => {
    const { verifier, challenge } = generatePkce()
    expect(verifier).toMatch(/^[A-Za-z0-9_-]{43,128}$/)
    expect(challenge).toBe(createHash('sha256').update(verifier).digest('base64url'))
    expect(generatePkce().verifier).not.toBe(verifier)
  })
})

describe('token vault', () => {
  it('stores the token encrypted and reads it back', () => {
    const { vault, files } = memoryVault()
    vault.save('secret-token')
    expect(files.get('token.bin')!.toString()).not.toContain('secret-token')
    expect(vault.load()).toBe('secret-token')
  })

  it('refuses to store when OS encryption is unavailable (no plaintext fallback)', () => {
    const { vault, files } = memoryVault(false)
    expect(() => vault.save('t')).toThrow(/encryption/i)
    expect(files.size).toBe(0)
  })

  it('clear removes the token', () => {
    const { vault } = memoryVault()
    vault.save('t')
    vault.clear()
    expect(vault.load()).toBeNull()
  })

  it('treats an unreadable file as signed out', () => {
    const { files } = memoryVault()
    files.set('token.bin', Buffer.from('garbage'))
    const deps = { decryptString: () => { throw new Error('bad') } }
    expect(createTokenVault({ ...(vaultDeps(files)), ...deps }).load()).toBeNull()
  })
})

function vaultDeps(files: Map<string, Buffer>): TokenVaultDeps {
  return {
    isEncryptionAvailable: () => true,
    encryptString: (s) => Buffer.from(s),
    decryptString: (b) => b.toString(),
    readFile: (p) => files.get(p)!,
    writeFile: (p, d) => { files.set(p, d) },
    removeFile: (p) => { files.delete(p) },
    path: 'token.bin',
  }
}

describe('loopback listener', () => {
  it('binds 127.0.0.1 on an unprivileged port and delivers the login code once', async () => {
    const listener = await startLoopbackListener({ timeoutMs: 5000 })
    expect(listener.port).toBeGreaterThanOrEqual(1024)
    const res = await fetch(`http://127.0.0.1:${listener.port}/callback?login_code=abcDEF123_-xyz`)
    expect(res.status).toBe(200)
    expect(await res.text()).toContain('You can close this tab')
    await expect(listener.code).resolves.toBe('abcDEF123_-xyz')
  })

  it('ignores requests that are not the callback or carry a malformed code', async () => {
    const listener = await startLoopbackListener({ timeoutMs: 5000 })
    const other = await fetch(`http://127.0.0.1:${listener.port}/other?login_code=abc`)
    expect(other.status).toBe(404)
    const bad = await fetch(`http://127.0.0.1:${listener.port}/callback?login_code=<script>`)
    expect(bad.status).toBe(400)
    const good = await fetch(`http://127.0.0.1:${listener.port}/callback?login_code=goodcode1`)
    expect(good.status).toBe(200)
    await expect(listener.code).resolves.toBe('goodcode1')
  })

  it('stops listening after the code arrives', async () => {
    const listener = await startLoopbackListener({ timeoutMs: 5000 })
    await fetch(`http://127.0.0.1:${listener.port}/callback?login_code=goodcode1`)
    await listener.code
    await expect(fetch(`http://127.0.0.1:${listener.port}/callback?login_code=another1`)).rejects.toThrow()
  })

  it('rejects and closes when the user never finishes', async () => {
    const listener = await startLoopbackListener({ timeoutMs: 50 })
    await expect(listener.code).rejects.toThrow(/timed out/i)
  })

  it('can be cancelled', async () => {
    const listener = await startLoopbackListener({ timeoutMs: 5000 })
    listener.close()
    await expect(listener.code).rejects.toThrow(/cancel/i)
  })
})

describe('account path allow-list', () => {
  it('permits only service API paths', () => {
    expect(isAllowedAccountPath('/v1/account')).toBe(true)
    expect(isAllowedAccountPath('/v1/cloud/builds/abc')).toBe(true)
    expect(isAllowedAccountPath('/b')).toBe(false)
    expect(isAllowedAccountPath('https://evil.test/v1/account')).toBe(false)
    expect(isAllowedAccountPath('//evil.test/v1/account')).toBe(false)
    expect(isAllowedAccountPath('/v1/../admin')).toBe(false)
    expect(isAllowedAccountPath('/v1/account\r\nX: y')).toBe(false)
  })
})

function setupAuth(opts: { fetchImpl?: typeof fetch; vaultAvailable?: boolean } = {}) {
  const { vault } = memoryVault(opts.vaultAvailable ?? true)
  const opened: string[] = []
  const calls: { url: string; init: RequestInit }[] = []
  const fetchImpl = opts.fetchImpl ?? (vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init })
    if (url.endsWith('/auth/desktop/exchange')) {
      return new Response(JSON.stringify({ session_token: 'sess-1', expires_at: 9 }), { status: 200 })
    }
    return new Response(JSON.stringify({ ok: true }), { status: 200 })
  }) as unknown as typeof fetch)
  const auth = createAccountAuth({
    apiBase: BASE,
    vault,
    fetchImpl,
    openBrowser: async (url) => { opened.push(url) },
    callbackTimeoutMs: 5000,
  })
  return { auth, vault, opened, calls, fetchImpl }
}

describe('desktop sign-in', () => {
  it('opens the system browser with the loopback port and PKCE challenge, then exchanges the code with the verifier', async () => {
    const { auth, vault, opened, calls } = setupAuth()
    const pending = auth.signIn()
    await vi.waitFor(() => expect(opened).toHaveLength(1))
    const start = new URL(opened[0])
    expect(`${start.origin}${start.pathname}`).toBe(`${BASE}/auth/discord/start`)
    expect(start.searchParams.get('client')).toBe('desktop')
    const port = Number(start.searchParams.get('port'))
    const challenge = start.searchParams.get('code_challenge')!
    expect(port).toBeGreaterThanOrEqual(1024)
    await fetch(`http://127.0.0.1:${port}/callback?login_code=login123`)
    expect(await pending).toEqual({ ok: true })
    const exchange = calls.find((c) => c.url.endsWith('/auth/desktop/exchange'))!
    const body = JSON.parse(String(exchange.init.body))
    expect(body.login_code).toBe('login123')
    expect(createHash('sha256').update(body.code_verifier).digest('base64url')).toBe(challenge)
    expect(vault.load()).toBe('sess-1')
  })

  it('fails without storing anything when encryption is unavailable', async () => {
    const { auth, vault, opened } = setupAuth({ vaultAvailable: false })
    const result = await auth.signIn()
    expect(result.ok).toBe(false)
    expect(opened).toHaveLength(0)
    expect(vault.load()).toBeNull()
  })

  it('reports a failed exchange and stores no token', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: { code: 'invalid_login_code' } }), { status: 400 })) as unknown as typeof fetch
    const { auth, vault, opened } = setupAuth({ fetchImpl })
    const pending = auth.signIn()
    await vi.waitFor(() => expect(opened).toHaveLength(1))
    const port = new URL(opened[0]).searchParams.get('port')
    await fetch(`http://127.0.0.1:${port}/callback?login_code=login123`)
    expect((await pending).ok).toBe(false)
    expect(vault.load()).toBeNull()
  })
})

describe('authenticated requests', () => {
  async function signedIn() {
    const ctx = setupAuth()
    ctx.vault.save('sess-1')
    return ctx
  }

  it('attaches the bearer token and no cookies', async () => {
    const { auth, calls } = await signedIn()
    await auth.request('GET', '/v1/account')
    const init = calls[0].init
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer sess-1')
    expect(init.credentials).toBe('omit')
  })

  it('refuses a path outside the service API without a network call', async () => {
    const { auth, calls } = await signedIn()
    const result = await auth.request('GET', 'https://evil.test/x')
    expect(result.ok).toBe(false)
    expect(calls).toHaveLength(0)
  })

  it('refuses a method outside the allowed set', async () => {
    const { auth, calls } = await signedIn()
    const result = await auth.request('TRACE', '/v1/account')
    expect(result.ok).toBe(false)
    expect(calls).toHaveLength(0)
  })

  it('answers unauthenticated without calling out when signed out', async () => {
    const { auth, calls } = setupAuth()
    const result = await auth.request('GET', '/v1/account')
    expect(result.status).toBe(401)
    expect(calls).toHaveLength(0)
  })

  it('clears the stored token when the service says it is no longer valid', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: { code: 'unauthenticated' } }), { status: 401 })) as unknown as typeof fetch
    const { auth, vault } = setupAuth({ fetchImpl })
    vault.save('old')
    await auth.request('GET', '/v1/account')
    expect(vault.load()).toBeNull()
  })

  it('stores a rotated token from the response header', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', { status: 200, headers: { 'X-TLI-Session-Token': 'sess-2' } })) as unknown as typeof fetch
    const { auth, vault } = setupAuth({ fetchImpl })
    vault.save('sess-1')
    await auth.request('GET', '/v1/account')
    expect(vault.load()).toBe('sess-2')
  })

  it('never returns the token to the renderer', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', { status: 200, headers: { 'X-TLI-Session-Token': 'sess-2' } })) as unknown as typeof fetch
    const { auth, vault } = setupAuth({ fetchImpl })
    vault.save('sess-1')
    const result = await auth.request('GET', '/v1/account')
    expect(JSON.stringify(result)).not.toContain('sess-')
  })

  it('sign-out revokes remotely when it can and always clears the local token', async () => {
    const fetchImpl = vi.fn(async () => { throw new Error('offline') }) as unknown as typeof fetch
    const { auth, vault } = setupAuth({ fetchImpl })
    vault.save('sess-1')
    await auth.signOut()
    expect(vault.load()).toBeNull()
  })
})

describe('reauth', () => {
  it('opens only an authorize URL on the service origin', async () => {
    const { auth, opened } = setupAuth()
    expect((await auth.reauth(`${BASE}/auth/discord/start?client=web&reauth=1`)).ok).toBe(true)
    expect(opened).toEqual([`${BASE}/auth/discord/start?client=web&reauth=1`])
    expect((await auth.reauth('https://evil.test/auth')).ok).toBe(false)
    expect(opened).toHaveLength(1)
  })
})
