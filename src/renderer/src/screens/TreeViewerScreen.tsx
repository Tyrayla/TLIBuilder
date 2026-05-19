import React, { useEffect, useRef, useState, useCallback } from 'react'
import { api, getApiBase, TreeData, TreeNode, NodeModifierEntry, TreeSlot } from '../api/client'
import SlotSidebar from '../components/SlotSidebar'

const COLS = 7
const ROWS = 5
const COL_LABELS = [0, 3, 6, 9, 12, 15, 18]
const VW = 700
const VH = 500
const HEADER = 42
const CELL_W = VW / COLS
const CELL_H = (VH - HEADER) / ROWS
const NODE_R = 28

function nodeX(col: number) { return col * CELL_W + CELL_W / 2 }
function nodeY(row: number) { return HEADER + row * CELL_H + CELL_H / 2 }
function colUnlocked(col: number, total: number) { return col === 0 || total >= col * 3 }
function sumPoints(states: Record<string, number>) {
  return Object.values(states).reduce((a, b) => a + b, 0)
}

const NODE_TYPES = ['Micro Talent', 'Medium Talent', 'Legendary Medium Talent'] as const
type NodeTypeStr = typeof NODE_TYPES[number]

const NODE_TYPE_CANONICAL: Record<NodeTypeStr, string> = {
  'Micro Talent': 'micro',
  'Medium Talent': 'medium',
  'Legendary Medium Talent': 'legendary_medium',
}


function nextType(t: NodeTypeStr): NodeTypeStr {
  const i = NODE_TYPES.indexOf(t)
  return NODE_TYPES[(i + 1) % NODE_TYPES.length]
}
function maxPointsFor(t: NodeTypeStr) { return t === 'Legendary Medium Talent' ? 1 : 3 }

function nodeColors(node: TreeNode, states: Record<string, number>, total: number) {
  const pts = states[node.id] ?? 0
  const locked = !colUnlocked(node.column, total)
  const full = pts >= node.max_points
  return {
    fill:   locked ? '#222233' : full ? '#533483' : '#0f3460',
    stroke: locked ? '#333344' : full ? '#e94560' : '#3a5a9a',
    text:   locked ? '#444455' : full ? '#ffffff'  : '#e0e0e0',
  }
}

function parseRank1(text: string): number {
  const m = text.match(/[+-]?\d+(?:\.\d+)?/)
  if (!m) return 0
  const raw = parseFloat(m[0])
  return text.includes('%') ? raw / 100 : raw
}

function deriveValues(rank1: number, maxPoints: number): number[] {
  if (maxPoints === 1) return [Math.round(rank1 * 1e6) / 1e6]
  return Array.from({ length: maxPoints }, (_, i) => Math.round(rank1 * (i + 1) * 1e6) / 1e6)
}

function scaleEffect(text: string, pts: number): string {
  const rank = Math.max(pts, 1)
  if (rank === 1) return text
  return text.replace(/(\d+(?:\.\d+)?)/, (_, num) => {
    const scaled = parseFloat(num) * rank
    return scaled % 1 === 0 ? String(scaled) : scaled.toFixed(2)
  })
}

interface Tip { nodeId: string; x: number; y: number }
type DebugTool = 'create' | 'type' | 'link' | 'stat'

interface StatModal {
  nodeId: string
  nodeType: NodeTypeStr
  maxPoints: number
}

interface Props {
  treeName: string
  treeColor: string
  treeColors: Record<string, string>
  initialNodeStates: Record<string, number>
  slots: (TreeSlot | null)[]
  activeSlot: number
  onBack: () => void
  onSlotClick: (slotIndex: number) => void
  onNodeStatesChange: (s: Record<string, number>) => void
  onReselect: () => void
  onSlotReorder?: (fromSlot: number, toSlot: number) => void
  onPreview?: () => void
  previewMode?: boolean
  devMode?: boolean
  deprecatedTools?: boolean
}

