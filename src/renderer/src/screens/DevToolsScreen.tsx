import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, SeasonSummary, SeasonDiff } from '../api/client'

type Tab = 'diff' | 'seasons'

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

function extractNodes(data: unknown): object[] {
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

function SeasonsTab() {
  const filesRef = useRef<HTMLInputElement>(null)
  const [seasons, setSeasons] = useState<SeasonSummary[]>([])
  const [seasonName, setSeasonName] = useState('')
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<{ trees_imported: string[]; skipped: string[] } | null>(null)
  const [importErr, setImportErr] = useState('')
  const [settingActive, setSettingActive] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const loadSeasons = useCallback(() => {
    api.listSeasons().then(setSeasons).catch(() => {})
  }, [])

  useEffect(() => { loadSeasons() }, [loadSeasons])

  const handleImport = async () => {
    const files = filesRef.current?.files
    if (!seasonName.trim() || !files || files.length === 0) return
    setImporting(true); setImportErr(''); setImportResult(null)
    try {
      const allNodes: object[] = []
      for (const file of Array.from(files)) {
        const data = JSON.parse(await file.text())
        allNodes.push(...extractNodes(data))
      }
      const res = await api.importSeason(seasonName.trim(), allNodes)
      setImportResult({ trees_imported: res.trees_imported, skipped: res.skipped })
      loadSeasons()
    } catch (ex) { setImportErr(String(ex)) }
    finally {
      setImporting(false)
      if (filesRef.current) filesRef.current.value = ''
    }
  }

  const handleSetActive = async (name: string | null) => {
    setSettingActive(true)
    try {
      await api.setActiveSeason(name)
      loadSeasons()
    } catch { /* ignore */ }
    finally { setSettingActive(false) }
  }

  const handleDelete = async (name: string) => {
    setConfirmDelete(null)
    try {
      await api.deleteSeason(name)
      loadSeasons()
    } catch { /* ignore */ }
  }

  const activeSeasonName = seasons.find(s => s.is_active)?.name ?? null

  return (
    <div>
      <p style={{ color: '#888', fontSize: 13, marginBottom: 14 }}>
        Import game-data JSON files to create a season snapshot. Once active, the tree viewer loads
        nodes and modifiers from the season instead of Python builders.
      </p>

      {/* Active season info */}
      <div style={{ background: '#12122a', border: '1px solid #2a2a4a', borderRadius: 8, padding: '10px 16px', marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>Active:</span>
        <span style={{ fontSize: 13, color: activeSeasonName ? '#c0a0ff' : '#444' }}>
          {activeSeasonName ?? '— Current (Python builders) —'}
        </span>
        {activeSeasonName && (
          <button
            className="btn btn-sm"
            style={{ marginLeft: 'auto' }}
            onClick={() => handleSetActive(null)}
            disabled={settingActive}
          >
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
          {seasons.map(s => (
            <div key={s.name} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 12px', marginBottom: 4,
              background: s.is_active ? '#1a103a' : '#12122a',
              border: `1px solid ${s.is_active ? '#533483' : '#2a2a4a'}`,
              borderRadius: 6,
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: s.is_active ? '#c0a0ff' : '#ddd', fontWeight: s.is_active ? 700 : 400 }}>
                  {s.name}
                  {s.is_active && <span style={{ fontSize: 10, color: '#533483', marginLeft: 8, background: '#2a1a5a', padding: '1px 6px', borderRadius: 3 }}>ACTIVE</span>}
                </div>
                <div style={{ fontSize: 11, color: '#555', marginTop: 2 }}>
                  {s.trees.length} trees · {Object.values(s.node_counts).reduce((a, b) => a + b, 0)} nodes
                </div>
              </div>
              {!s.is_active && (
                <button className="btn btn-sm btn-primary" onClick={() => handleSetActive(s.name)} disabled={settingActive}>
                  Set Active
                </button>
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
          ))}
        </div>
      )}

      {/* Import section */}
      <div style={{ background: '#12122a', border: '1px solid #2a2a4a', borderRadius: 8, padding: 16 }}>
        <div style={{ fontSize: 11, color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>
          Import New Season
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
          <input
            className="stat-val-input"
            type="text"
            placeholder="Season name (e.g. Season 12 Lunaria)"
            value={seasonName}
            onChange={e => setSeasonName(e.target.value)}
            style={{ flex: 1, padding: '6px 10px', fontSize: 13 }}
          />
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="btn btn-sm" style={{ cursor: 'pointer' }}>
            Choose JSON Files
            <input ref={filesRef} type="file" accept=".json" multiple style={{ display: 'none' }} />
          </label>
          <button
            className="btn btn-primary"
            onClick={handleImport}
            disabled={importing || !seasonName.trim()}
          >
            {importing ? 'Importing…' : 'Import'}
          </button>
        </div>
        {importErr && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 8 }}>{importErr}</div>}
        {importResult && (
          <div style={{ marginTop: 10, fontSize: 12 }}>
            <div style={{ color: '#4caf50', marginBottom: 4 }}>
              Imported: {importResult.trees_imported.join(', ') || '(none)'}
            </div>
            {importResult.skipped.length > 0 && (
              <div style={{ color: '#ff9800' }}>
                Skipped (unknown slug): {importResult.skipped.join(', ')}
              </div>
            )}
          </div>
        )}
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
      </div>
    </div>
  )
}
