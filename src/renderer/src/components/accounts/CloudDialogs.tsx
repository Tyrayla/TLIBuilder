import React, { useState } from 'react'
import { MAX_BUILD_NAME_LENGTH } from '../../utils/sync'

const bodyStyle: React.CSSProperties = { padding: '0 20px 14px', color: 'var(--fg-faint)', fontSize: 13, lineHeight: 1.6 }

export function NoticeDialog({ title, body, actions, onClose }: {
  title: string
  body: string
  actions?: { label: string; onClick: () => void }[]
  onClose: () => void
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="modal-accent" />
        <h3 className="modal-title">{title}</h3>
        <p style={bodyStyle}>{body}</p>
        <div className="modal-actions">
          {(actions ?? []).map((a) => (
            <button key={a.label} className="btn btn-primary" onClick={a.onClick}>{a.label}</button>
          ))}
          <button className="btn btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}

/** Cloud build names are at most 50 characters. Never shortens a name without the user's confirmation. */
export function ShortenNameDialog({ currentName, suggested, onConfirm, onCancel }: {
  currentName: string
  suggested: string
  onConfirm: (name: string) => void
  onCancel: () => void
}) {
  const [value, setValue] = useState(suggested)
  const trimmed = value.trim()
  return (
    <div className="modal-backdrop">
      <div className="modal-card" role="dialog" aria-label="Shorten build name">
        <div className="modal-accent" />
        <h3 className="modal-title">Shorten the build name</h3>
        <p style={bodyStyle}>
          Cloud build names can be at most {MAX_BUILD_NAME_LENGTH} characters. “{currentName}” has {currentName.length}.
          Choose a shorter name; your local build is renamed to match.
        </p>
        <input
          className="modal-input"
          value={value}
          maxLength={MAX_BUILD_NAME_LENGTH}
          aria-label="Build name"
          onChange={(e) => setValue(e.target.value)}
        />
        <p style={{ ...bodyStyle, paddingTop: 6 }}>{value.length} / {MAX_BUILD_NAME_LENGTH}</p>
        <div className="modal-actions">
          <button className="btn btn-primary" disabled={trimmed.length === 0} onClick={() => onConfirm(trimmed)}>Rename and upload</button>
          <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

/** An unlinked local build matches a build already in the account's cloud library. */
export function LinkPromptDialog({ cloudBuildName, onLink, onUploadNew, onCancel }: {
  cloudBuildName: string
  onLink: () => void
  onUploadNew: () => void
  onCancel: () => void
}) {
  return (
    <div className="modal-backdrop">
      <div className="modal-card" role="dialog" aria-label="Matching cloud build">
        <div className="modal-accent" />
        <h3 className="modal-title">This build is already in your cloud library</h3>
        <p style={bodyStyle}>
          “{cloudBuildName}” has the same content. Link this build to it to sync them from now on, which uses no extra
          slot. Or upload it as a separate cloud build, which uses one of your 20 cloud slots.
        </p>
        <div className="modal-actions">
          <button className="btn btn-primary" onClick={onLink}>{`Link to “${cloudBuildName}”`}</button>
          <button className="btn btn-secondary" onClick={onUploadNew}>Upload as a new build</button>
          <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

/** Moving a named link to a different revision always asks first. */
export function LinkUpdateDialog({ linkPath, onConfirm, onCancel }: {
  linkPath: string | null
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="modal-backdrop">
      <div className="modal-card" role="dialog" aria-label="Update shared link">
        <div className="modal-accent" />
        <h3 className="modal-title">Update the shared link?</h3>
        <p style={bodyStyle}>
          {linkPath ? <>Anyone who opens <strong>{linkPath}</strong> will see this version from now on. </> : 'Anyone who opens the shared link will see this version from now on. '}
          Saving or uploading never changes a shared link by itself.
        </p>
        <div className="modal-actions">
          <button className="btn btn-primary" onClick={onConfirm}>Update shared link</button>
          <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  )
}
