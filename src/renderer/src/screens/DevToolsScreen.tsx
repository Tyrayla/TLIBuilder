import React, { useEffect, useRef, useState } from 'react'
import {
  api, TalentSnapshot, TalentStat, TalentDiff, DiffStatus, DiffNamedTalent,
  SnapshotStatus, RebuildFilterResult, UnresolvedStat,
} from '../api/client'

type Tab = 'parser' | 'diff' | 'snapshot'

interface Props { onBack: () => void }

// ── Shared primitives ──────────────────────────────────────────────────────

const STATUS_COLOR: Record<DiffStatus, string> = {
  added:     '#4caf50',
  removed:   '#ef5350',
  changed:   '#ff9800',
  unchanged: '#555',
}

function StatLine({ stat }: { stat: TalentStat }) {
  return (
    <span>
      {stat.text}
      {stat.max_divinity_effect && (
        <span style={{
          marginLeft: 6, fontSize: 10, color: '#ff9800',
          background: '#2a1a00', padding: '1px 5px', borderRadius: 3,
          border: '1px solid #5a3a00', verticalAlign: 'middle',
        }}>
          MAX DIV
        </span>
      )}
    </span>
  )
}

// ── Snapshot slot (used in Diff tab) ──────────────────────────────────────

function SnapshotSlot({
  label, snapshot, onLoad, onClear,
}: {
  label: string
  snapshot: TalentSnapshot | null
  onLoad: (s: TalentSnapshot) => void
  onClear: () => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true); setErr('')
    try {
      const ext = file.name.split('.').pop()?.toLowerCase()
      if (ext === 'json') {
        onLoad(JSON.parse(await file.text()))
      } else {
        onLoad(await api.parseTalentDoc(file))
      }
    } catch (ex) { setErr(String(ex)) }
    finally {
      setLoading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const nodeCount = snapshot
    ? Object.values(snapshot.trees).reduce((s, t) => s + t.nodes.length, 0)
    : 0
  const ctCount = snapshot
    ? Object.values(snapshot.trees).reduce((s, t) => s + t.core_talents.length, 0)
    : 0

  return (
    <div style={{ flex: 1, background: '#12122a', borderRadius: 8, padding: 16, border: '1px solid #2a2a4a' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ color: '#aaa', fontSize: 13, fontWeight: 600 }}>{label}</span>
        {snapshot && <button className="btn btn-sm btn-danger" onClick={onClear}>Clear</button>}
      </div>
      {snapshot ? (
        <div>
          <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>
            {snapshot.source_file} · {snapshot.generated_at}
          </div>
          <div style={{ fontSize: 13, color: '#ccc' }}>
            {Object.keys(snapshot.trees).length} trees ·{' '}
            {nodeCount} nodes · {ctCount} core talents ·{' '}
            {snapshot.new_god_talents.length} New God
          </div>
          <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => {
            const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' })
            const a = document.createElement('a')
            a.href = URL.createObjectURL(blob)
            a.download = `snapshot_${snapshot.source_file.replace(/\.[^.]+$/, '')}.json`
            a.click()
          }}>Download JSON</button>
        </div>
      ) : (
        <div>
          <div style={{ color: '#555', fontSize: 12, marginBottom: 10 }}>No snapshot loaded</div>
          <label className="btn btn-sm btn-primary" style={{ cursor: 'pointer' }}>
            {loading ? 'Parsing…' : 'Upload PDF / DOCX / JSON'}
            <input ref={inputRef} type="file" accept=".pdf,.docx,.doc,.json"
              style={{ display: 'none' }} onChange={handleFile} disabled={loading} />
          </label>
          {err && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 8 }}>{err}</div>}
        </div>
      )}
    </div>
  )
}

// ── Diff display ───────────────────────────────────────────────────────────

