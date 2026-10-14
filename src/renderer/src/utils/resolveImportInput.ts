import { api } from '../api/client'
import { normalizeError, TliError } from '../errors/tliError'
import { AccountApiError, fetchNamedLink } from '../api/accounts'

/**
 * Thrown when an import input is a share link but the linked build could not be
 * fetched (service unreachable, network error, or unknown id). Lets callers
 * show a link-specific message instead of the generic "invalid code" error.
 */
export class ShareFetchError extends TliError {
  constructor(error: unknown) {
    super(normalizeError(error, 'TLI-SHARE-001', 'share.import').payload)
    this.name = 'ShareFetchError'
  }
}

/**
 * Normalises an import-field value into a raw tli1_ build code.
 *
 * - A share-service URL (an http(s) URL ending in `/b/<id>`) → the id is
 *   extracted and the raw code is fetched from the share service.
 * - Anything else (a raw tli1_ code — today's behaviour) → returned unchanged.
 *
 * The result is always a string ready to hand straight to api.decodeBuildCode().
 * Old raw codes keep working exactly as before; a pasted share link works in
 * the same field.
 */
export async function resolveImportInput(input: string): Promise<string> {
  return (await resolveImportSource(input)).code
}

/** A named link whose owner removed it. Shown as its own message instead of "invalid link". */
export class NamedLinkRemovedError extends ShareFetchError {
  constructor() {
    super(new TliError({
      code: 'TLI-SHARE-001',
      title: 'This build was removed',
      message: 'This build was removed by its owner.',
      operation: 'share.import.named-link',
      retryable: false,
    }))
    this.name = 'NamedLinkRemovedError'
  }
}

const NAMED_LINK_PATH = /^\/u\/([a-z0-9_.]{2,24}-\d{4})\/([a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?)\/?$/

/** `https://<host>/u/<name>-<tag>/<slug>` → its parts, or null for anything else. */
export function parseNamedLinkUrl(input: string): { handle: string; slug: string } | null {
  let url: URL
  try { url = new URL(input.trim()) } catch { return null }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return null
  const match = NAMED_LINK_PATH.exec(url.pathname)
  return match ? { handle: match[1], slug: match[2] } : null
}

/**
 * Like resolveImportInput, but also reports the game data version a named link was saved under so the
 * importer can warn when it differs from the current one. Raw codes and anonymous share links carry none.
 */
export async function resolveImportSource(
  input: string,
  deps: { fetchNamed?: (handle: string, slug: string) => Promise<{ name: string; code: string; dataVersion: string | null }> } = {},
): Promise<{ code: string; dataVersion: string | null }> {
  const trimmed = input.trim()

  const named = parseNamedLinkUrl(trimmed)
  if (named) {
    try {
      const fetchNamed = deps.fetchNamed ?? fetchNamedLink
      const result = await fetchNamed(named.handle, named.slug)
      return { code: result.code, dataVersion: result.dataVersion }
    } catch (e) {
      if (e instanceof AccountApiError && e.code === 'removed_by_owner') throw new NamedLinkRemovedError()
      throw new ShareFetchError(e)
    }
  }
  return { code: await resolveShareOrRaw(trimmed), dataVersion: null }
}

async function resolveShareOrRaw(trimmed: string): Promise<string> {

  // Treat the input as a share URL only if it looks like an http(s) URL AND
  // matches /b/<id>; otherwise treat it as a raw code.
  const urlMatch = trimmed.match(/\/b\/([A-Za-z0-9_-]+)\/?$/)
  if (/^https?:\/\//i.test(trimmed) && urlMatch) {
    try {
      const code = await api.fetchSharedBuildCode(urlMatch[1])
      // Validate before handing to the decoder — prevents an error page or
      // malformed response from the share service reaching the Python codec.
      if (!code.startsWith('tli1_')) {
        throw new ShareFetchError(new Error('Share service returned an invalid build code.'))
      }
      return code
    } catch (e) {
      if (e instanceof ShareFetchError) throw e
      throw new ShareFetchError(e)
    }
  }

  // A raw tli1_ build code — use as-is.
  return trimmed
}
