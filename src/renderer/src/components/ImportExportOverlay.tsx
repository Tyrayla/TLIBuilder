import React, { useRef, useState } from 'react'
import { api, Build } from '../api/client'
import ImportPanel from './ImportPanel'

interface Props {
  isDirty: boolean
  buildId: string | null
  buildName: string
  getBuildPayload: () => Record<string, unknown>
  onImport: (build: Build) => void
  onSaveFirst: (name: string) => Promise<void>
  onClose: () => void
  asScreen?: boolean
}

export default function ImportExportOverlay({ isDirty, buildId, buildName, getBuildPayload, onImport, onSaveFirst, onClose, asScreen = false }: Props) {
  const [tab, setTab] = useState<'export' | 'import'>('export')

  const [exportCode, setExportCode] = useState<string | null>(null)
  const [exportLoading, setExportLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  // Share-via-link state (additive; the raw-code copy path never depends on it).
  const [shareUrl, setShareUrl] = useState<string | null>(null)
  const [shareLoading, setShareLoading] = useState(false)
  const [shareError, setShareError] = useState<string | null>(null)
  const [shareCopied, setShareCopied] = useState(false)

  const [dirtyPrompt, setDirtyPrompt] = useState(false)
  const [dirtySaveName, setDirtySaveName] = useState(buildName)
  const [dirtySaving, setDirtySaving] = useState(false)
  // The build ImportPanel produced, held so the dirty Save/Discard prompt can apply it after the user decides.
  const decodedBuildRef = useRef<Build | null>(null)

  const handleGenerate = async () => {
    setExportLoading(true)
    try {
      const { code } = await api.encodeBuildCode(getBuildPayload())
      setExportCode(code)
      setCopied(false)
      setShareUrl(null)
      setShareError(null)
    } catch { /* silent */ }
    finally { setExportLoading(false) }
  }

  const handleCopy = () => {
    if (!exportCode) return
    navigator.clipboard.writeText(exportCode).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const handleShare = async () => {
    if (!exportCode) return
    setShareLoading(true)
    setShareError(null)
    try {
      const { url } = await api.shareBuildCode(exportCode)
      setShareUrl(url)
      setShareCopied(false)
    } catch {
      // Link sharing is additive — never a hard dependency. The raw code above
      // stays fully copyable when the share service is unreachable.
      setShareError("Couldn't create a share link — the service may be unavailable. You can still copy the code above.")
    } finally {
      setShareLoading(false)
    }
  }

  const handleCopyShareUrl = () => {
    if (!shareUrl) return
    navigator.clipboard.writeText(shareUrl).then(() => {
      setShareCopied(true)
      setTimeout(() => setShareCopied(false), 2000)
    })
  }

  const applyDecodedBuild = (build: Build) => {
    onImport(build)
    onClose()
  }

  // ImportPanel produced a ready build → apply it, prompting about unsaved changes first if needed.
  const proceedWithBuild = (decoded: Build) => {
    decodedBuildRef.current = decoded
    if (isDirty) { setDirtySaveName(buildName); setDirtyPrompt(true); return }
    applyDecodedBuild(decoded)
  }

  const handleDirtySave = async () => {
    const name = buildId ? buildName : (dirtySaveName.trim() || 'Untitled')
    setDirtySaving(true)
    try {
      await onSaveFirst(name)
      setDirtyPrompt(false)
      if (decodedBuildRef.current) applyDecodedBuild(decodedBuildRef.current)
    } catch { /* save failed — leave dirty prompt open */ }
    finally { setDirtySaving(false) }
  }

  const handleDirtyDiscard = () => {
    setDirtyPrompt(false)
    if (decodedBuildRef.current) applyDecodedBuild(decodedBuildRef.current)
  }

  const tabsAndContent = (
    <>
      <div className="import-export-tabs">
        <button
          className={`import-export-tab${tab === 'export' ? ' active' : ''}`}
          onClick={() => setTab('export')}
        >Export</button>
        <button
          className={`import-export-tab${tab === 'import' ? ' active' : ''}`}
          onClick={() => setTab('import')}
        >Import</button>
      </div>

      {tab === 'export' && (
        <>
          <p className="share-modal-hint">Generate a code to share this build. Anyone can import it to load your build.</p>
          {!exportCode ? (
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleGenerate} disabled={exportLoading}>
                {exportLoading ? 'Generating…' : 'Generate Code'}
              </button>
              {!asScreen && <button className="btn btn-secondary" onClick={onClose}>Close</button>}
            </div>
          ) : (
            <>
              <textarea
                className="share-code-area"
                readOnly
                value={exportCode}
                onFocus={e => e.target.select()}
              />
              <div className="modal-actions">
                <button
                  className={`btn btn-primary${copied ? ' share-copied' : ''}`}
                  onClick={handleCopy}
                >
                  {copied ? 'Copied!' : 'Copy Code'}
                </button>
                {!shareUrl && (
                  <button
                    className="btn btn-secondary"
                    onClick={handleShare}
                    disabled={shareLoading}
                  >
                    {shareLoading ? 'Creating link…' : 'Share via Link'}
                  </button>
                )}
                {!asScreen && <button className="btn btn-secondary" onClick={onClose}>Close</button>}
              </div>
              {shareError && <p className="share-import-error">{shareError}</p>}
              {shareUrl && (
                <>
                  <textarea
                    className="share-code-area"
                    readOnly
                    value={shareUrl}
                    onFocus={e => e.target.select()}
                  />
                  <div className="modal-actions">
                    <button
                      className={`btn btn-primary${shareCopied ? ' share-copied' : ''}`}
                      onClick={handleCopyShareUrl}
                    >
                      {shareCopied ? 'Copied!' : 'Copy Link'}
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </>
      )}

      {tab === 'import' && (
        <>
          <ImportPanel onImport={proceedWithBuild} autoFocus />
          {!asScreen && (
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
            </div>
          )}
        </>
      )}
    </>
  )

  const dirtyPromptModal = dirtyPrompt && (
    <div className="modal-backdrop" onClick={() => setDirtyPrompt(false)}>
      <div className="modal-card" onClick={e => e.stopPropagation()}>
        <div className="modal-accent" />
        <h3 className="modal-title">Unsaved Changes</h3>
        <p style={{ padding: '0 20px 12px', color: '#aaa', fontSize: 13, lineHeight: 1.6 }}>
          {buildId
            ? `Save "${buildName || 'this build'}" before importing?`
            : 'You have unsaved changes. Save before importing?'}
        </p>
        {!buildId && (
          <input
            className="modal-input"
            type="text"
            placeholder="Build name…"
            value={dirtySaveName}
            onChange={e => setDirtySaveName(e.target.value)}
            autoFocus
          />
        )}
        <div className="modal-actions">
          <button className="btn btn-primary" onClick={handleDirtySave} disabled={dirtySaving}>
            {dirtySaving ? 'Saving…' : 'Save'}
          </button>
          <button className="btn btn-danger" onClick={handleDirtyDiscard}>Discard</button>
          <button className="btn btn-secondary" onClick={() => setDirtyPrompt(false)}>Cancel</button>
        </div>
      </div>
    </div>
  )

  if (asScreen) {
    return (
      <div className="screen import-export-screen">
        <div className="import-export-screen-inner">
          {tabsAndContent}
        </div>
        {dirtyPromptModal}
      </div>
    )
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card import-export-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-accent" />
        {tabsAndContent}
        {dirtyPromptModal}
      </div>
    </div>
  )
}
