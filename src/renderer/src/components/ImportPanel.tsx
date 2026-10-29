import React, { useRef, useState } from 'react'
import { api, Build } from '../api/client'
import { resolveImportInput, ShareFetchError } from '../utils/resolveImportInput'
import { checkBuildCompatibility } from '../utils/buildCompat'
import { useReferenceStore } from '../store/referenceStore'
import { convertCompendiumBuild, resolveCompendiumSeason } from '../crosswalk/context'
import compendiumExportImg from '../assets/compendium-export.png'
import { copyableErrorDetails, normalizeError, type TliErrorPayload } from '../errors/tliError'
import { scanUeGameLog, type UeLogCharacterPreview } from '../importers/ueLog/parse'
import { createUeLogBuild, groupUeLogCaptures } from '../importers/ueLog/toBuild'

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
  const [mode, setMode] = useState<'builder' | 'compendium' | 'game-log'>('builder')
  const [importCode, setImportCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [structuredError, setStructuredError] = useState<TliErrorPayload | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [pendingBuild, setPendingBuild] = useState<Build | null>(null)   // decoded/converted, awaiting "Import Anyway"
  const [importing, setImporting] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const gameLogFileRef = useRef<HTMLInputElement>(null)
  const [gameLogPreview, setGameLogPreview] = useState<ReturnType<typeof groupUeLogCaptures> | null>(null)

  const refLegendary = useReferenceStore(s => s.legendaryCatalog)
  const refSkills = useReferenceStore(s => s.skills)
  const refCraftBaseTypes = useReferenceStore(s => s.craftBaseTypes)
  const refGrafts = useReferenceStore(s => s.grafts)
  const refHeroMemoryScaling = useReferenceStore(s => s.heroMemories?.base_stat_scaling)

  const reset = () => { setError(null); setStructuredError(null); setWarnings([]); setPendingBuild(null) }

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
      setStructuredError(normalizeError(
        e,
        e instanceof ShareFetchError ? 'TLI-SHARE-001' : 'TLI-BUILD-001',
        'build.import',
      ).payload)
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
        heroMemoryScaling: refHeroMemoryScaling,
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

  const inspectGameLogs = async (files: FileList | null) => {
    if (!files?.length) return
    reset(); setGameLogPreview(null); setImporting(true)
    try {
      const all: Array<{ fileNumber: number; modifiedAt: number; preview: UeLogCharacterPreview }> = []
      const problems: string[] = []
      const orderedFiles = Array.from(files).map((file, index) => ({ file, index })).sort((a, b) => a.file.lastModified - b.file.lastModified)
      for (const { file, index } of orderedFiles) {
        if (file.size > 512_000_000) {
          problems.push(`Selected file ${index + 1} is larger than the 512 MB limit.`)
          continue
        }
        const result = await scanUeGameLog(file)
        all.push(...result.characters.map(preview => ({ fileNumber: index + 1, modifiedAt: file.lastModified, preview })))
        problems.push(...result.errors.map(problem => `File ${index + 1}: ${problem}`))
      }
      setGameLogPreview(groupUeLogCaptures(all))
      setWarnings(problems)
      if (!all.length && !problems.length) setError('No GetPlayerData login dumps were found in the selected files.')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not read the selected game log.')
    } finally { setImporting(false) }
  }

  const createBuildFromLog = (preview: UeLogCharacterPreview, loginCount: number) => {
    if (!refGrafts || !refLegendary) {
      setError('Gear data is still loading. Try again in a moment.')
      return
    }
    reset()
    const result = createUeLogBuild(preview, refGrafts, refLegendary)
    if (loginCount > 1) result.warnings.splice(1, 0, `This character has ${loginCount} login captures. The draft uses the most recently modified selected log.`)
    setPendingBuild(result.build)
    setWarnings(result.warnings)
  }

  const switchMode = (m: 'builder' | 'compendium' | 'game-log') => {
    setMode(m); reset(); setImportCode(''); setGameLogPreview(null)
  }

  return (
    <div className="import-panel">
      <div className="import-source-toggle">
        <button className={`import-source-tab${mode === 'builder' ? ' active' : ''}`} onClick={() => switchMode('builder')}>TLI Builder Code</button>
        <button className={`import-source-tab${mode === 'compendium' ? ' active' : ''}`} onClick={() => switchMode('compendium')}>TLI Compendium Build</button>
        <button className={`import-source-tab${mode === 'game-log' ? ' active' : ''}`} onClick={() => switchMode('game-log')}>Game log preview</button>
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

      {mode === 'game-log' && (
        <>
          <p className="share-modal-hint">Choose UE_game.log and any backup logs. Your files stay on this device. Pick a login to create a draft build with the Vorax gear the app can identify. Other character data is listed before you import.</p>
          <input ref={gameLogFileRef} type="file" accept=".log,text/plain" multiple style={{ display: 'none' }}
            onChange={e => { void inspectGameLogs(e.target.files); e.target.value = '' }} />
          <div className="import-file-row">
            <button className="btn btn-primary" disabled={importing} onClick={() => gameLogFileRef.current?.click()}>
              {importing ? 'Reading logs…' : 'Choose UE_game.log files…'}
            </button>
          </div>
          {gameLogPreview && gameLogPreview.length === 0 && <p role="status">No login dumps were found.</p>}
          {gameLogPreview?.map(({ fileNumber, preview, loginCount }) => {
            const vorax = preview.gear.filter(item => refGrafts?.some(graft => graft.base_id === item.baseId))
            return (
              <section key={`${fileNumber}-${preview.dumpNumber}`} className="log-import-card">
                <div className="log-import-card__heading">
                  <div>
                    <h4>{preview.characterName || `Hero ${preview.heroId ?? 'unknown'}`}</h4>
                    <p>Level {preview.level ?? 'unknown'} · {loginCount} login {loginCount === 1 ? 'capture' : 'captures'} · File {fileNumber}</p>
                  </div>
                  <button className="btn btn-primary" disabled={importing} onClick={() => createBuildFromLog(preview, loginCount)}>Create draft build</button>
                </div>
                <div className="log-import-card__summary">
                  <span><strong>{preview.gear.length}</strong> equipped items detected</span>
                  <span><strong>{vorax.length}</strong> Vorax items ready to map</span>
                  {preview.truncatedSections.length > 0 && <span>Some log lists were capped</span>}
                </div>
                <details className="log-import-card__details">
                  <summary>Review detected Vorax gear</summary>
                  {vorax.length === 0 ? <p>No catalogued Vorax items were found in this login.</p> : vorax.map((item, index) => (
                    <div key={`${item.baseId}-${index}`} className="log-import-card__item">
                      <strong>{refGrafts?.find(graft => graft.base_id === item.baseId)?.name ?? `Vorax base ${item.baseId}`}</strong>
                      <span>Slot {item.equippedSlot ?? 'unknown'} · Item level {item.itemLevel ?? 'unknown'}</span>
                      <span>{[...item.prefixes, ...item.suffixes].length} affixes · Base affix {item.baseAffixIds.join(', ') || 'none'}</span>
                    </div>
                  ))}
                </details>
              </section>
            )
          })}
        </>
      )}

      {structuredError && (
        <div className="share-import-error" role="alert">
          <strong>{structuredError.title} ({structuredError.code}) — </strong>{structuredError.message}
          {structuredError.remediation && <div>{structuredError.remediation}</div>}
          <button className="btn" style={{ marginTop: 8 }} onClick={() => void navigator.clipboard?.writeText(copyableErrorDetails(structuredError))}>Copy details</button>
        </div>
      )}
      {error && !structuredError && <p className="share-import-error">{error}</p>}
      {warnings.length > 0 && (
        <div className="share-import-warning">
          <p>{pendingBuild && mode === 'compendium'
            ? '⚠ Some items couldn’t be mapped and were skipped (also saved in the build’s notes):'
            : mode === 'game-log'
              ? 'The game-log scan reported:'
            : '⚠ This build may be from an older version:'}</p>
          <ul>{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
          <p>Review these limits before you import the draft build.</p>
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
