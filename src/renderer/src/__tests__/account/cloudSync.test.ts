import { describe, it, expect } from 'vitest'
import { createCloudSync, type CloudSyncDeps } from '../../utils/cloudSync'
import { createSyncRecordStore, type SyncRecordBackend } from '../../utils/syncRecords'
import { AccountApiError, type CloudBuild, type CreateResult, type UploadInput } from '../../api/accounts'
import type { SyncRecord } from '../../utils/sync'

// An in-memory stand-in for the hosted service that follows docs/HOSTED_ACCOUNT_API_CONTRACT.md:
// 20-build limit, content match on create, conditional writes, unchanged-content uploads create no revision.
// It proves the app's behavior against the contract; it does not prove the real service.
function fakeService() {
  const builds = new Map<string, { summary: CloudBuild; revisions: Map<string, string> }>()
  let counter = 0
  const hashOf = (code: string) => `hash:${code}`
  const api = {
    async createCloudBuild(input: UploadInput & { allowDuplicate: boolean }): Promise<CreateResult> {
      const match = [...builds.values()].find((b) => b.summary.semanticHash === hashOf(input.code))
      if (match && !input.allowDuplicate) return { kind: 'match', cloudBuildId: match.summary.cloudBuildId, name: match.summary.name }
      if (builds.size >= 20) throw new AccountApiError(409, 'cloud_quota_reached', 'full')
      const id = `cb${++counter}`
      const rev = `rev${++counter}`
      const summary: CloudBuild = {
        cloudBuildId: id, name: input.name, currentRevisionId: rev, semanticHash: hashOf(input.code),
        updatedAt: counter, dataVersion: input.dataVersion, namedLink: null,
      }
      builds.set(id, { summary, revisions: new Map([[rev, input.code]]) })
      return { kind: 'created', build: summary }
    },
    async uploadRevision(id: string, input: UploadInput & { baseRevisionId: string }): Promise<CloudBuild> {
      const b = builds.get(id)
      if (!b) throw new AccountApiError(404, 'not_found', 'x')
      if (b.summary.currentRevisionId !== input.baseRevisionId) {
        throw new AccountApiError(409, 'stale_revision', 'stale', { currentRevisionId: b.summary.currentRevisionId })
      }
      if (b.summary.semanticHash === hashOf(input.code)) return b.summary
      const rev = `rev${++counter}`
      b.summary = { ...b.summary, name: input.name, currentRevisionId: rev, semanticHash: hashOf(input.code), updatedAt: counter }
      b.revisions.set(rev, input.code)
      return b.summary
    },
    async getCloudBuild(id: string) {
      const b = builds.get(id)
      if (!b) throw new AccountApiError(404, 'not_found', 'x')
      return { build: b.summary, code: b.revisions.get(b.summary.currentRevisionId)! }
    },
    async getRevision(id: string, revisionId: string) {
      const b = builds.get(id)!
      return { build: { ...b.summary, currentRevisionId: revisionId }, code: b.revisions.get(revisionId)! }
    },
    async listCloudBuilds() { return [...builds.values()].map((b) => b.summary) },
    async updateNamedLink(id: string, change: { revisionId?: string }) {
      const b = builds.get(id)!
      b.summary = { ...b.summary, namedLink: { urlPath: '/u/t-1/x', slug: 'x', listed: false, revisionId: change.revisionId ?? b.summary.currentRevisionId } }
      return b.summary.namedLink!
    },
  }
  return { api, builds }
}

function setup(opts: { user?: string | null } = {}) {
  const service = fakeService()
  const rows = new Map<string, SyncRecord>()
  const backend: SyncRecordBackend = {
    readAll: async () => [...rows.values()],
    put: async (r) => { rows.set(r.localBuildId, r) },
    remove: async (id) => { rows.delete(id) },
  }
  const records = createSyncRecordStore(backend)
  // Local library: id -> {name, code}. The "code" doubles as content; hash is derived from it.
  const library = new Map<string, { name: string; code: string }>()
  let nextLocal = 0
  let user: string | null = opts.user === undefined ? 'user-A' : opts.user
  const deps: CloudSyncDeps = {
    accounts: service.api,
    records,
    activeUserId: () => user,
    dataVersion: () => 'season-9',
    appVersion: () => '0.0.0-test',
    local: {
      async read(id) {
        const b = library.get(id)
        if (!b) throw new Error('missing local build')
        return { name: b.name, code: b.code, hash: `hash:${b.code}` }
      },
      async rename(id, name) { library.get(id)!.name = name },
      async createFromCloud(code, name) { const id = `L${++nextLocal}`; library.set(id, { name, code }); return id },
      async replaceFromCloud(id, code, name) { library.set(id, { name, code }) },
    },
    hashOf: async (code) => `hash:${code}`,
  }
  const sync = createCloudSync(deps)
  return {
    sync, service, records, library, rows,
    setUser: (u: string | null) => { user = u },
    addLocal: (id: string, name: string, code: string) => { library.set(id, { name, code }) },
  }
}

