import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { FloatingPortal, useFloating, autoUpdate, offset, flip, shift, size } from '@floating-ui/react'
import { api, getApiBase, iconUrl, TreeData, TreeNode, CoreTalentSlotOption } from '../api/client'
import SlotSidebar from '../components/SlotSidebar'
import { useBuildStore } from '../store/buildStore'
import { ModifierBadge, useConsumedStatSet, useConsumableUniverse, type ModifierStatus } from '../components/ModifierBadge'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { TooltipShell } from '../components/tooltip/TooltipShell'
import { NodeTooltipBody } from '../components/tooltip/bodies/NodeTooltipBody'
import { useDamageDelta, withNodePoints } from '../components/tooltip/useDamageDelta'

const COLS = 7
const ROWS = 5
const COL_LABELS = [0, 3, 6, 9, 12, 15, 18]
// Larger viewBox than the node size → more breathing room between columns/rows (the tree scales to fit
// the canvas, so this widens the gaps and shrinks the nodes a touch rather than zooming in).
const VW = 820
const VH = 586
const HEADER = 42
const CELL_W = VW / COLS
const CELL_H = (VH - HEADER) / ROWS
const NODE_R = 26

function nodeX(col: number) { return col * CELL_W + CELL_W / 2 }
function nodeY(row: number) { return HEADER + row * CELL_H + CELL_H / 2 }
function sumPoints(states: Record<string, number>) {
  return Object.values(states).reduce((a, b) => a + b, 0)
}

const NODE_TYPES = ['Micro Talent', 'Medium Talent', 'Legendary Medium Talent'] as const
type NodeTypeStr = typeof NODE_TYPES[number]




function nextType(t: NodeTypeStr): NodeTypeStr {
  const i = NODE_TYPES.indexOf(t)
  return NODE_TYPES[(i + 1) % NODE_TYPES.length]
}
function maxPointsFor(t: NodeTypeStr) { return t === 'Legendary Medium Talent' ? 1 : 3 }

// Rarity ring colors keyed by node type — the node's own border (kept distinct from the allocation
// progress arc rendered outside it).
const RARITY_RING_COLOR: Record<string, string> = {
  'Micro Talent': '#d0d0d0',
  'Medium Talent': '#60a5fa',
  'Legendary Medium Talent': '#e9c046',
  default: '#d0d0d0',
}

function nodeColors(node: TreeNode, states: Record<string, number>, locked: boolean) {
  const pts = states[node.id] ?? 0
  const full = pts >= node.max_points
  return {
    fill:   locked ? '#222233' : full ? '#533483' : '#0f3460',
    stroke: locked ? '#333344' : full ? '#e94560' : '#3a5a9a',
    text:   locked ? '#444455' : full ? '#ffffff'  : '#e0e0e0',
  }
}

type DebugTool = 'create' | 'type' | 'link'

interface TreeNodeGProps {
  node: TreeNode
  cx: number
  cy: number
  pts: number
  colors: { fill: string; stroke: string; text: string }
  locked: boolean
  isLinkSrc: boolean
  isHit: boolean
  isSearching: boolean
  processing: boolean
  debugMode: boolean
  onInteract: (node: TreeNode, isRight: boolean) => void
}

