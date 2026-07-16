import React, { useMemo, useState } from 'react'
import { markdownToHtml } from '../utils/markdown'
import { sanitizeHtml } from '../utils/sanitizeHtml'

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
  // electron-updater's GitHub provider already returns the release notes as HTML in many cases; fall back
  // to the markdown converter if the notes don't look like HTML (e.g. a generic feed). Either way, this is
  // an untrusted upstream string (a GitHub release body) — it ALWAYS goes through sanitizeHtml before
  // dangerouslySetInnerHTML, never injected verbatim. markdownToHtml already sanitizes its own output too,
  // so this is defense-in-depth for that branch and the only defense for the "looks like HTML" branch.
  const notesHtml = useMemo(() => {
    const notes = info.releaseNotes || ''
    const looksLikeHtml = /<\/?(h[1-6]|ul|ol|li|p|strong|em|a|code|pre|blockquote|br|div)\b/i.test(notes)
    return looksLikeHtml ? sanitizeHtml(notes) : markdownToHtml(notes)
  }, [info.releaseNotes])

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
              ? <div className="changelog-body" dangerouslySetInnerHTML={{ __html: notesHtml }} />
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
