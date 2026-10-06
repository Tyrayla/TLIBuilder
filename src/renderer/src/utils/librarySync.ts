// Passive sync status for the build library. It reads cloud revision ids once when the library opens
// (and again after an explicit sync action); it never runs while the user edits a build.
import type { CloudBuild } from '../api/accounts'
import { syncStatus, type SyncRecord, type SyncStatus } from './sync'

export const STATUS_LABEL: Record<SyncStatus, string> = {
  'not-uploaded': 'Not uploaded',
  synced: 'Synced',
  'local-changes': 'Local changes',
  'cloud-newer': 'Newer version in cloud',
  diverged: 'Diverged',
  'cloud-missing': 'Cloud copy deleted',
}

export interface LibraryStatus {
  status: SyncStatus
  cloud: CloudBuild | null
}

export async function computeLibraryStatuses(input: {
  localBuildIds: string[]
  activeUserId: string | null
  records: SyncRecord[]
  listCloud: () => Promise<CloudBuild[]>
  readLocalHash: (localBuildId: string) => Promise<string>
}): Promise<Map<string, LibraryStatus>> {
  const result = new Map<string, LibraryStatus>()
  if (!input.activeUserId) return result

  const mine = new Map(input.records.filter((r) => r.accountUserId === input.activeUserId).map((r) => [r.localBuildId, r]))

  let cloudById: Map<string, CloudBuild> | null = null
  if (mine.size > 0) {
    try {
      cloudById = new Map((await input.listCloud()).map((b) => [b.cloudBuildId, b]))
    } catch {
      cloudById = null // offline: local-only statuses below
    }
  }

  for (const id of input.localBuildIds) {
    const record = mine.get(id)
    if (!record) { result.set(id, { status: 'not-uploaded', cloud: null }); continue }
    try {
      const localHash = await input.readLocalHash(id)
      const cloud = cloudById ? (cloudById.get(record.cloudBuildId) ?? null) : undefined
      const status = syncStatus({ record, localHash, cloud, activeUserId: input.activeUserId })
      result.set(id, { status, cloud: cloud ?? null })
    } catch {
      // One unreadable build never hides the rest of the library.
    }
  }
  return result
}
