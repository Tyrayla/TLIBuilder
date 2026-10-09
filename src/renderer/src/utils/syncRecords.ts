// Local sync-record persistence (plan: "Local sync records").
//
// Sync records live next to the local build saves but never inside a Build, so they cannot enter a
// tli1_ code, an export, or the semantic hash. Desktop keeps them in a main-process file; the web app
// keeps them in its own IndexedDB database, separate from the build snapshot database.
import type { SyncRecord } from './sync'

export interface SyncRecordBackend {
  readAll(): Promise<SyncRecord[]>
  put(record: SyncRecord): Promise<void>
  remove(localBuildId: string): Promise<void>
}

function isRecord(value: unknown): value is SyncRecord {
  if (!value || typeof value !== 'object') return false
  const v = value as Record<string, unknown>
  return ['localBuildId', 'accountUserId', 'cloudBuildId', 'baseRevisionId', 'baseSemanticHash']
    .every((key) => typeof v[key] === 'string' && (v[key] as string).length > 0)
}

function pick(record: SyncRecord): SyncRecord {
  return {
    localBuildId: record.localBuildId,
    accountUserId: record.accountUserId,
    cloudBuildId: record.cloudBuildId,
    baseRevisionId: record.baseRevisionId,
    baseSemanticHash: record.baseSemanticHash,
  }
}

export function createSyncRecordStore(backend: SyncRecordBackend) {
  async function all(): Promise<SyncRecord[]> {
    const rows = await backend.readAll()
    return rows.filter(isRecord).map(pick)
  }

  return {
    all,

    /** Records the given account created. Another account's records stay stored but are not returned. */
    async forAccount(accountUserId: string | null): Promise<SyncRecord[]> {
      if (!accountUserId) return []
      return (await all()).filter((r) => r.accountUserId === accountUserId)
    },

    async find(localBuildId: string, accountUserId: string | null): Promise<SyncRecord | undefined> {
      if (!accountUserId) return undefined
      return (await all()).find((r) => r.localBuildId === localBuildId && r.accountUserId === accountUserId)
    },

    /** Upload or download: create or replace the record for this local build. */
    async upsert(record: SyncRecord): Promise<void> {
      if (!isRecord(record)) throw new Error('Invalid sync record.')
      await backend.put(pick(record))
    },

    /** Local delete. The cloud build stays until the user deletes it. */
    async removeForLocalBuild(localBuildId: string): Promise<void> {
      await backend.remove(localBuildId)
    },

    /** The cloud build was deleted: its local copies are plain local builds again. */
    async removeForCloudBuild(cloudBuildId: string, accountUserId: string): Promise<void> {
      for (const r of await all()) {
        if (r.cloudBuildId === cloudBuildId && r.accountUserId === accountUserId) await backend.remove(r.localBuildId)
      }
    },

    /** Account deletion: drop every record that account created. */
    async removeForAccount(accountUserId: string): Promise<void> {
      for (const r of await all()) {
        if (r.accountUserId === accountUserId) await backend.remove(r.localBuildId)
      }
    },
  }
}

export type SyncRecordStore = ReturnType<typeof createSyncRecordStore>

// ── Desktop: main-process file store ─────────────────────────────────────────
export function createBridgeBackend(bridge: {
  syncRecordsRead: () => Promise<SyncRecord[]>
  syncRecordsPut: (record: SyncRecord) => Promise<void>
  syncRecordsRemove: (localBuildId: string) => Promise<void>
}): SyncRecordBackend {
  return {
    readAll: () => bridge.syncRecordsRead(),
    put: (record) => bridge.syncRecordsPut(record),
    remove: (localBuildId) => bridge.syncRecordsRemove(localBuildId),
  }
}

// ── Web: its own IndexedDB database ──────────────────────────────────────────
const IDB_NAME = 'tli-sync'
const IDB_STORE = 'sync_records'

export function createIdbBackend(factory: IDBFactory | undefined): SyncRecordBackend {
  function open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      if (!factory) { reject(new Error('IndexedDB unavailable')); return }
      const req = factory.open(IDB_NAME, 1)
      req.onupgradeneeded = () => {
        if (!req.result.objectStoreNames.contains(IDB_STORE)) {
          req.result.createObjectStore(IDB_STORE, { keyPath: 'localBuildId' })
        }
      }
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error)
    })
  }

  async function write(action: (store: IDBObjectStore) => void): Promise<void> {
    const db = await open()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, 'readwrite')
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
      action(tx.objectStore(IDB_STORE))
    })
  }

  return {
    async readAll() {
      let db: IDBDatabase
      try { db = await open() } catch { return [] }
      return new Promise<SyncRecord[]>((resolve) => {
        const req = db.transaction(IDB_STORE, 'readonly').objectStore(IDB_STORE).getAll()
        req.onsuccess = () => resolve(Array.isArray(req.result) ? (req.result as SyncRecord[]) : [])
        req.onerror = () => resolve([])
      })
    },
    put: (record) => write((store) => { store.put(record) }),
    remove: (localBuildId) => write((store) => { store.delete(localBuildId) }),
  }
}

/** The backend for the running shell. */
export function defaultSyncRecordStore(): SyncRecordStore {
  const api = typeof window !== 'undefined' ? window.api : undefined
  if (api?.syncRecordsRead && api.syncRecordsPut && api.syncRecordsRemove) {
    return createSyncRecordStore(createBridgeBackend({
      syncRecordsRead: api.syncRecordsRead,
      syncRecordsPut: api.syncRecordsPut,
      syncRecordsRemove: api.syncRecordsRemove,
    }))
  }
  return createSyncRecordStore(createIdbBackend(typeof indexedDB !== 'undefined' ? indexedDB : undefined))
}