describe('upload', () => {
  it('requires sign-in and makes no cloud call', async () => {
    const t = setup({ user: null })
    t.addLocal('L0', 'Fire', 'c1')
    expect(await t.sync.upload('L0')).toEqual({ kind: 'sign-in-required' })
    expect(t.service.builds.size).toBe(0)
  })

  it('uploads an unlinked build as new and records the sync state', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    const out = await t.sync.upload('L0')
    expect(out.kind).toBe('uploaded')
    const rec = (await t.records.all())[0]
    expect(rec).toMatchObject({ localBuildId: 'L0', accountUserId: 'user-A', baseSemanticHash: 'hash:c1' })
    expect(rec.baseRevisionId).toBe([...t.service.builds.values()][0].summary.currentRevisionId)
  })

  it('creates no new revision for unchanged content', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    const before = [...t.service.builds.values()][0].revisions.size
    expect((await t.sync.upload('L0')).kind).toBe('unchanged')
    expect([...t.service.builds.values()][0].revisions.size).toBe(before)
  })

  it('uploads local edits as a conditional revision and advances the record', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    t.library.get('L0')!.code = 'c2'
    const out = await t.sync.upload('L0')
    expect(out.kind).toBe('uploaded')
    expect((await t.records.all())[0].baseSemanticHash).toBe('hash:c2')
    expect([...t.service.builds.values()][0].revisions.size).toBe(2)
  })

  it('asks for a shorter name over 50 characters and uploads nothing until confirmed', async () => {
    const t = setup()
    t.addLocal('L0', 'n'.repeat(60), 'c1')
    expect(await t.sync.upload('L0')).toEqual({ kind: 'shorten-name', suggestedName: 'n'.repeat(50), currentName: 'n'.repeat(60) })
    expect(t.service.builds.size).toBe(0)
    expect(t.library.get('L0')!.name).toBe('n'.repeat(60))
  })

  it('renames locally only after the user confirms a shorter name, then uploads', async () => {
    const t = setup()
    t.addLocal('L0', 'n'.repeat(60), 'c1')
    const out = await t.sync.upload('L0', { confirmedName: 'Short' })
    expect(out.kind).toBe('uploaded')
    expect(t.library.get('L0')!.name).toBe('Short')
    expect([...t.service.builds.values()][0].summary.name).toBe('Short')
  })

  it('rejects a confirmed name that is still too long', async () => {
    const t = setup()
    t.addLocal('L0', 'x', 'c1')
    expect((await t.sync.upload('L0', { confirmedName: 'z'.repeat(51) })).kind).toBe('shorten-name')
  })

  it('surfaces the 20-build limit', async () => {
    const t = setup()
    for (let i = 0; i < 21; i++) {
      t.addLocal(`L${i}`, `b${i}`, `code${i}`)
    }
    for (let i = 0; i < 20; i++) expect((await t.sync.upload(`L${i}`)).kind).toBe('uploaded')
    expect((await t.sync.upload('L20')).kind).toBe('quota-reached')
  })
})

describe('unlinked upload that matches an existing cloud build', () => {
  async function withExisting() {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    t.addLocal('COPY', 'Fire copy', 'c1') // duplicate: same content, no sync record
    return t
  }

  it('creates nothing and asks Link / New / Cancel', async () => {
    const t = await withExisting()
    const out = await t.sync.upload('COPY')
    expect(out).toMatchObject({ kind: 'link-prompt', cloudBuildName: 'Fire' })
    expect(t.service.builds.size).toBe(1)
    expect((await t.records.all()).map((r) => r.localBuildId)).toEqual(['L0'])
  })

  it('Link creates a sync record pointing at the existing build and uses no slot', async () => {
    const t = await withExisting()
    const prompt = await t.sync.upload('COPY')
    if (prompt.kind !== 'link-prompt') throw new Error('expected prompt')
    await t.sync.linkExisting('COPY', prompt.cloudBuildId)
    expect(t.service.builds.size).toBe(1)
    const rec = (await t.records.all()).find((r) => r.localBuildId === 'COPY')!
    expect(rec.cloudBuildId).toBe(prompt.cloudBuildId)
  })

  it('Upload as new repeats the upload with allow_duplicate and uses a slot', async () => {
    const t = await withExisting()
    const out = await t.sync.upload('COPY', { allowDuplicate: true })
    expect(out.kind).toBe('uploaded')
    expect(t.service.builds.size).toBe(2)
  })

  it('a duplicate that is edited and uploaded afterwards cannot overwrite the original', async () => {
    const t = await withExisting()
    t.library.get('COPY')!.code = 'edited'
    const out = await t.sync.upload('COPY')
    expect(out.kind).toBe('uploaded')
    const original = [...t.service.builds.values()].find((b) => b.summary.name === 'Fire')!
    expect([...original.revisions.values()]).toEqual(['c1'])
  })

  it('Cancel is simply not calling anything', async () => {
    const t = await withExisting()
    await t.sync.upload('COPY')
    expect(t.service.builds.size).toBe(1)
  })
})

