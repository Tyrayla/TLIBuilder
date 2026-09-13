// Build-code share service. This public host is intentionally separate from the local backend.
import { errorFromResponse, normalizeError } from '../errors/tliError'

const _shareEnv = (import.meta as unknown as { env?: Record<string, string | undefined> }).env
const SHARE_BASE = (_shareEnv?.VITE_SHARE_BASE_URL ?? 'https://api.tlibuilder.com').replace(/\/+$/, '')
const MAX_SHARE_CODE_BYTES = 512 * 1024
const MAX_SHARE_ERROR_BYTES = 16 * 1024

export function getShareBase(): string {
  return SHARE_BASE
}

async function readErrorBody(res: Response): Promise<unknown> {
  const declaredLength = Number(res.headers.get('content-length') ?? 0)
  if (declaredLength > MAX_SHARE_ERROR_BYTES || !res.body) return null
  const reader = res.body.getReader()
  const chunks: Uint8Array[] = []
  let size = 0
  while (true) {
    const next = await reader.read()
    if (next.done) break
    size += next.value.byteLength
    if (size > MAX_SHARE_ERROR_BYTES) {
      await reader.cancel()
      return null
    }
    chunks.push(next.value)
  }
  const bytes = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
  try { return JSON.parse(new TextDecoder().decode(bytes)) } catch { return null }
}

// Client-computed, display-only build summary sent alongside the code so the share-service
// overview page and its Discord/Twitter embed have something to show without the service ever
// decoding the build itself. Mirrors PreviewPayload in the share service's main.py exactly —
// field names and bounds must stay in sync with that model.
export interface SharePreview {
  hero: string
  trait: string
  level: number
  main_skill: string
  // Optional: omitted (never a reason to fail the whole preview) when the resolved icon isn't on
  // the service's own known CDN — e.g. a hero-trait record whose data hasn't been rehosted from
  // its original source yet. See buildSharePreview() in utils/buildSharePreview.ts.
  icon_url?: string
  max_life: number
  max_mana: number
  max_energy_shield: number
  total_dps: number
  fire_resist: number
  cold_resist: number
  lightning_resist: number
  erosion_resist: number
  movement_speed: number
}

async function postToShareService<T>(path: string, body: unknown): Promise<T> {
  const operation = `share.post.${path.replace(/^\//, '')}`
  try {
    const res = await fetch(`${SHARE_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    })
    if (!res.ok) {
      // The share service is a small, foreign service (see its own README) — its rejection body is
      // plain text or a bare {"detail": ...}, never this app's TliErrorPayload envelope, so
      // errorFromResponse's structured-match branch never fires for it. Read the raw body and pass it
      // through as the fallback message so a real validation rejection (e.g. "icon_url is not under an
      // allowed origin") reaches the user instead of collapsing to the generic registry title — this was
      // previously getting swallowed into a generic "service may be unavailable" message, misrepresenting
      // an actual rejection as an outage.
      const [parsedBody, rawDetail] = await Promise.all([
        readErrorBody(res.clone()),
        res.clone().text().catch(() => ''),
      ])
      throw errorFromResponse(
        parsedBody,
        'TLI-SHARE-001',
        operation,
        rawDetail ? `Share service request failed (${res.status}): ${rawDetail}` : `Share service request failed (${res.status}).`,
      )
    }
    return res.json() as Promise<T>
  } catch (error) {
    throw normalizeError(error, 'TLI-SHARE-001', operation)
  }
}

async function getFromShareService(path: string): Promise<string> {
  const operation = `share.get.${path.replace(/^\//, '')}`
  try {
    const res = await fetch(`${SHARE_BASE}${path}`, { signal: AbortSignal.timeout(15000) })
    if (!res.ok) {
      throw errorFromResponse(
        await readErrorBody(res),
        'TLI-SHARE-001',
        operation,
        `Shared build could not be loaded (${res.status}).`,
      )
    }
    const len = Number(res.headers.get('content-length') ?? 0)
    if (len > MAX_SHARE_CODE_BYTES) throw new Error('Shared build code exceeds size limit')
    const text = await res.text()
    if (text.length > MAX_SHARE_CODE_BYTES) throw new Error('Shared build code exceeds size limit')
    return text
  } catch (error) {
    throw normalizeError(error, 'TLI-SHARE-001', operation)
  }
}

/** Publish a build code to the share service; returns its id and shareable url.
 *  `preview` is optional and purely additive — omit it (e.g. the caller couldn't compute
 *  it, or the service rejects it) and the share still succeeds exactly as before. */
export function shareBuildCode(code: string, preview?: SharePreview): Promise<{ id: string; url: string }> {
  return postToShareService<{ id: string; url: string }>('/b', preview ? { code, preview } : { code })
}

export function fetchSharedBuildCode(id: string): Promise<string> {
  return getFromShareService(`/b/${id}`)
}

/** Best-effort fetch of a share's preview snapshot — `null` on any failure (unknown id, no preview
 *  ever submitted for it, network error). Never throws: the overview page still has a full gear/
 *  skills/trait render without a preview, just no headline-stats banner, so a preview miss is never
 *  worth surfacing as an error to the caller. Routed through this wrapper (rather than a raw
 *  `fetch`) for the same timeout every other share-service call gets. */
export async function fetchSharePreview(id: string): Promise<SharePreview | null> {
  try {
    const res = await fetch(`${SHARE_BASE}/b/${id}/preview`, { signal: AbortSignal.timeout(15000) })
    if (!res.ok) return null
    return await res.json() as SharePreview
  } catch {
    return null
  }
}