export default function TreeViewerScreen({
  treeName, treeColor, treeColors, initialNodeStates, slots, activeSlot,
  onBack, onSlotClick, onNodeStatesChange, onReselect, onSlotReorder, onPreview,
  previewMode = false, devMode = false, deprecatedTools = false,
}: Props) {
  const [treeData, setTreeData] = useState<TreeData | null>(null)
  const [loadError, setLoadError] = useState('')
  const [nodeStates, setNodeStates] = useState<Record<string, number>>(initialNodeStates)
  const [tip, setTip] = useState<Tip | null>(null)
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null)
  const [processing, setProcessing] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debug state
  const [debugMode, setDebugMode] = useState(false)
  const [debugTool, setDebugTool] = useState<DebugTool>('create')
  const [linkFrom, setLinkFrom] = useState<string | null>(null)
  const [statModal, setStatModal] = useState<StatModal | null>(null)
  const [nodeModifiers, setNodeModifiers] = useState<NodeModifierEntry[]>([])
  const [snapshotMods, setSnapshotMods] = useState<string[]>([])
  const [loadingMods, setLoadingMods] = useState(false)
  const [savingMods, setSavingMods] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<{ nodeId: string } | null>(null)
  const [modSearch, setModSearch] = useState('')

  const loadTree = useCallback(() => {
    setTreeData(null)
    setLoadError('')
    api.getTree(treeName)
      .then(data => setTreeData(data))
      .catch(e => setLoadError(String(e)))
  }, [treeName])

  useEffect(() => {
    setNodeStates(initialNodeStates)
    loadTree()
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [treeName])

  useEffect(() => {
    if (!deprecatedTools) { setDebugMode(false); setLinkFrom(null) }
  }, [deprecatedTools])


  const total = sumPoints(nodeStates)

  const flash = (msg: string, ok = false) => {
    setStatus({ msg, ok })
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setStatus(null), 3000)
  }

  // ── Normal allocation ──────────────────────────────────────────────────────

  const handleClick = async (nodeId: string, action: 'allocate' | 'deallocate') => {
    if (processing) return
    setProcessing(true)
    try {
      const res = await api.validateAllocate(treeName, nodeStates, nodeId, action)
      if (res.allowed) {
        setNodeStates(res.node_states)
        onNodeStatesChange(res.node_states)
      } else {
        flash(
          action === 'allocate'
            ? 'Cannot allocate — check column unlock & prerequisites.'
            : 'Cannot remove — would break a prerequisite.'
        )
      }
    } catch {
      flash('Request failed — is the backend running?')
    } finally {
      setProcessing(false)
    }
  }

  // ── Debug handlers ─────────────────────────────────────────────────────────

  const handleCreateOnEmpty = async (col: number, row: number) => {
    if (!treeData) return
    const id = `${treeData.node_prefix}c${col}_r${row}`
    try {
      await api.upsertNode(treeName, { id, column: col, row, node_type: 'Micro Talent', max_points: 3 })
      flash(`Created ${id}`, true)
      loadTree()
    } catch (e) { flash(String(e)) }
  }

  const handleDeleteNode = async (nodeId: string) => {
    setConfirmDelete(null)
    try {
      await api.removeNode(treeName, nodeId)
      flash(`Deleted ${nodeId}`, true)
      loadTree()
    } catch (e) { flash(String(e)) }
  }

  const handleTypeNode = async (node: TreeNode) => {
    const newType = nextType(node.node_type as NodeTypeStr)
    const newMax = maxPointsFor(newType)
    try {
      await api.upsertNode(treeName, {
        id: node.id, column: node.column, row: node.row,
        node_type: newType, max_points: newMax,
      })
      flash(`${node.id} → ${newType}`, true)
      loadTree()
    } catch (e) { flash(String(e)) }
  }

  const handleLinkNode = async (nodeId: string) => {
    if (!treeData) return
    if (linkFrom === null) {
      setLinkFrom(nodeId)
      flash(`Link from: ${nodeId} — click destination`)
    } else if (linkFrom === nodeId) {
      setLinkFrom(null)
      flash('Link cancelled')
    } else {
      const a = treeData.nodes.find(n => n.id === linkFrom)
      const b = treeData.nodes.find(n => n.id === nodeId)
      setLinkFrom(null)
      // Always send lower-column as "from"
      const [src, dst] = a && b && a.column > b.column
        ? [nodeId, linkFrom]
        : [linkFrom, nodeId]
      try {
        await api.toggleConnection(treeName, src, dst)
        flash(`Connection toggled: ${src} → ${dst}`, true)
        loadTree()
      } catch (e) { flash(String(e)) }
    }
  }

  const openStatModal = (node: TreeNode) => {
    const nt = node.node_type as NodeTypeStr
    setStatModal({ nodeId: node.id, nodeType: nt, maxPoints: node.max_points })
    setNodeModifiers([])
    setSnapshotMods([])
    setModSearch('')
    setLoadingMods(true)
    const canonical = NODE_TYPE_CANONICAL[nt]
    Promise.all([
      api.getNodeModifiers(treeName, node.id),
      api.getSnapshotModifiers(treeName, canonical),
    ]).then(([mods, snap]) => {
      setNodeModifiers(mods)
      setSnapshotMods(snap.map(s => s.text))
    }).catch(() => {}).finally(() => setLoadingMods(false))
  }

  const handleAddModifier = (text: string, maxPoints: number) => {
    const rank1 = parseRank1(text)
    const values = deriveValues(rank1, maxPoints)
    setNodeModifiers(prev => [...prev.filter(m => m.text !== text), { text, values }])
  }

  const handleSaveModifiers = async () => {
    if (!statModal) return
    setSavingMods(true)
    try {
      await api.postNodeModifiers(treeName, statModal.nodeId, nodeModifiers)
      flash('Modifiers saved!', true)
      setStatModal(null)
    } catch (e) { flash(String(e)) }
    finally { setSavingMods(false) }
  }

  const filteredSnapshotMods = modSearch.trim()
    ? snapshotMods.filter(t => t.toLowerCase().includes(modSearch.toLowerCase()))
    : snapshotMods

  const handleNodeInteract = (node: TreeNode, isRight: boolean) => {
    if (!debugMode) {
      handleClick(node.id, isRight ? 'deallocate' : 'allocate')
      return
    }
    switch (debugTool) {
      case 'create': setConfirmDelete({ nodeId: node.id }); break
      case 'type':   handleTypeNode(node); break
      case 'link':   handleLinkNode(node.id); break
      case 'stat':   openStatModal(node); break
    }
  }

  const handleReset = () => {
    const cleared = Object.fromEntries(Object.keys(nodeStates).map(k => [k, 0]))
    setNodeStates(cleared)
    onNodeStatesChange(cleared)
    flash('All points reset.', true)
  }

  // ── Header ─────────────────────────────────────────────────────────────────

  const header = previewMode ? (
    <div className="viewer-header preview-viewer-header">
      <div className="viewer-header-left">
        <button className="btn-back" onClick={onBack}>← Back to Preview</button>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
        <div className="preview-header-badge" style={{ fontSize: 10, padding: '2px 10px' }}>◈ PREVIEW MODE</div>
        <span className="viewer-tree-name" style={{ color: treeColor, fontSize: 20 }}>{treeName}</span>
      </div>
      <div className="viewer-header-right">
        <span style={{ fontSize: 11, color: '#555577', fontStyle: 'italic' }}>explore freely — nothing saved</span>
        <span className="viewer-points">Points: {total}</span>
      </div>
    </div>
  ) : (
    <div className="viewer-header">
      <div className="viewer-header-left">
        <button className="btn-back" onClick={onBack}>← Back</button>
        <span className="viewer-tree-name" style={{ color: treeColor }}>{treeName}</span>
      </div>
      {treeData && (
        <>
          <div className="viewer-header-center">
            <button
              className="btn btn-sm"
              style={{ background: '#3a1a1a', color: '#ff6b6b' }}
              onClick={handleReset}
            >Reset</button>
            <button
              className="btn btn-sm"
              style={{ background: '#1a1a3a', color: '#8888ff' }}
              onClick={onReselect}
              title="Clear this tree and pick a different one"
            >Reselect</button>
          </div>
          <div className="viewer-header-right">
            {devMode && deprecatedTools && (
              <button
                className={`btn btn-sm debug-toggle${debugMode ? ' active' : ''}`}
                onClick={() => { setDebugMode(d => !d); setLinkFrom(null) }}
                title="Toggle debug tools"
              >⚙ Debug</button>
            )}
            <span className="viewer-points">Points: {total}</span>
          </div>
        </>
      )}
    </div>
  )

  // ── Early returns ──────────────────────────────────────────────────────────

  if (loadError) {
    return (
      <div className="screen tree-viewer">
        {header}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12 }}>
          <p style={{ color: '#ff6b6b' }}>Failed to load {treeName}</p>
          <pre style={{ color: '#555', fontSize: 11 }}>{loadError}</pre>
          <pre style={{ color: '#333355', fontSize: 10 }}>API: {getApiBase()}</pre>
          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button className="btn btn-primary" onClick={loadTree}>↺ Retry</button>
            <button className="btn btn-back" onClick={onBack}>← Go Back</button>
          </div>
        </div>
      </div>
    )
  }

  if (!treeData) {
    return (
      <div className="screen tree-viewer">
        {header}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#888' }}>
          Loading {treeName}…
        </div>
      </div>
    )
  }

  const nodeMap = Object.fromEntries(treeData.nodes.map(n => [n.id, n]))
  const occupiedKeys = new Set(treeData.nodes.map(n => `${n.column},${n.row}`))

  const debugHint: Record<DebugTool, string> = {
    create: 'Click empty slot to create node; click existing node to delete it',
    type:   'Click any node to cycle its type (Micro → Medium → Legendary)',
    link:   linkFrom
      ? `Linking from ${linkFrom} — click another node to toggle connection`
      : 'Click a node to start a link, then click the target (lower col → higher col)',
    stat:   'Click any node to open the stat editor',
  }

  return (
    <div className="screen tree-viewer">
      {header}

      {debugMode && (
        <div className="debug-toolbar">
          <div className="debug-tools">
            {(['create', 'type', 'link', 'stat'] as DebugTool[]).map(t => (
              <button
                key={t}
                className={`btn btn-sm debug-tool-btn${debugTool === t ? ' active' : ''}`}
                onClick={() => { setDebugTool(t); setLinkFrom(null) }}
              >
                {t === 'create' && '+ Create'}
                {t === 'type'   && '◎ Type'}
                {t === 'link'   && '⟷ Link'}
                {t === 'stat'   && '≡ Stat'}
              </button>
            ))}
          </div>
          <span className="debug-hint">{debugHint[debugTool]}</span>
        </div>
      )}

      <div className="viewer-body">
        {!previewMode && (
          <SlotSidebar
            slots={slots}
            activeSlot={activeSlot}
            treeColors={treeColors}
            onOverview={onBack}
            onSlotClick={onSlotClick}
            onPreview={onPreview}
            viewerMode
            dragDropEnabled
            onSlotReorder={onSlotReorder}
          />
        )}

        <div className="viewer-main">
          <div className="viewer-canvas">
            <svg
              viewBox={`0 0 ${VW} ${VH}`}
              width="100%"
              height="100%"
              style={{ display: 'block' }}
              onContextMenu={e => e.preventDefault()}
            >
              {COL_LABELS.map((label, col) => {
                const cx = nodeX(col)
                const locked = !colUnlocked(col, total)
                return (
                  <g key={col}>
                    <text x={cx} y={15} textAnchor="middle" fill="#e0e0e0"
                      fontSize={11} fontFamily="Segoe UI" fontWeight="bold">{label}</text>
                    {locked && col > 0 && (
                      <text x={cx} y={30} textAnchor="middle" fill="#ff6b6b"
                        fontSize={9} fontFamily="Segoe UI" fontStyle="italic">
                        Need {col * 3} pts
                      </text>
                    )}
                  </g>
                )
              })}

              {treeData.connections.map(({ from, to }, i) => {
                const n1 = nodeMap[from]; const n2 = nodeMap[to]
                if (!n1 || !n2) return null
                const x1 = nodeX(n1.column), y1 = nodeY(n1.row)
                const x2 = nodeX(n2.column), y2 = nodeY(n2.row)
                const dx = x2 - x1, dy = y2 - y1
                const dist = Math.sqrt(dx * dx + dy * dy)
                const ox = dist ? dx / dist * NODE_R : 0
                const oy = dist ? dy / dist * NODE_R : 0
                const isLinked = debugMode && debugTool === 'link' &&
                  (from === linkFrom || to === linkFrom)
                return (
                  <line key={i}
                    x1={x1 + ox} y1={y1 + oy} x2={x2 - ox} y2={y2 - oy}
                    stroke={isLinked ? '#e9c046' : '#3a3a5a'}
                    strokeWidth={isLinked ? 2.5 : 2}
                  />
                )
              })}

              {debugMode && debugTool === 'create' &&
                Array.from({ length: COLS }, (_, col) =>
                  Array.from({ length: ROWS }, (_, row) => {
                    if (occupiedKeys.has(`${col},${row}`)) return null
                    const cx = nodeX(col), cy = nodeY(row)
                    return (
                      <g key={`ghost-${col}-${row}`}
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleCreateOnEmpty(col, row)}
                      >
                        <circle cx={cx} cy={cy} r={NODE_R}
                          fill="rgba(80,200,120,0.08)"
                          stroke="rgba(80,200,120,0.45)"
                          strokeWidth={1.5}
                          strokeDasharray="5 3"
                        />
                        <text x={cx} y={cy + 6} textAnchor="middle"
                          fill="rgba(80,200,120,0.55)" fontSize={20} fontWeight="bold"
                          style={{ pointerEvents: 'none' }}>+</text>
                      </g>
                    )
                  })
                ).flat()
              }

              {treeData.nodes.map(node => {
                const cx = nodeX(node.column)
                const cy = nodeY(node.row)
                const pts = nodeStates[node.id] ?? 0
                const colors = nodeColors(node, nodeStates, total)
                const locked = !colUnlocked(node.column, total)
                const isLinkSrc = debugMode && debugTool === 'link' && linkFrom === node.id
                return (
                  <g
                    key={node.id}
                    style={{ cursor: (locked && !debugMode) || processing ? 'default' : 'pointer' }}
                    onClick={e => { e.preventDefault(); handleNodeInteract(node, false) }}
                    onContextMenu={e => { e.preventDefault(); handleNodeInteract(node, true) }}
                    onMouseEnter={e => setTip({ nodeId: node.id, x: e.clientX, y: e.clientY })}
                    onMouseLeave={() => setTip(null)}
                    onMouseMove={e => setTip(t => t ? { ...t, x: e.clientX, y: e.clientY } : null)}
                  >
                    <circle cx={cx} cy={cy} r={NODE_R}
                      fill={isLinkSrc ? '#2a4a2a' : colors.fill}
                      stroke={isLinkSrc ? '#6be946' : colors.stroke}
                      strokeWidth={isLinkSrc ? 3 : 2}
                    />
                    {(node.node_type === 'Medium Talent' || node.node_type === 'Legendary Medium Talent') && (
                      <circle cx={cx} cy={cy} r={NODE_R - 4}
                        fill="none"
                        stroke={node.node_type === 'Legendary Medium Talent' ? '#e9c046' : '#60a5fa'}
                        strokeWidth={1.5}
                        style={{ pointerEvents: 'none' }}
                      />
                    )}
                    <text
                      x={cx} y={cy + 4}
                      textAnchor="middle"
                      fill={colors.text}
                      fontSize={11}
                      fontWeight="bold"
                      fontFamily="Segoe UI"
                      style={{ pointerEvents: 'none' }}
                    >
                      {pts}/{node.max_points}
                    </text>
                  </g>
                )
              })}
            </svg>
          </div>

          <div className="viewer-status" style={{ color: status?.ok ? '#6bcb77' : '#ff6b6b' }}>
            {status?.msg ?? ''}
          </div>
        </div>
      </div>

      {tip && nodeMap[tip.nodeId] && (() => {
        const node = nodeMap[tip.nodeId]
        const pts = nodeStates[node.id] ?? 0
        const effects = node.effects ?? []
        const atMax = pts >= node.max_points
        const flipX = tip.x > window.innerWidth - 230
        const flipY = tip.y > window.innerHeight - 160
        const tipStyle: React.CSSProperties = {
          left:   flipX ? undefined : tip.x + 14,
          right:  flipX ? window.innerWidth - tip.x + 14 : undefined,
          top:    flipY ? undefined : tip.y + 8,
          bottom: flipY ? window.innerHeight - tip.y + 8 : undefined,
        }
        return (
          <div className="tooltip" style={tipStyle}>
            <div className="tooltip-type">{node.node_type} {pts}/{node.max_points}</div>
            {pts > 0 && effects.length > 0 && (
              <div className="tooltip-stats">
                {effects.map((e, i) => (
                  <div key={i} className="tooltip-stat-row">{scaleEffect(e, pts)}</div>
                ))}
              </div>
            )}
            {!atMax && effects.length > 0 && (
              <>
                <div className="tooltip-next-level">Next Level</div>
                <div className="tooltip-stats">
                  {effects.map((e, i) => (
                    <div key={i} className="tooltip-stat-row">{scaleEffect(e, pts + 1)}</div>
                  ))}
                </div>
              </>
            )}
          </div>
        )
      })()}

      {/* Confirm delete dialog */}
      {confirmDelete && (
        <div className="modal-backdrop" onClick={() => setConfirmDelete(null)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">Delete Node?</h3>
            <p style={{ padding: '10px 20px', color: '#aaa', fontSize: 13 }}>
              Delete <strong style={{ color: '#ff6b6b' }}>{confirmDelete.nodeId}</strong> and all its connections?
            </p>
            <div className="modal-actions">
              <button className="btn btn-danger" onClick={() => handleDeleteNode(confirmDelete.nodeId)}>
                Delete
              </button>
              <button className="btn btn-primary" onClick={() => setConfirmDelete(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {statModal && (
        <div className="modal-backdrop" onClick={() => setStatModal(null)}>
          <div className="modal-card stat-editor-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">Modifiers — {statModal.nodeId}</h3>
            <div className="stat-editor-type">{statModal.nodeType}</div>

            {/* Assigned modifiers */}
            <div className="stat-list">
              {nodeModifiers.length === 0 && (
                <p className="stat-empty">No modifiers assigned yet.</p>
              )}
              {nodeModifiers.map((mod, i) => (
                <div key={i} className="stat-row">
                  <span className="stat-name" style={{ flex: 1 }}>{mod.text}</span>
                  <div style={{ display: 'flex', gap: 3 }}>
                    {mod.values.map((v, vi) => (
                      <input
                        key={vi}
                        className="stat-val-input"
                        type="number"
                        step="any"
                        value={v}
                        style={{ width: 58 }}
                        onChange={e => {
                          const next = nodeModifiers.map((m, mi) =>
                            mi !== i ? m : {
                              ...m,
                              values: m.values.map((vv, vvi) => vvi === vi ? (parseFloat(e.target.value) || 0) : vv),
                            }
                          )
                          setNodeModifiers(next)
                        }}
                      />
                    ))}
                  </div>
                  <button className="stat-remove" onClick={() => setNodeModifiers(nodeModifiers.filter((_, j) => j !== i))}>✕</button>
                </div>
              ))}
            </div>

            {/* Snapshot modifier picker */}
            <div className="stat-add-section">
              <div style={{ fontSize: 11, color: '#666', fontWeight: 700, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 1 }}>
                {loadingMods ? 'Loading…' : `From Snapshot (${filteredSnapshotMods.length}${modSearch ? ` of ${snapshotMods.length}` : ''})`}
              </div>
              <input
                className="stat-val-input"
                style={{ width: '100%', marginBottom: 6, boxSizing: 'border-box' }}
                type="text"
                placeholder="Search…"
                value={modSearch}
                onChange={e => setModSearch(e.target.value)}
              />
              <div style={{ maxHeight: 180, overflowY: 'auto', border: '1px solid #2a2a4a', borderRadius: 4 }}>
                {filteredSnapshotMods.length === 0 ? (
                  <div style={{ color: '#555', fontSize: 12, padding: '8px 10px' }}>
                    {snapshotMods.length === 0 ? 'No snapshot loaded — upload one in Dev Tools → Canonical Snapshot.' : 'No matches.'}
                  </div>
                ) : filteredSnapshotMods.map(text => {
                  const already = nodeModifiers.some(m => m.text === text)
                  return (
                    <div
                      key={text}
                      className="stat-row"
                      style={{ cursor: already ? 'default' : 'pointer', opacity: already ? 0.4 : 1, borderRadius: 0, borderBottom: '1px solid #1a1a2e' }}
                      onClick={() => { if (!already) handleAddModifier(text, statModal.maxPoints) }}
                    >
                      <span className="stat-name" style={{ flex: 1 }}>{text}</span>
                      <span style={{ fontSize: 11, color: already ? '#555' : '#4caf50', minWidth: 36, textAlign: 'right' }}>
                        {already ? '✓' : '+ add'}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleSaveModifiers} disabled={savingMods}>
                {savingMods ? 'Saving…' : 'Save Modifiers'}
              </button>
              <button className="btn btn-danger" onClick={() => setStatModal(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
