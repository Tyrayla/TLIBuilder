import React from 'react'
import { STATUS_LABEL, type LibraryStatus } from '../../utils/librarySync'

interface Props {
  status: LibraryStatus | undefined
  onUpload: () => void
  onDownload: () => void
  onLinkUpdate: () => void
}

/**
 * Passive sync indicator and explicit actions for one build card. The indicator only reports; the
 * conflict screen appears only after the user presses one of the buttons.
 */
export default function BuildCloudControls({ status, onUpload, onDownload, onLinkUpdate }: Props) {
  if (!status) return null
  const { status: s, cloud } = status
  const linked = s !== 'not-uploaded' && s !== 'cloud-missing'
  const hasNamedLink = linked && !!cloud?.namedLink
  const stop = (fn: () => void) => (e: { stopPropagation: () => void }) => { e.stopPropagation(); fn() }
  const action = s === 'not-uploaded' ? { label: 'Upload to cloud', run: onUpload }
    : s === 'local-changes' ? { label: 'Sync', run: onUpload }
    : s === 'cloud-newer' ? { label: 'Update from cloud', run: onDownload }
    : s === 'diverged' ? { label: 'Review conflict', run: onUpload }
    : s === 'cloud-missing' ? { label: 'Upload again', run: onUpload }
    : null
  const cloudDate = typeof cloud?.updatedAt === 'number' && Number.isFinite(cloud.updatedAt)
    ? new Date(cloud.updatedAt * 1000).toLocaleDateString()
    : null
  const syncedLabel = `Synced${cloudDate ? ` - ${cloudDate}` : ''}`
  const detail = s === 'cloud-newer' && cloudDate ? `Cloud copy updated ${cloudDate}`
    : s === 'local-changes' && cloudDate ? `Cloud copy last updated ${cloudDate}`
    : s === 'diverged' ? 'Local and cloud copies both changed'
    : null

  return (
    <div className="build-card-cloud" onClick={(e) => e.stopPropagation()}>
      <span className={`build-cloud-status${s === 'diverged' ? ' build-cloud-status--conflict' : ''}`} title="Cloud status">
        {s === 'synced' ? syncedLabel : STATUS_LABEL[s]}
      </span>
      {detail && <span className="build-cloud-detail">{detail}</span>}
      <div className="build-card-cloud-actions">
        {action && <button className="btn btn-secondary btn-sm" onClick={stop(action.run)}>{action.label}</button>}
        {hasNamedLink && <button className="btn btn-secondary btn-sm" onClick={stop(onLinkUpdate)}>Update shared link</button>}
      </div>
    </div>
  )
}
