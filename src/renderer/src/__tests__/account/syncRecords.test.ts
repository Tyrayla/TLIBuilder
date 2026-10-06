import { describe, it, expect, vi } from 'vitest'
import {
  createSyncRecordStore,
  createIdbBackend,
  createBridgeBackend,
  type SyncRecordBackend,
} from '../../utils/syncRecords'
import type { SyncRecord } from '../../utils/sync'

const rec = (over: Partial<SyncRecord> = {}): SyncRecord => ({
  localBuildId: 'local-1', accountUserId: 'user-A', cloudBuildId: 'cb-1',
  baseRevisionId: 'rev-1', baseSemanticHash: 'h1', ...over,
})

function memoryBackend(): SyncRecordBackend & { rows: Map<string, SyncRecord> } {
  const rows = new Map<string, SyncRecord>()
  return {
    rows,
    readAll: async () => [...rows.values()],
    put: async (r) => { rows.set(r.localBuildId, r) },
    remove: async (id) => { rows.delete(id) },
  }
}

describe('sync record store', () => {
  it('upload or download creates, then updates, one record per local build', async () => {
    const store = createSyncRecordStore(memoryBackend())
    await store.upsert(rec())
    await store.upsert(rec({ baseRevisionId: 'rev-2', baseSemanticHash: 'h2' }))
    const all = await store.all()
    expect(all).toHaveLength(1)
    expect(all[0]).toMatchObject({ baseRevisionId: 'rev-2', baseSemanticHash: 'h2' })
  })

  it('local delete removes the record', async () => {
    const store = createSyncRecordStore(memoryBackend())
    await store.upsert(rec())
    await store.removeForLocalBuild('local-1')
    expect(await store.all()).toEqual([])
  })

  it('returns only the active account\'s records and keeps the others stored', async () => {
    const backend = memoryBackend()
    const store = createSyncRecordStore(backend)
    await store.upsert(rec({ localBuildId: 'a' }))
    await store.upsert(rec({ localBuildId: 'b', accountUserId: 'user-B' }))
    expect((await store.forAccount('user-A')).map((r) => r.localBuildId)).toEqual(['a'])
    expect((await store.forAccount('user-B')).map((r) => r.localBuildId)).toEqual(['b'])
    expect(await store.forAccount(null)).toEqual([])
    expect(backend.rows.size).toBe(2)
  })

  it('finds a record only for the account that created it', async () => {
    const store = createSyncRecordStore(memoryBackend())
    await store.upsert(rec())
    expect(await store.find('local-1', 'user-A')).toMatchObject({ cloudBuildId: 'cb-1' })
    expect(await store.find('local-1', 'user-B')).toBeUndefined()
    expect(await store.find('local-1', null)).toBeUndefined()
  })

  it('drops the records of a deleted cloud build', async () => {
    const store = createSyncRecordStore(memoryBackend())
    await store.upsert(rec({ localBuildId: 'a', cloudBuildId: 'cb-1' }))
    await store.upsert(rec({ localBuildId: 'b', cloudBuildId: 'cb-2' }))
    await store.removeForCloudBuild('cb-1', 'user-A')
    expect((await store.all()).map((r) => r.localBuildId)).toEqual(['b'])
  })

  it('removes every record of an account that was deleted', async () => {
    const store = createSyncRecordStore(memoryBackend())
    await store.upsert(rec({ localBuildId: 'a' }))
    await store.upsert(rec({ localBuildId: 'b', accountUserId: 'user-B' }))
    await store.removeForAccount('user-A')
    expect((await store.all()).map((r) => r.localBuildId)).toEqual(['b'])
  })

  it('rejects malformed records instead of storing them', async () => {
    const store = createSyncRecordStore(memoryBackend())
    await expect(store.upsert(rec({ accountUserId: '' }))).rejects.toThrow()
    await expect(store.upsert(rec({ localBuildId: '' }))).rejects.toThrow()
  })

  it('ignores malformed rows read back from storage', async () => {
    const backend = memoryBackend()
    backend.rows.set('bad', { localBuildId: 'bad' } as unknown as SyncRecord)
    backend.rows.set('ok', rec({ localBuildId: 'ok' }))
    const store = createSyncRecordStore(backend)
    expect((await store.all()).map((r) => r.localBuildId)).toEqual(['ok'])
  })

  it('stores nothing but the five sync fields', async () => {
    const backend = memoryBackend()
    const store = createSyncRecordStore(backend)
    await store.upsert({ ...rec(), buildName: 'secret' } as SyncRecord)
    expect(Object.keys(backend.rows.get('local-1')!).sort()).toEqual(
      ['accountUserId', 'baseRevisionId', 'baseSemanticHash', 'cloudBuildId', 'localBuildId'],
    )
  })
})

