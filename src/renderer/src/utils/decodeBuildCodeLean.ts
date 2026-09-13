// decodeBuildCodeLean.ts — a lean, READ-ONLY, pure-TS port of the wire-format layer of
// backend/build_code.py's `_decompress_and_parse` (prefix check → base64url decode → bounded zlib
// inflate → JSON parse). This is for the share-link overview page ONLY: it needs to read a build's
// gear/skills/hero-trait selection to render a summary, without booting the full Pyodide/Python
// engine just to display a read-only page.
//
// Deliberately does NOT replicate `_migrate` (the v1->v2 condition-state merge) — the overview page
// never reads `conditionState`/`conditions`, only `gear`/`skills`/`traitId`, none of which the v1->v2
// migration touches, so there's nothing here that needs migrating.
//
// KEEP IN SYNC: if `backend/build_code.py`'s wire format ever changes (CODE_PREFIX, the
// base64url/zlib/JSON pipeline, or SCHEMA_VERSION's *meaning*), this needs a matching update or old/
// new share links will render wrong. That file's own module docstring documents the pipeline; this
// is a second, independent implementation of the same read-only slice — see the private share
// service's `build_code.py` (a "lean, validation-only port") for the sibling precedent.
//
// Uses the standard Compression Streams API (`DecompressionStream('deflate')`) rather than adding a
// dependency like pako — 'deflate' is the zlib-wrapped (RFC 1950) format, which is exactly what
// Python's `zlib.compress()` produces. Supported in browsers and in the Cloudflare Workers runtime
// that also renders this build's OG tags server-side, so the same implementation serves both.

const CODE_PREFIX = 'tli1'
// Mirrors build_code.py's MAX_DECOMPRESSED_BYTES zip-bomb guard.
const MAX_DECOMPRESSED_BYTES = 1_000_000
// The highest schema version this lean decoder has ever been checked against gear/skills/traitId
// for. NOT the same guard as backend/build_code.py's SCHEMA_VERSION forward-version check (which
// covers the full format, including conditions) — this only needs to know whether a FUTURE bump
// could have restructured the fields this decoder actually reads. Bump this only after confirming
// a new schema version doesn't change gear/skills/traitId's shape.
const MAX_KNOWN_SCHEMA_VERSION = 2

export class LeanBuildCodeError extends Error {}

function base64UrlDecode(b64url: string): Uint8Array {
  const padded = b64url + '='.repeat((4 - (b64url.length % 4)) % 4)
  const standard = padded.replace(/-/g, '+').replace(/_/g, '/')
  let binary: string
  try {
    binary = atob(standard)
  } catch {
    throw new LeanBuildCodeError('Build code is not valid base64.')
  }
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

async function inflateZlibBounded(bytes: Uint8Array): Promise<Uint8Array> {
  // `new Uint8Array(bytes)` copies into a fresh, definite ArrayBuffer-backed view — both to satisfy
  // TS's stricter typed-array generics (a plain Uint8Array's `.buffer` is typed ArrayBufferLike,
  // which could in principle be a SharedArrayBuffer) and, more importantly, because writing a BARE
  // ArrayBuffer (rather than a TypedArray view) to this writer is actively wrong at runtime: Node's
  // WritableStreamDefaultWriter implementation throws ERR_INVALID_ARG_TYPE on a raw ArrayBuffer chunk
  // internally, and since that rejection was only ever swallowed by a bare `.catch(() => {})` here,
  // the read loop below hung forever waiting for data a failed write had silently never produced.
  // Confirmed by isolating this outside the codebase entirely — write a real Uint8Array, it works.
  const view = new Uint8Array(bytes)

  const ds = new DecompressionStream('deflate')
  const writer = ds.writable.getWriter()
  const writeDone = writer.write(view).then(() => writer.close())
  // The read loop below is the real error signal (a corrupt stream reliably rejects reader.read()
  // itself) — this just stops an unawaited rejection here from logging as unhandled when the read
  // loop's own catch already fires and returns before ever reaching `await writeDone`.
  writeDone.catch(() => {})

  const reader = ds.readable.getReader()
  const chunks: Uint8Array[] = []
  let total = 0
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      total += value.byteLength
      if (total > MAX_DECOMPRESSED_BYTES) {
        // Tear the stream down explicitly rather than just throwing past it — leaving the reader/
        // writer half-open here is harmless (nothing keeps reading), but a cancelled/aborted stream
        // is the honest terminal state for "we're deliberately walking away mid-decompression."
        await reader.cancel().catch(() => {})
        await writer.abort().catch(() => {})
        throw new LeanBuildCodeError('Build code exceeds the maximum allowed size.')
      }
      chunks.push(value)
    }
    await writeDone
  } catch (e) {
    if (e instanceof LeanBuildCodeError) throw e
    throw new LeanBuildCodeError('Build code is corrupt.')
  }
  const out = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) { out.set(chunk, offset); offset += chunk.byteLength }
  return out
}

/**
 * Decode a `tli1_...` build code into its raw JSON object — gear/skills/hero-trait fields as
 * stored on the wire, NOT rehydrated (legendary gear items still need resolving against the
 * legendary-gear catalog; see the overview page's gear-resolution step) and NOT migrated.
 * Throws LeanBuildCodeError on anything structurally invalid.
 */
export async function decodeBuildCodeLean(code: string): Promise<Record<string, unknown>> {
  const trimmed = code.trim()
  const sep = trimmed.indexOf('_')
  // Split on the FIRST underscore only — base64url's own alphabet uses '_' (in place of '/'), so a
  // naive split('_') would cut into the payload itself, not just the "tli1" prefix separator. Mirrors
  // Python's `code.partition("_")`, which is first-occurrence by definition.
  if (sep < 0 || trimmed.slice(0, sep) !== CODE_PREFIX) {
    throw new LeanBuildCodeError('Unrecognized build code — wrong prefix or version.')
  }
  const b64 = trimmed.slice(sep + 1)

  const compressed = base64UrlDecode(b64)
  const raw = await inflateZlibBounded(compressed)

  let build: unknown
  try {
    build = JSON.parse(new TextDecoder('utf-8').decode(raw))
  } catch {
    throw new LeanBuildCodeError('Build code does not contain valid JSON.')
  }
  if (typeof build !== 'object' || build === null || Array.isArray(build)) {
    throw new LeanBuildCodeError('Build code has an unexpected structure.')
  }
  const record = build as Record<string, unknown>
  // A version newer than this decoder has ever been checked against might restructure gear/
  // skills/traitId in ways it can't know about — bail rather than silently mis-render. (Older
  // versions are fine: the only migration that exists, v1->v2, doesn't touch those fields — see
  // this file's module docstring.) A non-numeric `v` is rejected outright too, mirroring
  // backend/build_code.py's `_migrate` (`not isinstance(from_version, int)`) — falling through would
  // treat an adversarial/malformed version marker as an unknown-but-trusted schema.
  if ('v' in record && typeof record.v !== 'number') {
    throw new LeanBuildCodeError('Build code has an invalid schema version.')
  }
  if (typeof record.v === 'number' && record.v > MAX_KNOWN_SCHEMA_VERSION) {
    throw new LeanBuildCodeError('This build code is from a newer version of the app.')
  }
  return record
}