// A single passive-tree node (SVG group) plus its hover tooltip, routed through the shared
// floating-tooltip primitive. Element-anchored; damage-delta band wired (NYI until backend).
function TreeNodeG({
  node, cx, cy, pts, colors, locked, isLinkSrc, isHit, isSearching, processing, debugMode, onInteract,
}: TreeNodeGProps) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right' })
  const activeSlot = useBuildStore(s => s.activeSlot)
  // Marginal per-point delta: step the hovered node by +1 (or -1 when maxed) vs the current build.
  // Derive the current points from the SAME store snapshot used for the baseline — NOT the render-time
  // `pts` — so the step is always exactly one rank off the base. Using `pts` (local tree state) here
  // can desync from the store the engine prices against, yielding a 2-rank delta or a zeroed one
  // (bug-129 class).
  const maxPts = node.max_points
  const full = pts >= node.max_points
  const icon = iconUrl('talent_tree', node.icon_url)
  // Rarity ring = the node border (white micro / blue medium / orange legendary). Always shown — even on
  // locked nodes — so rarity reads at a glance; lock/allocation state comes from the dimmed icon + the
  // absence of the outer progress arc instead. Allocation is a separate OUTER arc so the two never overlap.
  const rarityColor = RARITY_RING_COLOR[node.node_type] ?? RARITY_RING_COLOR.default
  const frac = node.max_points > 0 ? Math.min(1, pts / node.max_points) : 0
  const delta = useDamageDelta(
    tip.open ? {
      key: `node:${activeSlot}:${node.id}`,
      step: s => {
        const cur = s.slots[activeSlot]?.nodeStates?.[node.id] ?? 0
        const tgt = cur < maxPts ? cur + 1 : Math.max(0, cur - 1)
        return withNodePoints(s, activeSlot, node.id, tgt)
      },
    } : null,
    tip.open,
  )
  return (
    <>
      <g
        {...tip.triggerProps}
        style={{
          cursor: (locked && !debugMode) || processing ? 'default' : 'pointer',
          opacity: isSearching && !isHit ? 0.15 : 1,
        }}
        onClick={e => { e.preventDefault(); onInteract(node, false) }}
        onContextMenu={e => { e.preventDefault(); onInteract(node, true) }}
      >
        {isSearching && isHit && (
          <circle cx={cx} cy={cy} r={NODE_R + 9}
            fill="rgba(233,192,70,0.12)"
            stroke="#e9c046"
            strokeWidth={2}
            style={{ pointerEvents: 'none' }}
          />
        )}
        {/* Node body + rarity-colored border (white/blue/orange by type). */}
        <circle cx={cx} cy={cy} r={NODE_R}
          fill={isLinkSrc ? '#2a4a2a' : (locked ? '#191925' : '#0e1230')}
          stroke={isLinkSrc ? '#6be946' : rarityColor}
          strokeWidth={node.node_type === 'Legendary Medium Talent' ? 3 : 2.5}
        />
        {icon && (
          <>
            <clipPath id={`nclip-${node.id}`}><circle cx={cx} cy={cy} r={NODE_R - 3} /></clipPath>
            <image
              href={icon}
              x={cx - (NODE_R - 3)} y={cy - (NODE_R - 3)}
              width={(NODE_R - 3) * 2} height={(NODE_R - 3) * 2}
              clipPath={`url(#nclip-${node.id})`}
              preserveAspectRatio="xMidYMid slice"
              // Allocated nodes show the icon bright; locked/empty are dimmed so the tree reads at a glance.
              opacity={locked ? 0.22 : full ? 0.95 : 0.5}
              style={{ pointerEvents: 'none' }}
            />
          </>
        )}
        {/* Allocation = outer progress arc on its own radius, so it never overlaps the rarity border.
            Faint full track + a red arc filled to pts/max (starts at 12 o'clock). */}
        {!locked && (
          <>
            <circle cx={cx} cy={cy} r={NODE_R + 4}
              fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={2.5}
              style={{ pointerEvents: 'none' }}
            />
            {pts > 0 && (
              <circle cx={cx} cy={cy} r={NODE_R + 4}
                fill="none" stroke="#e94560" strokeWidth={2.5}
                pathLength={1} strokeDasharray={`${frac} 1`} strokeLinecap="round"
                transform={`rotate(-90 ${cx} ${cy})`}
                style={{ pointerEvents: 'none' }}
              />
            )}
          </>
        )}
        <text
          x={cx} y={cy + 4}
          textAnchor="middle"
          fill={colors.text}
          fontSize={11}
          fontWeight="bold"
          fontFamily="Segoe UI"
          // Dark outline keeps the count legible over the icon art behind it.
          stroke={icon ? 'rgba(0,0,0,0.85)' : undefined}
          strokeWidth={icon ? 2.5 : undefined}
          paintOrder="stroke"
          style={{ pointerEvents: 'none' }}
        >
          {pts}/{node.max_points}
        </text>
      </g>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--node" {...tip.floatingProps}>
            <TooltipShell title={`${node.node_type} ${pts}/${node.max_points}`} delta={delta}>
              <NodeTooltipBody node={node} pts={pts} />
            </TooltipShell>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

interface Props {
  treeName: string
  treeColor: string
  treeColors: Record<string, string>
  onBack: () => void
  onSlotClick: (slotIndex: number) => void
  onReselect: () => void
  onSlotReorder?: (fromSlot: number, toSlot: number) => void
  onPreview?: () => void
  previewMode?: boolean
  devMode?: boolean
  deprecatedTools?: boolean
}

export default function TreeViewerScreen({
  treeName, treeColor, treeColors,
  onBack, onSlotClick, onReselect,
  onSlotReorder, onPreview,
  previewMode = false, devMode = false, deprecatedTools = false,
}: Props) {
  const slots = useBuildStore(s => s.slots)
  const activeSlot = useBuildStore(s => s.activeSlot)
  const updateSlotNodeStates = useBuildStore(s => s.updateSlotNodeStates)
  const updateSlotCoreTalentSelections = useBuildStore(s => s.updateSlotCoreTalentSelections)
  // Core-talent effect badges (roadmap #4), the same 4-state scheme as every other modifier, driven by
  // the tree's STATIC per-line resolution plus the build's consumed_stats + consumable_universe:
  //   • unresolved/deferred line                       → "Unrecognized (NYI)" (red)
  //   • resolves, talent granted, a stat consumed      → "Consumed" (green)
  //   • resolves, granted, stat in universe not consumed → "Inactive" (grey) — not for your skill
  //   • resolves, granted, stat the engine never reads → "Unconsumed" (yellow)
  //   • override line (applied via a flag, no stat)    → no badge
  const coreTalentStatuses = useBuildStore(s => s.computedStats.core_talent_statuses)
  const consumedStats = useConsumedStatSet()
  const universe = useConsumableUniverse()
  const grantedCoreNames = useMemo(() => {
    const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ')
    return new Set((coreTalentStatuses ?? []).map(st => norm(st.name)))
  }, [coreTalentStatuses])
  const coreEffectBadge = useCallback((opt: CoreTalentSlotOption, i: number): ModifierStatus | null => {
    const es = opt.effect_status?.[i]
    if (!es || es.kind === 'override') return null
    if (!es.resolved) return 'unrecognized'
    if (es.stat_keys.length === 0) return 'unrecognized'
    // Only meaningful once the talent is actually granted; ungranted options stay unbadged.
    const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ')
    if (!grantedCoreNames.has(norm(opt.name))) return null
    if (es.stat_keys.some(k => consumedStats.has(k))) return 'working'
    if (universe.size === 0 || es.stat_keys.some(k => universe.has(k))) return 'inactive'
    return 'unused'
  }, [grantedCoreNames, consumedStats, universe])

  const [treeData, setTreeData] = useState<TreeData | null>(null)
  const [loadError, setLoadError] = useState('')
  const [nodeStates, setNodeStates] = useState<Record<string, number>>(() => previewMode ? {} : (slots[activeSlot]?.nodeStates ?? {}))
  const [coreTalentSelections, setCoreTalentSelections] = useState<Record<number, string>>(() => previewMode ? {} : (slots[activeSlot]?.coreTalentSelections ?? {}))
  const [expandedSlot, setExpandedSlot] = useState<number | null>(null)

  // Float the core-talent dropdown beneath the expanded slot's circle, auto-shifting to stay fully
  // on-screen (anchored to the trigger, never clipped by the window edge).
  const coreFloat = useFloating({
    open: expandedSlot !== null,
    placement: 'bottom',
    whileElementsMounted: autoUpdate,
    middleware: [
      offset(6),
      flip({ padding: 8 }),
      shift({ padding: 8 }),
      size({
        padding: 8,
        apply({ availableWidth, elements }) {
          elements.floating.style.maxWidth = `${Math.max(240, availableWidth)}px`
        },
      }),
    ],
  })
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null)
  const [processing, setProcessing] = useState(false)
  const [search, setSearch] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debug state
  const [debugMode, setDebugMode] = useState(false)
  const [debugTool, setDebugTool] = useState<DebugTool>('create')
  const [linkFrom, setLinkFrom] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<{ nodeId: string } | null>(null)

  const loadTree = useCallback(() => {
    setTreeData(null)
    setLoadError('')
    api.getTree(treeName)
      .then(data => setTreeData(data))
      .catch(e => setLoadError(String(e)))
  }, [treeName])

  useEffect(() => {
    setNodeStates(previewMode ? {} : (slots[activeSlot]?.nodeStates ?? {}))
    setCoreTalentSelections(previewMode ? {} : (slots[activeSlot]?.coreTalentSelections ?? {}))
    setExpandedSlot(null)   // collapse — a stale index can be out of range for the new tree
    setSearch('')
    loadTree()
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [treeName])

  useEffect(() => {
    if (!deprecatedTools) { setDebugMode(false); setLinkFrom(null) }
  }, [deprecatedTools])


  const total = sumPoints(nodeStates)

  // Column unlock = points spent in columns strictly to the LEFT of a column (its own and
  // further-right points don't count). Column 0 is always open.
  const colPoints = Array(COLS).fill(0) as number[]
  if (treeData) for (const n of treeData.nodes) colPoints[n.column] += nodeStates[n.id] ?? 0
  const isColUnlocked = (col: number): boolean => {
    if (col === 0) return true
    let before = 0
    for (let c = 0; c < col; c++) before += colPoints[c]
    return before >= col * 3
  }

  const searchWords = search.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const isSearching = searchWords.length > 0
  const searchHits = new Set<string>()
  if (isSearching && treeData) {
    for (const node of treeData.nodes) {
      const haystack = (node.effects ?? []).join(' ').toLowerCase()
      if (searchWords.every(w => haystack.includes(w))) searchHits.add(node.id)
    }
  }

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
        if (!previewMode) updateSlotNodeStates(activeSlot, res.node_states)
        if (treeData && Object.keys(coreTalentSelections).length > 0) {
          const newTotal = sumPoints(res.node_states)
          const next = { ...coreTalentSelections }
          let changed = false
          for (const idxStr of Object.keys(coreTalentSelections)) {
            const idx = Number(idxStr)
            const slot = treeData.core_talent_slots[idx]
            if (slot && newTotal < slot.threshold) {
              delete next[idx]
              changed = true
            }
          }
          if (changed) {
            setCoreTalentSelections(next)
            if (!previewMode) updateSlotCoreTalentSelections(activeSlot, next)
          }
        }
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

  const handleNodeInteract = (node: TreeNode, isRight: boolean) => {
    if (!debugMode) {
      handleClick(node.id, isRight ? 'deallocate' : 'allocate')
      return
    }
    switch (debugTool) {
      case 'create': setConfirmDelete({ nodeId: node.id }); break
      case 'type':   handleTypeNode(node); break
      case 'link':   handleLinkNode(node.id); break
    }
  }

  const handleReset = () => {
    const cleared = Object.fromEntries(Object.keys(nodeStates).map(k => [k, 0]))
    setNodeStates(cleared)
    if (!previewMode) updateSlotNodeStates(activeSlot, cleared)
    flash('All points reset.', true)
  }

  const handleCoreTalentSelect = (slotIndex: number, talentId: string) => {
    // Options are always viewable, but selection is gated on meeting the slot's point threshold.
    const slot = treeData?.core_talent_slots[slotIndex]
    if (slot && total < slot.threshold) {
      flash(`Allocate ${slot.threshold} points to select this Core Talent.`)
      return
    }
    const next = { ...coreTalentSelections }
    if (next[slotIndex] === talentId) {
      delete next[slotIndex]
    } else {
      next[slotIndex] = talentId
      setExpandedSlot(null)
    }
    setCoreTalentSelections(next)
    if (!previewMode) updateSlotCoreTalentSelections(activeSlot, next)
  }

  // Core-talent widget (circles + Floating dropdown) — shared by the normal and preview headers.
  const coreTalentWidget = treeData && treeData.core_talent_slots.length > 0 ? (
          <div className="core-talent-header-widget">
            <div className="core-talent-circles">
              {treeData.core_talent_slots.map((slot, slotIdx) => {
                const unlocked = total >= slot.threshold
                const selectedId = coreTalentSelections[slotIdx]
                const isOpen = expandedSlot === slotIdx
                const ptsToward = Math.min(total, slot.threshold)
                const selectedOpt = selectedId ? slot.options.find(o => o.id === selectedId) : null
                const selectedTalentName = selectedOpt?.name ?? null
                const selectedIcon = iconUrl('talent_tree', selectedOpt?.icon_url)
                return (
                  <div key={slotIdx} className="core-talent-slot-item">
                    <button
                      ref={isOpen ? coreFloat.refs.setReference : undefined}
                      className={`core-talent-circle${unlocked ? ' unlocked' : ''}${isOpen ? ' open' : ''}${selectedId ? ' has-selection' : ''}`}
                      onClick={() => setExpandedSlot(isOpen ? null : slotIdx)}
                      title={unlocked ? `Core Talent Slot ${slotIdx + 1} — click to expand` : `Locked — need ${slot.threshold} pts (click to preview)`}
                    >
                      {selectedIcon
                        ? <img src={selectedIcon} className="core-talent-circle-img" alt="" />
                        : <span className="core-talent-circle-progress">
                            {unlocked ? '?' : `${ptsToward}/${slot.threshold}`}
                          </span>}
                    </button>
                    <span className="core-talent-circle-label">
                      {selectedTalentName ?? `Core Talent ${slotIdx + 1}`}
                    </span>
                  </div>
                )
              })}
            </div>
            {expandedSlot !== null && (() => {
              // Guard: expandedSlot can be stale after switching to a tree with fewer core-talent
              // slots (e.g. a 2-slot God tree → a 1-slot subtree), making this index out of range.
              const slot = treeData.core_talent_slots[expandedSlot]
              if (!slot) return null
              const selectedId = coreTalentSelections[expandedSlot]
              const slotUnlocked = total >= slot.threshold   // viewable always; selectable at threshold
              return (
                <FloatingPortal>
                  <div
                    ref={coreFloat.refs.setFloating}
                    style={coreFloat.floatingStyles}
                    className="core-talent-cards"
                  >
                    {!slotUnlocked && (
                      <div className="core-talent-locked-note">
                        Locked — allocate {slot.threshold} points in this tree to select.
                      </div>
                    )}
                    <div className="core-talent-card-row">
                      {slot.options.map(opt => {
                        const selected = selectedId === opt.id
                        return (
                          <div key={opt.id} className={`core-talent-card${selected ? ' selected' : ''}${slotUnlocked ? '' : ' locked'}`}>
                            <div className="core-talent-card-name">
                              {iconUrl('talent_tree', opt.icon_url) && (
                                <img src={iconUrl('talent_tree', opt.icon_url) ?? undefined} className="core-talent-card-icon" alt="" />
                              )}
                              <span>{opt.name}</span>
                            </div>
                            <div className="core-talent-card-desc">
                              {opt.effects.map((e, i) => (
                                <p key={i}>{e}<ModifierBadge status={coreEffectBadge(opt, i)} /></p>
                              ))}
                            </div>
                            <button
                              className={`core-talent-card-select${selected ? ' selected' : ''}`}
                              onClick={() => handleCoreTalentSelect(expandedSlot, opt.id)}
                              disabled={!slotUnlocked}
                              title={slotUnlocked ? '' : `Need ${slot.threshold} points to select`}
                            >
                              {selected ? 'Selected' : slotUnlocked ? 'Select' : 'Locked'}
                            </button>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </FloatingPortal>
              )
            })()}
          </div>
  ) : null

  // ── Header ─────────────────────────────────────────────────────────────────

  const header = previewMode ? (
    <div className="viewer-header preview-viewer-header">
      <div className="viewer-header-left">
        <button className="btn-back" onClick={onBack}>← Back to Preview</button>
        {coreTalentWidget}
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
        {coreTalentWidget}
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
            <div className="tree-search-bar">
              <input
                className="tree-search-input"
                type="text"
                placeholder="Search nodes…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
              {search && (
                <button className="tree-search-clear" onClick={() => setSearch('')}>✕</button>
              )}
            </div>
            {isSearching && (
              <span className="tree-search-count">
                {searchHits.size} match{searchHits.size !== 1 ? 'es' : ''}
              </span>
            )}
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
  }

  return (
    <div className="screen tree-viewer">
      {header}

      {debugMode && (
        <div className="debug-toolbar">
          <div className="debug-tools">
            {(['create', 'type', 'link'] as DebugTool[]).map(t => (
              <button
                key={t}
                className={`btn btn-sm debug-tool-btn${debugTool === t ? ' active' : ''}`}
                onClick={() => { setDebugTool(t); setLinkFrom(null) }}
              >
                {t === 'create' && '+ Create'}
                {t === 'type'   && '◎ Type'}
                {t === 'link'   && '⟷ Link'}
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
                const locked = !isColUnlocked(col)
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
                    stroke={isLinked ? '#e9c046' : '#6b78b8'}
                    strokeWidth={isLinked ? 3.5 : 3}
                    strokeLinecap="round"
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
                const locked = !isColUnlocked(node.column)
                const colors = nodeColors(node, nodeStates, locked)
                const isLinkSrc = debugMode && debugTool === 'link' && linkFrom === node.id
                const isHit = !isSearching || searchHits.has(node.id)
                return (
                  <TreeNodeG
                    key={node.id}
                    node={node}
                    cx={cx}
                    cy={cy}
                    pts={pts}
                    colors={colors}
                    locked={locked}
                    isLinkSrc={isLinkSrc}
                    isHit={isHit}
                    isSearching={isSearching}
                    processing={processing}
                    debugMode={debugMode}
                    onInteract={handleNodeInteract}
                  />
                )
              })}
            </svg>
          </div>

          <div className="viewer-status" style={{ color: status?.ok ? '#6bcb77' : '#ff6b6b' }}>
            {status?.msg ?? ''}
          </div>

        </div>
      </div>

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

    </div>
  )
}
