import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { FloatingPortal, useFloating, autoUpdate, offset, flip, shift, size } from '@floating-ui/react'
import { api, getApiBase, iconUrl, TreeData, TreeNode, CoreTalentSlotOption,
  PrismCatalogItem, CraftedPrism, PlacedPrism, PrismRolls, EtherealCatalog, EtherealConfig } from '../api/client'
import SlotSidebar from '../components/SlotSidebar'
import PrismOverlay, { RARE_TINT, condensePrismImplicit } from '../components/PrismOverlay'
import { isPrimary } from '../treeGroups'
import { useBuildStore } from '../store/buildStore'
import { ModifierBadge, useConsumedStatSet, useConsumableUniverse, type ModifierStatus } from '../components/ModifierBadge'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { TooltipShell } from '../components/tooltip/TooltipShell'
import { NodeTooltipBody } from '../components/tooltip/bodies/NodeTooltipBody'
import { useDamageDelta, withNodePoints, withPrismBoxPoints } from '../components/tooltip/useDamageDelta'

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
// Prism reflected effect = source effect × (1 + roll/100), where the roll is the prism's value for the SOURCE
// node's tier (matches the engine in node_resolver.resolve_nodes).
const PRISM_TIER_KEY: Record<string, keyof PrismRolls> = {
  'Micro Talent': 'micro', 'Medium Talent': 'medium', 'Legendary Medium Talent': 'legendary',
}
function prismMult(rolls: PrismRolls, nodeType: string): number {
  return 1 + (rolls[PRISM_TIER_KEY[nodeType] ?? 'micro'] ?? -100) / 100
}
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
  maxOverride?: number      // raised cap from an Ethereal Prism's over-allocation affix
  inPrismBox?: boolean      // node sits inside a placed Ethereal Prism's effect area
}

