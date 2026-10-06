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
  const canUpload = s === 'not-uploaded' || s === 'local-changes' || s === 'diverged' || s === 'cloud-missing'
  const hasNamedLink = linked && !!cloud?.namedLink
  const stop = (fn: () => void) => (e: { stopPropagation: () => void }) => { e.stopPropagation(); fn() }

  return (
    <div className="build-card-cloud" style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end', marginLeft: 'auto' }} onClick={(e) => e.stopPropagation()}>
      <span style={{ fontSize: 11, color: s === 'diverged' ? 'var(--err)' : 'var(--fg-faint)' }} title="Cloud status">{STATUS_LABEL[s]}</span>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        {canUpload && <button className="btn btn-secondary btn-sm" onClick={stop(onUpload)}>Upload to cloud</button>}
        {linked && <button className="btn btn-secondary btn-sm" onClick={stop(onDownload)}>Download from cloud</button>}
        {hasNamedLink && <button className="btn btn-secondary btn-sm" onClick={stop(onLinkUpdate)}>Update shared link</button>}
      </div>
    </div>
  )
}