describe('bridge backend (desktop)', () => {
  it('delegates to the main-process file store', async () => {
    const bridge = {
      syncRecordsRead: vi.fn().mockResolvedValue([rec()]),
      syncRecordsPut: vi.fn().mockResolvedValue(undefined),
      syncRecordsRemove: vi.fn().mockResolvedValue(undefined),
    }
    const backend = createBridgeBackend(bridge)
    expect(await backend.readAll()).toEqual([rec()])
    await backend.put(rec())
    await backend.remove('local-1')
    expect(bridge.syncRecordsPut).toHaveBeenCalledWith(rec())
    expect(bridge.syncRecordsRemove).toHaveBeenCalledWith('local-1')
  })
})

// A just-enough IndexedDB double: one database, object stores keyed by keyPath, request-style callbacks.
function fakeIndexedDb() {
  const stores = new Map<string, Map<string, unknown>>()
  const created: string[] = []
  const makeRequest = <T,>(compute: () => T) => {
    const req: { result?: T; onsuccess?: () => void; onerror?: () => void; error?: unknown } = {}
    queueMicrotask(() => { req.result = compute(); req.onsuccess?.() })
    return req
  }
  const db = {
    objectStoreNames: { contains: (n: string) => stores.has(n) },
    createObjectStore: (name: string) => { stores.set(name, new Map()); created.push(name) },
    transaction: (name: string) => {
      const tx: { oncomplete?: () => void; onerror?: () => void; objectStore: (n: string) => unknown } = {
        objectStore: () => ({
          getAll: () => makeRequest(() => [...stores.get(name)!.values()]),
          put: (value: { localBuildId: string }) => {
            const req = makeRequest(() => { stores.get(name)!.set(value.localBuildId, value); return undefined })
            setTimeout(() => tx.oncomplete?.(), 0)
            return req
          },
          delete: (key: string) => {
            const req = makeRequest(() => { stores.get(name)!.delete(key); return undefined })
            setTimeout(() => tx.oncomplete?.(), 0)
            return req
          },
        }),
      }
      return tx
    },
  }
  const indexedDB = {
    open: vi.fn(() => {
      const req: { result?: unknown; onupgradeneeded?: () => void; onsuccess?: () => void; onerror?: () => void } = {}
      queueMicrotask(() => {
        req.result = db
        req.onupgradeneeded?.()
        req.onsuccess?.()
      })
      return req
    }),
  }
  return { indexedDB: indexedDB as unknown as IDBFactory, stores, created, open: indexedDB.open }
}

describe('indexeddb backend (web)', () => {
  it('uses its own database, separate from the build snapshot database', async () => {
    const fake = fakeIndexedDb()
    const backend = createIdbBackend(fake.indexedDB)
    await backend.put(rec())
    expect(fake.open).toHaveBeenCalledWith('tli-sync', 1)
    expect(fake.created).toEqual(['sync_records'])
  })

  it('round-trips put, read and remove', async () => {
    const backend = createIdbBackend(fakeIndexedDb().indexedDB)
    await backend.put(rec({ localBuildId: 'a' }))
    await backend.put(rec({ localBuildId: 'b' }))
    expect((await backend.readAll()).map((r) => r.localBuildId).sort()).toEqual(['a', 'b'])
    await backend.remove('a')
    expect((await backend.readAll()).map((r) => r.localBuildId)).toEqual(['b'])
  })

  it('reads as empty when storage is unavailable', async () => {
    const backend = createIdbBackend(undefined)
    expect(await backend.readAll()).toEqual([])
  })
})
