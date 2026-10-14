// Cloud-sync decisions, kept pure so every rule in docs/HOSTED_ACCOUNT_PLATFORM_PLAN.md ("Local sync
// records", "Sync status and the conflict screen") can be tested without a network or a UI.
//
// A sync record is separate from the Build: it never enters a tli1_ code, an export, or the semantic
// hash. This module only decides; stores and screens perform the calls.
import { decodeBuildCodeLean } from './decodeBuildCodeLean'

export const MAX_BUILD_NAME_LENGTH = 50

export interface SyncRecord {
  localBuildId: string
  accountUserId: string
  cloudBuildId: string
  baseRevisionId: string
  baseSemanticHash: string
}

export interface CloudBuildSummary {
  cloudBuildId: string
  name: string
  currentRevisionId: string
  semanticHash: string
  updatedAt: number
}

export type SyncStatus =
  | 'not-uploaded'
  | 'synced'
  | 'local-changes'
  | 'cloud-newer'
  | 'diverged'
  | 'cloud-missing'

// ── Semantic hash ────────────────────────────────────────────────────────────
// Contract shared with the hosted service: SHA-256 (lowercase hex) of the decoded build JSON with the
// technical persistence fields removed, keys sorted at every depth, compact separators, UTF-8 output
// with no ASCII escaping, and integer-valued numbers written without a fraction. Name and notes stay.
const TECHNICAL_FIELDS = new Set(['id', 'createdAt', 'updatedAt'])

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (value !== null && typeof value === 'object') {
    const obj = value as Record<string, unknown>
    const keys = Object.keys(obj).filter((k) => obj[k] !== undefined).sort()
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(obj[k])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

export async function semanticBuildHash(code: string): Promise<string> {
  const decoded = await decodeBuildCodeLean(code)
  const content: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(decoded)) {
    if (!TECHNICAL_FIELDS.has(key)) content[key] = value
  }
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalJson(content)))
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
}

// ── Status ───────────────────────────────────────────────────────────────────
export interface StatusInput {
  record: SyncRecord | undefined
  localHash: string | null
  /** `undefined`: cloud state not read yet. `null`: read, and the cloud build no longer exists. */
  cloud: CloudBuildSummary | null | undefined
  activeUserId: string | null
}

/** The record this account may use. Another account's record, or no signed-in account, hides it. */
function usableRecord(record: SyncRecord | undefined, activeUserId: string | null): SyncRecord | undefined {
  if (!record || !activeUserId || record.accountUserId !== activeUserId) return undefined
  return record
}

export function recordsForAccount(records: SyncRecord[], activeUserId: string | null): SyncRecord[] {
  if (!activeUserId) return []
  return records.filter((r) => r.accountUserId === activeUserId)
}

export function syncStatus(input: StatusInput): SyncStatus {
  const record = usableRecord(input.record, input.activeUserId)
  if (!record) return 'not-uploaded'
  if (input.cloud === null) return 'cloud-missing'
  const localChanged = input.localHash !== null && input.localHash !== record.baseSemanticHash
  const cloudNewer = input.cloud !== undefined && input.cloud.currentRevisionId !== record.baseRevisionId
  if (localChanged && cloudNewer) return 'diverged'
  if (cloudNewer) return 'cloud-newer'
  if (localChanged) return 'local-changes'
  return 'synced'
}

// ── Names ────────────────────────────────────────────────────────────────────
export function shortenBuildName(name: string): string {
  return name.length > MAX_BUILD_NAME_LENGTH ? name.slice(0, MAX_BUILD_NAME_LENGTH) : name
}

// ── Plans ────────────────────────────────────────────────────────────────────
export type ConflictChoice = 'keep-both' | 'keep-local' | 'keep-cloud'

export interface ConflictPlan {
  kind: 'conflict'
  cloudBuildId: string
  cloudRevisionId: string
  defaultChoice: 'keep-both'
}

function conflict(cloud: CloudBuildSummary): ConflictPlan {
  return { kind: 'conflict', cloudBuildId: cloud.cloudBuildId, cloudRevisionId: cloud.currentRevisionId, defaultChoice: 'keep-both' }
}

export interface ActionInput {
  activeUserId: string | null
  record: SyncRecord | undefined
  localHash: string | null
  cloud: CloudBuildSummary | null | undefined
}

