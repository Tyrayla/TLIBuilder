import React, { useRef, useState } from 'react'
import { api, Build } from '../api/client'
import { resolveImportInput, ShareFetchError } from '../utils/resolveImportInput'
import { checkBuildCompatibility } from '../utils/buildCompat'
import { useReferenceStore } from '../store/referenceStore'
import { convertCompendiumBuild, resolveCompendiumSeason } from '../crosswalk/context'
import compendiumExportImg from '../assets/compendium-export.png'

/**
 * Shared import UI used by BOTH the main-menu import modal (BuildSelectScreen) and the in-build Import/Export
 * overlay, so they look and behave identically. Two sub-tabs: "TLI Builder Code" (a tli1_ code / share link) and
 * "TLI Compendium Build" (a .json export, converted via the crosswalk). It produces a ready Build and hands it to
 * `onImport` — the host owns what happens next (unsaved-changes prompt, opening the build, closing the modal).
 */
interface Props {
  onImport: (build: Build) => void
  autoFocus?: boolean
}

export default function ImportPanel({ onImport, autoFocus }: Props) {
  const [mode, setMode] = useState<'builder' | 'compendium'>('builder')
  const [importCode, setImportCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [pendingBuild, setPendingBuild] = useState<Build | null>(null)   // decoded/converted, awaiting "Import Anyway"
  const [importing, setImporting] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const refLegendary = useReferenceStore(s => s.legendaryCatalog)
  const refSkills = useReferenceStore(s => s.skills)
  const refCraftBaseTypes = useReferenceStore(s => s.craftBaseTypes)
  const refGrafts = useReferenceStore(s => s.grafts)

  const reset = () => { setError(null); setWarnings([]); setPendingBuild(null) }

  // A build is ready: if the source produced warnings, show them and wait for an explicit "Import Anyway";
  // otherwise hand it straight to the host.
  const ready = (build: Build, w: string[]) => {
    if (w.length) { setPendingBuild(build); setWarnings(w); return }
    onImport(build)
  }

  const importCodeNow = async () => {
    const code = importCode.trim()
    if (!code) return
    setImporting(true); reset()
    try {
      const resolved = await resolveImportInput(code)          // tli1_ code OR share link → raw code
      const { build } = await api.decodeBuildCode(resolved)
      ready({ ...(build as unknown as Build), name: 'New Build' }, checkBuildCompatibility(build))
    } catch (e: unknown) {
      if (e instanceof ShareFetchError) {
        setError("Couldn't fetch the shared build (link may be invalid or the service is unavailable).")
      } else {
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg.includes('400') ? "This doesn't look like a TLI Builder code. Paste a tli1_… code or share link — in-game codes from Torchlight: Infinite aren't supported." : 'Failed to import — try again.')
      }
    } finally { setImporting(false) }
  }

  const convertCompendium = async (src: any) => {
    setImporting(true); reset()
    try {
      if (!refLegendary || !refSkills || !refCraftBaseTypes || !refGrafts) {
        setError('Build data is still loading — please try again in a moment.'); return
      }
      const payload = await api.getCrosswalkTables()
      if (!payload.tables || !payload.tables['skills']) {
        setError(`No TLI Compendium crosswalk data is available for the current season${payload.season ? ` (${payload.season})` : ''}.`); return
      }
      const resolved = resolveCompendiumSeason(src.patch, payload.tables, payload.season ?? '')
      if (payload.season && resolved !== payload.season) {
        setError(`This build is patch ${src.patch}; the app only has Compendium data for ${payload.season}. Switch to that season and try again.`); return
      }
      const { build, warnings: w } = convertCompendiumBuild(src, payload, {
        legendaryCatalog: refLegendary, skills: refSkills, craftBaseTypes: refCraftBaseTypes, grafts: refGrafts,
      })
      ready({ ...(build as unknown as Build), name: (build as { name?: string }).name ?? 'Imported build' }, w)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to convert the Compendium build.')
    } finally { setImporting(false) }
  }

  const onFile = async (file: File | null | undefined) => {
    if (!file) return
    reset()
    if (file.size > 5_000_000) { setError('That file is too large to be a Compendium build export.'); return }
    let src: unknown
    try { src = JSON.parse(await file.text()) }
    catch { setError('That file isn’t valid JSON.'); return }
    const o = src as Record<string, unknown>
    if (!o || typeof o !== 'object' || Array.isArray(o) || !(o.loadouts || o.hero || o.name)) {
      setError('That doesn’t look like a TLI Compendium build export.'); return
    }
    convertCompendium(o)
  }

  const switchMode = (m: 'builder' | 'compendium') => { setMode(m); reset(); setImportCode('') }

  return (
    <div className="import-panel">
      <div className="import-source-toggle">
        <button className={`import-source-tab${mode === 'builder' ? ' active' : ''}`} onClick={() => switchMode('builder')}>TLI Builder Code</button>
        <button className={`import-source-tab${mode === 'compendium' ? ' active' : ''}`} onClick={() => switchMode('compendium')}>TLI Compendium Build</button>
      </div>

      {mode === 'builder' && (
        <>
          <p className="share-modal-hint">Paste a TLI Builder code (<code>tli1_…</code>) or an <b>api.tlibuilder.com</b> share link to load a build. This replaces your current build. In-game build codes from Torchlight: Infinite aren’t supported.</p>
          <textarea
            autoFocus={autoFocus}
            className="share-code-area share-code-area--input"
            placeholder="Paste a tli1_… code or share link…"
            value={importCode}
            onChange={e => { setImportCode(e.target.value); reset() }}
            onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) importCodeNow() }}
          />
        </>
      )}

      {mode === 'compendium' && (
        <>
          <p className="share-modal-hint">Open your build on <b>TLI Compendium</b>’s build planner, use the <b>Export → JSON</b> button in the top-right, then select that file here. It’s converted into a TLI Builder build; anything that can’t be mapped is skipped and noted in the build’s notes.</p>
          <img className="import-compendium-img" src={compendiumExportImg} alt="TLI Compendium: the Export button is in the top-right of the build planner" />
          <input ref={fileRef} type="file" accept=".json,application/json" style={{ display: 'none' }}
            onChange={e => { onFile(e.target.files?.[0]); e.target.value = '' }} />
          <div className="import-file-row">
            <button className="btn btn-primary" disabled={importing} onClick={() => fileRef.current?.click()}>
              {importing ? 'Converting…' : 'Choose Compendium file…'}
            </button>
          </div>
        </>
      )}

      {error && <p className="share-import-error">{error}</p>}
      {warnings.length > 0 && (
        <div className="share-import-warning">
          <p>{pendingBuild && mode === 'compendium'
            ? '⚠ Some items couldn’t be mapped and were skipped (also saved in the build’s notes):'
            : '⚠ This build may be from an older version:'}</p>
          <ul>{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
          <p>Click <b>Import Anyway</b> to proceed.</p>
        </div>
      )}

      <div className="modal-actions import-panel-actions">
        {pendingBuild ? (
          <button className="btn btn-primary" onClick={() => onImport(pendingBuild)} disabled={importing}>
            {importing ? 'Importing…' : 'Import Anyway'}
          </button>
        ) : mode === 'builder' ? (
          <button className="btn btn-primary" onClick={importCodeNow} disabled={importing || !importCode.trim()}>
            {importing ? 'Importing…' : 'Import'}
          </button>
        ) : null}
      </div>
    </div>
  )
}
