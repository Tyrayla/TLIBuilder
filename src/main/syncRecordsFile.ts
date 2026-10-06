// Desktop sync-record file (userData/sync-records.json). Holds only the five sync fields per local
// build; never a build, a name, or a token. The renderer reaches it through three narrow IPC calls and
// every incoming record is re-validated and trimmed here.

export interface StoredSyncRecord {
  localBuildId: string
  accountUserId: string
  cloudBuildId: string
  baseRevisionId: string
  baseSemanticHash: string
}

const FIELDS = ['localBuildId', 'accountUserId', 'cloudBuildId', 'baseRevisionId', 'baseSemanticHash'] as const
const MAX_FIELD = 256
const MAX_RECORDS = 2000

function clean(value: unknown): StoredSyncRecord | null {
  if (!value || typeof value !== 'object') return null
  const v = value as Record<string, unknown>
  const out = {} as Record<string, string>
  for (const key of FIELDS) {
    const field = v[key]
    if (typeof field !== 'string' || field.length === 0 || field.length > MAX_FIELD) return null
    out[key] = field
  }
  return out as unknown as StoredSyncRecord
}

export function createSyncRecordsFile(io: { read: () => string; write: (text: string) => void }) {
  function load(): StoredSyncRecord[] {
    try {
      const parsed = JSON.parse(io.read()) as { records?: unknown }
      if (!Array.isArray(parsed?.records)) return []
      return parsed.records.map(clean).filter((r): r is StoredSyncRecord => r !== null)
    } catch {
      return []
    }
  }
  function save(records: StoredSyncRecord[]): void {
    io.write(JSON.stringify({ version: 1, records }))
  }

  return {
    read: load,
    put(record: unknown): void {
      const next = clean(record)
      if (!next) throw new Error('Invalid sync record.')
      const records = load().filter((r) => r.localBuildId !== next.localBuildId)
      records.push(next)
      save(records.slice(-MAX_RECORDS))
    },
    remove(localBuildId: unknown): void {
      if (typeof localBuildId !== 'string') throw new Error('Invalid build id.')
      const before = load()
      const after = before.filter((r) => r.localBuildId !== localBuildId)
      if (after.length !== before.length) save(after)
    },
  }
}