export type UploadPlan =
  | { kind: 'sign-in-required' }
  | { kind: 'shorten-name'; suggestedName: string }
  | { kind: 'upload-new'; allowDuplicate: boolean }
  | { kind: 'upload-revision'; cloudBuildId: string; baseRevisionId: string }
  | { kind: 'nothing-to-upload' }
  | { kind: 'cloud-newer' }
  | { kind: 'cloud-missing' }
  | ConflictPlan

export function planUpload(input: ActionInput & { name: string }): UploadPlan {
  if (!input.activeUserId) return { kind: 'sign-in-required' }
  const record = usableRecord(input.record, input.activeUserId)
  let plan: UploadPlan
  if (!record) {
    plan = { kind: 'upload-new', allowDuplicate: false }
  } else {
    const status = syncStatus({ ...input, record })
    if (status === 'cloud-missing') return { kind: 'cloud-missing' }
    if (status === 'diverged' && input.cloud) return conflict(input.cloud)
    if (status === 'cloud-newer') return { kind: 'cloud-newer' }
    if (status === 'synced') return { kind: 'nothing-to-upload' }
    // The write is conditional on the revision this local copy was edited from.
    plan = { kind: 'upload-revision', cloudBuildId: record.cloudBuildId, baseRevisionId: record.baseRevisionId }
  }
  if (input.name.length > MAX_BUILD_NAME_LENGTH) {
    return { kind: 'shorten-name', suggestedName: shortenBuildName(input.name) }
  }
  return plan
}

export type DownloadPlan =
  | { kind: 'sign-in-required' }
  | { kind: 'download'; cloudBuildId: string; revisionId: string }
  | { kind: 'download-as-new'; cloudBuildId: string; revisionId: string }
  | { kind: 'nothing-to-download' }
  | { kind: 'cloud-missing' }
  | ConflictPlan

export function planDownload(input: ActionInput): DownloadPlan {
  if (!input.activeUserId) return { kind: 'sign-in-required' }
  if (input.cloud === null) return { kind: 'cloud-missing' }
  if (!input.cloud) return { kind: 'nothing-to-download' }
  const record = usableRecord(input.record, input.activeUserId)
  if (!record) {
    return { kind: 'download-as-new', cloudBuildId: input.cloud.cloudBuildId, revisionId: input.cloud.currentRevisionId }
  }
  const status = syncStatus({ ...input, record })
  // Downloading over unsynced local changes would replace them, so it goes through the conflict screen.
  if (status === 'diverged' || status === 'local-changes') return conflict(input.cloud)
  if (status === 'synced') return { kind: 'nothing-to-download' }
  return { kind: 'download', cloudBuildId: input.cloud.cloudBuildId, revisionId: input.cloud.currentRevisionId }
}

export type SharedLinkUpdatePlan =
  | { kind: 'sign-in-required' }
  | { kind: 'upload-first' }
  | { kind: 'confirm-link-update'; cloudBuildId: string; revisionId: string }
  | ConflictPlan

export function planSharedLinkUpdate(input: ActionInput): SharedLinkUpdatePlan {
  if (!input.activeUserId) return { kind: 'sign-in-required' }
  const record = usableRecord(input.record, input.activeUserId)
  if (!record || !input.cloud) return { kind: 'upload-first' }
  const status = syncStatus({ ...input, record })
  if (status === 'diverged') return conflict(input.cloud)
  if (status === 'local-changes') return { kind: 'upload-first' }
  // A normal save never moves a named URL; this always waits for the owner's explicit confirmation.
  return { kind: 'confirm-link-update', cloudBuildId: input.cloud.cloudBuildId, revisionId: input.cloud.currentRevisionId }
}

export type ConflictResolution =
  | { kind: 'save-cloud-as-new-local'; attachSyncRecord: false }
  | { kind: 'needs-confirmation'; replaces: 'cloud' | 'local' }
  | { kind: 'upload-conditional' }
  | { kind: 'replace-local' }

export function resolveConflict(choice: ConflictChoice, opts: { confirmed: boolean }): ConflictResolution {
  if (choice === 'keep-both') return { kind: 'save-cloud-as-new-local', attachSyncRecord: false }
  if (choice === 'keep-local') {
    return opts.confirmed ? { kind: 'upload-conditional' } : { kind: 'needs-confirmation', replaces: 'cloud' }
  }
  return opts.confirmed ? { kind: 'replace-local' } : { kind: 'needs-confirmation', replaces: 'local' }
}
