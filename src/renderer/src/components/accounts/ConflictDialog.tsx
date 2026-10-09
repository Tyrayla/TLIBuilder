import React, { useState } from 'react'

export interface ConflictSide {
  name: string
  /** Unix seconds, or null when unknown. */
  savedAt: number | null
  hero: string | null
  mainSkill: string | null
}

interface Props {
  local: ConflictSide
  cloud: ConflictSide
  busy: boolean
  error: string | null
  onKeepBoth: () => void
  onKeepLocal: () => void
  onKeepCloud: () => void
  onCancel: () => void
}

function when(savedAt: number | null): string {
  return savedAt ? new Date(savedAt * 1000).toLocaleString() : 'Unknown'
}

function SideCard({ title, side }: { title: string; side: ConflictSide }) {
  const rows: [string, string][] = [
    ['Name', side.name],
    ['Saved', when(side.savedAt)],
    ['Hero', side.hero ?? 'Unknown'],
    ['Main skill', side.mainSkill ?? 'None'],
  ]
  return (
    <div style={{ flex: 1, minWidth: 0, background: 'var(--bg-deep)', border: '1px solid var(--border)', borderRadius: 6, padding: 10 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{title}</div>
      {rows.map(([label, value]) => (
        <div key={label} style={{ fontSize: 12, marginBottom: 3, overflowWrap: 'anywhere' }}>
          <span style={{ color: 'var(--fg-faint)' }}>{label}: </span>
          <span>{value}</span>
        </div>
      ))}
    </div>
  )
}

/**
 * Shown only after the user starts an explicit upload, download or shared-link update on a build whose
 * local copy and cloud copy have both changed. Keep both is the default and is safe; Keep local and
 * Keep cloud each ask a second time and name what will be replaced.
 */
export default function ConflictDialog({ local, cloud, busy, error, onKeepBoth, onKeepLocal, onKeepCloud, onCancel }: Props) {
  const [confirming, setConfirming] = useState<'local' | 'cloud' | null>(null)

  return (
    <div className="modal-backdrop">
      <div className="modal-card" style={{ width: 560, maxWidth: '92vw' }} role="dialog" aria-label="Resolve conflict">
        <div className="modal-accent" />
        <h3 className="modal-title">This build changed in two places</h3>
        <div style={{ padding: '0 20px 12px' }}>
          <p style={{ color: 'var(--fg-faint)', fontSize: 13, lineHeight: 1.5, margin: '0 0 10px' }}>
            The copy on this device and the copy in the cloud both have changes the other does not.
          </p>
          <div style={{ display: 'flex', gap: 10 }}>
            <SideCard title="This device" side={local} />
            <SideCard title="Cloud" side={cloud} />
          </div>

          {confirming === 'local' && (
            <p style={{ marginTop: 12, fontSize: 13, lineHeight: 1.5 }}>
              This replaces the cloud version “{cloud.name}” (saved {when(cloud.savedAt)}) with your local version.
              The replaced cloud version is not kept.
            </p>
          )}
          {confirming === 'cloud' && (
            <p style={{ marginTop: 12, fontSize: 13, lineHeight: 1.5 }}>
              This replaces your local build “{local.name}” (saved {when(local.savedAt)}) with the cloud version.
              Your local changes are not kept.
            </p>
          )}
          {error && <p role="alert" style={{ marginTop: 10, color: 'var(--err)', fontSize: 13 }}>{error}</p>}
        </div>

        <div className="modal-actions">
          {confirming === null ? (
            <>
              <button className="btn btn-primary" disabled={busy} onClick={onKeepBoth}>Keep both</button>
              <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirming('local')}>Keep local</button>
              <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirming('cloud')}>Keep cloud</button>
              <button className="btn btn-secondary" disabled={busy} onClick={onCancel}>Cancel</button>
            </>
          ) : (
            <>
              <button
                className="btn btn-danger"
                disabled={busy}
                onClick={confirming === 'local' ? onKeepLocal : onKeepCloud}
              >{confirming === 'local' ? 'Replace cloud version' : 'Replace local build'}</button>
              <button className="btn btn-secondary" disabled={busy} onClick={() => setConfirming(null)}>Back</button>
            </>
          )}
        </div>
        {confirming === null && (
          <p style={{ padding: '0 20px 14px', margin: 0, fontSize: 12, color: 'var(--fg-faint)' }}>
            Keep both saves the cloud version as a new local build and leaves your build as it is.
          </p>
        )}
      </div>
    </div>
  )
}
