import { api } from '../api/client'

/**
 * Thrown when an import input is a share link but the linked build could not be
 * fetched (service unreachable, network error, or unknown id). Lets callers
 * show a link-specific message instead of the generic "invalid code" error.
 */
export class ShareFetchError extends Error {
  constructor(message: string) {
    super(message)
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
  const trimmed = input.trim()

  // Treat the input as a share URL only if it looks like an http(s) URL AND
  // matches /b/<id>; otherwise treat it as a raw code.
  const urlMatch = trimmed.match(/\/b\/([A-Za-z0-9_-]+)\/?$/)
  if (/^https?:\/\//i.test(trimmed) && urlMatch) {
    try {
      const code = await api.fetchSharedBuildCode(urlMatch[1])
      // Validate before handing to the decoder — prevents an error page or
      // malformed response from the share service reaching the Python codec.
      if (!code.startsWith('tli1_')) {
        throw new ShareFetchError('Share service returned an invalid build code.')
      }
      return code
    } catch (e) {
      if (e instanceof ShareFetchError) throw e
      throw new ShareFetchError(e instanceof Error ? e.message : String(e))
    }
  }

  // A raw tli1_ build code — use as-is.
  return trimmed
}
