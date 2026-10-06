import { describe, it, expect } from 'vitest'
import zlib from 'node:zlib'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import {
  semanticBuildHash,
  syncStatus,
  recordsForAccount,
  planUpload,
  planDownload,
  planSharedLinkUpdate,
  resolveConflict,
  shortenBuildName,
  MAX_BUILD_NAME_LENGTH,
  type SyncRecord,
  type CloudBuildSummary,
} from '../utils/sync'

function encodeForTest(obj: unknown): string {
  const compressed = zlib.deflateSync(Buffer.from(JSON.stringify(obj), 'utf-8'), { level: 9 })
  return `tli1_${compressed.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}`
}

const record = (over: Partial<SyncRecord> = {}): SyncRecord => ({
  localBuildId: 'local-1',
  accountUserId: 'user-A',
  cloudBuildId: 'cloud-1',
  baseRevisionId: 'rev-1',
  baseSemanticHash: 'hash-1',
  ...over,
})

const cloud = (over: Partial<CloudBuildSummary> = {}): CloudBuildSummary => ({
  cloudBuildId: 'cloud-1',
  name: 'Fire Mage',
  currentRevisionId: 'rev-1',
  semanticHash: 'hash-1',
  updatedAt: 1_700_000_000,
  ...over,
})

describe('semanticBuildHash', () => {
  it('ignores id, createdAt and updatedAt', async () => {
    const a = await semanticBuildHash(encodeForTest({ v: 2, id: 'x', createdAt: 1, updatedAt: 2, name: 'Fire', slots: [] }))
    const b = await semanticBuildHash(encodeForTest({ v: 2, id: 'y', createdAt: 9, updatedAt: 10, name: 'Fire', slots: [] }))
    expect(a).toBe(b)
    expect(a).toMatch(/^[0-9a-f]{64}$/)
  })

  it('ignores key order', async () => {
    const a = await semanticBuildHash(encodeForTest({ v: 2, name: 'Fire', characterLevel: 90 }))
    const b = await semanticBuildHash(encodeForTest({ characterLevel: 90, name: 'Fire', v: 2 }))
    expect(a).toBe(b)
  })

  it('keeps name and notes in the hash', async () => {
    const base = await semanticBuildHash(encodeForTest({ v: 2, name: 'Fire', notes: 'a' }))
    expect(await semanticBuildHash(encodeForTest({ v: 2, name: 'Fire 2', notes: 'a' }))).not.toBe(base)
    expect(await semanticBuildHash(encodeForTest({ v: 2, name: 'Fire', notes: 'b' }))).not.toBe(base)
  })

  it('matches a known SHA-256 of the canonical JSON', async () => {
    // Contract shared with the service: sha256 of the decoded JSON with sorted keys, compact
    // separators, and id/createdAt/updatedAt removed.
    expect(await semanticBuildHash(encodeForTest({ v: 2, id: 'z', name: 'Fire' })))
      .toBe(await sha256Hex('{"name":"Fire","v":2}'))
  })

  it('sorts nested keys and preserves array order', async () => {
    const a = await semanticBuildHash(encodeForTest({ v: 2, gear: [{ b: 1, a: 2 }, { slot: 'x' }] }))
    const b = await semanticBuildHash(encodeForTest({ v: 2, gear: [{ a: 2, b: 1 }, { slot: 'x' }] }))
    const c = await semanticBuildHash(encodeForTest({ v: 2, gear: [{ slot: 'x' }, { a: 2, b: 1 }] }))
    expect(a).toBe(b)
    expect(a).not.toBe(c)
  })
})

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

