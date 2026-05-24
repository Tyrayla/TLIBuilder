import React, { useRef, useState } from 'react'
import { api, Build } from '../api/client'
import { resolveImportInput, ShareFetchError } from '../utils/resolveImportInput'

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

const KNOWN_BUILD_KEYS = new Set([
  'name', 'id', 'slots', 'slates', 'conditions', 'conditionValues',
  'gear', 'skills', 'characterLevel', 'hasPrism', 'traitId',
  'traitLevel', 'traitSlotLevels', 'advancedTraitSelections',
  'heroMemories', 'pactSpirits', 'notes',
])

function checkBuildCompatibility(build: Record<string, unknown>): string[] {
  const issues: string[] = []
  if (!Array.isArray(build.slots)) issues.push('Slots data is missing or unreadable.')
  else if ((build.slots as unknown[]).every(s => !s)) issues.push('Build has no tree slots selected.')
  if (Array.isArray(build.gear)) {
    const unmatched = (build.gear as Record<string, unknown>[]).filter(g => !Array.isArray(g.affixes))
    if (unmatched.length) {
      const names = unmatched.map(g => (g.name ?? g.item_id ?? 'Unknown') as string).join(', ')
      issues.push(`${unmatched.length} gear item(s) not found in current season data: ${names}`)
    }
  }
  const unknown = Object.keys(build).filter(k => !KNOWN_BUILD_KEYS.has(k))
  if (unknown.length) issues.push(`Unrecognized fields (older format): ${unknown.join(', ')}`)
  return issues
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

  const [importCode, setImportCode] = useState('')
  const [importError, setImportError] = useState<string | null>(null)
  const [importWarnings, setImportWarnings] = useState<string[]>([])
  const [importConfirmed, setImportConfirmed] = useState(false)
  const [importing, setImporting] = useState(false)

  const [dirtyPrompt, setDirtyPrompt] = useState(false)
  const [dirtySaveName, setDirtySaveName] = useState(buildName)
  const [dirtySaving, setDirtySaving] = useState(false)
  const pendingCodeRef = useRef<string | null>(null)

  const importRef = useRef<HTMLTextAreaElement>(null)

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

  const doImport = async (code: string) => {
    setImporting(true)
    setImportError(null)
    try {
      // Accepts either a raw tli1_ code or a share link; a share link is
      // resolved to a raw code here, then the existing decode path runs.
      const resolved = await resolveImportInput(code)
      const { build } = await api.decodeBuildCode(resolved)
      const warnings = checkBuildCompatibility(build)
      if (warnings.length && !importConfirmed) {
        setImportWarnings(warnings)
        setImportConfirmed(true)
        return
      }
      onImport(build as unknown as Build)
      onClose()
    } catch (e: unknown) {
      if (e instanceof ShareFetchError) {
        setImportError("Couldn't fetch the shared build (link may be invalid or the service is unavailable).")
      } else {
        const msg = e instanceof Error ? e.message : String(e)
        setImportError(msg.includes('400') ? 'Invalid or unrecognized build code.' : 'Failed to import — try again.')
      }
    } finally {
      setImporting(false)
    }
  }

  const handleImportClick = () => {
    const code = importCode.trim()
    if (!code) return
    if (isDirty) {
      pendingCodeRef.current = code
      setDirtySaveName(buildName)
      setDirtyPrompt(true)
      return
    }
    doImport(code)
  }

  const handleDirtySave = async () => {
    const name = buildId ? buildName : (dirtySaveName.trim() || 'Untitled')
    setDirtySaving(true)
    try {
      await onSaveFirst(name)
      setDirtyPrompt(false)
      if (pendingCodeRef.current) doImport(pendingCodeRef.current)
    } catch { /* save failed — leave dirty prompt open */ }
    finally { setDirtySaving(false) }
  }

  const handleDirtyDiscard = () => {
    setDirtyPrompt(false)
    if (pendingCodeRef.current) doImport(pendingCodeRef.current)
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
          <p className="share-modal-hint">Paste a build code to load it. This will replace your current build.</p>
          <textarea
            ref={importRef}
            className="share-code-area share-code-area--input"
            placeholder="Paste tli1_… code here"
            value={importCode}
            onChange={e => {
              setImportCode(e.target.value)
              setImportError(null)
              setImportWarnings([])
              setImportConfirmed(false)
            }}
            onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleImportClick() }}
          />
          {importError && <p className="share-import-error">{importError}</p>}
          {importWarnings.length > 0 && (
            <div className="share-import-warning">
              <p>⚠ This code may be from an older version:</p>
              <ul>{importWarnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
              <p>Unsupported fields will be ignored. Click "Import Anyway" to proceed.</p>
            </div>
          )}
          <div className="modal-actions">
            <button
              className="btn btn-primary"
              onClick={handleImportClick}
              disabled={importing || !importCode.trim()}
            >
              {importing ? 'Importing…' : importConfirmed ? 'Import Anyway' : 'Import'}
            </button>
            {!asScreen && <button className="btn btn-secondary" onClick={onClose}>Cancel</button>}
          </div>
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
