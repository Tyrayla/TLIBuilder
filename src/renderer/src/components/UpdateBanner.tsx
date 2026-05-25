import React, { useState } from 'react'

export interface UpdateInfo {
  version: string
  releaseNotes: string
  releaseDate: string
}

interface Props {
  info: UpdateInfo
  downloading: boolean
  progress: number
  downloaded: boolean
  onDownload: () => void
  onInstall: () => void
}

export default function UpdateBanner({ info, downloading, progress, downloaded, onDownload, onInstall }: Props) {
  const [dismissed, setDismissed] = useState(false)
  const [changelogOpen, setChangelogOpen] = useState(false)

  if (dismissed) return null

  return (
    <>
      <div className="update-banner">
        <span>Version {info.version} is available</span>
        <button className="btn btn-sm" onClick={() => setChangelogOpen(true)}>What's New</button>
        {!downloaded ? (
          <button className="btn btn-sm btn-primary" onClick={onDownload} disabled={downloading}>
            {downloading ? `Downloading… ${progress}%` : 'Download'}
          </button>
        ) : (
          <button className="btn btn-sm btn-primary" onClick={onInstall}>
            Restart &amp; Install
          </button>
        )}
        <button className="update-banner-dismiss" onClick={() => setDismissed(true)}>✕</button>
      </div>

      {changelogOpen && (
        <div className="modal-backdrop" onClick={() => setChangelogOpen(false)}>
          <div className="modal-card changelog-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">What's New in {info.version}</h3>
            {info.releaseNotes
              ? <div className="changelog-body" dangerouslySetInnerHTML={{ __html: info.releaseNotes }} />
              : <div className="changelog-body changelog-body-empty">No release notes provided.</div>
            }
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setChangelogOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