describe('syncStatus', () => {
  it('is not-uploaded with no record', () => {
    expect(syncStatus({ record: undefined, localHash: 'h', cloud: undefined, activeUserId: 'user-A' })).toBe('not-uploaded')
  })

  it('treats another account\'s record as not-uploaded', () => {
    expect(syncStatus({ record: record({ accountUserId: 'user-B' }), localHash: 'hash-1', cloud: cloud(), activeUserId: 'user-A' }))
      .toBe('not-uploaded')
  })

  it('treats a signed-out guest as not-uploaded', () => {
    expect(syncStatus({ record: record(), localHash: 'hash-1', cloud: undefined, activeUserId: null })).toBe('not-uploaded')
  })

  it('is synced when nothing changed on either side', () => {
    expect(syncStatus({ record: record(), localHash: 'hash-1', cloud: cloud(), activeUserId: 'user-A' })).toBe('synced')
  })

  it('is local-changes when only the local hash moved', () => {
    expect(syncStatus({ record: record(), localHash: 'hash-2', cloud: cloud(), activeUserId: 'user-A' })).toBe('local-changes')
  })

  it('is cloud-newer when only the cloud revision moved', () => {
    expect(syncStatus({ record: record(), localHash: 'hash-1', cloud: cloud({ currentRevisionId: 'rev-2', semanticHash: 'h2' }), activeUserId: 'user-A' }))
      .toBe('cloud-newer')
  })

  it('is diverged when both moved', () => {
    expect(syncStatus({ record: record(), localHash: 'hash-2', cloud: cloud({ currentRevisionId: 'rev-2' }), activeUserId: 'user-A' }))
      .toBe('diverged')
  })

  it('reports local-changes without a cloud read when cloud state is unknown', () => {
    expect(syncStatus({ record: record(), localHash: 'hash-2', cloud: undefined, activeUserId: 'user-A' })).toBe('local-changes')
  })

  it('reports synced for an unread cloud when the local hash is unchanged', () => {
    expect(syncStatus({ record: record(), localHash: 'hash-1', cloud: undefined, activeUserId: 'user-A' })).toBe('synced')
  })

  it('reports cloud-missing when the cloud build was deleted', () => {
    expect(syncStatus({ record: record(), localHash: 'hash-1', cloud: null, activeUserId: 'user-A' })).toBe('cloud-missing')
  })
})

describe('recordsForAccount', () => {
  it('hides records that belong to another account', () => {
    const rs = [record({ localBuildId: 'a' }), record({ localBuildId: 'b', accountUserId: 'user-B' })]
    expect(recordsForAccount(rs, 'user-A').map((r) => r.localBuildId)).toEqual(['a'])
    expect(recordsForAccount(rs, null)).toEqual([])
  })
})

describe('planUpload', () => {
  const base = { activeUserId: 'user-A', name: 'Fire Mage' }

  it('requires sign-in', () => {
    expect(planUpload({ ...base, activeUserId: null, record: undefined, localHash: 'h', cloud: undefined }).kind).toBe('sign-in-required')
  })

  it('asks for a shorter name over the limit and pre-fills the first 50 characters', () => {
    const long = 'x'.repeat(60)
    const plan = planUpload({ ...base, name: long, record: undefined, localHash: 'h', cloud: undefined })
    expect(plan).toEqual({ kind: 'shorten-name', suggestedName: 'x'.repeat(MAX_BUILD_NAME_LENGTH) })
  })

  it('uploads an unlinked build as new (the service decides on a content match)', () => {
    expect(planUpload({ ...base, record: undefined, localHash: 'h', cloud: undefined })).toEqual({ kind: 'upload-new', allowDuplicate: false })
  })

  it('never uses another account\'s record to overwrite', () => {
    const plan = planUpload({ ...base, record: record({ accountUserId: 'user-B' }), localHash: 'h', cloud: cloud() })
    expect(plan).toEqual({ kind: 'upload-new', allowDuplicate: false })
  })

  it('uploads a locally changed linked build as a conditional write on its base revision', () => {
    expect(planUpload({ ...base, record: record(), localHash: 'hash-2', cloud: cloud() }))
      .toEqual({ kind: 'upload-revision', cloudBuildId: 'cloud-1', baseRevisionId: 'rev-1' })
  })

  it('does nothing for an unchanged linked build', () => {
    expect(planUpload({ ...base, record: record(), localHash: 'hash-1', cloud: cloud() }).kind).toBe('nothing-to-upload')
  })

  it('points at download when only the cloud moved', () => {
    expect(planUpload({ ...base, record: record(), localHash: 'hash-1', cloud: cloud({ currentRevisionId: 'rev-2' }) }).kind).toBe('cloud-newer')
  })

  it('opens the conflict screen for a diverged build', () => {
    const plan = planUpload({ ...base, record: record(), localHash: 'hash-2', cloud: cloud({ currentRevisionId: 'rev-2' }) })
    expect(plan).toEqual({ kind: 'conflict', cloudBuildId: 'cloud-1', cloudRevisionId: 'rev-2', defaultChoice: 'keep-both' })
  })

  it('re-links a build whose cloud copy was deleted only by asking for a new upload', () => {
    expect(planUpload({ ...base, record: record(), localHash: 'hash-2', cloud: null }).kind).toBe('cloud-missing')
  })
})

