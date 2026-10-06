// Explicit cloud sync actions (upload, download, link, conflict resolution, shared-link update).
//
// This executes the decisions made by utils/sync.ts. Every write to the cloud is conditional on the
// revision the user was shown; nothing here runs in the background, and nothing replaces local or
// cloud content without the user's explicit choice (plan: "Sync status and the conflict screen").
import {
  AccountApiError,
  type AccountsApi,
  type CloudBuild,
} from '../api/accounts'
import {
  MAX_BUILD_NAME_LENGTH,
  planDownload,
  planSharedLinkUpdate,
  planUpload,
  resolveConflict as decideConflict,
  shortenBuildName,
  type ConflictChoice,
} from './sync'
import type { SyncRecordStore } from './syncRecords'

export interface LocalBuildAccess {
  /** The build's current encoded content and semantic hash. */
  read(localBuildId: string): Promise<{ name: string; code: string; hash: string }>
  /** Apply a name the user confirmed. */
  rename(localBuildId: string, name: string): Promise<void>
  /** Save cloud content as a new local build (no sync record is created here). */
  createFromCloud(code: string, name: string): Promise<string>
  /** Replace an existing local build with cloud content. */
  replaceFromCloud(localBuildId: string, code: string, name: string): Promise<void>
}

export interface CloudSyncDeps {
  accounts: Pick<AccountsApi, 'createCloudBuild' | 'uploadRevision' | 'getCloudBuild' | 'listCloudBuilds' | 'updateNamedLink'>
  records: SyncRecordStore
  activeUserId: () => string | null
  dataVersion: () => string
  appVersion: () => string
  local: LocalBuildAccess
  hashOf: (code: string) => Promise<string>
}

export interface ConflictOutcome {
  kind: 'conflict'
  cloudBuildId: string
  cloudRevisionId: string
  defaultChoice: 'keep-both'
  cloud: { build: CloudBuild; code: string }
  local: { name: string; code: string }
}

export type UploadOutcome =
  | { kind: 'sign-in-required' }
  | { kind: 'shorten-name'; suggestedName: string }
  | { kind: 'uploaded'; build: CloudBuild }
  | { kind: 'unchanged' }
  | { kind: 'link-prompt'; cloudBuildId: string; cloudBuildName: string }
  | { kind: 'cloud-newer' }
  | { kind: 'cloud-missing' }
  | { kind: 'quota-reached' }
  | { kind: 'error'; code: string; message: string }
  | ConflictOutcome

export type DownloadOutcome =
  | { kind: 'sign-in-required' }
  | { kind: 'not-linked' }
  | { kind: 'up-to-date' }
  | { kind: 'cloud-missing' }
  | { kind: 'downloaded' }
  | { kind: 'downloaded-new'; localBuildId: string }
  | { kind: 'error'; code: string; message: string }
  | ConflictOutcome

export type ResolveOutcome =
  | { kind: 'kept-both'; newLocalBuildId: string }
  | { kind: 'needs-confirmation'; replaces: 'cloud' | 'local' }
  | { kind: 'replaced-local' }
  | Extract<UploadOutcome, { kind: 'uploaded' | 'shorten-name' | 'error' | 'quota-reached' }>
  | ConflictOutcome

export type LinkUpdatePlan =
  | { kind: 'sign-in-required' }
  | { kind: 'upload-first' }
  | { kind: 'confirm-link-update'; cloudBuildId: string; revisionId: string }
  | ConflictOutcome

function asError(error: unknown): { kind: 'error'; code: string; message: string } {
  if (error instanceof AccountApiError) return { kind: 'error', code: error.code, message: error.message }
  return { kind: 'error', code: 'unexpected', message: error instanceof Error ? error.message : 'Unexpected error.' }
}

