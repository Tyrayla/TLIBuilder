import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, SeasonSummary, SeasonDiff, RebuildFilterResult, UnresolvedStat, FilterOverride } from '../api/client'

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

function extractTalentNodes(data: unknown): object[] {
  if (Array.isArray(data)) {
    const nodes: object[] = []
    for (const item of data) {
      if (item && typeof item === 'object') {
        if ('global_node_id' in item) nodes.push(item)
        else if ('nodes' in item && Array.isArray((item as { nodes: unknown[] }).nodes))
          nodes.push(...(item as { nodes: object[] }).nodes)
      }
    }
    return nodes
  }
  if (data && typeof data === 'object' && 'nodes' in data && Array.isArray((data as { nodes: unknown[] }).nodes))
    return (data as { nodes: object[] }).nodes
  return []
}

function extractNewGodItems(data: unknown): object[] {
  if (!data || typeof data !== 'object') return []
  const d = data as Record<string, unknown>
  if (Array.isArray(d.items)) {
    const items = d.items as object[]
    if (items.length > 0 && 'effect_lines' in (items[0] as object))
      return items.filter(i => i && typeof i === 'object' && 'name' in i)
  }
  return []
}

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
  const [seasons, setSeasons] = useState<SeasonSummary[]>([])
  const [seasonName, setSeasonName] = useState('')
  const [settingActive, setSettingActive] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [talentImport, setTalentImport] = useState<ImportState>(emptyImport())
  const [legendaryImport, setLegendaryImport] = useState<ImportState>(emptyImport())

  const loadSeasons = useCallback(() => {
    api.listSeasons().then(setSeasons).catch(() => {})
  }, [])

  useEffect(() => { loadSeasons() }, [loadSeasons])

  const handleImportTalents = async () => {
    const files = talentFilesRef.current?.files
    if (!seasonName.trim() || !files || files.length === 0) return
    setTalentImport({ importing: true, result: null, err: '' })
    try {
      const allNodes: object[] = []
      const allNewGodItems: object[] = []
      for (const file of Array.from(files)) {
        const data = JSON.parse(await file.text())
        const newGod = extractNewGodItems(data)
        if (newGod.length > 0) allNewGodItems.push(...newGod)
        else allNodes.push(...extractTalentNodes(data))
      }
      const parts: string[] = []
      if (allNodes.length > 0) {
        const res = await api.importSeason(seasonName.trim(), allNodes)
        parts.push(`Trees: ${res.trees_imported.join(', ') || '(none)'}`)
        if (res.skipped.length) parts.push(`Skipped: ${res.skipped.join(', ')}`)
      }
      if (allNewGodItems.length > 0) {
        const res = await api.importNewGodTalents(seasonName.trim(), allNewGodItems)
        parts.push(`${res.count} New God talent${res.count !== 1 ? 's' : ''}`)
      }
      setTalentImport({ importing: false, result: parts.join(' · ') || 'Nothing imported', err: '' })
      loadSeasons()
    } catch (ex) {
      setTalentImport({ importing: false, result: null, err: String(ex) })
    } finally {
      if (talentFilesRef.current) talentFilesRef.current.value = ''
    }
  }

  const handleImportLegendaryGear = async () => {
    const files = legendaryFilesRef.current?.files
    if (!seasonName.trim() || !files || files.length === 0) return
    setLegendaryImport({ importing: true, result: null, err: '' })
    try {
      let totalCount = 0
      let setName = 'Legendary Gear'
      for (const file of Array.from(files)) {
        const data = JSON.parse(await file.text())
        if (!data || !Array.isArray(data.items)) {
          throw new Error(`${file.name}: not a valid legendary gear JSON (missing items array)`)
        }
        const res = await api.importLegendaryGear(seasonName.trim(), data)
        totalCount += res.count
        setName = res.set_name
      }
      setLegendaryImport({ importing: false, result: `${setName}: ${totalCount} items imported`, err: '' })
      loadSeasons()
    } catch (ex) {
      setLegendaryImport({ importing: false, result: null, err: String(ex) })
    } finally {
      if (legendaryFilesRef.current) legendaryFilesRef.current.value = ''
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

  return (
    <div>
      {/* Active season bar */}
      <div style={{ background: '#12122a', border: '1px solid #2a2a4a', borderRadius: 8, padding: '10px 16px', marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>Active:</span>
        <span style={{ fontSize: 13, color: activeSeasonName ? '#c0a0ff' : '#444' }}>
          {activeSeasonName ?? '— Current (Python builders) —'}
        </span>
        {activeSeasonName && (
          <button className="btn btn-sm" style={{ marginLeft: 'auto' }} onClick={() => handleSetActive(null)} disabled={settingActive}>
            Reset to Current
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
                display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', marginBottom: 4,
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
            <input ref={talentFilesRef} type="file" accept=".json" multiple style={{ display: 'none' }} />
          </label>
          <button className="btn btn-primary btn-sm" onClick={handleImportTalents}
            disabled={talentImport.importing || !seasonName.trim()}>
            {talentImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {talentImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{talentImport.err}</div>}
        {talentImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{talentImport.result}</div>}
      </CategoryCard>

      <CategoryCard label="Legendary Gear" description="Legendary equipment pool, affixes, and numeric ranges" enabled>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            Choose File
            <input ref={legendaryFilesRef} type="file" accept=".json" multiple style={{ display: 'none' }} />
          </label>
          <button className="btn btn-primary btn-sm" onClick={handleImportLegendaryGear}
            disabled={legendaryImport.importing || !seasonName.trim()}>
            {legendaryImport.importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {legendaryImport.err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 6 }}>{legendaryImport.err}</div>}
        {legendaryImport.result && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 6 }}>{legendaryImport.result}</div>}
      </CategoryCard>
      <CategoryCard label="Normal Gear" description="Normal and magic equipment pool" enabled={false} />
      <CategoryCard label="Skills" description="Active skill definitions and modifiers" enabled={false} />
      <CategoryCard label="Hero Traits" description="Hero-specific passive trait trees" enabled={false} />
      <CategoryCard label="Pact Spirits" description="Pact spirit bonuses and tiers" enabled={false} />
    </div>
  )
}

// ── Tools tab ──────────────────────────────────────────────────────────────

type DetailSection = 'matched' | 'ambiguous' | 'unmatched' | null

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
      setExportUnmatchedMsg(`${r.unique} unique texts → docs/stat-unmatched-review.md`)
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
  const unmatched = result?.unresolved.filter(u => u.reason === 'unmatched') ?? []

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
                <div style={{ textAlign: 'right', marginLeft: 'auto' }}>
                  <div style={{ fontSize: 11, color: '#555' }}>built at</div>
                  <div style={{ fontSize: 11, color: '#888' }}>{meta.generated_at}</div>
                </div>
              </div>
              {detail === 'matched'   && <MatchedTable matchedTexts={result!.matched_texts} />}
              {detail === 'ambiguous' && <AmbiguousTable items={ambiguous} onOverride={handleOverride} />}
              {detail === 'unmatched' && <UnmatchedTable items={unmatched} />}
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
