import React, { useEffect, useRef, useState } from 'react'
import { api, Build, IS_WEB } from '../api/client'
import { resolveImportInput, ShareFetchError } from '../utils/resolveImportInput'
import { checkBuildCompatibility } from '../utils/buildCompat'
import SettingsOverlay from '../components/SettingsOverlay'
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

  const [aboutOpen, setAboutOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  // Open an external link on either platform: desktop routes through the IPC openExternal (system browser),
  // web falls back to window.open (where window.api doesn't exist).
  const openExternal = (url: string) => {
    if (window.api?.openExternal) window.api.openExternal(url)
    else window.open(url, '_blank', 'noopener,noreferrer')
  }
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
    // Desktop reads the version via IPC; the web build has no IPC, so it uses the version baked in at build
    // time (vite `define` __APP_VERSION__). `typeof` guard keeps the desktop bundle safe where it's undefined.
    if (typeof __APP_VERSION__ !== 'undefined' && __APP_VERSION__) setVersion(__APP_VERSION__)
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
      onOpenBuild({ ...(build as unknown as Build), name: 'New Build' })
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

  const handleDelete = async (id: string, name: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm(`Delete "${name || 'this build'}"? This can't be undone.`)) return
    await api.deleteBuild(id)
    loadBuilds()
  }

  return (
    <div className="screen build-select">
      <div className="build-select-top">
        <div className="build-select-spacer">
          <button
            className="btn btn-sm"
            onClick={() => openExternal('https://discord.gg/7hEySM4WYx')}
            style={{ color: '#c7d0ff', borderColor: '#3a3f8a', background: '#1a1c3a' }}
          >
            💬 Join the Discord to share feedback or bugs you find!
          </button>
        </div>
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
        <div className="build-list dark-scroll">
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
                  onClick={e => build.id && handleDelete(build.id, build.name, e)}
                >Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="build-select-footer">
        {/* Row 1: version + Check for Update, stacked above Settings/About. */}
        <div className="build-select-footer-actions">
          {version && <span className="build-select-version">v{version}</span>}
          {/* Auto-update is desktop-only; the web app updates by redeploy + refresh. */}
          {!IS_WEB && <button
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
          </button>}
        </div>
        {/* Row 2: Settings + About. */}
        <div className="build-select-footer-actions">
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => setSettingsOpen(true)}
          >
            ⚙ Settings
          </button>
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => setAboutOpen(true)}
          >
            About
          </button>
        </div>
      </div>

      {settingsOpen && <SettingsOverlay onClose={() => setSettingsOpen(false)} />}

      {aboutOpen && (
        <div className="modal-backdrop" onClick={() => setAboutOpen(false)}>
          <div className="modal-card about-modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">About TLI Builder{version ? ` · v${version}` : ''}</h3>
            <div className="about-modal-body">
              <h4 className="about-section-title">Guides &amp; Info</h4>
              <p>
                Visit the TLI Builder website for guides, FAQs, and more about the project:{' '}
                <button className="about-link-inline" onClick={() => openExternal('https://about.tlibuilder.com')}>about.tlibuilder.com</button>
              </p>

              <h4 className="about-section-title">Disclaimer</h4>
              <p>
                <strong>TLI Builder is an unofficial, non-commercial fan-made project.</strong> It is not
                affiliated with, endorsed by, sponsored by, or in any way officially connected to XD Inc. /
                XD Games or any of their subsidiaries or affiliates.
              </p>
              <p>
                <em>Torchlight: Infinite</em> and all related names, logos, characters, images, and assets
                are trademarks and copyrights of their respective owners. They are used here solely for
                identification and reference purposes.
              </p>

              <h4 className="about-section-title">Data &amp; Sources</h4>
              <p>
                Game data and icons used throughout TLI Builder — skills, gear, talent trees, pact spirits,
                hero traits, and more — are sourced from <strong>TLIDB</strong>, the community Torchlight:
                Infinite database, used with permission. Full credit and thanks go to the TLIDB team for
                maintaining this resource. No ownership of any game assets is claimed.
              </p>

              <h4 className="about-section-title">Asset Removal &amp; Contact</h4>
              <p>
                If you are a rights holder (or an authorized representative) and would like any asset removed,
                please reach out and it will be removed promptly:
              </p>
              <p className="about-contact">
                Email: <span>Tyrayla@gmail.com</span><br />
                Discord: <span>tyrayla</span>
              </p>
              <p className="about-links">
                <button className="about-link-btn" onClick={() => openExternal('https://about.tlibuilder.com')}>Website</button>
                <button className="about-link-btn" onClick={() => openExternal('https://tlidb.com')}>TLIDB</button>
                <button className="about-link-btn" onClick={() => openExternal('https://github.com/Tyrayla/TLIBuilder')}>GitHub</button>
              </p>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setAboutOpen(false)}>Close</button>
            </div>
          </div>
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