// A single passive-tree node (SVG group) plus its hover tooltip, routed through the shared
// floating-tooltip primitive. Element-anchored; damage-delta band wired (NYI until backend).
function TreeNodeG({
  node, cx, cy, pts, colors, locked, isLinkSrc, isHit, isSearching, processing, debugMode, onInteract,
  maxOverride, inPrismBox,
}: TreeNodeGProps) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right' })
  const activeSlot = useBuildStore(s => s.activeSlot)
  // Marginal per-point delta: step the hovered node by +1 (or -1 when maxed) vs the current build.
  // Derive the current points from the SAME store snapshot used for the baseline — NOT the render-time
  // `pts` — so the step is always exactly one rank off the base. Using `pts` (local tree state) here
  // can desync from the store the engine prices against, yielding a 2-rank delta or a zeroed one
  // (bug-129 class).
  const maxPts = maxOverride ?? node.max_points     // Ethereal over-allocation raises the cap
  const full = pts >= maxPts
  const icon = iconUrl('talent_tree', node.icon_url)
  // Rarity ring = the node border (white micro / blue medium / orange legendary). Always shown — even on
  // locked nodes — so rarity reads at a glance; lock/allocation state comes from the dimmed icon + the
  // absence of the outer progress arc instead. Allocation is a separate OUTER arc so the two never overlap.
  const rarityColor = RARITY_RING_COLOR[node.node_type] ?? RARITY_RING_COLOR.default
  const frac = maxPts > 0 ? Math.min(1, pts / maxPts) : 0
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
        {/* Inside a placed Ethereal Prism's effect area: a violet marker ring (modify-in-place). */}
        {inPrismBox && (
          <circle cx={cx} cy={cy} r={NODE_R + 7} fill="none" stroke="#c79bff" strokeWidth={1.5}
            strokeDasharray="3 3" opacity={0.55} style={{ pointerEvents: 'none' }} />
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
          {pts}/{maxPts}
        </text>
      </g>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--node" {...tip.floatingProps}>
            <TooltipShell title={`${node.node_type} ${pts}/${maxPts}`} delta={delta}>
              <NodeTooltipBody node={node} pts={pts} />
            </TooltipShell>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

// A reflected COPY rendered in an Inverse Image's mirror box: shows the SOURCE node (point-reflected from the
// other side), allocatable with broken connection-prereqs (only the column threshold gates it). Its own tooltip
// shows the source node's effects; the prism multiplier is applied to DPS in Plan 2.
function ReflectedNodeG({ col, row, src, pts, unlocked, posKey, mult, prismId, onAlloc }: {
  col: number; row: number; src: TreeNode; pts: number; unlocked: boolean; posKey: string; mult: number
  prismId: string; onAlloc: (add: boolean) => void
}) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right' })
  const cx = nodeX(col), cy = nodeY(row)
  // Marginal DPS of stepping this reflected copy ±1 — priced by the engine via the prisms payload (so it
  // covers the reflected effect's scaled stats, and any future prism-granted stats, generically).
  const delta = useDamageDelta(
    tip.open ? {
      key: `prism:${prismId}:${posKey}`,
      step: s => {
        const cur = s.prisms.find(p => p.id === prismId)?.boxAllocations?.[posKey] ?? 0
        const tgt = cur < src.max_points ? cur + 1 : Math.max(0, cur - 1)
        return withPrismBoxPoints(s, prismId, posKey, tgt)
      },
    } : null,
    tip.open,
  )
  const icon = iconUrl('talent_tree', src.icon_url)
  const rarity = RARITY_RING_COLOR[src.node_type] ?? RARITY_RING_COLOR.default
  const full = pts >= src.max_points
  const frac = src.max_points > 0 ? Math.min(1, pts / src.max_points) : 0
  return (
    <>
      <g {...tip.triggerProps} style={{ cursor: unlocked ? 'pointer' : 'default' }}
        onClick={e => { e.preventDefault(); onAlloc(true) }}
        onContextMenu={e => { e.preventDefault(); onAlloc(false) }}>
        {/* Reflected-copy marker ring (violet, dashed) */}
        <circle cx={cx} cy={cy} r={NODE_R + 7} fill="none" stroke="#c79bff" strokeWidth={1.5}
          strokeDasharray="3 3" opacity={0.6} style={{ pointerEvents: 'none' }} />
        <circle cx={cx} cy={cy} r={NODE_R} fill={unlocked ? '#0e1230' : '#191925'}
          stroke={rarity} strokeWidth={src.node_type === 'Legendary Medium Talent' ? 3 : 2.5} />
        {icon && (
          <>
            <clipPath id={`rclip-${posKey}`}><circle cx={cx} cy={cy} r={NODE_R - 3} /></clipPath>
            <image href={icon} x={cx - (NODE_R - 3)} y={cy - (NODE_R - 3)}
              width={(NODE_R - 3) * 2} height={(NODE_R - 3) * 2} clipPath={`url(#rclip-${posKey})`}
              preserveAspectRatio="xMidYMid slice" opacity={!unlocked ? 0.22 : full ? 0.95 : 0.5}
              style={{ pointerEvents: 'none' }} />
          </>
        )}
        {unlocked && (
          <>
            <circle cx={cx} cy={cy} r={NODE_R + 4} fill="none" stroke="rgba(255,255,255,0.08)"
              strokeWidth={2.5} style={{ pointerEvents: 'none' }} />
            {pts > 0 && (
              <circle cx={cx} cy={cy} r={NODE_R + 4} fill="none" stroke="#c79bff" strokeWidth={2.5}
                pathLength={1} strokeDasharray={`${frac} 1`} strokeLinecap="round"
                transform={`rotate(-90 ${cx} ${cy})`} style={{ pointerEvents: 'none' }} />
            )}
          </>
        )}
        <text x={cx} y={cy + 4} textAnchor="middle" fill="#fff" fontSize={11} fontWeight="bold"
          stroke={icon ? 'rgba(0,0,0,0.85)' : undefined} strokeWidth={icon ? 2.5 : undefined}
          paintOrder="stroke" style={{ pointerEvents: 'none' }}>{pts}/{src.max_points}</text>
      </g>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--node" {...tip.floatingProps}>
            <TooltipShell title={`${src.node_type} ${pts}/${src.max_points} · Reflected`} delta={delta}>
              <NodeTooltipBody node={src} pts={pts} mult={mult} />
            </TooltipShell>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

// The installed prism on its anchor node: prism icon, a hover tooltip showing its rolls, left-click to edit,
// right-click to remove. The anchor node is overridden (grants no effect) and breaks the prereq chain.
function PrismAnchorG({ prism, cx, cy, onEdit, onRemove }: {
  prism: PlacedPrism; cx: number; cy: number; onEdit: () => void; onRemove: () => void
}) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right' })
  const TLABEL: [keyof PrismRolls, string][] = [['micro', 'Micro'], ['medium', 'Medium'], ['legendary', 'Legendary Medium']]
  const eth = prism.kind === 'ethereal_prism' ? prism.ethereal : undefined
  const rare = eth?.rarity === 'rare'
  const ring = rare ? '#c79bff' : '#e9c046'
  const tint = rare && eth?.tintWhenRare
  const short = (s: string, n = 96) => s.length > n ? s.slice(0, n - 1) + '…' : s
  return (
    <>
      <g {...tip.triggerProps} style={{ cursor: 'pointer' }}
        onClick={e => { e.preventDefault(); onEdit() }}
        onContextMenu={e => { e.preventDefault(); onRemove() }}>
        <clipPath id="prism-anchor-clip"><circle cx={cx} cy={cy} r={NODE_R - 2} /></clipPath>
        <circle cx={cx} cy={cy} r={NODE_R} fill="#1a1326" stroke={ring} strokeWidth={3} />
        <image href={iconUrl('prism', prism.iconUrl) ?? undefined}
          x={cx - NODE_R + 2} y={cy - NODE_R + 2} width={(NODE_R - 2) * 2} height={(NODE_R - 2) * 2}
          clipPath="url(#prism-anchor-clip)" style={{ filter: tint ? RARE_TINT : undefined }} />
      </g>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--node" {...tip.floatingProps}>
            <TooltipShell title={prism.name}>
              <div style={{ padding: '6px 2px' }}>
                {eth ? (
                  <div style={{ fontSize: 12, color: '#cfd3ee', lineHeight: 1.5 }}>
                    <div style={{ color: rare ? '#c79bff' : '#e9c046', textTransform: 'capitalize' }}>{eth.rarity}</div>
                    <div>{short(condensePrismImplicit(eth.implicit, eth.shortName))}</div>
                    {eth.boxCols && <div style={{ color: '#9aa' }}>Effect Area: {eth.boxCols}×{eth.boxRows}</div>}
                    {eth.middle && <div>{short(eth.middle)}</div>}
                    {eth.advanced && <div>{short(eth.advanced)}</div>}
                  </div>
                ) : (
                  TLABEL.map(([k, lbl]) => (
                    <div key={k} style={{ fontSize: 12, color: prism.rolls[k] <= -100 ? '#666' : '#cfd3ee' }}>
                      {prism.rolls[k] > 0 ? '+' : ''}{prism.rolls[k]}% all reflected {lbl} Talent Effects
                    </div>
                  ))
                )}
                <div style={{ marginTop: 6, fontSize: 11, color: '#8a8aa5' }}>
                  Overrides this node · breaks prerequisites · left-click to edit · right-click to remove
                </div>
              </div>
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
  // Allocation is now validated client-side & applied synchronously (no per-click backend round-trip), so there's
  // no in-flight "processing" state. Kept as a const false purely to feed the node's cursor prop unchanged.
  const processing = false
  const [search, setSearch] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debug state
  const [debugMode, setDebugMode] = useState(false)
  const [debugTool, setDebugTool] = useState<DebugTool>('create')
  const [linkFrom, setLinkFrom] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<{ nodeId: string } | null>(null)

  // ── Prisms ─────────────────────────────────────────────────────────────────
  const prisms = useBuildStore(s => s.prisms)
  const prismInventory = useBuildStore(s => s.prismInventory)
  const setPrisms = useBuildStore(s => s.setPrisms)
  const setPrismInventory = useBuildStore(s => s.setPrismInventory)
  const [prismCatalog, setPrismCatalog] = useState<PrismCatalogItem[]>([])
  const [etherealCat, setEtherealCat] = useState<EtherealCatalog | null>(null)
  const [prismOverlayOpen, setPrismOverlayOpen] = useState(false)
  const [placingPrism, setPlacingPrism] = useState<CraftedPrism | null>(null)
  const [editingPlaced, setEditingPlaced] = useState<PlacedPrism | null>(null)
  const [hoverPlaceCell, setHoverPlaceCell] = useState<{ col: number; row: number } | null>(null)
  useEffect(() => {
    api.getEtherealPrism().then(r => { setPrismCatalog(r.items ?? []); setEtherealCat(r.catalog ?? null) }).catch(() => {})
  }, [])
  // The prism installed on THIS tree (Plan 1: ≤1 per tree). previewMode never shows prisms.
  const treePrism = previewMode ? undefined : prisms.find(p => p.treeName === treeName)

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


  // Prism reflected-box points count toward the budget + column thresholds (they cost points in-game).
  const total = sumPoints(nodeStates) + (treePrism ? sumPoints(treePrism.boxAllocations) : 0)

  // Column unlock = points spent in columns strictly to the LEFT of a column (its own and
  // further-right points don't count). Column 0 is always open.
  const colPoints = Array(COLS).fill(0) as number[]
  if (treeData) {
    for (const n of treeData.nodes) colPoints[n.column] += nodeStates[n.id] ?? 0
    // Reflected-box allocations are position-keyed ("col,row") — their column is the key's first field.
    if (treePrism) for (const [pos, pts] of Object.entries(treePrism.boxAllocations)) colPoints[Number(pos.split(',')[0]) || 0] += pts
  }
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

  // Node ids whose prerequisite chain a placed Prism breaks. Inverse Image: the overridden anchor + every
  // reflected-box cell (those cells are allocated client-side, never via this validator). Ethereal Prism: just
  // the overridden anchor (the box modifies the existing nodes in place — they stay normal/prereq-gated).
  const prismBrokenIds = (): string[] => {
    if (!treePrism || !treeData) return []
    const byPos: Record<string, TreeNode> = {}
    for (const n of treeData.nodes) byPos[`${n.column},${n.row}`] = n
    const anchor = byPos[`${treePrism.anchorCol},${treePrism.anchorRow}`]
    const ids = anchor ? [anchor.id] : []
    if (treePrism.kind === 'inverse_image') {
      const mc = 6 - treePrism.anchorCol, mr = 4 - treePrism.anchorRow
      for (let dc = -1; dc <= 1; dc++) for (let dr = -1; dr <= 1; dr++) {
        const cell = byPos[`${mc + dc},${mr + dr}`]
        if (cell && cell.id !== anchor?.id) ids.push(cell.id)
      }
    }
    return ids
  }

  // Ethereal Prism effect-area geometry: the NxM box (anchor-centred, clipped) and the existing nodes in it.
  const ethBoxGeom = (): { cfg?: EtherealConfig; positions: Set<string> } | null => {
    if (!treePrism || treePrism.kind !== 'ethereal_prism') return null
    const cfg = treePrism.ethereal
    const W = cfg?.boxCols, H = cfg?.boxRows
    if (!W || !H) return { cfg, positions: new Set() }   // no area-size affix → no effect box yet
    const left = Math.floor((W - 1) / 2), top = Math.floor((H - 1) / 2)
    const positions = new Set<string>()
    for (let c = treePrism.anchorCol - left; c < treePrism.anchorCol - left + W; c++)
      for (let r = treePrism.anchorRow - top; r < treePrism.anchorRow - top + H; r++) {
        if (c < 0 || c > 6 || r < 0 || r > 4) continue
        positions.add(`${c},${r}`)
      }
    return { cfg, positions }
  }
  // Box positions for an arbitrary (anchor, config) — used both for the placed prism and for repair previews.
  const boxPositionsFor = (anchorCol: number, anchorRow: number, cfg?: EtherealConfig): Set<string> => {
    const W = cfg?.boxCols, H = cfg?.boxRows
    const pos = new Set<string>()
    if (!W || !H) return pos
    const left = Math.floor((W - 1) / 2), top = Math.floor((H - 1) / 2)
    for (let c = anchorCol - left; c < anchorCol - left + W; c++)
      for (let r = anchorRow - top; r < anchorRow - top + H; r++)
        if (c >= 0 && c <= 6 && r >= 0 && r <= 4) pos.add(`${c},${r}`)
    return pos
  }
  // Over-allocation: raise the max-point cap of box nodes of the affix's tier by N. Prereq threshold untouched.
  const maxOverridesFor = (anchorCol: number, anchorRow: number, cfg?: EtherealConfig): Record<string, number> => {
    if (!cfg?.advanced || !treeData) return {}
    const m = cfg.advanced.match(/Points can be allocated to all\s+(Micro|Medium|Legendary Medium)\s+Talent.*?(\d+)\s+additional/i)
    if (!m) return {}
    const tierType = m[1] === 'Legendary Medium' ? 'Legendary Medium Talent' : `${m[1]} Talent`
    const count = Number(m[2])
    const pos = boxPositionsFor(anchorCol, anchorRow, cfg)
    const out: Record<string, number> = {}
    for (const n of treeData.nodes)
      if (pos.has(`${n.column},${n.row}`) && n.node_type === tierType) out[n.id] = n.max_points + count
    return out
  }
  const prismMaxOverrides = (): Record<string, number> =>
    treePrism?.kind === 'ethereal_prism'
      ? maxOverridesFor(treePrism.anchorCol, treePrism.anchorRow, treePrism.ethereal) : {}

  // Re-validate a node-state map after a prism's caps change (removed/edited): clamp every node to its effective
  // max, then cascade-remove any point now in a locked column or whose prereqs are no longer met. `brokenIds` =
  // node ids whose outgoing prereq is treated as satisfied (an installed prism's overridden anchor).
  const repairAllocations = (states: Record<string, number>, maxOverrides: Record<string, number>,
    brokenIds: string[] = []): Record<string, number> => {
    if (!treeData) return states
    const next = { ...states }
    const effMax = (n: TreeNode) => maxOverrides[n.id] ?? n.max_points
    for (const n of treeData.nodes) if ((next[n.id] ?? 0) > effMax(n)) next[n.id] = effMax(n)
    const incoming: Record<string, string[]> = {}
    for (const { from, to } of treeData.connections) (incoming[to] ??= []).push(from)
    const byId = Object.fromEntries(treeData.nodes.map(n => [n.id, n]))
    const broken = new Set(brokenIds)
    const thr = (n: TreeNode) => n.node_type === 'Legendary Medium Talent' ? 1 : 3
    let changed = true
    while (changed) {
      changed = false
      const colPts = Array(COLS).fill(0) as number[]
      for (const n of treeData.nodes) colPts[n.column] += next[n.id] ?? 0
      const before = (col: number) => { let s = 0; for (let c = 0; c < col; c++) s += colPts[c]; return s }
      for (const n of treeData.nodes) {
        if ((next[n.id] ?? 0) <= 0) continue
        if (n.column > 0 && before(n.column) < n.column * 3) { next[n.id] = 0; changed = true; continue }
        const inc = incoming[n.id] ?? []
        if (inc.length > 0 && !inc.every(s => broken.has(s) || (next[s] ?? 0) >= thr(byId[s]))) {
          next[n.id] = 0; changed = true
        }
      }
    }
    return next
  }
  // Extra points per column from an Inverse Image's reflected box (virtual cells) so the backend's column-unlock
  // and strand math matches the frontend. Ethereal box points live in real node_states, so nothing extra there.
  const prismExtraColumnPoints = (): Record<number, number> => {
    if (treePrism?.kind !== 'inverse_image') return {}
    const out: Record<number, number> = {}
    for (const [pos, pts] of Object.entries(treePrism.boxAllocations)) {
      const col = Number(pos.split(',')[0]) || 0
      out[col] = (out[col] ?? 0) + pts
    }
    return out
  }

  // Client-side mirror of the backend allocate/deallocate validator (models/passive_tree.py). Runs synchronously
  // so allocating a point is instant instead of awaiting a per-click round-trip — the stats recompute still
  // re-derives everything server-side in the debounced background. RULES MUST STAY IN LOCKSTEP with PassiveTree.
  const tryLocalAllocate = (
    nodeId: string, action: 'allocate' | 'deallocate',
  ): { allowed: boolean; nodeStates?: Record<string, number>; reason?: string } => {
    if (!treeData) return { allowed: false, reason: 'Tree not loaded.' }
    const byId: Record<string, TreeNode> = {}
    for (const n of treeData.nodes) byId[n.id] = n
    const node = byId[nodeId]
    if (!node) return { allowed: false, reason: 'Node not found.' }

    const broken = new Set(prismBrokenIds())
    const maxOv = prismMaxOverrides()
    const extraCol = prismExtraColumnPoints()
    const thr = (n: TreeNode) => (n.node_type === 'Legendary Medium Talent' ? 1 : 3)
    const colPtsOf = (states: Record<string, number>, col: number): number => {
      let s = extraCol[col] ?? 0
      for (const n of treeData.nodes) if (n.column === col) s += states[n.id] ?? 0
      return s
    }
    const beforeCol = (states: Record<string, number>, col: number): number => {
      let s = 0
      for (let c = 0; c < col; c++) s += colPtsOf(states, c)
      return s
    }

    if (action === 'allocate') {
      if (node.column !== 0 && beforeCol(nodeStates, node.column) < node.column * 3)
        return { allowed: false, reason: `Column ${node.column * 3} is locked — need ${node.column * 3} points in earlier columns.` }
      const effMax = maxOv[nodeId] ?? node.max_points
      const cur = nodeStates[nodeId] ?? 0
      if (cur >= effMax) return { allowed: false, reason: `'${node.node_type}' is already at max (${cur}/${effMax}).` }
      for (const { from, to } of treeData.connections) {
        if (to !== nodeId || broken.has(from)) continue
        const prereq = byId[from]
        if (prereq && (nodeStates[from] ?? 0) < thr(prereq))
          return { allowed: false, reason: `Requires the connected '${prereq.node_type}' to have ≥${thr(prereq)} pt(s) first.` }
      }
      return { allowed: true, nodeStates: { ...nodeStates, [nodeId]: cur + 1 } }
    }

    // deallocate
    const cur = nodeStates[nodeId] ?? 0
    if (cur <= 0) return { allowed: false, reason: `'${node.node_type}' already has 0 points.` }
    const after = { ...nodeStates, [nodeId]: cur - 1 }
    // Removing a point in this column can strand any column to its RIGHT that relied on it for its unlock.
    for (let col = node.column + 1; col < COLS; col++) {
      if (colPtsOf(after, col) > 0 && beforeCol(after, col) < col * 3)
        return { allowed: false, reason: `Cannot remove: column ${col * 3} requires ${col * 3} points in earlier columns.` }
    }
    // Dropping below this node's own threshold must not orphan a connected dependant.
    if (cur - 1 < thr(node) && !broken.has(nodeId)) {
      for (const { from, to } of treeData.connections) {
        if (from !== nodeId) continue
        const dep = byId[to]
        if (dep && (nodeStates[to] ?? 0) > 0)
          return { allowed: false, reason: `Cannot remove: '${dep.node_type}' depends on this node having ≥${thr(node)} pt(s).` }
      }
    }
    return { allowed: true, nodeStates: after }
  }

  const handleClick = (nodeId: string, action: 'allocate' | 'deallocate') => {
    const res = tryLocalAllocate(nodeId, action)
    if (res.allowed && res.nodeStates) {
      const ns = res.nodeStates
      setNodeStates(ns)
      if (!previewMode) updateSlotNodeStates(activeSlot, ns)
      if (treeData && Object.keys(coreTalentSelections).length > 0) {
        const newTotal = sumPoints(ns)
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
      flash(res.reason ?? (action === 'allocate'
        ? 'Cannot allocate — check column unlock & prerequisites.'
        : 'Cannot remove — would break a prerequisite.'))
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

  // Dismiss the open core-talent menu on any click outside it (e.g. opening the prism menu, clicking a node).
  // Uses 'click' (not 'mousedown') so it fires ALONGSIDE the clicked control's own handler rather than
  // pre-empting it — otherwise the first click would only close the menu and the button itself wouldn't fire.
  useEffect(() => {
    if (expandedSlot === null) return
    const onClickAway = (e: MouseEvent) => {
      const t = e.target as HTMLElement
      if (t.closest?.('.core-talent-cards') || t.closest?.('.core-talent-circle')) return
      setExpandedSlot(null)
    }
    document.addEventListener('click', onClickAway)
    return () => document.removeEventListener('click', onClickAway)
  }, [expandedSlot])

  // Core-talent widget (circles + Floating dropdown) — shared by the normal and preview headers.
  // Part A (visual only): how a placed Ethereal Prism affects this tree's Core Talent. The actual swap/effects
  // resolve in the engine (Plan B); here we just surface it, gated by the same point threshold.
  // Split a run-on talent description into one line per effect clause (break before each '+N'/'-N').
  const splitEffectLines = (text: string): string[] =>
    text ? text.trim().split(/\s+(?=[+-]\d)/).map(s => s.trim()).filter(Boolean) : []

  const ethCoreInfo = (): { label: string; talentName: string; lines: string[] } | null => {
    if (!treePrism || treePrism.kind !== 'ethereal_prism' || !treePrism.ethereal) return null
    const e = treePrism.ethereal
    if (/effects of Random Affixes/i.test(e.implicit)) return null   // Phantasmagoria amplify — no Core Talent change
    const dnr = !!e.advanced && /no longer replace the original talent/i.test(e.advanced)
    const catItem = etherealCat?.items.find(i => i.short_name === e.shortName)
    if (/^Replaces the Core Talent/i.test(e.implicit)) {
      const desc = catItem?.replace_description || (dnr
        ? 'Added as an extra box below the original Core Talent.'
        : 'Replaces the selected Core Talent at the threshold.')
      return { label: dnr ? 'Adds Core Talent (Do-Not-Replace)' : 'Replaces Core Talent',
        talentName: e.shortName, lines: splitEffectLines(desc) }
    }
    if (/^Adds an additional effect/i.test(e.implicit)) {
      const i = e.implicit.indexOf('Advanced Talent Panel:')
      const effect = (i >= 0 ? e.implicit.slice(i + 'Advanced Talent Panel:'.length) : e.implicit).trim()
      return { label: 'Adds an effect to the Core Talent', talentName: '', lines: splitEffectLines(effect) }
    }
    return null
  }
  const ethCore = ethCoreInfo()
  const ethCoreThreshold = treeData?.core_talent_slots[0]?.threshold ?? 24
  const ethCoreActive = total >= ethCoreThreshold
  const ethRare = treePrism?.kind === 'ethereal_prism' && treePrism.ethereal?.rarity === 'rare'

  // Whether the engine actually models this prism's Core-Talent effect (status comes back as resolved/unresolved).
  // Drives an honest "In DPS" / "Not modeled (NYI)" badge so an unmodeled replacement never looks active.
  const ethPrismStatus = treePrism?.kind === 'ethereal_prism' && treePrism.ethereal
    ? (coreTalentStatuses ?? []).find(st => st.name === `${treePrism.ethereal!.shortName} (Prism)`)
    : undefined
  const ethModeled = ethPrismStatus?.resolved === true

  // Prism effect banner shown INSIDE the expanded core-talent panel (not as a header note — that squished the tree).
  // Width-constrained (won't widen the panel past the 4 cards) and each effect clause on its own wrapped line.
  const ethCoreBanner = ethCore ? (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '8px 10px', marginBottom: 8,
      border: `1px solid ${ethRare ? '#7a4ea0' : '#5a4a2a'}`, borderRadius: 6, background: '#161426', fontSize: 12,
      maxWidth: 670, boxSizing: 'border-box' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ color: ethRare ? '#c79bff' : '#e9c046', fontWeight: 600 }}>◈ {ethCore.label}</span>
        {ethCoreActive && (
          <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 4,
            background: ethModeled ? 'rgba(107,203,119,0.15)' : 'rgba(255,107,107,0.15)',
            color: ethModeled ? '#6bcb77' : '#ff6b6b' }}>
            {ethModeled ? 'In DPS' : 'Not modeled (NYI)'}
          </span>
        )}
        <span style={{ marginLeft: 'auto', color: ethCoreActive ? '#6bcb77' : '#888' }}>
          {ethCoreActive ? 'Active' : `${Math.min(total, ethCoreThreshold)}/${ethCoreThreshold}`}
        </span>
      </div>
      {ethCore.talentName && (
        <div style={{ color: '#e9e0ff', fontWeight: 600, fontSize: 13 }}>{ethCore.talentName}</div>
      )}
      <div style={{ color: '#9aa', lineHeight: 1.4, display: 'flex', flexDirection: 'column', gap: 1 }}>
        {ethCore.lines.map((ln, i) => <div key={i} style={{ wordBreak: 'break-word' }}>{ln}</div>)}
      </div>
    </div>
  ) : null

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
                    {ethCoreBanner}
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
            {/* Hidden while placing a prism so the placement banner can't overlap (and be clicked through to) these. */}
            {!placingPrism && <>
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
              {!isPrimary(treeName) && (
                <button
                  className="btn btn-sm"
                  style={{ marginLeft: 14, background: '#241a3a', color: '#c79bff' }}
                  onClick={() => { setPlacingPrism(null); setExpandedSlot(null); setPrismOverlayOpen(true) }}
                  title="Craft and install prisms"
                >◈ Add Prism</button>
              )}
            </>}
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

  // ── Prism reflection geometry ──────────────────────────────────────────────
  // Inverse Image: point-reflect through the tree centre (3,2): mirror(c,r)=(6−c,4−r). The prism's 3×3 box
  // is the SOURCE (unmodified); the reflected box's cells show COPIES of the source nodes. The central 3×3
  // (cols 2-4 × rows 1-3) is locked (a box and its image overlap there). Plan 1 = visuals + allocation, no DPS.
  const nodeByPos: Record<string, TreeNode> = {}
  for (const n of treeData.nodes) nodeByPos[`${n.column},${n.row}`] = n
  const inCentralLock = (c: number, r: number) => c >= 2 && c <= 4 && r >= 1 && r <= 3
  const isPrimaryTree = isPrimary(treeName)

  // For the placed prism: the anchor node id + a map of reflected-cell node id → its SOURCE node (the
  // point-reflected primary-box node it copies). Keyed by NODE ID so the normal node map + connections can
  // reliably skip/break by id (a position lookup desynced when the box clipped at edges).
  const anchorNode = treePrism ? nodeByPos[`${treePrism.anchorCol},${treePrism.anchorRow}`] : undefined
  const anchorId = anchorNode?.id
  const isInversePlaced = treePrism?.kind === 'inverse_image'
  const isEtherealPlaced = treePrism?.kind === 'ethereal_prism'
  // Inverse Image reflected box = 3×3 around mirror(anchor), clipped. EVERY cell in it is replaced: a copy of
  // its mirror-source (primary-box node) when that source exists, or EMPTY (existing node deleted) otherwise.
  const reflCells: { col: number; row: number; src: TreeNode | null }[] = []
  const reflectedPositions = new Set<string>()
  if (treePrism && isInversePlaced) {
    const mc = 6 - treePrism.anchorCol, mr = 4 - treePrism.anchorRow
    for (let dc = -1; dc <= 1; dc++) for (let dr = -1; dr <= 1; dr++) {
      const rc = mc + dc, rr = mr + dr
      if (rc < 0 || rc > 6 || rr < 0 || rr > 4) continue
      if (rc === treePrism.anchorCol && rr === treePrism.anchorRow) continue   // never overlaps the anchor (central locked)
      reflCells.push({ col: rc, row: rr, src: nodeByPos[`${6 - rc},${4 - rr}`] ?? null })
      reflectedPositions.add(`${rc},${rr}`)
    }
  }
  // Ethereal effect-area box: the existing nodes inside the NxM box (modify-in-place; stay normal nodes).
  const ethGeom = isEtherealPlaced ? ethBoxGeom() : null
  const ethBoxPositions = ethGeom?.positions ?? new Set<string>()
  const ethBoxNodeIds = new Set(
    treeData ? treeData.nodes.filter(n => ethBoxPositions.has(`${n.column},${n.row}`)).map(n => n.id) : [])
  const ethMaxOverrides = isEtherealPlaced ? prismMaxOverrides() : {}
  // A node id is "prism-handled" (skipped from the normal tree + its connections broken) when it's the overridden
  // anchor, or — for Inverse Image only — a reflected-region cell. Ethereal box nodes stay as normal nodes.
  const isPrismHandledId = (id: string): boolean => {
    if (!treePrism) return false
    if (id === anchorId) return true
    if (isInversePlaced) { const n = nodeMap[id]; return !!n && reflectedPositions.has(`${n.column},${n.row}`) }
    return false
  }

  const canPlaceOn = (n: TreeNode): boolean => {
    if (isPrimaryTree) return false
    if (placingPrism?.kind === 'inverse_image')
      // Inverse Image: 1 total, central 3×3 locked.
      return !inCentralLock(n.column, n.row) && !prisms.some(p => p.kind === 'inverse_image' && p.treeName !== treeName)
    if (placingPrism?.kind === 'ethereal_prism')
      // Ethereal: 1 total, no central lock.
      return !prisms.some(p => p.kind === 'ethereal_prism' && p.treeName !== treeName)
    return false
  }

  // Ethereal placement clears the anchor + every allocated node reachable forward from it (those that depended on
  // the anchor as a prereq), since the anchor is now overridden. The rest of the tree is left untouched.
  const clearDownstreamOfAnchor = (rootId: string): Record<string, number> => {
    const next = { ...nodeStates }
    const fwd: Record<string, string[]> = {}
    for (const { from, to } of (treeData?.connections ?? [])) (fwd[from] ??= []).push(to)
    const queue = [rootId]; const seen = new Set<string>([rootId])
    while (queue.length) {
      const id = queue.shift()!
      next[id] = 0
      for (const nb of (fwd[id] ?? [])) if (!seen.has(nb)) { seen.add(nb); queue.push(nb) }
    }
    return next
  }

  const placePrismAt = (n: TreeNode) => {
    if (!placingPrism) return
    if (!canPlaceOn(n)) {
      const onOther = prisms.find(p => p.kind === placingPrism.kind && p.treeName !== treeName)
      const why = isPrimaryTree ? 'primary trees cannot host prisms'
        : placingPrism.kind === 'inverse_image' && inCentralLock(n.column, n.row) ? 'that cell is in the locked centre'
        : onOther ? `only one ${placingPrism.kind === 'inverse_image' ? 'Inverse Image' : 'Ethereal Prism'} can be installed — remove the one on "${onOther.treeName}" first`
        : 'cannot place there'
      setStatus({ msg: `Cannot place: ${why}.`, ok: false })
      return
    }
    const placed: PlacedPrism = {
      id: `${Date.now()}-${Math.floor(performance.now() * 1000) % 1000000}`,
      templateId: placingPrism.id, kind: placingPrism.kind, name: placingPrism.name,
      iconUrl: placingPrism.iconUrl, rolls: placingPrism.rolls, ethereal: placingPrism.ethereal,
      treeName, anchorCol: n.column, anchorRow: n.row, boxAllocations: {},
    }
    if (placingPrism.kind === 'inverse_image') {
      // resetOnPlace: wipe this tree's allocations (column-point math shifts with the reflection).
      const cleared = Object.fromEntries(Object.keys(nodeStates).map(k => [k, 0]))
      setNodeStates(cleared)
      updateSlotNodeStates(activeSlot, cleared)
      setStatus({ msg: `Placed ${placed.name}. Tree reset; reflected nodes are prerequisite-free.`, ok: true })
    } else {
      // Ethereal: clear only the anchor + nodes downstream of it; keep the rest of the tree.
      const next = clearDownstreamOfAnchor(n.id)
      setNodeStates(next)
      updateSlotNodeStates(activeSlot, next)
      setStatus({ msg: `Placed ${placed.name}. Anchor overridden; downstream nodes cleared.`, ok: true })
    }
    setPrisms([...prisms.filter(p => p.treeName !== treeName), placed])
    setPlacingPrism(null)
  }

  const removePrism = () => {
    if (!treePrism) return
    if (treePrism.kind === 'inverse_image') {
      const cleared = Object.fromEntries(Object.keys(nodeStates).map(k => [k, 0]))
      setNodeStates(cleared)
      updateSlotNodeStates(activeSlot, cleared)
      setStatus({ msg: 'Prism removed; tree reset.', ok: true })
    } else {
      // Ethereal: prism gone → no over-alloc caps, no broken anchor. Clamp every node to its normal max and
      // cascade-remove anything now in a locked column or with an unmet prereq (over-alloc points that were
      // unlocking later columns are refunded, and their now-stranded dependents come off too).
      const next = repairAllocations(nodeStates, {}, [])
      setNodeStates(next)
      updateSlotNodeStates(activeSlot, next)
      setStatus({ msg: 'Prism removed; over-allocated points refunded.', ok: true })
    }
    setPrisms(prisms.filter(p => p.id !== treePrism.id))
  }

  // Allocate into a reflected copy (keyed by position — cells can be empty grid slots). Connection prereqs are
  // broken; only the column threshold applies.
  const allocateReflected = (col: number, row: number, src: TreeNode, add: boolean) => {
    if (!treePrism) return
    const key = `${col},${row}`
    const cur = treePrism.boxAllocations[key] ?? 0
    if (add) {
      if (!isColUnlocked(col)) { setStatus({ msg: `Need ${col * 3} pts in earlier columns.`, ok: false }); return }
      if (cur >= src.max_points) return
    } else if (cur <= 0) return
    const next = { ...treePrism.boxAllocations, [key]: cur + (add ? 1 : -1) }
    if (next[key] <= 0) delete next[key]
    setPrisms(prisms.map(p => p.id === treePrism.id ? { ...p, boxAllocations: next } : p))
  }

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
                // Prism breaks prerequisites: drop connection lines touching the anchor or any reflected copy.
                if (isPrismHandledId(from) || isPrismHandledId(to)) return null
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
                // Nodes the prism overrides (anchor) or copies (reflected box) are drawn in the prism layer below.
                if (isPrismHandledId(node.id)) return null
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
                    onInteract={placingPrism ? (n => placePrismAt(n)) : handleNodeInteract}
                    maxOverride={ethMaxOverrides[node.id]}
                    inPrismBox={ethBoxNodeIds.has(node.id)}
                  />
                )
              })}

              {/* Prism layer: box outlines (white, like in-game) + anchor prism + (Inverse Image) reflected copies */}
              {treePrism && (() => {
                // A rounded box outline spanning a 3×3 around (cc,cr), clipped to the grid (Inverse Image).
                const boxRect = (cc: number, cr: number, key: string) => {
                  const x = nodeX(Math.max(0, cc - 1)) - NODE_R - 6
                  const x2 = nodeX(Math.min(6, cc + 1)) + NODE_R + 6
                  const y = nodeY(Math.max(0, cr - 1)) - NODE_R - 6
                  const y2 = nodeY(Math.min(4, cr + 1)) + NODE_R + 6
                  return <rect key={key} x={x} y={y} width={x2 - x} height={y2 - y} rx={12}
                    fill="none" stroke="#ffffff" strokeWidth={1.5} strokeDasharray="6 4" opacity={0.55} />
                }
                // A box outline spanning an arbitrary set of cell positions (Ethereal effect area).
                const spanRect = (positions: Set<string>, key: string) => {
                  if (positions.size === 0) return null
                  const cs = [...positions].map(p => Number(p.split(',')[0]))
                  const rs = [...positions].map(p => Number(p.split(',')[1]))
                  const x = nodeX(Math.min(...cs)) - NODE_R - 6, x2 = nodeX(Math.max(...cs)) + NODE_R + 6
                  const y = nodeY(Math.min(...rs)) - NODE_R - 6, y2 = nodeY(Math.max(...rs)) + NODE_R + 6
                  return <rect key={key} x={x} y={y} width={x2 - x} height={y2 - y} rx={12}
                    fill="none" stroke="#ffffff" strokeWidth={1.5} strokeDasharray="6 4" opacity={0.55} />
                }
                return (
                  <>
                    {isInversePlaced && boxRect(treePrism.anchorCol, treePrism.anchorRow, 'pbox')}
                    {isInversePlaced && boxRect(6 - treePrism.anchorCol, 4 - treePrism.anchorRow, 'rbox')}
                    {isEtherealPlaced && spanRect(ethBoxPositions, 'ebox')}
                    {anchorNode && (
                      <PrismAnchorG prism={treePrism} cx={nodeX(anchorNode.column)} cy={nodeY(anchorNode.row)}
                        onEdit={() => { setEditingPlaced(treePrism); setPrismOverlayOpen(true) }}
                        onRemove={removePrism} />
                    )}
                    {reflCells.map(({ col, row, src }) => {
                      if (!src) return null    // mirror source empty → this reflected cell is empty (deleted)
                      const key = `${col},${row}`
                      return (
                        <ReflectedNodeG key={`refl-${key}`} col={col} row={row} src={src} posKey={key}
                          pts={treePrism.boxAllocations[key] ?? 0}
                          unlocked={isColUnlocked(col)}
                          mult={prismMult(treePrism.rolls, src.node_type)}
                          prismId={treePrism.id}
                          onAlloc={add => allocateReflected(col, row, src, add)} />
                      )
                    })}
                  </>
                )
              })()}

              {/* Placement mode: highlight valid drop cells */}
              {placingPrism && treeData.nodes.map(node => {
                const ok = canPlaceOn(node)
                const cx = nodeX(node.column), cy = nodeY(node.row)
                return (
                  <circle key={`place-${node.id}`} cx={cx} cy={cy} r={NODE_R + 3}
                    fill={ok ? 'rgba(150,110,255,0.12)' : 'rgba(255,80,80,0.06)'}
                    stroke={ok ? 'rgba(180,140,255,0.8)' : 'rgba(255,80,80,0.3)'}
                    strokeWidth={2} strokeDasharray="5 3"
                    style={{ cursor: ok ? 'pointer' : 'not-allowed' }}
                    onMouseEnter={() => setHoverPlaceCell({ col: node.column, row: node.row })}
                    onMouseLeave={() => setHoverPlaceCell(c => (c && c.col === node.column && c.row === node.row) ? null : c)}
                    onClick={() => placePrismAt(node)} />
                )
              })}

              {/* Placement preview: ghost box(es) + the prism icon at the hovered cell. */}
              {placingPrism && hoverPlaceCell &&
                !(placingPrism.kind === 'inverse_image' && inCentralLock(hoverPlaceCell.col, hoverPlaceCell.row)) && (() => {
                const a = hoverPlaceCell
                const eth = placingPrism.kind === 'ethereal_prism' ? placingPrism.ethereal : undefined
                const ghostBox = (cc: number, cr: number, key: string) => {
                  const x = nodeX(Math.max(0, cc - 1)) - NODE_R - 6
                  const x2 = nodeX(Math.min(6, cc + 1)) + NODE_R + 6
                  const y = nodeY(Math.max(0, cr - 1)) - NODE_R - 6
                  const y2 = nodeY(Math.min(4, cr + 1)) + NODE_R + 6
                  return <rect key={key} x={x} y={y} width={x2 - x} height={y2 - y} rx={12}
                    fill="rgba(255,255,255,0.04)" stroke="#ffffff" strokeWidth={1.5} strokeDasharray="6 4"
                    opacity={0.8} style={{ pointerEvents: 'none' }} />
                }
                // Ethereal: a single NxM ghost box (anchor-centred, clipped) around the hovered cell. No size → no box.
                const ghostSpan = (key: string) => {
                  const W = eth?.boxCols, H = eth?.boxRows
                  if (!W || !H) return null
                  const left = Math.floor((W - 1) / 2), top = Math.floor((H - 1) / 2)
                  const c0 = Math.max(0, a.col - left), c1 = Math.min(6, a.col - left + W - 1)
                  const r0 = Math.max(0, a.row - top), r1 = Math.min(4, a.row - top + H - 1)
                  const x = nodeX(c0) - NODE_R - 6, x2 = nodeX(c1) + NODE_R + 6
                  const y = nodeY(r0) - NODE_R - 6, y2 = nodeY(r1) + NODE_R + 6
                  return <rect key={key} x={x} y={y} width={x2 - x} height={y2 - y} rx={12}
                    fill="rgba(255,255,255,0.04)" stroke="#ffffff" strokeWidth={1.5} strokeDasharray="6 4"
                    opacity={0.8} style={{ pointerEvents: 'none' }} />
                }
                const acx = nodeX(a.col), acy = nodeY(a.row)
                const rare = eth?.rarity === 'rare'
                return (
                  <g style={{ pointerEvents: 'none' }}>
                    {placingPrism.kind === 'inverse_image' ? (
                      <>{ghostBox(a.col, a.row, 'gp')}{ghostBox(6 - a.col, 4 - a.row, 'gr')}</>
                    ) : ghostSpan('ges')}
                    <clipPath id="ghost-prism-clip"><circle cx={acx} cy={acy} r={NODE_R - 2} /></clipPath>
                    <circle cx={acx} cy={acy} r={NODE_R} fill="#1a1326" stroke={rare ? '#c79bff' : '#e9c046'} strokeWidth={3} opacity={0.85} />
                    <image href={iconUrl('prism', placingPrism.iconUrl) ?? undefined}
                      x={acx - NODE_R + 2} y={acy - NODE_R + 2} width={(NODE_R - 2) * 2} height={(NODE_R - 2) * 2}
                      clipPath="url(#ghost-prism-clip)"
                      style={{ filter: rare && eth?.tintWhenRare ? RARE_TINT : undefined }} opacity={0.85} />
                  </g>
                )
              })()}
            </svg>
          </div>

          <div className="viewer-status" style={{ color: status?.ok ? '#6bcb77' : '#ff6b6b' }}>
            {status?.msg ?? ''}
          </div>

        </div>
      </div>

      {/* Prism placement banner */}
      {placingPrism && (
        <div style={{ position: 'absolute', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 35,
          background: '#241a3a', border: '1px solid #6a4a9a', borderRadius: 8, padding: '8px 14px',
          display: 'flex', alignItems: 'center', gap: 12, color: '#d8c8ff', fontSize: 13 }}>
          <span>Placing <strong>{placingPrism.name}</strong> — click a highlighted node{isPrimaryTree ? ' (not available on a primary tree)' : ''}.</span>
          <button className="btn btn-sm" style={{ background: '#3a2a4a', color: '#ccaaff' }}
            onClick={() => setPlacingPrism(null)}>Cancel</button>
        </div>
      )}

      {/* Prism inventory / craft overlay */}
      {prismOverlayOpen && (
        <PrismOverlay
          items={prismCatalog}
          ethereal={etherealCat}
          inventory={prismInventory}
          setInventory={setPrismInventory}
          onPlace={p => { setPrismOverlayOpen(false); setEditingPlaced(null); setPlacingPrism(p) }}
          onClose={() => { setPrismOverlayOpen(false); setEditingPlaced(null) }}
          editPlaced={editingPlaced}
          onUpdatePlaced={patch => {
            if (!treePrism) return
            setPrisms(prisms.map(p => p.id === treePrism.id ? { ...p, ...patch } : p))
            // If the prism's box/over-alloc changed, re-validate allocations against the NEW caps (a shrunk
            // box or removed over-alloc affix must drop now-illegal points + cascade their dependents).
            if (patch.ethereal && treeData) {
              const overrides = maxOverridesFor(treePrism.anchorCol, treePrism.anchorRow, patch.ethereal)
              const next = repairAllocations(nodeStates, overrides, anchorId ? [anchorId] : [])
              setNodeStates(next)
              if (!previewMode) updateSlotNodeStates(activeSlot, next)
            }
          }}
          onRemovePlaced={removePrism}
        />
      )}

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
