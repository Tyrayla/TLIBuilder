import React, { useCallback, useEffect, useState } from 'react'
import { AccountApiError, getAccountsApi, type CloudBuild } from '../../api/accounts'
import { getAccountStore, useAccountStore } from '../../store/accountStore'
import { getCloudSync } from '../../utils/cloudSyncRuntime'
import { defaultSyncRecordStore } from '../../utils/syncRecords'

export interface CloudLibraryActions {
  saveToDevice: (cloudBuildId: string) => Promise<void>
  deleteBuild: (cloudBuildId: string) => Promise<void>
  createLink: (cloudBuildId: string, slug: string | undefined) => Promise<void>
  setListed: (cloudBuildId: string, listed: boolean) => Promise<void>
  removeLink: (cloudBuildId: string) => Promise<void>
  close: () => void
}

interface ViewProps {
  builds: CloudBuild[] | null
  loading: boolean
  loadError: string | null
  usage: { cloudBuilds: number; limit: number }
  actions: CloudLibraryActions
}

const SLUG_RULE = /^[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?$/
const SLUG_RULE_TEXT = 'Link names use 1–48 lowercase letters, numbers, or dashes, with no dash at the start or end.'

function describeError(error: unknown): string {
  if (error instanceof AccountApiError) {
    if (error.code === 'profile_quota_reached') return 'Your profile already shows 10 builds. Hide one first.'
    if (error.code === 'slug_taken') return 'That link name is already used. Choose another.'
    if (error.code === 'invalid_slug') return SLUG_RULE_TEXT
    return error.message
  }
  return error instanceof Error ? error.message : 'Something went wrong.'
}

export function CloudLibraryView({ builds, loading, loadError, usage, actions }: ViewProps) {
  const [slugs, setSlugs] = useState<Record<string, string>>({})
  const [deleteTarget, setDeleteTarget] = useState<CloudBuild | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)

  const attempt = async (key: string, fn: () => Promise<void>): Promise<void> => {
    setBusy(true)
    setErrors((e) => { const next = { ...e }; delete next[key]; return next })
    try { await fn() } catch (error) { setErrors((e) => ({ ...e, [key]: describeError(error) })) } finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={actions.close}>
      <div className="modal-card" style={{ width: 640, maxWidth: '94vw', maxHeight: '86vh', display: 'flex', flexDirection: 'column' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-accent" />
        <h3 className="modal-title">Cloud library</h3>
        <p style={{ padding: '0 20px 8px', margin: 0, fontSize: 13, color: 'var(--fg-faint)' }}>
          {`${usage.cloudBuilds} of ${usage.limit} cloud builds used. `}Cloud builds are private until you create a named link.
        </p>

        <div className="dark-scroll" style={{ padding: '0 20px 12px', overflowY: 'auto', flex: 1 }}>
          {loading && <p>Loading…</p>}
          {loadError && <p role="alert" style={{ color: 'var(--err)' }}>{loadError}</p>}
          {builds && builds.length === 0 && <p>No cloud builds yet. Use “Upload to cloud” on a build in your library.</p>}
          {builds?.map((b) => (
            <div key={b.cloudBuildId} style={{ borderTop: '1px solid var(--border)', padding: '10px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
                <span style={{ fontWeight: 600, overflowWrap: 'anywhere' }}>{b.name}</span>
                <span style={{ fontSize: 12, color: 'var(--fg-faint)' }}>{new Date(b.updatedAt * 1000).toLocaleDateString()}</span>
              </div>

              {b.namedLink ? (
                <div style={{ fontSize: 13, margin: '6px 0' }}>
                  <span style={{ overflowWrap: 'anywhere' }}>{b.namedLink.urlPath}</span>
                  {' · '}
                  <span>{b.namedLink.listed ? 'Shown on profile' : 'Unlisted'}</span>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: 6, margin: '6px 0' }}>
                  <input
                    className="modal-input"
                    style={{ flex: 1 }}
                    placeholder="link-name (optional)"
                    aria-label={`Link name for ${b.name}`}
                    value={slugs[b.cloudBuildId] ?? ''}
                    onChange={(e) => setSlugs((s) => ({ ...s, [b.cloudBuildId]: e.target.value }))}
                  />
                </div>
              )}

              <div className="settings-segmented" style={{ flexWrap: 'wrap' }}>
                <button className="settings-seg-btn" disabled={busy} onClick={() => attempt(b.cloudBuildId, () => actions.saveToDevice(b.cloudBuildId))}>Save to this device</button>
                {b.namedLink ? (
                  <>
                    <button className="settings-seg-btn" disabled={busy} onClick={() => attempt(b.cloudBuildId, () => actions.setListed(b.cloudBuildId, !b.namedLink!.listed))}>
                      {b.namedLink.listed ? 'Hide from profile' : 'Show on profile'}
                    </button>
                    <button className="settings-seg-btn" disabled={busy} onClick={() => attempt(b.cloudBuildId, () => actions.removeLink(b.cloudBuildId))}>Remove link</button>
                  </>
                ) : (
                  <button
                    className="settings-seg-btn"
                    disabled={busy}
                    onClick={() => attempt(b.cloudBuildId, async () => {
                      const slug = (slugs[b.cloudBuildId] ?? '').trim()
                      if (slug && !SLUG_RULE.test(slug)) throw new Error(SLUG_RULE_TEXT)
                      await actions.createLink(b.cloudBuildId, slug || undefined)
                    })}
                  >Create link</button>
                )}
                <button className="settings-seg-btn" disabled={busy} onClick={() => setDeleteTarget(b)}>Delete from cloud</button>
              </div>
              {errors[b.cloudBuildId] && <p role="alert" style={{ color: 'var(--err)', fontSize: 13, margin: '6px 0 0' }}>{errors[b.cloudBuildId]}</p>}
            </div>
          ))}
        </div>

        {deleteTarget && (
          <div style={{ padding: '10px 20px', borderTop: '1px solid var(--border)' }}>
            <p style={{ margin: '0 0 8px', fontSize: 13, lineHeight: 1.5 }}>
              Delete “{deleteTarget.name}” from the cloud?
              {deleteTarget.namedLink && <> <strong>{deleteTarget.namedLink.urlPath}</strong> will stop working for anyone who has it.</>}
              {' '}Your local copy is not affected.
            </p>
            <div className="settings-segmented">
              <button
                className="settings-seg-btn"
                disabled={busy}
                onClick={() => {
                  const target = deleteTarget
                  setDeleteTarget(null)
                  void attempt(target.cloudBuildId, () => actions.deleteBuild(target.cloudBuildId))
                }}
              >{deleteTarget.namedLink ? 'Delete build and link' : 'Delete build'}</button>
              <button className="settings-seg-btn" onClick={() => setDeleteTarget(null)}>Cancel</button>
            </div>
          </div>
        )}

        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={actions.close}>Close</button>
        </div>
      </div>
    </div>
  )
}

/** Connected overlay. `onChanged` runs after anything that changed local builds or sync records. */
export default function CloudLibraryOverlay({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const account = useAccountStore((s) => s.account)
  const [builds, setBuilds] = useState<CloudBuild[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      setBuilds(await getAccountsApi().listCloudBuilds())
      setLoadError(null)
    } catch (e) {
      setLoadError(describeError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void reload() }, [reload])

  const actions: CloudLibraryActions = {
    close: onClose,
    async saveToDevice(cloudBuildId) {
      const outcome = await getCloudSync().downloadCloudBuild(cloudBuildId)
      if (outcome.kind === 'error') throw new Error(outcome.message)
      onChanged()
    },
    async deleteBuild(cloudBuildId) {
      await getAccountsApi().deleteCloudBuild(cloudBuildId)
      const userId = getAccountStore().getState().account?.userId
      if (userId) await defaultSyncRecordStore().removeForCloudBuild(cloudBuildId, userId)
      await reload()
      void getAccountStore().getState().refresh()
      onChanged()
    },
    async createLink(cloudBuildId, slug) {
      await getAccountsApi().updateNamedLink(cloudBuildId, { slug, listed: false })
      await reload()
    },
    async setListed(cloudBuildId, listed) {
      await getAccountsApi().updateNamedLink(cloudBuildId, { listed })
      await reload()
      void getAccountStore().getState().refresh()
    },
    async removeLink(cloudBuildId) {
      await getAccountsApi().deleteNamedLink(cloudBuildId)
      await reload()
    },
  }

  return (
    <CloudLibraryView
      builds={builds}
      loading={loading}
      loadError={loadError}
      usage={{ cloudBuilds: builds?.length ?? account?.usage.cloudBuilds ?? 0, limit: account?.limits.cloudBuilds ?? 20 }}
      actions={actions}
    />
  )
}
