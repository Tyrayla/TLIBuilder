import { describe, it, expect, vi } from 'vitest'
import { computeLibraryStatuses, STATUS_LABEL } from '../../utils/librarySync'
import type { SyncRecord } from '../../utils/sync'
import type { CloudBuild } from '../../api/accounts'

const rec = (id: string, over: Partial<SyncRecord> = {}): SyncRecord => ({
  localBuildId: id, accountUserId: 'user-A', cloudBuildId: `cb-${id}`, baseRevisionId: 'r1', baseSemanticHash: 'h1', ...over,
})
const cloud = (id: string, over: Partial<CloudBuild> = {}): CloudBuild => ({
  cloudBuildId: `cb-${id}`, name: id, currentRevisionId: 'r1', semanticHash: 'h1', updatedAt: 1, dataVersion: 's', namedLink: null, ...over,
})

function setup(over: { records?: SyncRecord[]; cloud?: CloudBuild[]; hashes?: Record<string, string>; user?: string | null; listCloud?: () => Promise<CloudBuild[]> } = {}) {
  const readLocalHash = vi.fn(async (id: string) => over.hashes?.[id] ?? 'h1')
  const listCloud = vi.fn(over.listCloud ?? (async () => over.cloud ?? []))
  const run = () => computeLibraryStatuses({
    localBuildIds: ['a', 'b', 'c'],
    activeUserId: over.user === undefined ? 'user-A' : over.user,
    records: over.records ?? [],
    listCloud,
    readLocalHash,
  })
  return { run, readLocalHash, listCloud }
}

describe('computeLibraryStatuses', () => {
  it('a guest gets no statuses and makes no network call', async () => {
    const t = setup({ user: null, records: [rec('a')] })
    expect((await t.run()).size).toBe(0)
    expect(t.listCloud).not.toHaveBeenCalled()
  })

  it('marks unlinked builds as not uploaded without hashing them', async () => {
    const t = setup({ records: [] })
    const result = await t.run()
    expect(result.get('a')?.status).toBe('not-uploaded')
    expect(t.readLocalHash).not.toHaveBeenCalled()
  })

  it('reads cloud revision ids once and hashes only linked builds', async () => {
    const t = setup({
      records: [rec('a'), rec('b')],
      cloud: [cloud('a'), cloud('b', { currentRevisionId: 'r2' })],
      hashes: { b: 'h2' },
    })
    const result = await t.run()
    expect(t.listCloud).toHaveBeenCalledTimes(1)
    expect(t.readLocalHash).toHaveBeenCalledTimes(2)
    expect(result.get('a')?.status).toBe('synced')
    expect(result.get('b')?.status).toBe('diverged')
    expect(result.get('c')?.status).toBe('not-uploaded')
  })

  it('local-only change and cloud-only change are told apart', async () => {
    const t = setup({
      records: [rec('a'), rec('b')],
      cloud: [cloud('a'), cloud('b', { currentRevisionId: 'r2' })],
      hashes: { a: 'edited' },
    })
    const result = await t.run()
    expect(result.get('a')?.status).toBe('local-changes')
    expect(result.get('b')?.status).toBe('cloud-newer')
  })

  it('a cloud build deleted elsewhere shows as cloud-missing', async () => {
    const t = setup({ records: [rec('a')], cloud: [] })
    expect((await t.run()).get('a')?.status).toBe('cloud-missing')
  })

  it('ignores another account\'s records', async () => {
    const t = setup({ records: [rec('a', { accountUserId: 'user-B' })], cloud: [cloud('a')] })
    expect((await t.run()).get('a')?.status).toBe('not-uploaded')
  })

  it('still shows local-only statuses when the service cannot be reached', async () => {
    const t = setup({
      records: [rec('a')],
      hashes: { a: 'edited' },
      listCloud: async () => { throw new Error('offline') },
    })
    expect((await t.run()).get('a')?.status).toBe('local-changes')
  })

  it('never throws when one build cannot be read', async () => {
    const t = setup({ records: [rec('a')], cloud: [cloud('a')] })
    t.readLocalHash.mockRejectedValueOnce(new Error('broken'))
    expect((await t.run()).has('a')).toBe(false)
  })

  it('exposes the plain-language labels', () => {
    expect(STATUS_LABEL['not-uploaded']).toBe('Not uploaded')
    expect(STATUS_LABEL['local-changes']).toBe('Local changes')
    expect(STATUS_LABEL['cloud-newer']).toBe('Newer version in cloud')
    expect(STATUS_LABEL.diverged).toBe('Diverged')
  })
})