describe('account isolation', () => {
  it('never uploads over a cloud build through another account\'s record', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    t.setUser('user-B')
    t.library.get('L0')!.code = 'c2'
    const out = await t.sync.upload('L0')
    expect(out.kind).toBe('uploaded') // as a NEW build for user-B, with a new record
    const original = [...t.service.builds.values()].find((b) => b.summary.cloudBuildId === 'cb1')!
    expect([...original.revisions.values()]).toEqual(['c1'])
  })
})

describe('stale and diverged cloud state', () => {
  async function linkedWithCloudAhead() {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    // Another device uploads revision 2 behind this app's back.
    const cb = [...t.service.builds.values()][0]
    await t.service.api.uploadRevision(cb.summary.cloudBuildId, {
      baseRevisionId: cb.summary.currentRevisionId, name: 'Fire', code: 'cloud2', dataVersion: 's', appVersion: 'x',
    })
    return t
  }

  it('upload of an unchanged local build just reports a newer cloud version', async () => {
    const t = await linkedWithCloudAhead()
    expect((await t.sync.upload('L0')).kind).toBe('cloud-newer')
  })

  it('a diverged build goes to the conflict screen with keep-both as the default', async () => {
    const t = await linkedWithCloudAhead()
    t.library.get('L0')!.code = 'local2'
    const out = await t.sync.upload('L0')
    expect(out).toMatchObject({ kind: 'conflict', defaultChoice: 'keep-both' })
  })

  it('keep-both saves the cloud revision as a new unlinked local build and keeps the original and its record', async () => {
    const t = await linkedWithCloudAhead()
    t.library.get('L0')!.code = 'local2'
    const out = await t.sync.upload('L0')
    if (out.kind !== 'conflict') throw new Error('expected conflict')
    const result = await t.sync.resolveConflict('L0', out, 'keep-both', { confirmed: false })
    expect(result.kind).toBe('kept-both')
    expect(t.library.get('L0')!.code).toBe('local2')
    const copy = [...t.library.entries()].find(([id]) => id.startsWith('L') && id !== 'L0')!
    expect(copy[1].code).toBe('cloud2')
    expect((await t.records.all()).map((r) => r.localBuildId)).toEqual(['L0'])
  })

  it('keep-local and keep-cloud refuse to act without the second confirmation', async () => {
    const t = await linkedWithCloudAhead()
    t.library.get('L0')!.code = 'local2'
    const out = await t.sync.upload('L0')
    if (out.kind !== 'conflict') throw new Error('expected conflict')
    expect(await t.sync.resolveConflict('L0', out, 'keep-local', { confirmed: false })).toEqual({ kind: 'needs-confirmation', replaces: 'cloud' })
    expect(await t.sync.resolveConflict('L0', out, 'keep-cloud', { confirmed: false })).toEqual({ kind: 'needs-confirmation', replaces: 'local' })
    expect(t.library.get('L0')!.code).toBe('local2')
    expect([...t.service.builds.values()][0].summary.semanticHash).toBe('hash:cloud2')
  })

  it('confirmed keep-local still writes conditionally on the revision the user was shown', async () => {
    const t = await linkedWithCloudAhead()
    t.library.get('L0')!.code = 'local2'
    const out = await t.sync.upload('L0')
    if (out.kind !== 'conflict') throw new Error('expected conflict')
    // The cloud moves AGAIN after the conflict screen opened and before the user confirms.
    const cb = [...t.service.builds.values()][0]
    await t.service.api.uploadRevision(cb.summary.cloudBuildId, {
      baseRevisionId: cb.summary.currentRevisionId, name: 'Fire', code: 'cloud3', dataVersion: 's', appVersion: 'x',
    })
    const result = await t.sync.resolveConflict('L0', out, 'keep-local', { confirmed: true })
    expect(result.kind).toBe('conflict')
    expect([...t.service.builds.values()][0].summary.semanticHash).toBe('hash:cloud3')
  })

  it('confirmed keep-local replaces the cloud revision when nothing moved meanwhile', async () => {
    const t = await linkedWithCloudAhead()
    t.library.get('L0')!.code = 'local2'
    const out = await t.sync.upload('L0')
    if (out.kind !== 'conflict') throw new Error('expected conflict')
    const result = await t.sync.resolveConflict('L0', out, 'keep-local', { confirmed: true })
    expect(result.kind).toBe('uploaded')
    expect([...t.service.builds.values()][0].summary.semanticHash).toBe('hash:local2')
    expect((await t.records.all())[0].baseSemanticHash).toBe('hash:local2')
  })

  it('confirmed keep-cloud replaces the local build and advances the record', async () => {
    const t = await linkedWithCloudAhead()
    t.library.get('L0')!.code = 'local2'
    const out = await t.sync.upload('L0')
    if (out.kind !== 'conflict') throw new Error('expected conflict')
    const result = await t.sync.resolveConflict('L0', out, 'keep-cloud', { confirmed: true })
    expect(result.kind).toBe('replaced-local')
    expect(t.library.get('L0')!.code).toBe('cloud2')
    expect((await t.records.all())[0].baseSemanticHash).toBe('hash:cloud2')
  })

  it('a stale write rejected by the service becomes a conflict, never an overwrite', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    t.library.get('L0')!.code = 'local2'
    // The cloud moves between the app's status read and its write; the app has not seen it yet.
    const cb = [...t.service.builds.values()][0]
    const staleList = t.service.api.listCloudBuilds
    t.service.api.listCloudBuilds = async () => [{ ...cb.summary }]
    await t.service.api.uploadRevision(cb.summary.cloudBuildId, {
      baseRevisionId: cb.summary.currentRevisionId, name: 'Fire', code: 'cloud2', dataVersion: 's', appVersion: 'x',
    })
    const out = await t.sync.upload('L0')
    t.service.api.listCloudBuilds = staleList
    expect(out.kind).toBe('conflict')
    expect([...t.service.builds.values()][0].summary.semanticHash).toBe('hash:cloud2')
  })
})