describe('planDownload', () => {
  it('downloads straight into a build with no local changes', () => {
    expect(planDownload({ activeUserId: 'user-A', record: record(), localHash: 'hash-1', cloud: cloud({ currentRevisionId: 'rev-2' }) }))
      .toEqual({ kind: 'download', cloudBuildId: 'cloud-1', revisionId: 'rev-2' })
  })

  it('never overwrites local changes silently', () => {
    expect(planDownload({ activeUserId: 'user-A', record: record(), localHash: 'hash-2', cloud: cloud({ currentRevisionId: 'rev-2' }) }).kind).toBe('conflict')
  })

  it('opens a cloud build with no local counterpart as a new local build', () => {
    expect(planDownload({ activeUserId: 'user-A', record: undefined, localHash: null, cloud: cloud() }))
      .toEqual({ kind: 'download-as-new', cloudBuildId: 'cloud-1', revisionId: 'rev-1' })
  })
})

describe('planSharedLinkUpdate', () => {
  it('requires the user to name the replaced revision on a diverged build', () => {
    const plan = planSharedLinkUpdate({ activeUserId: 'user-A', record: record(), localHash: 'hash-2', cloud: cloud({ currentRevisionId: 'rev-2' }) })
    expect(plan.kind).toBe('conflict')
  })

  it('always requires a confirmation before moving the link', () => {
    const plan = planSharedLinkUpdate({ activeUserId: 'user-A', record: record(), localHash: 'hash-1', cloud: cloud() })
    expect(plan).toEqual({ kind: 'confirm-link-update', cloudBuildId: 'cloud-1', revisionId: 'rev-1' })
  })

  it('needs an uploaded build', () => {
    expect(planSharedLinkUpdate({ activeUserId: 'user-A', record: undefined, localHash: 'h', cloud: undefined }).kind).toBe('upload-first')
  })
})

describe('resolveConflict', () => {
  it('keep-both saves the cloud revision as a new unlinked local build and stops', () => {
    expect(resolveConflict('keep-both', { confirmed: false })).toEqual({ kind: 'save-cloud-as-new-local', attachSyncRecord: false })
  })

  it('keep-local and keep-cloud refuse to run without the second confirmation', () => {
    expect(resolveConflict('keep-local', { confirmed: false })).toEqual({ kind: 'needs-confirmation', replaces: 'cloud' })
    expect(resolveConflict('keep-cloud', { confirmed: false })).toEqual({ kind: 'needs-confirmation', replaces: 'local' })
  })

  it('keep-local uploads over the cloud as a conditional write once confirmed', () => {
    expect(resolveConflict('keep-local', { confirmed: true })).toEqual({ kind: 'upload-conditional' })
  })

  it('keep-cloud replaces the local build once confirmed', () => {
    expect(resolveConflict('keep-cloud', { confirmed: true })).toEqual({ kind: 'replace-local' })
  })
})

describe('shortenBuildName', () => {
  it('leaves names within the limit alone', () => {
    expect(shortenBuildName('Fire Mage')).toBe('Fire Mage')
  })
  it('cuts to the first 50 characters', () => {
    expect(shortenBuildName('y'.repeat(51))).toBe('y'.repeat(50))
  })
})

describe('shared semantic-hash vectors (docs/HOSTED_ACCOUNT_HASH_VECTORS.json)', () => {
  const file = fileURLToPath(new URL('../../../../docs/HOSTED_ACCOUNT_HASH_VECTORS.json', import.meta.url))
  const doc = JSON.parse(readFileSync(file, 'utf-8')) as { vectors: { name: string; input_json: string; sha256: string }[] }

  it('has vectors', () => expect(doc.vectors.length).toBeGreaterThanOrEqual(9))

  for (const vector of doc.vectors) {
    it(`matches the committed hash for ${vector.name}`, async () => {
      const deflated = zlib.deflateSync(Buffer.from(vector.input_json, 'utf-8'), { level: 9 })
      const code = `tli1_${deflated.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}`
      expect(await semanticBuildHash(code)).toBe(vector.sha256)
    })
  }
})
