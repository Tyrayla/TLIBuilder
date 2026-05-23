import React, { useEffect, useRef, useState } from 'react'
import { api, Build } from '../api/client'
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
  const [importing, setImporting] = useState(false)
  const importRef = useRef<HTMLTextAreaElement>(null)

  const loadBuilds = () => {
    setLoading(true)
    api.getBuilds()
      .then(b => { setBuilds(b); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { loadBuilds() }, [])

  useEffect(() => {
    if (importOpen) setTimeout(() => importRef.current?.focus(), 50)
  }, [importOpen])

  const openImport = () => {
    setImportCode('')
    setImportError(null)
    setImportOpen(true)
  }

  const handleImport = async () => {
    const code = importCode.trim()
    if (!code) return
    setImporting(true)
    setImportError(null)
    try {
      const { build } = await api.decodeBuildCode(code)
      setImportOpen(false)
      onOpenBuild(build as unknown as Build)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setImportError(msg.includes('400') ? 'Invalid or unrecognized build code.' : 'Failed to import — try again.')
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
              onChange={e => { setImportCode(e.target.value); setImportError(null) }}
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleImport() }}
            />
            {importError && <p className="share-import-error">{importError}</p>}
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleImport} disabled={importing || !importCode.trim()}>
                {importing ? 'Importing…' : 'Import'}
              </button>
              <button className="btn btn-secondary" onClick={() => setImportOpen(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