export function createCloudSync(deps: CloudSyncDeps) {
  /** `null` when the cloud build no longer exists. */
  async function findCloud(cloudBuildId: string): Promise<CloudBuild | null> {
    const list = await deps.accounts.listCloudBuilds()
    return list.find((b) => b.cloudBuildId === cloudBuildId) ?? null
  }

  async function conflictFor(localBuildId: string, cloudBuildId: string): Promise<ConflictOutcome> {
    const [cloud, local] = await Promise.all([deps.accounts.getCloudBuild(cloudBuildId), deps.local.read(localBuildId)])
    return {
      kind: 'conflict',
      cloudBuildId,
      cloudRevisionId: cloud.build.currentRevisionId,
      defaultChoice: 'keep-both',
      cloud,
      local: { name: local.name, code: local.code },
    }
  }

  async function writeRecord(localBuildId: string, userId: string, build: CloudBuild, hash: string): Promise<void> {
    await deps.records.upsert({
      localBuildId,
      accountUserId: userId,
      cloudBuildId: build.cloudBuildId,
      baseRevisionId: build.currentRevisionId,
      baseSemanticHash: hash,
    })
  }

  async function upload(
    localBuildId: string,
    opts: { confirmedName?: string; allowDuplicate?: boolean } = {},
  ): Promise<UploadOutcome> {
    const userId = deps.activeUserId()
    if (!userId) return { kind: 'sign-in-required' }
    try {
      if (opts.confirmedName !== undefined) {
        if (opts.confirmedName.length > MAX_BUILD_NAME_LENGTH) {
          return { kind: 'shorten-name', suggestedName: shortenBuildName(opts.confirmedName) }
        }
        await deps.local.rename(localBuildId, opts.confirmedName)
      }
      const local = await deps.local.read(localBuildId)
      const record = await deps.records.find(localBuildId, userId)
      const cloud = record ? await findCloud(record.cloudBuildId) : undefined
      const plan = planUpload({ activeUserId: userId, name: local.name, record, localHash: local.hash, cloud })
      const payload = { name: local.name, code: local.code, dataVersion: deps.dataVersion(), appVersion: deps.appVersion() }

      switch (plan.kind) {
        case 'sign-in-required': return { kind: 'sign-in-required' }
        case 'shorten-name': return { kind: 'shorten-name', suggestedName: plan.suggestedName }
        case 'nothing-to-upload': return { kind: 'unchanged' }
        case 'cloud-newer': return { kind: 'cloud-newer' }
        case 'cloud-missing': return { kind: 'cloud-missing' }
        case 'conflict': return await conflictFor(localBuildId, plan.cloudBuildId)
        case 'upload-new': {
          const created = await deps.accounts.createCloudBuild({ ...payload, allowDuplicate: opts.allowDuplicate ?? false })
          if (created.kind === 'match') {
            return { kind: 'link-prompt', cloudBuildId: created.cloudBuildId, cloudBuildName: created.name }
          }
          await writeRecord(localBuildId, userId, created.build, local.hash)
          return { kind: 'uploaded', build: created.build }
        }
        case 'upload-revision': {
          try {
            const build = await deps.accounts.uploadRevision(plan.cloudBuildId, { ...payload, baseRevisionId: plan.baseRevisionId })
            await writeRecord(localBuildId, userId, build, local.hash)
            return { kind: 'uploaded', build }
          } catch (error) {
            // The cloud moved after the status read. The service refused the write, so nothing was replaced.
            if (error instanceof AccountApiError && error.code === 'stale_revision') {
              return await conflictFor(localBuildId, plan.cloudBuildId)
            }
            throw error
          }
        }
      }
    } catch (error) {
      if (error instanceof AccountApiError && error.code === 'cloud_quota_reached') return { kind: 'quota-reached' }
      return asError(error)
    }
  }

  /** Link a local build to an existing cloud build that already has its content. Uses no slot. */
  async function linkExisting(localBuildId: string, cloudBuildId: string): Promise<void> {
    const userId = deps.activeUserId()
    if (!userId) throw new AccountApiError(401, 'unauthenticated', 'Not signed in.')
    const [local, cloud] = await Promise.all([deps.local.read(localBuildId), deps.accounts.getCloudBuild(cloudBuildId)])
    await writeRecord(localBuildId, userId, cloud.build, local.hash)
  }

  async function resolveConflict(
    localBuildId: string,
    conflict: ConflictOutcome,
    choice: ConflictChoice,
    opts: { confirmed: boolean },
  ): Promise<ResolveOutcome> {
    const userId = deps.activeUserId()
    if (!userId) return { kind: 'error', code: 'unauthenticated', message: 'Not signed in.' }
    const decision = decideConflict(choice, opts)
    try {
      switch (decision.kind) {
        case 'needs-confirmation':
          return decision
        case 'save-cloud-as-new-local': {
          const newLocalBuildId = await deps.local.createFromCloud(conflict.cloud.code, conflict.cloud.build.name)
          return { kind: 'kept-both', newLocalBuildId }
        }
        case 'replace-local': {
          const hash = await deps.hashOf(conflict.cloud.code)
          await deps.local.replaceFromCloud(localBuildId, conflict.cloud.code, conflict.cloud.build.name)
          await writeRecord(localBuildId, userId, conflict.cloud.build, hash)
          return { kind: 'replaced-local' }
        }
        case 'upload-conditional': {
          const local = await deps.local.read(localBuildId)
          if (local.name.length > MAX_BUILD_NAME_LENGTH) {
            return { kind: 'shorten-name', suggestedName: shortenBuildName(local.name) }
          }
          try {
            // Still conditional: the base is the revision the user was shown, so a cloud change that
            // landed since then is refused rather than overwritten.
            const build = await deps.accounts.uploadRevision(conflict.cloudBuildId, {
              name: local.name, code: local.code, dataVersion: deps.dataVersion(), appVersion: deps.appVersion(),
              baseRevisionId: conflict.cloudRevisionId,
            })
            await writeRecord(localBuildId, userId, build, local.hash)
            return { kind: 'uploaded', build }
          } catch (error) {
            if (error instanceof AccountApiError && error.code === 'stale_revision') {
              return await conflictFor(localBuildId, conflict.cloudBuildId)
            }
            throw error
          }
        }
      }
    } catch (error) {
      return asError(error)
    }
  }

  async function download(localBuildId: string): Promise<DownloadOutcome> {
    const userId = deps.activeUserId()
    if (!userId) return { kind: 'sign-in-required' }
    try {
      const record = await deps.records.find(localBuildId, userId)
      if (!record) return { kind: 'not-linked' }
      const [local, cloud] = await Promise.all([deps.local.read(localBuildId), findCloud(record.cloudBuildId)])
      const plan = planDownload({ activeUserId: userId, record, localHash: local.hash, cloud })
      switch (plan.kind) {
        case 'sign-in-required': return { kind: 'sign-in-required' }
        case 'cloud-missing': return { kind: 'cloud-missing' }
        case 'nothing-to-download': return { kind: 'up-to-date' }
        case 'conflict': return await conflictFor(localBuildId, plan.cloudBuildId)
        case 'download-as-new': // not reachable with a record; handled for exhaustiveness
        case 'download': {
          const fetched = await deps.accounts.getCloudBuild(plan.cloudBuildId)
          const hash = await deps.hashOf(fetched.code)
          await deps.local.replaceFromCloud(localBuildId, fetched.code, fetched.build.name)
          await writeRecord(localBuildId, userId, fetched.build, hash)
          return { kind: 'downloaded' }
        }
      }
    } catch (error) {
      return asError(error)
    }
  }

  /** Open a cloud build that has no local counterpart. */
  async function downloadCloudBuild(cloudBuildId: string): Promise<DownloadOutcome> {
    const userId = deps.activeUserId()
    if (!userId) return { kind: 'sign-in-required' }
    try {
      const fetched = await deps.accounts.getCloudBuild(cloudBuildId)
      const hash = await deps.hashOf(fetched.code)
      const localBuildId = await deps.local.createFromCloud(fetched.code, fetched.build.name)
      await writeRecord(localBuildId, userId, fetched.build, hash)
      return { kind: 'downloaded-new', localBuildId }
    } catch (error) {
      return asError(error)
    }
  }

  async function planLinkUpdate(localBuildId: string): Promise<LinkUpdatePlan> {
    const userId = deps.activeUserId()
    if (!userId) return { kind: 'sign-in-required' }
    const record = await deps.records.find(localBuildId, userId)
    const local = await deps.local.read(localBuildId)
    const cloud = record ? await findCloud(record.cloudBuildId) : undefined
    const plan = planSharedLinkUpdate({ activeUserId: userId, record, localHash: local.hash, cloud })
    if (plan.kind === 'conflict') return conflictFor(localBuildId, plan.cloudBuildId)
    return plan
  }

  /** Runs only after the user confirmed the update; the only call that moves a named URL. */
  async function confirmSharedLinkUpdate(plan: { cloudBuildId: string; revisionId: string }) {
    return deps.accounts.updateNamedLink(plan.cloudBuildId, { revisionId: plan.revisionId })
  }

  async function onLocalBuildDeleted(localBuildId: string): Promise<void> {
    await deps.records.removeForLocalBuild(localBuildId)
  }

  return {
    upload,
    linkExisting,
    resolveConflict,
    download,
    downloadCloudBuild,
    planSharedLinkUpdate: planLinkUpdate,
    confirmSharedLinkUpdate,
    onLocalBuildDeleted,
  }
}

export type CloudSync = ReturnType<typeof createCloudSync>
