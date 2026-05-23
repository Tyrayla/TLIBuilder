import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, SeasonSummary, SeasonDiff, RebuildFilterResult, UnresolvedStat, FilterOverride, ImportCrawlerTreeResult } from '../api/client'

type Tab = 'diff' | 'seasons' | 'tools'

interface Props {
  onBack: () => void
  deprecatedTools: boolean
  onToggleDeprecatedTools: () => void
}

// ── Diff tab ───────────────────────────────────────────────────────────────

const DIFF_COLOR = { added: '#4caf50', removed: '#ef5350', changed: '#ff9800', unchanged: '#555' }

function DiffTab() {
  const [seasons, setSeasons] = useState<SeasonSummary[]>([])
  const [seasonA, setSeasonA] = useState('')
  const [seasonB, setSeasonB] = useState('')
  const [diff, setDiff] = useState<SeasonDiff | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [openTrees, setOpenTrees] = useState<Record<string, boolean>>({})
  const [showUnchanged, setShowUnchanged] = useState(false)

  useEffect(() => { api.listSeasons().then(setSeasons).catch(() => {}) }, [])

  const runDiff = async () => {
    if (!seasonA || !seasonB) return
    setLoading(true); setErr(''); setDiff(null); setOpenTrees({})
    try { setDiff(await api.diffSeasons(seasonA, seasonB)) }
    catch (ex) { setErr(String(ex)) }
    finally { setLoading(false) }
  }

  const toggle = (name: string) => setOpenTrees(s => ({ ...s, [name]: !s[name] }))

  return (
    <div>
      <p style={{ color: '#888', fontSize: 13, marginBottom: 14 }}>
        Compare two imported seasons to see what nodes, effects, and connections changed.
      </p>

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 16, flexWrap: 'wrap' }}>
        {(['A (old)', 'B (new)'] as const).map((label, i) => {
          const val = i === 0 ? seasonA : seasonB
          const set = i === 0 ? setSeasonA : setSeasonB
          return (
            <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 220 }}>
              <span style={{ fontSize: 11, color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>Season {label}</span>
              <select
                value={val}
                onChange={e => { set(e.target.value); setDiff(null) }}
                style={{ background: '#1a1a3a', color: '#ddd', border: '1px solid #3a3a5a', borderRadius: 4, padding: '6px 10px', fontSize: 13 }}
              >
                <option value="">— Select —</option>
                {seasons.map(s => <option key={s.name} value={s.name}>{s.name}</option>)}
              </select>
            </div>
          )
        })}
        <button className="btn btn-primary" onClick={runDiff} disabled={!seasonA || !seasonB || loading || seasonA === seasonB}>
          {loading ? 'Comparing…' : 'Run Diff'}
        </button>
      </div>

      {err && <div style={{ color: '#ff6b6b', fontSize: 13, marginBottom: 10 }}>{err}</div>}

      {diff && (() => {
        const summary = diff.summary
        const summaryItems = [
          { label: 'Trees added',       val: summary.trees_added,       color: '#4caf50' },
          { label: 'Trees removed',     val: summary.trees_removed,     color: '#ef5350' },
          { label: 'Nodes added',       val: summary.nodes_added,       color: '#4caf50' },
          { label: 'Nodes removed',     val: summary.nodes_removed,     color: '#ef5350' },
          { label: 'Nodes changed',     val: summary.nodes_changed,     color: '#ff9800' },
          { label: 'Connections added', val: summary.connections_added, color: '#4caf50' },
          { label: 'Connections removed', val: summary.connections_removed, color: '#ef5350' },
        ]
        return (
          <div style={{ marginTop: 4 }}>
            <div style={{ display: 'flex', gap: 14, marginBottom: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              {summaryItems.map(({ label, val, color }) => (
                <div key={label} style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: val > 0 ? color : '#333' }}>{val}</div>
                  <div style={{ fontSize: 10, color: '#555' }}>{label}</div>
                </div>
              ))}
              <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#888', cursor: 'pointer' }}>
                <input type="checkbox" checked={showUnchanged} onChange={e => setShowUnchanged(e.target.checked)} />
                Show unchanged
              </label>
            </div>

            {Object.entries(diff.trees)
              .filter(([, t]) => showUnchanged || t.status !== 'unchanged')
              .map(([treeName, tree]) => {
                const open = openTrees[treeName] ?? tree.status !== 'unchanged'
                const changeCount = tree.nodes_added.length + tree.nodes_removed.length + tree.nodes_changed.length +
                  tree.connections_added.length + tree.connections_removed.length
                return (
                  <div key={treeName} style={{ marginBottom: 6, border: '1px solid #2a2a4a', borderRadius: 6, overflow: 'hidden' }}>
                    <button
                      onClick={() => toggle(treeName)}
                      style={{ width: '100%', textAlign: 'left', background: '#1a1a3a', border: 'none', padding: '8px 12px', cursor: 'pointer', display: 'flex', gap: 10, alignItems: 'center' }}
                    >
                      <span style={{ fontSize: 11, fontWeight: 700, minWidth: 64, color: DIFF_COLOR[tree.status] }}>{tree.status.toUpperCase()}</span>
                      <span style={{ fontSize: 13, color: '#ccc' }}>{treeName}</span>
                      <span style={{ marginLeft: 'auto', color: '#555', fontSize: 12 }}>{changeCount} changes · {open ? '▲' : '▼'}</span>
                    </button>
                    {open && (
                      <div style={{ padding: '8px 12px', background: '#0e0e28' }}>
                        {tree.nodes_added.map(n => (
                          <div key={n.id} style={{ marginBottom: 4, padding: '5px 10px', background: '#0a1a0a', borderRadius: 4, borderLeft: '3px solid #4caf50' }}>
                            <div style={{ fontSize: 11, color: '#4caf50', fontWeight: 700 }}>ADDED — {n.id}</div>
                            <div style={{ fontSize: 11, color: '#888' }}>{n.node_type} · {n.max_points} pts</div>
                            {n.effects.map((e, i) => <div key={i} style={{ fontSize: 12, color: '#a5d6a7' }}>{e}</div>)}
                          </div>
                        ))}
                        {tree.nodes_removed.map(n => (
                          <div key={n.id} style={{ marginBottom: 4, padding: '5px 10px', background: '#1a0a0a', borderRadius: 4, borderLeft: '3px solid #ef5350' }}>
                            <div style={{ fontSize: 11, color: '#ef5350', fontWeight: 700 }}>REMOVED — {n.id}</div>
                            <div style={{ fontSize: 11, color: '#888' }}>{n.node_type} · {n.max_points} pts</div>
                            {n.effects.map((e, i) => <div key={i} style={{ fontSize: 12, color: '#ef9a9a' }}>{e}</div>)}
                          </div>
                        ))}
                        {tree.nodes_changed.map(n => (
                          <div key={n.id} style={{ marginBottom: 4, padding: '5px 10px', background: '#1a1200', borderRadius: 4, borderLeft: '3px solid #ff9800' }}>
                            <div style={{ fontSize: 11, color: '#ff9800', fontWeight: 700 }}>CHANGED — {n.id}</div>
                            <div style={{ display: 'flex', gap: 16, marginTop: 4 }}>
                              <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 10, color: '#666', marginBottom: 2 }}>BEFORE</div>
                                {n.old && <div style={{ fontSize: 11, color: '#888' }}>{n.old.node_type} · {n.old.max_points} pts</div>}
                                {n.old?.effects.map((e, i) => <div key={i} style={{ fontSize: 12, color: '#ef9a9a' }}>{e}</div>)}
                              </div>
                              <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 10, color: '#666', marginBottom: 2 }}>AFTER</div>
                                {n.new && <div style={{ fontSize: 11, color: '#888' }}>{n.new.node_type} · {n.new.max_points} pts</div>}
                                {n.new?.effects.map((e, i) => <div key={i} style={{ fontSize: 12, color: '#a5d6a7' }}>{e}</div>)}
                              </div>
                            </div>
                          </div>
                        ))}
                        {tree.connections_added.map((c, i) => (
                          <div key={i} style={{ marginBottom: 4, padding: '4px 10px', background: '#0a1a0a', borderRadius: 4, borderLeft: '3px solid #4caf50' }}>
                            <span style={{ fontSize: 11, color: '#4caf50', fontWeight: 700 }}>CONNECTION ADDED </span>
                            <span style={{ fontSize: 11, color: '#888' }}>{c.from} → {c.to}</span>
                          </div>
                        ))}
                        {tree.connections_removed.map((c, i) => (
                          <div key={i} style={{ marginBottom: 4, padding: '4px 10px', background: '#1a0a0a', borderRadius: 4, borderLeft: '3px solid #ef5350' }}>
                            <span style={{ fontSize: 11, color: '#ef5350', fontWeight: 700 }}>CONNECTION REMOVED </span>
                            <span style={{ fontSize: 11, color: '#888' }}>{c.from} → {c.to}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
          </div>
        )
      })()}
    </div>
  )
}

// ── Seasons tab ────────────────────────────────────────────────────────────

interface ImportState {
  importing: boolean
  result: string | null
  err: string
}

const emptyImport = (): ImportState => ({ importing: false, result: null, err: '' })

interface CategoryCardProps {
  label: string
  description: string
  badge?: string
  enabled: boolean
  children?: React.ReactNode
}

function CategoryCard({ label, description, badge, enabled, children }: CategoryCardProps) {
  return (
    <div style={{
      border: `1px solid ${enabled ? '#2a2a4a' : '#1a1a2a'}`,
      borderRadius: 7, marginBottom: 10, overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '9px 14px', background: enabled ? '#14142a' : '#0f0f1e',
      }}>
        <div style={{ flex: 1 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: enabled ? '#ccc' : '#3a3a5a' }}>{label}</span>
          {badge && (
            <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 700, color: '#4a8', background: '#0a2a1a', padding: '1px 6px', borderRadius: 3 }}>
              {badge}
            </span>
          )}
          <div style={{ fontSize: 11, color: enabled ? '#555' : '#2a2a3a', marginTop: 2 }}>{description}</div>
        </div>
        {!enabled && (
          <span style={{ fontSize: 10, color: '#2a2a4a', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>Coming Soon</span>
        )}
      </div>
      {enabled && children && (
        <div style={{ padding: '12px 14px', background: '#0e0e24', borderTop: '1px solid #1a1a3a' }}>
          {children}
        </div>
      )}
    </div>
  )
}

function SeasonsTab() {
  const talentFilesRef = useRef<HTMLInputElement>(null)
  const legendaryFilesRef = useRef<HTMLInputElement>(null)
  const skillsFilesRef = useRef<HTMLInputElement>(null)
  const heroTraitFilesRef = useRef<HTMLInputElement>(null)
  const pactSpiritFilesRef = useRef<HTMLInputElement>(null)
  const craftBaseTypeFilesRef = useRef<HTMLInputElement>(null)
  const graftFilesRef = useRef<HTMLInputElement>(null)
  const destinyFileRef = useRef<HTMLInputElement>(null)
  const etherealPrismFileRef = useRef<HTMLInputElement>(null)
  const heroMemoriesFileRef = useRef<HTMLInputElement>(null)
  const memoryRevivalFileRef = useRef<HTMLInputElement>(null)
  const towerSequenceFileRef = useRef<HTMLInputElement>(null)
  const [seasons, setSeasons] = useState<SeasonSummary[]>([])
  const [seasonName, setSeasonName] = useState('')
  const [settingActive, setSettingActive] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [talentImport, setTalentImport] = useState<ImportState>(emptyImport())
  const [legendaryImport, setLegendaryImport] = useState<ImportState>(emptyImport())
  const [skillsImport, setSkillsImport] = useState<ImportState>(emptyImport())
  const [heroTraitImport, setHeroTraitImport] = useState<ImportState>(emptyImport())
  const [pactSpiritImport, setPactSpiritImport] = useState<ImportState>(emptyImport())
  const [craftBaseTypeImport, setCraftBaseTypeImport] = useState<ImportState>(emptyImport())
  const [graftImport, setGraftImport] = useState<ImportState>(emptyImport())
  const [destinyImport, setDestinyImport] = useState<ImportState>(emptyImport())
  const [etherealPrismImport, setEtherealPrismImport] = useState<ImportState>(emptyImport())
  const [heroMemoriesImport, setHeroMemoriesImport] = useState<ImportState>(emptyImport())
  const [memoryRevivalImport, setMemoryRevivalImport] = useState<ImportState>(emptyImport())
  const [towerSequenceImport, setTowerSequenceImport] = useState<ImportState>(emptyImport())
  const [talentFileNames, setTalentFileNames] = useState<string[]>([])
  const [legendaryFileNames, setLegendaryFileNames] = useState<string[]>([])
  const [skillsFileNames, setSkillsFileNames] = useState<string[]>([])
  const [heroTraitFileNames, setHeroTraitFileNames] = useState<string[]>([])
  const [pactSpiritFileNames, setPactSpiritFileNames] = useState<string[]>([])
  const [craftBaseTypeFileNames, setCraftBaseTypeFileNames] = useState<string[]>([])
  const [graftFileNames, setGraftFileNames] = useState<string[]>([])
  const [singletonFileName, setSingletonFileName] = useState<Record<string, string>>({})

  const loadSeasons = useCallback(() => {
    api.listSeasons().then(setSeasons).catch(() => {})
  }, [])

  useEffect(() => { loadSeasons() }, [loadSeasons])

  const handleImportTalents = async () => {
    const files = talentFilesRef.current?.files
    if (!seasonName.trim() || !files || files.length === 0) return
    setTalentImport({ importing: true, result: null, err: '' })
    try {
      const lines: string[] = []
      for (const file of Array.from(files)) {
        const data = JSON.parse(await file.text()) as Record<string, unknown>
        const treeName = (data.name as string | undefined)?.trim()
        if (!treeName) {
          lines.push(`${file.name}: missing "name" field`)
          continue
        }
        const res: ImportCrawlerTreeResult = await api.importCrawlerTree(seasonName.trim(), treeName, data)
        if (res.count != null) {
          lines.push(`${treeName}: ${res.count} talent${res.count !== 1 ? 's' : ''}`)
        } else {
          lines.push(`${treeName}: ${res.node_count ?? 0} nodes, ${res.connection_count ?? 0} connections`)
        }
      }
      setTalentImport({ importing: false, result: lines.join(' · ') || 'Nothing imported', err: '' })
      loadSeasons()
    } catch (ex) {
      setTalentImport({ importing: false, result: null, err: String(ex) })
    } finally {
      if (talentFilesRef.current) talentFilesRef.current.value = ''
      setTalentFileNames([])
    }
  }

  const handleImportLegendaryGear = async () => {
    const files = legendaryFilesRef.current?.files
    if (!seasonName.trim() || !files || files.length === 0) return
    setLegendaryImport({ importing: true, result: null, err: '' })
    try {
      const items: object[] = []
      for (const file of Array.from(files)) {
        const data = JSON.parse(await file.text())
        if (!data?.name) throw new Error(`${file.name}: missing "name" field`)
        items.push(data)
      }
      const res = await api.importCrawlerLegendaryGear(seasonName.trim(), items)
      setLegendaryImport({ importing: false, result: `${res.count} items imported`, err: '' })
      loadSeasons()
    } catch (ex) {
      setLegendaryImport({ importing: false, result: null, err: String(ex) })
    } finally {
      if (legendaryFilesRef.current) legendaryFilesRef.current.value = ''
      setLegendaryFileNames([])
    }
  }

  const handleImportSkills = async () => {
    const files = skillsFilesRef.current?.files
    if (!seasonName.trim() || !files || files.length === 0) return
    setSkillsImport({ importing: true, result: null, err: '' })
    try {
      const items: object[] = []
      for (const file of Array.from(files)) {
        const data = JSON.parse(await file.text())
        if (!data?.name) throw new Error(`${file.name}: missing "name" field`)
        items.push(data)
      }
      const res = await api.importCrawlerSkills(seasonName.trim(), items)
      setSkillsImport({ importing: false, result: `${res.added} skill(s) imported — ${res.total} total in season`, err: '' })
      loadSeasons()
    } catch (ex) {
      setSkillsImport({ importing: false, result: null, err: String(ex) })
    } finally {
      if (skillsFilesRef.current) skillsFilesRef.current.value = ''
      setSkillsFileNames([])
    }
  }

  const handleClearSkills = async () => {
    try {
      await api.clearSkills()
      setSkillsImport(emptyImport())
      loadSeasons()
    } catch { /* ignore */ }
  }

  const handleImportHeroTraits = async () => {
    const files = heroTraitFilesRef.current?.files
    if (!seasonName.trim() || !files || files.length === 0) return
    setHeroTraitImport({ importing: true, result: null, err: '' })
    try {
      const items: object[] = []
      for (const file of Array.from(files)) {
        const data = JSON.parse(await file.text())
        if (!data?.name) throw new Error(`${file.name}: missing "name" field`)
        items.push(data)
      }
      const res = await api.importCrawlerHeroTraits(seasonName.trim(), items)
      setHeroTraitImport({ importing: false, result: `${res.added} trait(s) imported — ${res.total} total across ${res.heroes} hero(es)`, err: '' })
      loadSeasons()
    } catch (ex) {
      setHeroTraitImport({ importing: false, result: null, err: String(ex) })
    } finally {
      if (heroTraitFilesRef.current) heroTraitFilesRef.current.value = ''
      setHeroTraitFileNames([])
    }
  }

  const handleClearHeroTraits = async () => {
    try {
      await api.clearHeroTraits()
      setHeroTraitImport(emptyImport())
      loadSeasons()
    } catch { /* ignore */ }
  }

  const handleImportPactSpirits = async () => {
    const files = pactSpiritFilesRef.current?.files
    if (!seasonName.trim() || !files || files.length === 0) return
    setPactSpiritImport({ importing: true, result: null, err: '' })
    try {
      const items: object[] = []
      for (const file of Array.from(files)) {
        const data = JSON.parse(await file.text())
        if (!data?.name) throw new Error(`${file.name}: missing "name" field`)
        items.push(data)
      }
      const res = await api.importCrawlerPactSpirits(seasonName.trim(), items)
      setPactSpiritImport({ importing: false, result: `${res.count} pact spirit(s) imported`, err: '' })
      loadSeasons()
    } catch (ex) {
      setPactSpiritImport({ importing: false, result: null, err: String(ex) })
    } finally {
      if (pactSpiritFilesRef.current) pactSpiritFilesRef.current.value = ''
      setPactSpiritFileNames([])
    }
  }

  const handleImportCraftBaseTypes = async () => {
    const files = craftBaseTypeFilesRef.current?.files
    if (!seasonName.trim() || !files || files.length === 0) return
    setCraftBaseTypeImport({ importing: true, result: null, err: '' })
    try {
      const items: object[] = []
      for (const file of Array.from(files)) {
        const data = JSON.parse(await file.text())
        if (!data?.name) throw new Error(`${file.name}: missing "name" field`)
        items.push(data)
      }
      const res = await api.importCrawlerCraftBaseTypes(seasonName.trim(), items)
      setCraftBaseTypeImport({ importing: false, result: `${res.count} base type(s) imported`, err: '' })
      loadSeasons()
    } catch (ex) {
      setCraftBaseTypeImport({ importing: false, result: null, err: String(ex) })
    } finally {
      if (craftBaseTypeFilesRef.current) craftBaseTypeFilesRef.current.value = ''
      setCraftBaseTypeFileNames([])
    }
  }

  const handleImportGrafts = async () => {
    const files = graftFilesRef.current?.files
    if (!seasonName.trim() || !files || files.length === 0) return
    setGraftImport({ importing: true, result: null, err: '' })
    try {
      const items: object[] = []
      for (const file of Array.from(files)) {
        const data = JSON.parse(await file.text())
        if (!data?.name) throw new Error(`${file.name}: missing "name" field`)
        items.push(data)
      }
      const res = await api.importCrawlerGrafts(seasonName.trim(), items)
      setGraftImport({ importing: false, result: `${res.count} graft(s) imported`, err: '' })
      loadSeasons()
    } catch (ex) {
      setGraftImport({ importing: false, result: null, err: String(ex) })
    } finally {
      if (graftFilesRef.current) graftFilesRef.current.value = ''
      setGraftFileNames([])
    }
  }

  const handleImportSingleton = async (
    key: string,
    fileRef: React.RefObject<HTMLInputElement>,
    setImport: React.Dispatch<React.SetStateAction<ImportState>>,
    importFn: (seasonName: string, data: object) => Promise<{ ok: boolean; count: number }>,
    label: string,
  ) => {
    const file = fileRef.current?.files?.[0]
    if (!seasonName.trim() || !file) return
    setImport({ importing: true, result: null, err: '' })
    try {
      const data = JSON.parse(await file.text())
      const res = await importFn(seasonName.trim(), data)
      setImport({ importing: false, result: `${res.count} ${label} imported`, err: '' })
      loadSeasons()
    } catch (ex) {
      setImport({ importing: false, result: null, err: String(ex) })
    } finally {
      if (fileRef.current) fileRef.current.value = ''
      setSingletonFileName(prev => ({ ...prev, [key]: '' }))
    }
  }

  const handleSetActive = async (name: string | null) => {
    setSettingActive(true)
    try { await api.setActiveSeason(name); loadSeasons() }
    catch { /* ignore */ }
    finally { setSettingActive(false) }
  }

  const handleDelete = async (name: string) => {
    setConfirmDelete(null)
    try { await api.deleteSeason(name); loadSeasons() }
    catch { /* ignore */ }
  }

  const activeSeasonName = seasons.find(s => s.is_active)?.name ?? null
  const displaySeasonName = activeSeasonName ?? seasons[0]?.name ?? null

  return (
    <div>
      {/* Active season bar */}
      <div style={{ background: '#12122a', border: '1px solid #2a2a4a', borderRadius: 8, padding: '10px 16px', marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>Active:</span>
        <span style={{ fontSize: 13, color: displaySeasonName ? '#c0a0ff' : '#444' }}>
          {displaySeasonName ?? '—'}
          {!activeSeasonName && displaySeasonName && (
            <span style={{ fontSize: 10, color: '#555', marginLeft: 8 }}>(default)</span>
          )}
        </span>
        {activeSeasonName && (
          <button className="btn btn-sm" style={{ marginLeft: 'auto' }} onClick={() => handleSetActive(null)} disabled={settingActive}>
            Reset to Default
          </button>
        )}
      </div>

      {/* Season list */}
      {seasons.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11, color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            Saved Seasons ({seasons.length})
          </div>
          {seasons.map(s => {
            const nodeTotal = Object.values(s.node_counts).reduce((a, b) => a + b, 0)
            return (
              <div key={s.name} style={{
                display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 12px', marginBottom: 4,
                background: s.is_active ? '#1a103a' : '#12122a',
                border: `1px solid ${s.is_active ? '#533483' : '#2a2a4a'}`, borderRadius: 6,
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: s.is_active ? '#c0a0ff' : '#ddd', fontWeight: s.is_active ? 700 : 400 }}>
                    {s.name}
                    {s.is_active && <span style={{ fontSize: 10, color: '#533483', marginLeft: 8, background: '#2a1a5a', padding: '1px 6px', borderRadius: 3 }}>ACTIVE</span>}
                  </div>
                  <div style={{ fontSize: 11, color: '#555', marginTop: 2, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <span>{s.trees.length} trees · {nodeTotal} nodes</span>
                    {s.new_god_count != null && <span>{s.new_god_count} new god talents</span>}
                    {s.legendary_gear_count != null && <span>{s.legendary_gear_count} legendary items</span>}
                    {s.skill_count != null && <span>{s.skill_count} skills</span>}
                    {s.hero_trait_count != null && <span>{s.hero_trait_count} hero traits</span>}
                    {s.pact_spirit_count != null && <span>{s.pact_spirit_count} pact spirits</span>}
                    {s.craft_base_type_count != null && <span>{s.craft_base_type_count} base types</span>}
                    {s.graft_count != null && <span>{s.graft_count} grafts</span>}
                    {s.destiny_count != null && <span>{s.destiny_count} destiny</span>}
                    {s.ethereal_prism_count != null && <span>{s.ethereal_prism_count} ethereal prism</span>}
                    {s.hero_memories_count != null && <span>{s.hero_memories_count} hero memories</span>}
                    {s.memory_revival_count != null && <span>{s.memory_revival_count} revival affixes</span>}
                    {s.tower_sequence_count != null && <span>{s.tower_sequence_count} tower entries</span>}
                  </div>
                </div>
                {!s.is_active && (
                  <button className="btn btn-sm btn-primary" onClick={() => handleSetActive(s.name)} disabled={settingActive}>Set Active</button>
                )}
                {confirmDelete === s.name ? (
                  <>
                    <button className="btn btn-sm btn-danger" onClick={() => handleDelete(s.name)}>Confirm Delete</button>
                    <button className="btn btn-sm" onClick={() => setConfirmDelete(null)}>Cancel</button>
                  </>
                ) : (
                  <button className="btn btn-sm btn-danger" onClick={() => setConfirmDelete(s.name)}>Delete</button>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Season name (shared across all import sections) */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 11, color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>
          Season
        </div>
        <input
          className="stat-val-input"
          type="text"
          placeholder="Season name (e.g. SS12 Lunaria)"
          value={seasonName}
          onChange={e => setSeasonName(e.target.value)}
          style={{ width: '100%', boxSizing: 'border-box', padding: '7px 10px', fontSize: 13 }}
        />
        {!seasonName.trim() && (
          <div style={{ fontSize: 11, color: '#4a4a6a', marginTop: 4 }}>Enter a season name to enable imports below.</div>
        )}
      </div>

      {/* Data category sections */}
      <div style={{ fontSize: 11, color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>
        Import Data
      </div>

      <CategoryCard label="Talent Trees" description="Tree nodes, connections, modifiers, core talents, and New God talents" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            Choose Files
            <input ref={talentFilesRef} type="file" accept=".json" multiple style={{ display: 'none' }}
              onChange={e => setTalentFileNames(Array.from(e.target.files ?? []).map(f => f.name))} />
          </label>
          <button className="btn btn-primary btn-sm" onClick={handleImportTalents}
            disabled={talentImport.importing || !seasonName.trim()}>
            {talentImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {talentFileNames.length > 0 && !talentImport.result && !talentImport.err && (
          <div style={{ fontSize: 11, color: '#666', marginTop: 6 }}>{talentFileNames.join(', ')}</div>
        )}
        {talentImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{talentImport.err}</div>}
        {talentImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{talentImport.result}</div>}
      </CategoryCard>

      <CategoryCard label="Legendary Gear" description="Legendary equipment pool, affixes, and numeric ranges" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            Choose File
            <input ref={legendaryFilesRef} type="file" accept=".json" multiple style={{ display: 'none' }}
              onChange={e => setLegendaryFileNames(Array.from(e.target.files ?? []).map(f => f.name))} />
          </label>
          <button className="btn btn-primary btn-sm" onClick={handleImportLegendaryGear}
            disabled={legendaryImport.importing || !seasonName.trim()}>
            {legendaryImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {legendaryFileNames.length > 0 && !legendaryImport.result && !legendaryImport.err && (
          <div style={{ fontSize: 11, color: '#666', marginTop: 6 }}>{legendaryFileNames.join(', ')}</div>
        )}
        {legendaryImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{legendaryImport.err}</div>}
        {legendaryImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{legendaryImport.result}</div>}
      </CategoryCard>
      <CategoryCard label="Skills" description="Active skill definitions, tags, and effect text" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            Choose Files
            <input ref={skillsFilesRef} type="file" accept=".json" multiple style={{ display: 'none' }}
              onChange={e => setSkillsFileNames(Array.from(e.target.files ?? []).map(f => f.name))} />
          </label>
          <button className="btn btn-primary btn-sm" onClick={handleImportSkills}
            disabled={skillsImport.importing || !seasonName.trim()}>
            {skillsImport.importing ? 'Importing…' : 'Import'}
          </button>
          <button className="btn btn-danger btn-sm" onClick={handleClearSkills}
            disabled={skillsImport.importing || !seasonName.trim()}>
            Clear
          </button>
        </div>
        {skillsFileNames.length > 0 && !skillsImport.result && !skillsImport.err && (
          <div style={{ fontSize: 11, color: '#666', marginTop: 6 }}>{skillsFileNames.join(', ')}</div>
        )}
        {skillsImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{skillsImport.err}</div>}
        {skillsImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{skillsImport.result}</div>}
      </CategoryCard>
      <CategoryCard label="Hero Traits" description="Hero and trait variant definitions, base levels, and advanced traits" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            Choose Files
            <input ref={heroTraitFilesRef} type="file" accept=".json" multiple style={{ display: 'none' }}
              onChange={e => setHeroTraitFileNames(Array.from(e.target.files ?? []).map(f => f.name))} />
          </label>
          <button className="btn btn-primary btn-sm" onClick={handleImportHeroTraits}
            disabled={heroTraitImport.importing || !seasonName.trim()}>
            {heroTraitImport.importing ? 'Importing…' : 'Import'}
          </button>
          <button className="btn btn-danger btn-sm" onClick={handleClearHeroTraits}
            disabled={heroTraitImport.importing || !seasonName.trim()}>
            Clear
          </button>
        </div>
        {heroTraitFileNames.length > 0 && !heroTraitImport.result && !heroTraitImport.err && (
          <div style={{ fontSize: 11, color: '#666', marginTop: 6 }}>{heroTraitFileNames.join(', ')}</div>
        )}
        {heroTraitImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{heroTraitImport.err}</div>}
        {heroTraitImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{heroTraitImport.result}</div>}
      </CategoryCard>
      <CategoryCard label="Pact Spirits" description="Pact spirit definitions, upgrade ranks, ring slots, and glossary (166 files)" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            Choose Files
            <input ref={pactSpiritFilesRef} type="file" accept=".json" multiple style={{ display: 'none' }}
              onChange={e => setPactSpiritFileNames(Array.from(e.target.files ?? []).map(f => f.name))} />
          </label>
          <button className="btn btn-primary btn-sm" onClick={handleImportPactSpirits}
            disabled={pactSpiritImport.importing || !seasonName.trim()}>
            {pactSpiritImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {pactSpiritFileNames.length > 0 && !pactSpiritImport.result && !pactSpiritImport.err && (
          <div style={{ fontSize: 11, color: '#666', marginTop: 6 }}>{pactSpiritFileNames.length} file(s) selected</div>
        )}
        {pactSpiritImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{pactSpiritImport.err}</div>}
        {pactSpiritImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{pactSpiritImport.result}</div>}
      </CategoryCard>

      <CategoryCard label="Craft Base Types" description="Gear base type affix pools and ranges (38 files)" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            Choose Files
            <input ref={craftBaseTypeFilesRef} type="file" accept=".json" multiple style={{ display: 'none' }}
              onChange={e => setCraftBaseTypeFileNames(Array.from(e.target.files ?? []).map(f => f.name))} />
          </label>
          <button className="btn btn-primary btn-sm" onClick={handleImportCraftBaseTypes}
            disabled={craftBaseTypeImport.importing || !seasonName.trim()}>
            {craftBaseTypeImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {craftBaseTypeFileNames.length > 0 && !craftBaseTypeImport.result && !craftBaseTypeImport.err && (
          <div style={{ fontSize: 11, color: '#666', marginTop: 6 }}>{craftBaseTypeFileNames.length} file(s) selected</div>
        )}
        {craftBaseTypeImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{craftBaseTypeImport.err}</div>}
        {craftBaseTypeImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{craftBaseTypeImport.result}</div>}
      </CategoryCard>

      <CategoryCard label="Grafts" description="Graft body part affix tiers and weights (10 files)" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            Choose Files
            <input ref={graftFilesRef} type="file" accept=".json" multiple style={{ display: 'none' }}
              onChange={e => setGraftFileNames(Array.from(e.target.files ?? []).map(f => f.name))} />
          </label>
          <button className="btn btn-primary btn-sm" onClick={handleImportGrafts}
            disabled={graftImport.importing || !seasonName.trim()}>
            {graftImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {graftFileNames.length > 0 && !graftImport.result && !graftImport.err && (
          <div style={{ fontSize: 11, color: '#666', marginTop: 6 }}>{graftFileNames.length} file(s) selected</div>
        )}
        {graftImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{graftImport.err}</div>}
        {graftImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{graftImport.result}</div>}
      </CategoryCard>

      <CategoryCard label="Destiny" description="Fate items installable in talent nodes (single file)" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            {singletonFileName['destiny'] || 'Choose File'}
            <input ref={destinyFileRef} type="file" accept=".json" style={{ display: 'none' }}
              onChange={e => setSingletonFileName(p => ({ ...p, destiny: e.target.files?.[0]?.name ?? '' }))} />
          </label>
          <button className="btn btn-primary btn-sm"
            onClick={() => handleImportSingleton('destiny', destinyFileRef, setDestinyImport, api.importDestiny, 'items')}
            disabled={destinyImport.importing || !seasonName.trim()}>
            {destinyImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {destinyImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{destinyImport.err}</div>}
        {destinyImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{destinyImport.result}</div>}
      </CategoryCard>

      <CategoryCard label="Ethereal Prism" description="Core talent additional modifiers (single file)" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            {singletonFileName['ethereal_prism'] || 'Choose File'}
            <input ref={etherealPrismFileRef} type="file" accept=".json" style={{ display: 'none' }}
              onChange={e => setSingletonFileName(p => ({ ...p, ethereal_prism: e.target.files?.[0]?.name ?? '' }))} />
          </label>
          <button className="btn btn-primary btn-sm"
            onClick={() => handleImportSingleton('ethereal_prism', etherealPrismFileRef, setEtherealPrismImport, api.importEtherealPrism, 'modifiers')}
            disabled={etherealPrismImport.importing || !seasonName.trim()}>
            {etherealPrismImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {etherealPrismImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{etherealPrismImport.err}</div>}
        {etherealPrismImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{etherealPrismImport.result}</div>}
      </CategoryCard>

      <CategoryCard label="Hero Memories" description="Memory affix pool by origin, discipline, and progress types (single file)" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            {singletonFileName['hero_memories'] || 'Choose File'}
            <input ref={heroMemoriesFileRef} type="file" accept=".json" style={{ display: 'none' }}
              onChange={e => setSingletonFileName(p => ({ ...p, hero_memories: e.target.files?.[0]?.name ?? '' }))} />
          </label>
          <button className="btn btn-primary btn-sm"
            onClick={() => handleImportSingleton('hero_memories', heroMemoriesFileRef, setHeroMemoriesImport, api.importHeroMemories, 'affixes')}
            disabled={heroMemoriesImport.importing || !seasonName.trim()}>
            {heroMemoriesImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {heroMemoriesImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{heroMemoriesImport.err}</div>}
        {heroMemoriesImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{heroMemoriesImport.result}</div>}
      </CategoryCard>

      <CategoryCard label="Memory Revival" description="Tiered revival affix pool with weights (single file)" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            {singletonFileName['memory_revival'] || 'Choose File'}
            <input ref={memoryRevivalFileRef} type="file" accept=".json" style={{ display: 'none' }}
              onChange={e => setSingletonFileName(p => ({ ...p, memory_revival: e.target.files?.[0]?.name ?? '' }))} />
          </label>
          <button className="btn btn-primary btn-sm"
            onClick={() => handleImportSingleton('memory_revival', memoryRevivalFileRef, setMemoryRevivalImport, api.importMemoryRevival, 'affixes')}
            disabled={memoryRevivalImport.importing || !seasonName.trim()}>
            {memoryRevivalImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {memoryRevivalImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{memoryRevivalImport.err}</div>}
        {memoryRevivalImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{memoryRevivalImport.result}</div>}
      </CategoryCard>

      <CategoryCard label="Tower Sequence" description="Tower sequence affixes by weapon source (single file)" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            {singletonFileName['tower_sequence'] || 'Choose File'}
            <input ref={towerSequenceFileRef} type="file" accept=".json" style={{ display: 'none' }}
              onChange={e => setSingletonFileName(p => ({ ...p, tower_sequence: e.target.files?.[0]?.name ?? '' }))} />
          </label>
          <button className="btn btn-primary btn-sm"
            onClick={() => handleImportSingleton('tower_sequence', towerSequenceFileRef, setTowerSequenceImport, api.importTowerSequence, 'entries')}
            disabled={towerSequenceImport.importing || !seasonName.trim()}>
            {towerSequenceImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {towerSequenceImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{towerSequenceImport.err}</div>}
        {towerSequenceImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{towerSequenceImport.result}</div>}
      </CategoryCard>
    </div>
  )
}

// ── Tools tab ──────────────────────────────────────────────────────────────

type DetailSection = 'matched' | 'ambiguous' | 'unmatched' | 'conditional' | null

function AmbiguousTable({ items, onOverride }: {
  items: UnresolvedStat[]
  onOverride: (text: string, stat: string) => Promise<void>
}) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)
  const [resolved, setResolved] = useState<Record<string, string>>({})

  const unique = Array.from(new Map(items.map(i => [i.text, i])).values())

  const handleUse = async (item: UnresolvedStat, stat: string) => {
    setSaving(item.text)
    try {
      await onOverride(item.text, stat)
      setResolved(r => ({ ...r, [item.text]: stat }))
      setExpanded(null)
    } finally {
      setSaving(null)
    }
  }

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: 11, color: '#666', marginBottom: 6 }}>
        {unique.length} unique texts ({items.length} total occurrences) — click a row to resolve
      </div>
      <div style={{ maxHeight: 420, overflowY: 'auto', border: '1px solid #1a1a3a', borderRadius: 4 }}>
        {unique.map((item, i) => {
          const isResolved = !!resolved[item.text]
          const isOpen = expanded === item.text
          return (
            <div key={i} style={{ borderBottom: '1px solid #1a1a3a', background: isResolved ? '#0a1a0a' : i % 2 === 0 ? '#0a0a1e' : '#0e0e24' }}>
              <div
                onClick={() => !isResolved && setExpanded(isOpen ? null : item.text)}
                style={{ padding: '6px 10px', cursor: isResolved ? 'default' : 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
              >
                <span style={{ fontSize: 12, color: isResolved ? '#4caf50' : '#ccc', flex: 1 }}>{item.text}</span>
                {isResolved
                  ? <span style={{ fontSize: 10, color: '#4caf50', fontFamily: 'monospace' }}>{resolved[item.text]} ✓</span>
                  : item.tied && <span style={{ fontSize: 10, color: '#ff9800' }}>{item.tied.length} tied · {isOpen ? '▲' : '▼'}</span>
                }
              </div>
              {isOpen && !isResolved && item.tied && (
                <div style={{ padding: '4px 10px 8px 20px', background: '#0a0a1a' }}>
                  {item.tied.map((c, j) => (
                    <div key={j} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#ff9800', minWidth: 220 }}>{c.stat}</span>
                      <span style={{ fontSize: 11, color: '#666', flex: 1 }}>{c.display_name}</span>
                      <span style={{ fontSize: 10, color: '#555', minWidth: 60 }}>score {c.score}</span>
                      <button
                        className="btn btn-sm btn-primary"
                        style={{ fontSize: 10, padding: '2px 8px' }}
                        disabled={saving === item.text}
                        onClick={e => { e.stopPropagation(); handleUse(item, c.stat) }}
                      >
                        Use this
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function UnmatchedTable({ items }: { items: UnresolvedStat[] }) {
  const unique = Array.from(new Map(items.map(i => [i.text, i])).values())
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: 11, color: '#666', marginBottom: 6 }}>
        {unique.length} unique texts ({items.length} total occurrences)
      </div>
      <div style={{ maxHeight: 420, overflowY: 'auto', border: '1px solid #1a1a3a', borderRadius: 4 }}>
        {unique.map((item, i) => (
          <div key={i} style={{ padding: '5px 10px', borderBottom: '1px solid #1a1a3a', background: i % 2 === 0 ? '#0a0a1e' : '#0e0e24' }}>
            <span style={{ fontSize: 12, color: '#888' }}>{item.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function MatchedTable({ matchedTexts }: { matchedTexts: Record<string, string[]> }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const entries = Object.entries(matchedTexts).sort(([a], [b]) => a.localeCompare(b))
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: 11, color: '#666', marginBottom: 6 }}>
        {entries.length} stats matched — click to see which texts resolved to each stat
      </div>
      <div style={{ maxHeight: 420, overflowY: 'auto', border: '1px solid #1a1a3a', borderRadius: 4 }}>
        {entries.map(([stat, texts], i) => {
          const isOpen = expanded === stat
          return (
            <div key={i} style={{ borderBottom: '1px solid #1a1a3a', background: i % 2 === 0 ? '#0a0a1e' : '#0e0e24' }}>
              <div
                onClick={() => setExpanded(isOpen ? null : stat)}
                style={{ padding: '6px 10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
              >
                <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#4caf50', flex: 1 }}>{stat}</span>
                <span style={{ fontSize: 10, color: '#555' }}>{texts.length} text{texts.length !== 1 ? 's' : ''} · {isOpen ? '▲' : '▼'}</span>
              </div>
              {isOpen && (
                <div style={{ padding: '4px 10px 8px 20px', background: '#0a0a1a' }}>
                  {texts.map((t, j) => (
                    <div key={j} style={{ fontSize: 11, color: '#888', marginBottom: 2 }}>{t}</div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function OverridesPanel({ overrides, onDelete }: {
  overrides: Record<string, FilterOverride>
  onDelete: (key: string) => void
}) {
  const entries = Object.entries(overrides)
  if (entries.length === 0) return null
  return (
    <div style={{ marginTop: 12, border: '1px solid #2a2a4a', borderRadius: 6, overflow: 'hidden' }}>
      <div style={{ padding: '7px 12px', background: '#14142a', fontSize: 12, fontWeight: 600, color: '#aaa' }}>
        Manual Overrides ({entries.length})
      </div>
      <div style={{ maxHeight: 240, overflowY: 'auto' }}>
        {entries.map(([key, ov], i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 12px', borderBottom: '1px solid #1a1a3a', background: i % 2 === 0 ? '#0a0a1e' : '#0e0e24' }}>
            <span style={{ fontSize: 11, color: '#888', flex: 1 }}>{ov.example}</span>
            <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#4caf50', minWidth: 180 }}>{ov.stat}</span>
            <button className="btn btn-sm btn-danger" style={{ fontSize: 10, padding: '2px 6px' }} onClick={() => onDelete(key)}>✕</button>
          </div>
        ))}
      </div>
    </div>
  )
}

function ToolsTab() {
  const [building, setBuilding] = useState(false)
  const [result, setResult] = useState<RebuildFilterResult | null>(null)
  const [err, setErr] = useState('')
  const [detail, setDetail] = useState<DetailSection>(null)
  const [overrides, setOverrides] = useState<Record<string, FilterOverride>>({})
  const [exporting, setExporting] = useState(false)
  const [exportMsg, setExportMsg] = useState('')
  const [exportingUnmatched, setExportingUnmatched] = useState(false)
  const [exportUnmatchedMsg, setExportUnmatchedMsg] = useState('')

  useEffect(() => {
    api.getNodeTypeFilterOverrides().then(r => setOverrides(r.overrides)).catch(() => {})
  }, [])

  const handleRebuild = async () => {
    setBuilding(true); setErr(''); setResult(null); setDetail(null)
    try {
      setResult(await api.rebuildNodeTypeFilter())
    } catch (ex) {
      setErr(String(ex))
    } finally {
      setBuilding(false)
    }
  }

  const handleExport = async () => {
    setExporting(true); setExportMsg('')
    try {
      const r = await api.exportStatMeta()
      setExportMsg(`Exported ${r.stat_count} stats → docs/stat-meta-review.csv`)
    } catch (ex) {
      setExportMsg(`Error: ${String(ex)}`)
    } finally {
      setExporting(false)
    }
  }

  const handleExportUnmatched = async () => {
    setExportingUnmatched(true); setExportUnmatchedMsg('')
    try {
      const r = await api.exportUnmatched()
      setExportUnmatchedMsg(`${r.unique} unique texts → docs/stat-audit.md`)
    } catch (ex) {
      setExportUnmatchedMsg(`Error: ${String(ex)}`)
    } finally {
      setExportingUnmatched(false)
    }
  }

  const handleOverride = async (text: string, stat: string) => {
    const r = await api.addNodeTypeFilterOverride(text, stat)
    setOverrides(prev => ({ ...prev, [r.key]: { stat, example: text } }))
  }

  const handleDeleteOverride = async (key: string) => {
    await api.deleteNodeTypeFilterOverride(key)
    setOverrides(prev => { const n = { ...prev }; delete n[key]; return n })
  }

  const meta = result?._meta
  const ambiguous = result?.unresolved.filter(u => u.reason === 'ambiguous') ?? []
  const unmatched = result?.unresolved.filter(u => u.reason === 'unmatched' || u.reason === 'multi_text') ?? []
  const conditional = result?.unresolved.filter(u => u.reason === 'conditional') ?? []

  const toggleDetail = (section: DetailSection) => setDetail(d => d === section ? null : section)

  return (
    <div>
      <div style={{ border: '1px solid #2a2a4a', borderRadius: 7, overflow: 'hidden', marginBottom: 10 }}>
        <div style={{ padding: '9px 14px', background: '#14142a' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#ccc' }}>Exports</span>
          <div style={{ fontSize: 11, color: '#555', marginTop: 2 }}>
            Generate review documents from current stat definitions and filter state.
          </div>
        </div>
        <div style={{ padding: '12px 14px', background: '#0e0e24', borderTop: '1px solid #1a1a3a', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button className="btn btn-sm" onClick={handleExport} disabled={exporting} style={{ minWidth: 170 }}>
              {exporting ? 'Exporting…' : 'Export Stat Meta (CSV)'}
            </button>
            {exportMsg && (
              <span style={{ fontSize: 12, color: exportMsg.startsWith('Error') ? '#ff6b6b' : '#4caf50' }}>{exportMsg}</span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button className="btn btn-sm" onClick={handleExportUnmatched} disabled={exportingUnmatched} style={{ minWidth: 170 }}>
              {exportingUnmatched ? 'Exporting…' : 'Export Unmatched (MD)'}
            </button>
            {exportUnmatchedMsg && (
              <span style={{ fontSize: 12, color: exportUnmatchedMsg.startsWith('Error') ? '#ff6b6b' : '#4caf50' }}>{exportUnmatchedMsg}</span>
            )}
          </div>
        </div>
      </div>

      <div style={{ border: '1px solid #2a2a4a', borderRadius: 7, overflow: 'hidden', marginBottom: 10 }}>
        <div style={{ padding: '9px 14px', background: '#14142a' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#ccc' }}>Node Type Filter</span>
          <div style={{ fontSize: 11, color: '#555', marginTop: 2 }}>
            Rebuilds data/node_type_filter.json by matching talent snapshot modifier texts to stat definitions.
          </div>
        </div>
        <div style={{ padding: '12px 14px', background: '#0e0e24', borderTop: '1px solid #1a1a3a' }}>
          <button className="btn btn-primary btn-sm" onClick={handleRebuild} disabled={building}>
            {building ? 'Rebuilding…' : 'Rebuild Node Type Filter'}
          </button>
          {err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 8 }}>{err}</div>}
          {meta && (
            <>
              <div style={{ display: 'flex', gap: 20, marginTop: 10, alignItems: 'flex-end' }}>
                <button onClick={() => toggleDetail('matched')} style={{ textAlign: 'center', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: detail === 'matched' ? '#81c784' : '#4caf50' }}>{meta.matched}</div>
                  <div style={{ fontSize: 10, color: detail === 'matched' ? '#4caf50' : '#555' }}>matched {detail === 'matched' ? '▲' : '▼'}</div>
                </button>
                <button onClick={() => toggleDetail('ambiguous')} style={{ textAlign: 'center', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: detail === 'ambiguous' ? '#ffb74d' : '#ff9800' }}>{meta.ambiguous}</div>
                  <div style={{ fontSize: 10, color: detail === 'ambiguous' ? '#ff9800' : '#555' }}>ambiguous {detail === 'ambiguous' ? '▲' : '▼'}</div>
                </button>
                <button onClick={() => toggleDetail('unmatched')} style={{ textAlign: 'center', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: detail === 'unmatched' ? '#e57373' : (meta.unmatched > 0 ? '#ef5350' : '#4caf50') }}>{meta.unmatched}</div>
                  <div style={{ fontSize: 10, color: detail === 'unmatched' ? '#ef5350' : '#555' }}>unmatched {detail === 'unmatched' ? '▲' : '▼'}</div>
                </button>
                <button onClick={() => toggleDetail('conditional')} style={{ textAlign: 'center', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: detail === 'conditional' ? '#ce93d8' : '#9c27b0' }}>{meta.conditional ?? 0}</div>
                  <div style={{ fontSize: 10, color: detail === 'conditional' ? '#9c27b0' : '#555' }}>conditional {detail === 'conditional' ? '▲' : '▼'}</div>
                </button>
                <div style={{ textAlign: 'right', marginLeft: 'auto' }}>
                  <div style={{ fontSize: 11, color: '#555' }}>built at</div>
                  <div style={{ fontSize: 11, color: '#888' }}>{meta.generated_at}</div>
                </div>
              </div>
              {detail === 'matched'     && <MatchedTable matchedTexts={result!.matched_texts} />}
              {detail === 'ambiguous'   && <AmbiguousTable items={ambiguous} onOverride={handleOverride} />}
              {detail === 'unmatched'   && <UnmatchedTable items={unmatched} />}
              {detail === 'conditional' && <UnmatchedTable items={conditional} />}
            </>
          )}
          <OverridesPanel overrides={overrides} onDelete={handleDeleteOverride} />
        </div>
      </div>
    </div>
  )
}

// ── Main screen ────────────────────────────────────────────────────────────

export default function DevToolsScreen({ onBack, deprecatedTools, onToggleDeprecatedTools }: Props) {
  const [tab, setTab] = useState<Tab>('seasons')

  return (
    <div className="screen" style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 16, padding: '12px 20px',
        background: '#0e0e28', borderBottom: '1px solid #2a2a4a', flexShrink: 0,
      }}>
        <button className="btn btn-sm" onClick={onBack}>← Back</button>
        <h2 style={{ margin: 0, fontSize: 16, color: '#e0e0e0' }}>Dev Tools</h2>
        <span style={{
          fontSize: 10, fontWeight: 700, color: '#ff9800', background: '#2a1a00',
          padding: '2px 6px', borderRadius: 3, border: '1px solid #5a3a00',
        }}>DEV MODE</span>
        <label style={{
          marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8,
          cursor: 'pointer', fontSize: 12,
          color: deprecatedTools ? '#ff9800' : '#555',
        }}>
          <input type="checkbox" checked={deprecatedTools} onChange={onToggleDeprecatedTools} />
          Deprecated Tools
        </label>
      </div>

      <div style={{
        display: 'flex', gap: 4, padding: '10px 20px 0',
        background: '#0e0e28', borderBottom: '1px solid #2a2a4a', flexShrink: 0,
      }}>
        {([
          { id: 'seasons', label: 'Seasons' },
          { id: 'diff',    label: 'Season Diff' },
          { id: 'tools',   label: 'Tools' },
        ] as { id: Tab; label: string }[]).map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: '6px 16px', border: 'none', cursor: 'pointer', fontSize: 13,
            borderRadius: '4px 4px 0 0',
            background: tab === t.id ? '#1a1a3a' : 'transparent',
            color: tab === t.id ? '#e0e0e0' : '#666',
            borderBottom: tab === t.id ? '2px solid #533483' : '2px solid transparent',
          }}>{t.label}</button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
        {tab === 'seasons' && <SeasonsTab />}
        {tab === 'diff'    && <DiffTab />}
        {tab === 'tools'   && <ToolsTab />}
      </div>
    </div>
  )
}