describe('download', () => {
  it('opens a cloud build with no local counterpart as a new local build with a record', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    t.library.delete('L0')
    await t.records.removeForLocalBuild('L0')
    const out = await t.sync.downloadCloudBuild('cb1')
    expect(out.kind).toBe('downloaded-new')
    const rec = (await t.records.all())[0]
    expect(rec).toMatchObject({ cloudBuildId: 'cb1', baseSemanticHash: 'hash:c1' })
  })

  it('downloads a newer cloud revision into an unchanged linked build', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    const cb = [...t.service.builds.values()][0]
    await t.service.api.uploadRevision(cb.summary.cloudBuildId, {
      baseRevisionId: cb.summary.currentRevisionId, name: 'Fire', code: 'cloud2', dataVersion: 's', appVersion: 'x',
    })
    const out = await t.sync.download('L0')
    expect(out.kind).toBe('downloaded')
    expect(t.library.get('L0')!.code).toBe('cloud2')
  })

  it('never overwrites local changes silently', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    t.library.get('L0')!.code = 'local2'
    const out = await t.sync.download('L0')
    expect(out.kind).toBe('conflict')
    expect(t.library.get('L0')!.code).toBe('local2')
  })
})

describe('shared link update', () => {
  it('waits for confirmation and then moves the link to the chosen revision only', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    const plan = await t.sync.planSharedLinkUpdate('L0')
    expect(plan.kind).toBe('confirm-link-update')
    expect([...t.service.builds.values()][0].summary.namedLink).toBeNull()
    if (plan.kind !== 'confirm-link-update') return
    await t.sync.confirmSharedLinkUpdate(plan)
    expect([...t.service.builds.values()][0].summary.namedLink?.revisionId).toBe(plan.revisionId)
  })

  it('a normal upload never moves a named link', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    const cb = [...t.service.builds.values()][0]
    await t.service.api.updateNamedLink(cb.summary.cloudBuildId, {})
    const pinned = cb.summary.namedLink!.revisionId
    t.library.get('L0')!.code = 'c2'
    await t.sync.upload('L0')
    expect([...t.service.builds.values()][0].summary.namedLink!.revisionId).toBe(pinned)
  })
})

describe('cloud copy deleted elsewhere', () => {
  it('reports it, and after unlinking the next upload creates a new cloud build', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    t.service.builds.clear()
    t.library.get('L0')!.code = 'c2'
    expect((await t.sync.upload('L0')).kind).toBe('cloud-missing')
    await t.sync.unlink('L0')
    expect((await t.sync.upload('L0')).kind).toBe('uploaded')
    expect(t.service.builds.size).toBe(1)
  })
})

describe('local deletion', () => {
  it('removes the sync record and leaves the cloud build', async () => {
    const t = setup()
    t.addLocal('L0', 'Fire', 'c1')
    await t.sync.upload('L0')
    await t.sync.onLocalBuildDeleted('L0')
    expect(await t.records.all()).toEqual([])
    expect(t.service.builds.size).toBe(1)
  })
})
