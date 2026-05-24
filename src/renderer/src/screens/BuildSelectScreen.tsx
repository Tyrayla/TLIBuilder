import React, { useEffect, useRef, useState } from 'react'
import { api, Build } from '../api/client'
import { resolveImportInput, ShareFetchError } from '../utils/resolveImportInput'
import logoSrc from '../assets/logo.png'

interface Props {
  onNewBuild: () => void
  onOpenBuild: (build: Build) => void
  devMode?: boolean
  onDevTools?: () => void
}

function slotSummary(build: Build): string {
  const names = build.slots.filter(Boolean).map(s => s!.treeName)
  return names.length ? names.join(' · ') : 'No trees selected'
}

function totalPoints(build: Build): number {
  return build.slots.filter(Boolean).reduce((sum, s) =>
    sum + Object.values(s!.nodeStates).reduce((a, b) => a + b, 0), 0)
}

export default function BuildSelectScreen({ onNewBuild, onOpenBuild, devMode, onDevTools }: Props) {
  const [builds, setBuilds] = useState<Build[]>([])
  const [loading, setLoading] = useState(true)

  const [importOpen, setImportOpen] = useState(false)
  const [importCode, setImportCode] = useState('')
  const [importError, setImportError] = useState<string | null>(null)
  const [importWarnings, setImportWarnings] = useState<string[]>([])
  const [importConfirmed, setImportConfirmed] = useState(false)
  const [importing, setImporting] = useState(false)
  const importRef = useRef<HTMLTextAreaElement>(null)

  const [version, setVersion] = useState('')
  const [checkStatus, setCheckStatus] = useState<'idle' | 'checking' | 'up-to-date' | 'available' | 'error'>('idle')
  const [checkError, setCheckError] = useState('')

  const loadBuilds = () => {
    setLoading(true)
    api.getBuilds()
      .then(b => { setBuilds(b); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { loadBuilds() }, [])

  useEffect(() => {
    window.api?.getAppVersion?.().then(v => setVersion(v)).catch(() => {})
    window.api?.onUpdateNotAvailable?.(() => setCheckStatus('up-to-date'))
    window.api?.onUpdateAvailable?.(() => setCheckStatus('available'))
    window.api?.onUpdateCheckError?.((msg) => { setCheckStatus('error'); setCheckError(msg) })
  }, [])

  const handleCheckForUpdate = async () => {
    setCheckStatus('checking')
    const timeout = setTimeout(() => setCheckStatus('idle'), 10000)
    await window.api?.checkForUpdate?.().catch(() => {})
    clearTimeout(timeout)
  }

  useEffect(() => {
    if (importOpen) setTimeout(() => importRef.current?.focus(), 50)
  }, [importOpen])

  const KNOWN_BUILD_KEYS = new Set([
    'name', 'id', 'slots', 'slates', 'conditions', 'conditionValues',
    'gear', 'skills', 'characterLevel', 'hasPrism', 'traitId',
    'traitLevel', 'traitSlotLevels', 'advancedTraitSelections',
    'heroMemories', 'pactSpirits',
  ])

  function checkBuildCompatibility(build: Record<string, unknown>): string[] {
    const issues: string[] = []
    if (!Array.isArray(build.slots)) issues.push('Slots data is missing or unreadable.')
    else if ((build.slots as unknown[]).every(s => !s)) issues.push('Build has no tree slots selected.')
    if (Array.isArray(build.gear)) {
      const unmatched = (build.gear as Record<string, unknown>[]).filter(g => !Array.isArray(g.affixes))
      if (unmatched.length) {
        const names = unmatched.map(g => g.name ?? g.item_id ?? 'Unknown').join(', ')
        issues.push(`${unmatched.length} gear item(s) not found in current season data and will contribute no stats: ${names}`)
      }
    }
    const unknown = Object.keys(build).filter(k => !KNOWN_BUILD_KEYS.has(k))
    if (unknown.length) issues.push(`Unrecognized fields (older format): ${unknown.join(', ')}`)
    return issues
  }

  const openImport = () => {
    setImportCode('')
    setImportError(null)
    setImportWarnings([])
    setImportConfirmed(false)
    setImportOpen(true)
  }

  const handleImport = async () => {
    const code = importCode.trim()
    if (!code) return
    setImporting(true)
    setImportError(null)
    try {
      // Accepts either a raw tli1_ code or a share link.
      const resolved = await resolveImportInput(code)
      const { build } = await api.decodeBuildCode(resolved)
      const warnings = checkBuildCompatibility(build)
      if (warnings.length && !importConfirmed) {
        setImportWarnings(warnings)
        setImportConfirmed(true)
        return
      }
      setImportOpen(false)
      setImportConfirmed(false)
      onOpenBuild(build as unknown as Build)
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

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    await api.deleteBuild(id)
    loadBuilds()
  }

  return (
    <div className="screen build-select">
      <div className="build-select-top">
        <div className="build-select-spacer" />
        <img src={logoSrc} className="build-select-logo" alt="TLI Builder" />
        <div className="build-select-actions">
          {devMode && (
            <button
              className="btn btn-sm"
              onClick={onDevTools}
              style={{ color: '#ff9800', borderColor: '#5a3a00', background: '#1a0e00' }}
              title="Developer Tools"
            >
              Dev Tools
            </button>
          )}
          <button className="btn btn-secondary btn-sm" onClick={openImport}>Import Code</button>
          <button className="btn btn-primary" onClick={onNewBuild}>+ New Build</button>
        </div>
      </div>

      {loading ? (
        <p style={{ color: '#888', marginTop: 8 }}>Loading…</p>
      ) : builds.length === 0 ? (
        <div className="empty-state">
          <p>No saved builds yet.</p>
          <p>Click <strong style={{ color: '#e0e0e0' }}>+ New Build</strong> to get started.</p>
        </div>
      ) : (
        <div className="build-list">
          {builds.map(build => (
            <div key={build.id} className="build-card" onClick={() => onOpenBuild(build)}>
              <div className="build-card-info">
                <span className="build-name">{build.name}</span>
                <span className="build-tree">{slotSummary(build)}</span>
                <span className="build-pts">{totalPoints(build)} pts</span>
              </div>
              <div className="build-card-actions">
                <button
                  className="btn btn-danger btn-sm"
                  onClick={e => build.id && handleDelete(build.id, e)}
                >Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="build-select-footer">
        {version && <span className="build-select-version">v{version}</span>}
        <div className="build-select-footer-actions">
          <button
            className="btn btn-sm btn-secondary"
            onClick={handleCheckForUpdate}
            disabled={checkStatus === 'checking'}
            title={checkStatus === 'error' ? checkError : undefined}
          >
            {checkStatus === 'checking' ? 'Checking…'
              : checkStatus === 'up-to-date' ? '✓ Up to date'
              : checkStatus === 'available' ? 'Update available'
              : checkStatus === 'error' ? `Check failed`
              : 'Check for Update'}
          </button>
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => window.api?.openExternal?.('https://github.com/Tyrayla/TLIBuilder')}
          >
            About
          </button>
        </div>
      </div>

      {importOpen && (
        <div className="modal-backdrop" onClick={() => setImportOpen(false)}>
          <div className="modal-card share-modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">Import Build Code</h3>
            <p className="share-modal-hint">Paste a build code shared by someone else to load their build.</p>
            <textarea
              ref={importRef}
              className="share-code-area share-code-area--input"
              placeholder="Paste tli1_… code here"
              value={importCode}
              onChange={e => { setImportCode(e.target.value); setImportError(null); setImportWarnings([]); setImportConfirmed(false) }}
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleImport() }}
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
              <button className="btn btn-primary" onClick={handleImport} disabled={importing || !importCode.trim()}>
                {importing ? 'Importing…' : importConfirmed ? 'Import Anyway' : 'Import'}
              </button>
              <button className="btn btn-secondary" onClick={() => setImportOpen(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