function StatsDiff({ statsA, statsB, status }: {
  statsA: TalentStat[] | null
  statsB: TalentStat[] | null
  status: DiffStatus
}) {
  if (status === 'changed') {
    return (
      <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 10, color: '#666', marginBottom: 2 }}>BEFORE</div>
          {(statsA ?? []).map((s, i) => (
            <div key={i} style={{ fontSize: 12, color: '#ef9a9a' }}><StatLine stat={s} /></div>
          ))}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 10, color: '#666', marginBottom: 2 }}>AFTER</div>
          {(statsB ?? []).map((s, i) => (
            <div key={i} style={{ fontSize: 12, color: '#a5d6a7' }}><StatLine stat={s} /></div>
          ))}
        </div>
      </div>
    )
  }
  const stats = (status === 'removed' ? statsA : statsB) ?? []
  const color = status === 'added' ? '#a5d6a7' : status === 'removed' ? '#ef9a9a' : '#aaa'
  return (
    <div style={{ marginTop: 4 }}>
      {stats.map((s, i) => <div key={i} style={{ fontSize: 12, color }}><StatLine stat={s} /></div>)}
    </div>
  )
}

function NamedTalentDiff({ talent, kind }: { talent: DiffNamedTalent; kind: 'Core' | 'New God' }) {
  if (talent.status === 'unchanged') return null
  return (
    <div style={{
      marginBottom: 6, padding: '6px 10px', background: '#12122a', borderRadius: 4,
      borderLeft: `3px solid ${STATUS_COLOR[talent.status]}`,
    }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <span style={{ fontSize: 10, color: STATUS_COLOR[talent.status], fontWeight: 700 }}>
          {talent.status.toUpperCase()}
        </span>
        <span style={{ fontSize: 11, color: '#666' }}>{kind}</span>
        <span style={{ fontSize: 13, color: '#ddd' }}>{talent.name}</span>
      </div>
      <StatsDiff statsA={talent.stats_a} statsB={talent.stats_b} status={talent.status} />
    </div>
  )
}

function DiffView({ diff }: { diff: TalentDiff }) {
  const [openTrees, setOpenTrees] = useState<Record<string, boolean>>({})
  const [showUnchanged, setShowUnchanged] = useState(false)

  const toggle = (name: string) => setOpenTrees(s => ({ ...s, [name]: !s[name] }))
  const { summary } = diff

  const statRows = [
    { label: 'Trees added',          val: summary.trees_added,            color: '#4caf50' },
    { label: 'Trees removed',        val: summary.trees_removed,          color: '#ef5350' },
    { label: 'Nodes added',          val: summary.nodes_added,            color: '#4caf50' },
    { label: 'Nodes removed',        val: summary.nodes_removed,          color: '#ef5350' },
    { label: 'Nodes changed',        val: summary.nodes_changed,          color: '#ff9800' },
    { label: 'Core added',           val: summary.core_talents_added,     color: '#4caf50' },
    { label: 'Core removed',         val: summary.core_talents_removed,   color: '#ef5350' },
    { label: 'Core changed',         val: summary.core_talents_changed,   color: '#ff9800' },
    { label: 'New God added',        val: summary.new_god_added,          color: '#4caf50' },
    { label: 'New God removed',      val: summary.new_god_removed,        color: '#ef5350' },
    { label: 'New God changed',      val: summary.new_god_changed,        color: '#ff9800' },
  ]

  const hasChanges = statRows.some(r => r.val > 0)

  // New God section
  const newGodChanges = diff.new_god_talents.filter(t => t.status !== 'unchanged')

  return (
    <div style={{ marginTop: 16 }}>
      {/* Summary bar */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 14, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        {statRows.map(({ label, val, color }) => (
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

      {!hasChanges && (
        <div style={{ color: '#4caf50', fontSize: 14, padding: '12px 0' }}>
          No differences found — snapshots are identical.
        </div>
      )}

      {/* New God section */}
      {(newGodChanges.length > 0 || showUnchanged) && (
        <div style={{ marginBottom: 8, border: '1px solid #2a2a4a', borderRadius: 6, overflow: 'hidden' }}>
          <button
            onClick={() => toggle('__new_god__')}
            style={{ width: '100%', textAlign: 'left', background: '#1a1a3a', border: 'none', padding: '8px 12px', cursor: 'pointer', display: 'flex', gap: 10, alignItems: 'center' }}
          >
            <span style={{ color: '#e0a030', fontSize: 12, fontWeight: 700 }}>NEW GOD</span>
            <span style={{ color: '#ccc', fontSize: 13 }}>Slate Talents</span>
            <span style={{ marginLeft: 'auto', color: '#555', fontSize: 12 }}>
              {newGodChanges.length} changes · {openTrees['__new_god__'] ? '▲' : '▼'}
            </span>
          </button>
          {openTrees['__new_god__'] && (
            <div style={{ padding: '8px 12px', background: '#0e0e28' }}>
              {diff.new_god_talents
                .filter(t => showUnchanged || t.status !== 'unchanged')
                .map(t => <NamedTalentDiff key={t.name} talent={t} kind="New God" />)}
            </div>
          )}
        </div>
      )}

      {/* Per-tree sections */}
      {Object.entries(diff.trees)
        .filter(([, t]) => showUnchanged || t.status !== 'unchanged')
        .map(([treeName, tree]) => {
          const open = openTrees[treeName] ?? tree.status !== 'unchanged'
          const changedCount =
            tree.nodes.filter(n => n.status !== 'unchanged').length +
            tree.core_talents.filter(ct => ct.status !== 'unchanged').length
          return (
            <div key={treeName} style={{ marginBottom: 6, border: '1px solid #2a2a4a', borderRadius: 6, overflow: 'hidden' }}>
              <button
                onClick={() => toggle(treeName)}
                style={{ width: '100%', textAlign: 'left', background: '#1a1a3a', border: 'none', padding: '8px 12px', cursor: 'pointer', display: 'flex', gap: 10, alignItems: 'center' }}
              >
                <span style={{ color: STATUS_COLOR[tree.status], fontSize: 11, fontWeight: 700, minWidth: 60 }}>
                  {tree.status.toUpperCase()}
                </span>
                <span style={{ color: '#ccc', fontSize: 13 }}>{treeName}</span>
                <span style={{ marginLeft: 'auto', color: '#555', fontSize: 12 }}>
                  {changedCount} changes · {open ? '▲' : '▼'}
                </span>
              </button>
              {open && (
                <div style={{ padding: '8px 12px', background: '#0e0e28' }}>
                  {/* Regular nodes */}
                  {tree.nodes
                    .filter(n => showUnchanged || n.status !== 'unchanged')
                    .map(node => (
                      <div key={node.index} style={{
                        marginBottom: 6, padding: '6px 10px', background: '#12122a', borderRadius: 4,
                        borderLeft: `3px solid ${STATUS_COLOR[node.status]}`,
                      }}>
                        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                          <span style={{ fontSize: 10, color: STATUS_COLOR[node.status], fontWeight: 700 }}>
                            {node.status.toUpperCase()}
                          </span>
                          <span style={{ fontSize: 11, color: '#888' }}>{node.node_type} #{node.index}</span>
                        </div>
                        <StatsDiff statsA={node.stats_a} statsB={node.stats_b} status={node.status} />
                      </div>
                    ))}
                  {/* Core talents */}
                  {tree.core_talents
                    .filter(ct => showUnchanged || ct.status !== 'unchanged')
                    .map(ct => <NamedTalentDiff key={ct.name} talent={ct} kind="Core" />)}
                </div>
              )}
            </div>
          )
        })}
    </div>
  )
}

// ── Parser tab ─────────────────────────────────────────────────────────────

type ParserView = 'nodes' | 'core' | 'newgod'

function ParserTab() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [snapshot, setSnapshot] = useState<TalentSnapshot | null>(null)
  const [selectedTree, setSelectedTree] = useState<string | null>(null)
  const [view, setView] = useState<ParserView>('nodes')

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true); setErr(''); setSnapshot(null)
    try {
      setSnapshot(await api.parseTalentDoc(file))
      setSelectedTree(null)
      setView('nodes')
    } catch (ex) { setErr(String(ex)) }
    finally {
      setLoading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const treeNames = snapshot ? Object.keys(snapshot.trees).sort() : []
  const displayTree = selectedTree ?? treeNames[0] ?? null
  const treeData = (snapshot && displayTree) ? snapshot.trees[displayTree] : null
  const nodeCount = snapshot ? Object.values(snapshot.trees).reduce((s, t) => s + t.nodes.length, 0) : 0
  const ctCount = snapshot ? Object.values(snapshot.trees).reduce((s, t) => s + t.core_talents.length, 0) : 0

  return (
    <div>
      <p style={{ color: '#888', fontSize: 13, marginBottom: 14 }}>
        Upload a PDF or DOCX file. Nodes, core talents, and New God talents are extracted separately.
      </p>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16 }}>
        <label className="btn btn-primary" style={{ cursor: 'pointer' }}>
          {loading ? 'Parsing…' : 'Upload PDF / DOCX'}
          <input ref={inputRef} type="file" accept=".pdf,.docx,.doc"
            style={{ display: 'none' }} onChange={handleFile} disabled={loading} />
        </label>
        {snapshot && (
          <button className="btn btn-sm" onClick={() => {
            const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' })
            const a = document.createElement('a')
            a.href = URL.createObjectURL(blob)
            a.download = `snapshot_${snapshot.source_file.replace(/\.[^.]+$/, '')}.json`
            a.click()
          }}>Download Snapshot JSON</button>
        )}
      </div>

      {err && <div style={{ color: '#ff6b6b', fontSize: 13, marginBottom: 12 }}>{err}</div>}

      {snapshot && (
        <div>
          <div style={{ fontSize: 12, color: '#666', marginBottom: 12 }}>
            <strong style={{ color: '#aaa' }}>{snapshot.source_file}</strong> · {snapshot.generated_at}
            {' · '}<strong style={{ color: '#aaa' }}>{treeNames.length}</strong> trees ·{' '}
            <strong style={{ color: '#aaa' }}>{nodeCount}</strong> nodes ·{' '}
            <strong style={{ color: '#aaa' }}>{ctCount}</strong> core talents ·{' '}
            <strong style={{ color: '#e0a030' }}>{snapshot.new_god_talents.length}</strong> New God
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            {/* Left: tree list + New God entry */}
            <div style={{ width: 200, flexShrink: 0 }}>
              {/* New God pseudo-tree */}
              <button
                onClick={() => { setSelectedTree(null); setView('newgod') }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '5px 8px', marginBottom: 4, borderRadius: 4, border: 'none',
                  background: view === 'newgod' ? '#3a2a00' : '#1a1a3a',
                  color: view === 'newgod' ? '#e0a030' : '#888',
                  cursor: 'pointer', fontSize: 12,
                }}
              >
                New God Talents
                <span style={{ float: 'right', color: '#666' }}>{snapshot.new_god_talents.length}</span>
              </button>
              {/* Tree list */}
              {treeNames.map(name => {
                const active = name === displayTree && view !== 'newgod'
                const tData = snapshot.trees[name]
                const hasCT = tData.core_talents.length > 0
                return (
                  <div key={name} style={{ marginBottom: 2 }}>
                    <button
                      onClick={() => { setSelectedTree(name); setView('nodes') }}
                      style={{
                        display: 'block', width: '100%', textAlign: 'left',
                        padding: '5px 8px', borderRadius: hasCT ? '4px 4px 0 0' : 4, border: 'none',
                        background: active && view === 'nodes' ? '#533483' : '#1a1a3a',
                        color: active && view === 'nodes' ? '#fff' : '#aaa',
                        cursor: 'pointer', fontSize: 12,
                      }}
                    >
                      {name}
                      <span style={{ float: 'right', color: '#666' }}>{tData.nodes.length}</span>
                    </button>
                    {hasCT && (
                      <button
                        onClick={() => { setSelectedTree(name); setView('core') }}
                        style={{
                          display: 'block', width: '100%', textAlign: 'left',
                          padding: '3px 8px 3px 16px', borderRadius: '0 0 4px 4px', border: 'none',
                          borderTop: '1px solid #0e0e28',
                          background: active && view === 'core' ? '#2a1a5a' : '#141430',
                          color: active && view === 'core' ? '#c0a0ff' : '#666',
                          cursor: 'pointer', fontSize: 11,
                        }}
                      >
                        Core Talents
                        <span style={{ float: 'right', color: '#555' }}>{tData.core_talents.length}</span>
                      </button>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Right: content panel */}
            <div style={{ flex: 1, maxHeight: 440, overflowY: 'auto' }}>
              {view === 'newgod' && (
                snapshot.new_god_talents.length === 0 ? (
                  <div style={{ color: '#555', fontSize: 13 }}>No New God talents parsed.</div>
                ) : (
                  snapshot.new_god_talents.map((ng, i) => (
                    <div key={i} style={{
                      marginBottom: 6, padding: '8px 10px', background: '#1a1a3a', borderRadius: 4,
                      borderLeft: '3px solid #e0a030',
                    }}>
                      <div style={{ fontSize: 12, color: '#e0a030', fontWeight: 600, marginBottom: 4 }}>
                        {ng.name}
                      </div>
                      {ng.stats.map((s, j) => (
                        <div key={j} style={{ fontSize: 12, color: '#ccc' }}><StatLine stat={s} /></div>
                      ))}
                    </div>
                  ))
                )
              )}

              {view === 'nodes' && treeData && (
                treeData.nodes.length === 0 ? (
                  <div style={{ color: '#555', fontSize: 13 }}>No regular nodes found.</div>
                ) : (
                  treeData.nodes.map((node, i) => (
                    <div key={i} style={{
                      marginBottom: 6, padding: '8px 10px', background: '#1a1a3a', borderRadius: 4,
                      borderLeft: '3px solid #3a5a9a',
                    }}>
                      <div style={{ fontSize: 11, color: '#888', marginBottom: 4 }}>
                        #{i} — {node.node_type}
                      </div>
                      {node.stats.map((s, j) => (
                        <div key={j} style={{ fontSize: 13, color: '#ccc' }}><StatLine stat={s} /></div>
                      ))}
                    </div>
                  ))
                )
              )}

              {view === 'core' && treeData && (
                treeData.core_talents.length === 0 ? (
                  <div style={{ color: '#555', fontSize: 13 }}>No core talents found.</div>
                ) : (
                  treeData.core_talents.map((ct, i) => (
                    <div key={i} style={{
                      marginBottom: 6, padding: '8px 10px', background: '#1a1a3a', borderRadius: 4,
                      borderLeft: '3px solid #c0a0ff',
                    }}>
                      <div style={{ fontSize: 12, color: '#c0a0ff', fontWeight: 600, marginBottom: 4 }}>
                        {ct.name}
                      </div>
                      {ct.stats.map((s, j) => (
                        <div key={j} style={{ fontSize: 12, color: '#ccc' }}><StatLine stat={s} /></div>
                      ))}
                    </div>
                  ))
                )
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Diff tab ───────────────────────────────────────────────────────────────

function DiffTab() {
  const [snapA, setSnapA] = useState<TalentSnapshot | null>(null)
  const [snapB, setSnapB] = useState<TalentSnapshot | null>(null)
  const [diff, setDiff] = useState<TalentDiff | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  const runDiff = async () => {
    if (!snapA || !snapB) return
    setLoading(true); setErr('')
    try { setDiff(await api.diffSnapshots(snapA, snapB)) }
    catch (ex) { setErr(String(ex)) }
    finally { setLoading(false) }
  }

  return (
    <div>
      <p style={{ color: '#888', fontSize: 13, marginBottom: 14 }}>
        Load two snapshots then run the diff to see what changed between game versions.
        Core talents are matched by name; regular nodes by position.
      </p>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        <SnapshotSlot label="Snapshot A  (old)" snapshot={snapA}
          onLoad={setSnapA} onClear={() => { setSnapA(null); setDiff(null) }} />
        <SnapshotSlot label="Snapshot B  (new)" snapshot={snapB}
          onLoad={setSnapB} onClear={() => { setSnapB(null); setDiff(null) }} />
      </div>
      <button className="btn btn-primary" onClick={runDiff} disabled={!snapA || !snapB || loading}>
        {loading ? 'Comparing…' : 'Run Diff'}
      </button>
      {err && <div style={{ color: '#ff6b6b', fontSize: 13, marginTop: 10 }}>{err}</div>}
      {diff && <DiffView diff={diff} />}
    </div>
  )
}

// ── Snapshot tab ───────────────────────────────────────────────────────────

const NT_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  micro:            { label: 'Micro',       color: '#90caf9', bg: '#0a1929' },
  medium:           { label: 'Medium',      color: '#ce93d8', bg: '#1a0a29' },
  legendary_medium: { label: 'Legendary',   color: '#ffd54f', bg: '#1a1500' },
}

function SnapshotTab() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [status, setStatus] = useState<SnapshotStatus | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadErr, setUploadErr] = useState('')
  const [rebuilding, setRebuilding] = useState(false)
  const [rebuildResult, setRebuildResult] = useState<RebuildFilterResult | null>(null)
  const [rebuildErr, setRebuildErr] = useState('')
  const [unresolvedOpen, setUnresolvedOpen] = useState(false)

  useEffect(() => {
    api.getSnapshotStatus().then(setStatus).catch(() => {})
  }, [])

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true); setUploadErr('')
    try {
      const snapshot = JSON.parse(await file.text())
      const res = await api.saveCanonicalSnapshot(snapshot)
      setStatus({ exists: true, source_file: res.source_file, generated_at: res.generated_at })
      setRebuildResult(null)
    } catch (ex) { setUploadErr(String(ex)) }
    finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const handleRebuild = async () => {
    setRebuilding(true); setRebuildErr('')
    try {
      setRebuildResult(await api.rebuildNodeTypeFilter())
    } catch (ex) { setRebuildErr(String(ex)) }
    finally { setRebuilding(false) }
  }

  return (
    <div>
      <p style={{ color: '#888', fontSize: 13, marginBottom: 14 }}>
        Upload a talent document as the canonical snapshot, then rebuild the node-type filter to power
        stat filtering and Quick Add in the stat editor.
      </p>

      {/* Snapshot status */}
      <div style={{ background: '#12122a', border: '1px solid #2a2a4a', borderRadius: 8, padding: 16, marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: '#666', fontWeight: 700, marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>
          Canonical Snapshot
        </div>
        {status?.exists ? (
          <div style={{ fontSize: 13, color: '#ccc', marginBottom: 12 }}>
            <span style={{ color: '#aaa', fontWeight: 600 }}>{status.source_file}</span>
            {' '}&middot;{' '}
            <span style={{ color: '#666' }}>{status.generated_at}</span>
          </div>
        ) : (
          <div style={{ fontSize: 13, color: '#555', marginBottom: 12 }}>No canonical snapshot saved yet.</div>
        )}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <label className="btn btn-primary" style={{ cursor: 'pointer' }}>
            {uploading ? 'Saving…' : 'Upload Snapshot JSON'}
            <input ref={inputRef} type="file" accept=".json"
              style={{ display: 'none' }} onChange={handleFile} disabled={uploading} />
          </label>
          <button
            className="btn btn-sm"
            onClick={handleRebuild}
            disabled={!status?.exists || rebuilding}
          >
            {rebuilding ? 'Rebuilding…' : 'Rebuild Node-Type Filter'}
          </button>
          <button
            className="btn btn-sm btn-danger"
            onClick={async () => {
              await api.clearSnapshot()
              await api.clearNodeTypeFilter()
              setStatus({ exists: false, source_file: null, generated_at: null })
              setRebuildResult(null)
            }}
            disabled={!status?.exists}
          >
            Clear All
          </button>
        </div>
        {uploadErr && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 8 }}>{uploadErr}</div>}
        {rebuildErr && <div style={{ color: '#ff6b6b', fontSize: 12, marginTop: 8 }}>{rebuildErr}</div>}
      </div>

      {/* Rebuild result */}
      {rebuildResult && (
        <div>
          {/* Meta summary badges */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
            {[
              { label: 'Matched',   val: rebuildResult._meta.matched,   color: '#4caf50' },
              { label: 'Ambiguous', val: rebuildResult._meta.ambiguous,  color: '#ff9800' },
              { label: 'Unmatched', val: rebuildResult._meta.unmatched,  color: '#ef5350' },
            ].map(({ label, val, color }) => (
              <div key={label} style={{ textAlign: 'center', background: '#12122a', borderRadius: 6, padding: '8px 14px', border: '1px solid #2a2a4a' }}>
                <div style={{ fontSize: 22, fontWeight: 700, color }}>{val}</div>
                <div style={{ fontSize: 10, color: '#555', marginTop: 2 }}>{label}</div>
              </div>
            ))}
            <div style={{ fontSize: 11, color: '#555', alignSelf: 'center', marginLeft: 4 }}>
              {rebuildResult._meta.snapshot_source} · {rebuildResult._meta.generated_at}
            </div>
          </div>

          {/* Filter preview */}
          {Object.keys(rebuildResult.stats).length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
                Filter Preview — {Object.keys(rebuildResult.stats).length} stats mapped
              </div>
              <div style={{ maxHeight: 260, overflowY: 'auto', background: '#12122a', borderRadius: 6, border: '1px solid #2a2a4a', padding: '4px 0' }}>
                {Object.entries(rebuildResult.stats).map(([stat, types]) => (
                  <div key={stat} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 12px', borderBottom: '1px solid #1a1a2e' }}>
                    <span style={{ fontSize: 12, color: '#aaa', flex: 1 }}>{stat}</span>
                    <div style={{ display: 'flex', gap: 4 }}>
                      {(types as string[]).map(nt => {
                        const b = NT_BADGE[nt] ?? { label: nt, color: '#aaa', bg: '#1a1a3a' }
                        return (
                          <span key={nt} style={{
                            fontSize: 10, color: b.color, background: b.bg,
                            padding: '1px 6px', borderRadius: 3, border: `1px solid ${b.color}33`,
                          }}>{b.label}</span>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Unresolved stats */}
          {rebuildResult.unresolved.length > 0 && (
            <div>
              <button
                onClick={() => setUnresolvedOpen(o => !o)}
                style={{
                  width: '100%', textAlign: 'left', background: '#1a0a00', border: '1px solid #5a2a00',
                  borderRadius: 6, padding: '8px 12px', cursor: 'pointer', display: 'flex', gap: 10, alignItems: 'center',
                  marginBottom: unresolvedOpen ? 0 : 0, borderBottomLeftRadius: unresolvedOpen ? 0 : 6, borderBottomRightRadius: unresolvedOpen ? 0 : 6,
                }}
              >
                <span style={{ fontSize: 11, fontWeight: 700, color: '#ef5350' }}>UNRESOLVED</span>
                <span style={{ fontSize: 13, color: '#ccc' }}>
                  {rebuildResult.unresolved.length} stat text{rebuildResult.unresolved.length !== 1 ? 's' : ''} need attention
                </span>
                <span style={{ marginLeft: 'auto', color: '#666', fontSize: 12 }}>{unresolvedOpen ? '▲' : '▼'}</span>
              </button>
              {unresolvedOpen && (
                <div style={{ background: '#120800', border: '1px solid #5a2a00', borderTop: 'none', borderRadius: '0 0 6px 6px', maxHeight: 300, overflowY: 'auto', padding: '4px 0' }}>
                  {(rebuildResult.unresolved as UnresolvedStat[]).map((u, i) => {
                    const b = NT_BADGE[u.node_type] ?? { label: u.node_type, color: '#aaa', bg: '#1a1a3a' }
                    return (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 12px', borderBottom: '1px solid #1a0800' }}>
                        <span style={{ fontSize: 12, color: '#ccc', flex: 1 }}>{u.text}</span>
                        <span style={{ fontSize: 10, color: '#888' }}>{u.tree}</span>
                        <span style={{
                          fontSize: 10, color: b.color, background: b.bg,
                          padding: '1px 6px', borderRadius: 3,
                        }}>{b.label}</span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main screen ────────────────────────────────────────────────────────────

export default function DevToolsScreen({ onBack }: Props) {
  const [tab, setTab] = useState<Tab>('parser')

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
      </div>

      <div style={{
        display: 'flex', gap: 4, padding: '10px 20px 0',
        background: '#0e0e28', borderBottom: '1px solid #2a2a4a', flexShrink: 0,
      }}>
        {([
          { id: 'parser',   label: 'Talent Doc Parser' },
          { id: 'diff',     label: 'Snapshot Diff' },
          { id: 'snapshot', label: 'Canonical Snapshot' },
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
        {tab === 'parser'   && <ParserTab />}
        {tab === 'diff'     && <DiffTab />}
        {tab === 'snapshot' && <SnapshotTab />}
      </div>
    </div>
  )
}
