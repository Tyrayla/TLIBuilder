// ── Build-code share service ─────────────────────────────────────────────────
// The build-code share service is a PUBLIC host, separate from the local Python
// backend. Share calls never go through the local backend or Electron IPC — they
// are plain fetches to SHARE_BASE. This is the ONE exception to the "renderer
// talks to the backend only via api.*" rule, and it lives here, apart from
// client.ts, so the boundary is visible in the file layout.
//
// The base URL is configurable at build time via the Vite env var
// VITE_SHARE_BASE_URL; it falls back to production.

const _shareEnv = (import.meta as unknown as { env?: Record<string, string | undefined> }).env
const SHARE_BASE = (_shareEnv?.VITE_SHARE_BASE_URL ?? 'https://api.tlibuilder.com').replace(/\/+$/, '')

export function getShareBase(): string {
  return SHARE_BASE
}

const MAX_SHARE_CODE_BYTES = 512 * 1024 // 512 KB — more than enough for any build code

async function postToShareService<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${SHARE_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  })
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function getFromShareService(path: string): Promise<string> {
  // The share service returns the raw tli1_ code as text/plain.
  const res = await fetch(`${SHARE_BASE}${path}`, {
    signal: AbortSignal.timeout(15000),
  })
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  const len = Number(res.headers.get('content-length') ?? 0)
  if (len > MAX_SHARE_CODE_BYTES) throw new Error('Shared build code exceeds size limit')
  // No Content-Length fallback: buffers entire response before rejecting — acceptable
  // given threat model; a streaming reader would be needed to truly bound a hostile server.
  const text = await res.text()
  if (text.length > MAX_SHARE_CODE_BYTES) throw new Error('Shared build code exceeds size limit')
  return text
}

/** Publish a build code to the share service; returns its id and shareable url. */
export function shareBuildCode(code: string): Promise<{ id: string; url: string }> {
  return postToShareService<{ id: string; url: string }>('/b', { code })
}

/** Fetch a previously-shared build code by id. Returns the raw tli1_ string. */
export function fetchSharedBuildCode(id: string): Promise<string> {
  return getFromShareService(`/b/${id}`)
}
