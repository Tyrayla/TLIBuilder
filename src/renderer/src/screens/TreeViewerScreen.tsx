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
import {
  useDamageDelta, withNodePoints, withPrismBoxPoints, withNodeStatesMap, type LabeledDelta,
} from '../components/tooltip/useDamageDelta'
import { nodeThreshold, diffAdded, diffRemoved, nodeStatesSignature } from '../utils/passiveTreeDiff'

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
// The allocation arc is gone (2026-07-16 restructure) — allocation is now the node's FILL PROPORTION itself
// (see bodyFill/the fill-wipe rect in TreeNodeG), and the rarity ring alone owns the outer border, bolder
// than it's ever been now that it isn't sharing radius with a meter. Three channels, three meanings, zero
// overlap: fill = points, ring = rarity, connectors = path open/closed.
// Node body / neutral-dark tokens (Task 3b): the OLD unallocated fill (#0e1230) was ~55% saturated blue-violet
// — competing with the violet meter instead of receding behind it. Desaturated toward near-neutral dark so the
// violet fill (unchanged hue, #533483) is the only saturated thing in the node.
const NODE_EMPTY_FILL = '#1c1c24'
// Prism marker + search halo: STATIC per-node indicators (shown for however many nodes qualify, not
// hover-gated), so these are the ones the "bullseye" complaint was actually about — pulled back in now
// that there's no thick arc to clear (was +10/+13 to clear a 5px arc; the ring alone only needs +1.75px
// of clearance over its own bolder-but-still-modest stroke).
const PRISM_MARK_R = NODE_R + 5
const SEARCH_HALO_R = NODE_R + 8
// Hover preview rings sit OUTSIDE those — they're transient/hover-only (at most one or two nodes at a time),
// so a touch more radius here doesn't reinstate the permanent-bullseye problem. Two dedicated, non-overlapping
// radii so a node that's BOTH previewable-forward (green) and previewable-in-a-cascade (red) at once — a
// partial (not-full) node whose direct deallocate is blocked (a column-strand dependency today; a threshold
// break too, if a shipped tree ever gives a node a threshold below its max_points — see the reversePreview
// comment below and utils/passiveTreeDiff.ts's nodeThreshold doc) — shows both without either winning a
// color tie-break. The common single-preview case uses the inner radius; the outer slot is only reached
// when both are active on the same node simultaneously.
const PREVIEW_R = NODE_R + 11
const PREVIEW_R_OUTER = NODE_R + 14

function nodeX(col: number) { return col * CELL_W + CELL_W / 2 }
function nodeY(row: number) { return HEADER + row * CELL_H + CELL_H / 2 }
function sumPoints(states: Record<string, number>) {
  return Object.values(states).reduce((a, b) => a + b, 0)
}
// nodeThreshold/diffAdded/diffRemoved live in utils/passiveTreeDiff.ts (extracted so they're independently
// unit-testable — see that file's header for the nodeThreshold/max_points independence note). Single
// definition; allocPrimitives/repairAllocations/the hover preview below all call the imported versions.

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

// Only the text color was ever consumed downstream (the node-body fill/border are computed inline in
// TreeNodeG, from `locked`/`pts`/`full` directly) — this used to also return a dead fill/stroke pair from
// a third, unused palette; trimmed to the one thing anyone reads.
function nodeTextColor(node: TreeNode, states: Record<string, number>, locked: boolean): string {
  const pts = states[node.id] ?? 0
  const full = pts >= node.max_points
  return locked ? '#444455' : full ? '#ffffff' : '#e0e0e0'
}

type DebugTool = 'create' | 'type' | 'link'

// A hypothetical multi-node change the hover preview is pricing — a forward "path-to-here" allocation, or
// a reverse cascade removal. `after` is the COMPLETE resulting node-states map (for withNodeStatesMap);
// `changed` is the diff (added or removed points) keyed by node id, purely for ring/connector membership.
interface TreePreview { after: Record<string, number>; changed: Record<string, number>; cost: number }

interface TreeNodeGProps {
  node: TreeNode
  cx: number
  cy: number
  pts: number
  textColor: string
  locked: boolean
  isLinkSrc: boolean
  isHit: boolean
  isSearching: boolean
  processing: boolean
  debugMode: boolean
  onInteract: (node: TreeNode, isRight: boolean) => void
  maxOverride?: number      // raised cap from an Ethereal Prism's over-allocation affix
  inPrismBox?: boolean      // node sits inside a placed Ethereal Prism's effect area
  previewAdd?: boolean      // this node would gain points under the currently-hovered forward preview
  previewRemove?: boolean   // this node would lose points under the currently-hovered reverse cascade preview
  // Non-null ONLY for the node whose id === hoveredNodeId (the render-site call narrows every other node
  // to `null` — 2026-07-16 perf fix, see the render-site comment). Two benefits: (1) React.memo sees a
  // stable `null` reference for the 34 non-hovered nodes across a hover-only re-render instead of a fresh
  // shared TreePreview object every tick, and (2) it retires a suspected race the correctness review raised
  // — this used to be the SAME object passed to every node, gated only by that node's OWN tip.open, which
  // assumed at most one node's tooltip could be open at once; now a node whose local tip.open is transiently
  // true but whose id no longer matches hoveredNodeId (e.g. mid mouse-cross between two adjacent nodes)
  // gets `null` here regardless, so showForward/showReverse (which also require `!!forwardPreview`) can't
  // price or display its neighbor's preview even in that frame.
  forwardPreview?: TreePreview | null
  reversePreview?: TreePreview | null
  onHoverChange: (id: string, open: boolean) => void
}

// A single passive-tree node (SVG group) plus its hover tooltip, routed through the shared
// floating-tooltip primitive. Element-anchored; damage-delta band wired (NYI until backend).
//
// Wrapped in React.memo: hover state used to be local to each node's own useFloatingTooltip, but it's now
// lifted to the parent (hoveredNodeId, tracked via onHoverChange below) so the connector <line>s can know
// which edges belong to the previewed path/cascade — which means the PARENT re-renders on every hover
// transition, recreating props for all 35 nodes. The parent only passes a non-null forwardPreview/
// reversePreview to the ONE node that's actually hovered (see the render-site call below) — every other
// node always gets the same `null` reference for both — so memo's default shallow-prop comparison is
// enough to skip the other 34 on a hover-only re-render (previewAdd/previewRemove are already primitive
// booleans, so those compare fine on their own).
function TreeNodeGImpl({
  node, cx, cy, pts, textColor, locked, isLinkSrc, isHit, isSearching, processing, debugMode, onInteract,
  maxOverride, inPrismBox, previewAdd, previewRemove, forwardPreview, reversePreview, onHoverChange,
}: TreeNodeGProps) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right' })
  const activeSlot = useBuildStore(s => s.activeSlot)
  // Tell the parent when THIS node is the hovered one (tied to the same floating-ui hover state that opens
  // the tooltip, not a separate mouseenter listener, so the two can never desync). The functional guard in
  // the parent's setter (`cur === id ? null : cur`) protects against a stale close firing after a new node's
  // open when the mouse crosses two adjacent nodes.
  useEffect(() => { onHoverChange(node.id, tip.open) }, [tip.open, node.id, onHoverChange])
  const maxPts = maxOverride ?? node.max_points     // Ethereal over-allocation raises the cap
  const full = pts >= maxPts
  const icon = iconUrl('talent_tree', node.icon_url)
  // Rarity ring = the node border (white micro / blue medium / orange legendary), the ONLY thing the outer
  // ring carries now that allocation moved to the fill itself — always shown, even on locked nodes, so
  // rarity reads at a glance regardless of allocation state.
  const rarityColor = RARITY_RING_COLOR[node.node_type] ?? RARITY_RING_COLOR.default
  const frac = maxPts > 0 ? Math.min(1, pts / maxPts) : 0

  // Marginal delta: normally a plain ±1 step (current behavior, preserved as the fallback for a fully-maxed
  // node whose single point can be legally refunded — no path/cascade applies there). When a forward path or
  // a real reverse cascade IS being previewed, price that instead — a multi-node change can span more than
  // one rank, so the ±1 step would silently under/over-report it (see bug-139: base+step must always be
  // priced from the SAME states, exactly one hypothetical apart — a multi-node path needs its own transform,
  // not the single-node one, to keep that guarantee).
  const showForward = tip.open && !!forwardPreview
  const showReverse = tip.open && !!reversePreview
  // Cache key: a signature of the resulting AFTER map, not the scalar point-cost — two different paths to
  // the same node can cost the same total points while landing on different node-state maps (especially in
  // previewMode, where in-place nodeStates edits never bump buildVersion), so a cost-only key would let the
  // second hover silently reuse the first's stale delta (bug-tree-hover-preview-cost-keyed-cache-collision).
  const forwardDelta = useDamageDelta(
    showForward ? {
      key: `nodepath:${activeSlot}:${node.id}:${nodeStatesSignature(forwardPreview!.after)}`,
      step: s => withNodeStatesMap(s, activeSlot, forwardPreview!.after),
    } : null,
    showForward,
  )
  const reverseDelta = useDamageDelta(
    showReverse ? {
      key: `nodecascade:${activeSlot}:${node.id}:${nodeStatesSignature(reversePreview!.after)}`,
      step: s => withNodeStatesMap(s, activeSlot, reversePreview!.after),
    } : null,
    showReverse,
  )
  const fallbackDelta = useDamageDelta(
    tip.open && !showForward && !showReverse ? {
      key: `node:${activeSlot}:${node.id}`,
      step: s => {
        const cur = s.slots[activeSlot]?.nodeStates?.[node.id] ?? 0
        const tgt = cur < maxPts ? cur + 1 : Math.max(0, cur - 1)
        return withNodePoints(s, activeSlot, node.id, tgt)
      },
    } : null,
    tip.open && !showForward && !showReverse,
  )
  const labeledDeltas: LabeledDelta[] = []
  if (showForward) {
    labeledDeltas.push({ label: `+${forwardPreview!.cost} pt${forwardPreview!.cost === 1 ? '' : 's'}`, delta: forwardDelta })
  }
  if (showReverse) {
    labeledDeltas.push({ label: `-${reversePreview!.cost} pt${reversePreview!.cost === 1 ? '' : 's'}`, delta: reverseDelta })
  }
  // Node body: the EMPTY color underneath the fill-wipe (drawn just below). `locked` (column-gated) stays its
  // own dark shade regardless of point count — an access state, not a fill state.
  const bodyFill = locked ? '#191925' : NODE_EMPTY_FILL
  // Preview ring radii: both get their OWN dedicated slot (no color-precedence tie-break) — see PREVIEW_R /
  // PREVIEW_R_OUTER above. A node that's simultaneously reachable-forward AND would cascade in reverse (not
  // full, and its own direct deallocate is blocked — a column-strand dependency today) shows both, red inner /
  // green outer, rather than one hiding the other.
  const bothPreview = !!previewAdd && !!previewRemove
  const removeRingR = PREVIEW_R
  const addRingR = bothPreview ? PREVIEW_R_OUTER : PREVIEW_R
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
          <circle cx={cx} cy={cy} r={SEARCH_HALO_R}
            fill="rgba(233,192,70,0.12)"
            stroke="#e9c046"
            strokeWidth={2}
            style={{ pointerEvents: 'none' }}
          />
        )}
        {/* Inside a placed Ethereal Prism's effect area: a violet marker ring (modify-in-place). */}
        {inPrismBox && (
          <circle cx={cx} cy={cy} r={PRISM_MARK_R} fill="none" stroke="#c79bff" strokeWidth={1.5}
            strokeDasharray="3 3" opacity={0.55} style={{ pointerEvents: 'none' }} />
        )}
        {/* Hover preview rings: green = this node would GAIN points via the forward path-to-here preview,
            red = it would LOSE points via the reverse cascade preview (real cascades only — see
            reversePreview's gating in the parent). Both can render at once (see bothPreview above) —
            separate radii so one never hides the other. */}
        {previewRemove && (
          <circle cx={cx} cy={cy} r={removeRingR} fill="none"
            stroke="#e94560" strokeWidth={1.5}
            style={{ pointerEvents: 'none' }}
          />
        )}
        {previewAdd && (
          <circle cx={cx} cy={cy} r={addRingR} fill="none"
            stroke="#6be946" strokeWidth={1.5}
            style={{ pointerEvents: 'none' }}
          />
        )}
        {/* Node body: EMPTY base circle (locked shade, or the desaturated near-neutral NODE_EMPTY_FILL) plus,
            when unlocked, a bottom-up violet WIPE clipped to the same circle — the fill level IS the meter now
            (replaces the old separate progress arc). Border is the rarity ring, alone on its radius. */}
        <circle cx={cx} cy={cy} r={NODE_R}
          fill={isLinkSrc ? '#2a4a2a' : bodyFill}
          stroke={isLinkSrc ? '#6be946' : rarityColor}
          strokeWidth={node.node_type === 'Legendary Medium Talent' ? 5 : 4}
        />
        {!locked && pts > 0 && (
          <>
            <clipPath id={`nfill-${node.id}`}><circle cx={cx} cy={cy} r={NODE_R} /></clipPath>
            {/* Height = frac of the full diameter, anchored to the bottom of the circle; the clip truncates it
                into a level "liquid" line inside the circular vessel instead of a literal rectangle. */}
            <rect
              x={cx - NODE_R} y={cy + NODE_R - 2 * NODE_R * frac}
              width={NODE_R * 2} height={2 * NODE_R * frac + 1}
              fill="#533483"
              clipPath={`url(#nfill-${node.id})`}
              style={{ pointerEvents: 'none' }}
            />
          </>
        )}
        {icon && (
          <>
            <clipPath id={`nclip-${node.id}`}><circle cx={cx} cy={cy} r={NODE_R - 3} /></clipPath>
            <image
              href={icon}
              x={cx - (NODE_R - 3)} y={cy - (NODE_R - 3)}
              width={(NODE_R - 3) * 2} height={(NODE_R - 3) * 2}
              clipPath={`url(#nclip-${node.id})`}
              preserveAspectRatio="xMidYMid slice"
              // Locked/empty stay dimmed. Maxed is fully opaque (solid violet behind it, no boundary to muddy).
              // Partial (1..maxPts-1) is bumped up from the old flat 0.5 to 0.75 — the fill boundary now passes
              // BEHIND the icon at those ranks (it didn't before: the old 3-state fill was flat across the
              // whole circle), so a more opaque icon reads consistently over the two-tone body instead of
              // showing a visible seam through translucent icon art.
              opacity={locked ? 0.22 : full ? 0.95 : pts > 0 ? 0.75 : 0.5}
              style={{ pointerEvents: 'none' }}
            />
          </>
        )}
        <text
          x={cx} y={cy + 4}
          textAnchor="middle"
          fill={textColor}
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
            <TooltipShell title={`${node.node_type} ${pts}/${maxPts}`} delta={fallbackDelta} deltas={labeledDeltas}>
              <NodeTooltipBody node={node} pts={pts} />
            </TooltipShell>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}
const TreeNodeG = React.memo(TreeNodeGImpl)

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
        <circle cx={cx} cy={cy} r={PRISM_MARK_R} fill="none" stroke="#c79bff" strokeWidth={1.5}
          strokeDasharray="3 3" opacity={0.6} style={{ pointerEvents: 'none' }} />
        {/* Same fill-is-the-meter treatment as the normal node (TreeNodeG): the arc is gone, the rarity ring
            alone owns the border (bolder), and allocation reads as a bottom-up violet wipe of the body. */}
        <circle cx={cx} cy={cy} r={NODE_R} fill={unlocked ? NODE_EMPTY_FILL : '#191925'}
          stroke={rarity} strokeWidth={src.node_type === 'Legendary Medium Talent' ? 5 : 4} />
        {unlocked && pts > 0 && (
          <>
            <clipPath id={`rfill-${posKey}`}><circle cx={cx} cy={cy} r={NODE_R} /></clipPath>
            <rect
              x={cx - NODE_R} y={cy + NODE_R - 2 * NODE_R * frac}
              width={NODE_R * 2} height={2 * NODE_R * frac + 1}
              fill="#533483"
              clipPath={`url(#rfill-${posKey})`}
              style={{ pointerEvents: 'none' }}
            />
          </>
        )}
        {icon && (
          <>
            <clipPath id={`rclip-${posKey}`}><circle cx={cx} cy={cy} r={NODE_R - 3} /></clipPath>
            <image href={icon} x={cx - (NODE_R - 3)} y={cy - (NODE_R - 3)}
              width={(NODE_R - 3) * 2} height={(NODE_R - 3) * 2} clipPath={`url(#rclip-${posKey})`}
              preserveAspectRatio="xMidYMid slice" opacity={!unlocked ? 0.22 : full ? 0.95 : pts > 0 ? 0.75 : 0.5}
              style={{ pointerEvents: 'none' }} />
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
    const byId = nodeIndex
    const broken = new Set(brokenIds)
    const thr = nodeThreshold
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

  // Node-id index, memoized off treeData alone (not rebuilt per allocPrimitives() call). Perf prerequisite for
  // the hover preview below: tryLocalAllocate/solvePathTo/cascadeRemove all call allocPrimitives(), and hover
  // now triggers those on every mouseenter across the tree (not just on click), so rebuilding this
  // Object.fromEntries-equivalent from scratch each time would have added up fast.
  const nodeIndex = useMemo(() => {
    const byId: Record<string, TreeNode> = {}
    for (const n of (treeData?.nodes ?? [])) byId[n.id] = n
    return byId
  }, [treeData])

  // Pure allocation primitives mirroring the backend validator (models/passive_tree.py). Snapshot the prism-
  // derived inputs once; every helper takes an explicit `states` map so we can simulate on working copies.
  const allocPrimitives = () => {
    const nodes = treeData?.nodes ?? []
    const conns = treeData?.connections ?? []
    const byId = nodeIndex
    const broken = new Set(prismBrokenIds())
    const maxOv = prismMaxOverrides()
    const extraCol = prismExtraColumnPoints()
    const thr = nodeThreshold
    const effMax = (id: string) => maxOv[id] ?? (byId[id]?.max_points ?? 0)
    const colPts = (st: Record<string, number>, col: number): number => {
      let s = extraCol[col] ?? 0
      for (const n of nodes) if (n.column === col) s += st[n.id] ?? 0
      return s
    }
    const before = (st: Record<string, number>, col: number): number => {
      let s = 0
      for (let c = 0; c < col; c++) s += colPts(st, c)
      return s
    }
    const colUnlocked = (st: Record<string, number>, col: number) => col === 0 || before(st, col) >= col * 3
    const unmetSources = (st: Record<string, number>, id: string): string[] => {
      const out: string[] = []
      for (const { from, to } of conns) {
        if (to !== id || broken.has(from)) continue
        const p = byId[from]
        if (p && (st[from] ?? 0) < thr(p)) out.push(from)
      }
      return out
    }
    return { nodes, conns, byId, broken, thr, effMax, colPts, before, colUnlocked, unmetSources }
  }

  // Client-side mirror of the backend allocate/deallocate validator. Runs synchronously so allocating is instant
  // (no per-click round-trip) — the stats recompute still re-derives everything server-side in the debounced
  // background. `states` defaults to the live map but can be a working copy (used by the path solver below).
  // RULES MUST STAY IN LOCKSTEP with PassiveTree.allocate/deallocate.
  const tryLocalAllocate = (
    nodeId: string, action: 'allocate' | 'deallocate', states: Record<string, number> = nodeStates,
  ): { allowed: boolean; nodeStates?: Record<string, number>; reason?: string } => {
    if (!treeData) return { allowed: false, reason: 'Tree not loaded.' }
    const P = allocPrimitives()
    const node = P.byId[nodeId]
    if (!node) return { allowed: false, reason: 'Node not found.' }

    if (action === 'allocate') {
      if (!P.colUnlocked(states, node.column))
        return { allowed: false, reason: `Column ${node.column * 3} is locked — need ${node.column * 3} points in earlier columns.` }
      const cur = states[nodeId] ?? 0
      if (cur >= P.effMax(nodeId)) return { allowed: false, reason: `'${node.node_type}' is already at max (${cur}/${P.effMax(nodeId)}).` }
      const unmet = P.unmetSources(states, nodeId)
      if (unmet.length) {
        const p = P.byId[unmet[0]]
        return { allowed: false, reason: `Requires the connected '${p.node_type}' to have ≥${P.thr(p)} pt(s) first.` }
      }
      return { allowed: true, nodeStates: { ...states, [nodeId]: cur + 1 } }
    }

    // deallocate
    const cur = states[nodeId] ?? 0
    if (cur <= 0) return { allowed: false, reason: `'${node.node_type}' already has 0 points.` }
    const after = { ...states, [nodeId]: cur - 1 }
    // Removing a point in this column can strand any column to its RIGHT that relied on it for its unlock.
    for (let col = node.column + 1; col < COLS; col++) {
      if (P.colPts(after, col) > 0 && P.before(after, col) < col * 3)
        return { allowed: false, reason: `Cannot remove: column ${col * 3} requires ${col * 3} points in earlier columns.` }
    }
    // Dropping below this node's own threshold must not orphan a connected dependant.
    if (cur - 1 < P.thr(node) && !P.broken.has(nodeId)) {
      for (const { from, to } of P.conns) {
        if (from !== nodeId) continue
        const dep = P.byId[to]
        if (dep && (states[to] ?? 0) > 0)
          return { allowed: false, reason: `Cannot remove: '${dep.node_type}' depends on this node having ≥${P.thr(node)} pt(s).` }
      }
    }
    return { allowed: true, nodeStates: after }
  }

  // "Allocate a path to here": clicking a node further along a chain than you've reached fills the prerequisite
  // chain (via incoming connections) + any needed column unlocks, then puts 1 point in the target. Every mutation
  // goes through tryLocalAllocate so the result is always a legal tree state. Returns the new states, or null if
  // the target can't be reached (e.g. no point budget path satisfies its column unlock).
  const solvePathTo = (targetId: string): Record<string, number> | null => {
    const P = allocPrimitives()
    if (!P.byId[targetId]) return null
    const CAP = 300
    let added = 0

    const unlockColumn = (st: Record<string, number>, col: number, seen: Set<string>): Record<string, number> | null => {
      const needed = col * 3
      // Earlier-column candidates, preferring already-allocated nodes and lower columns (top up before branching).
      const cands = P.nodes.filter(n => n.column < col).sort((a, b) =>
        (((st[b.id] ?? 0) > 0 ? 1 : 0) - ((st[a.id] ?? 0) > 0 ? 1 : 0)) || (a.column - b.column))
      let guard = 0
      while (P.before(st, col) < needed) {
        if (guard++ > CAP || added > CAP) return null
        let done = false
        for (const n of cands) {
          const r = tryLocalAllocate(n.id, 'allocate', st)
          if (r.allowed && r.nodeStates) { st = r.nodeStates; added++; done = true; break }
        }
        if (!done) {
          // No directly-allocatable earlier node — try to make one reachable via its own prereqs.
          for (const n of cands) {
            if ((st[n.id] ?? 0) < P.effMax(n.id)) {
              const r = ensure(st, n.id, (st[n.id] ?? 0) + 1, seen)
              if (r) { st = r; done = true; break }
            }
          }
        }
        if (!done) return null
      }
      return st
    }

    const ensure = (st: Record<string, number>, id: string, want: number, seen: Set<string>): Record<string, number> | null => {
      const n = P.byId[id]
      if (!n) return null
      if ((st[id] ?? 0) >= want) return st
      if (want > P.effMax(id) || seen.has(id)) return null
      const seen2 = new Set(seen).add(id)
      let guard = 0
      while ((st[id] ?? 0) < want) {
        if (guard++ > CAP || added > CAP) return null
        const r = tryLocalAllocate(id, 'allocate', st)
        if (r.allowed && r.nodeStates) { st = r.nodeStates; added++; continue }
        const unmet = P.unmetSources(st, id)
        if (unmet.length) {
          let ok = true
          for (const s of unmet) {
            const r2 = ensure(st, s, P.thr(P.byId[s]), seen2)
            if (r2) st = r2; else { ok = false; break }
          }
          if (!ok) return null
          continue
        }
        if (!P.colUnlocked(st, n.column)) {
          const r3 = unlockColumn(st, n.column, seen2)
          if (r3) { st = r3; continue }
          return null
        }
        return null   // at max / otherwise stuck
      }
      return st
    }

    return ensure({ ...nodeStates }, targetId, 1, new Set())
  }

  // Apply a new node-state map: mirror it into the store and prune core-talent selections whose threshold no
  // longer holds (only relevant when points drop).
  const applyNodeStates = (ns: Record<string, number>) => {
    setNodeStates(ns)
    if (!previewMode) updateSlotNodeStates(activeSlot, ns)
    if (treeData && Object.keys(coreTalentSelections).length > 0) {
      const newTotal = sumPoints(ns)
      const next = { ...coreTalentSelections }
      let changed = false
      for (const idxStr of Object.keys(coreTalentSelections)) {
        const idx = Number(idxStr)
        const slot = treeData.core_talent_slots[idx]
        if (slot && newTotal < slot.threshold) { delete next[idx]; changed = true }
      }
      if (changed) {
        setCoreTalentSelections(next)
        if (!previewMode) updateSlotCoreTalentSelections(activeSlot, next)
      }
    }
  }

  // Right-click "remove, cascading if needed": force nodeId down by 1, then repair the WHOLE tree against the
  // same prism-derived caps/broken-ids the normal allocator uses — repairAllocations already cascades off
  // anything no longer legal (an unmet prereq threshold, or a now-unaffordable column unlock), so reuse it
  // rather than re-deriving the same rule set a third time. Returns null if there's nothing to remove.
  const cascadeRemove = (nodeId: string): Record<string, number> | null => {
    const cur = nodeStates[nodeId] ?? 0
    if (cur <= 0) return null
    const tentative = { ...nodeStates, [nodeId]: cur - 1 }
    return repairAllocations(tentative, prismMaxOverrides(), prismBrokenIds())
  }

  const handleClick = (nodeId: string, action: 'allocate' | 'deallocate') => {
    const res = tryLocalAllocate(nodeId, action)
    if (res.allowed && res.nodeStates) { applyNodeStates(res.nodeStates); return }
    // A direct allocate blocked by an unmet prereq / locked column (not an at-max node) → try to auto-fill a path.
    if (action === 'allocate' && res.reason && !res.reason.includes('at max')) {
      const path = solvePathTo(nodeId)
      if (path) { applyNodeStates(path); return }
    }
    // A direct deallocate blocked by a stranded column / orphaned dependent (not the trivial "already 0" case)
    // → cascade-remove the full set that has to go, mirroring the allocate-side auto-fill above. This is the
    // fix for the old pain point: right-click on an upstream node used to just fail and flash a reason, forcing
    // the user to walk the chain leaf-first by hand.
    if (action === 'deallocate' && res.reason && !res.reason.includes('already has 0 points')) {
      const cascade = cascadeRemove(nodeId)
      if (cascade) { applyNodeStates(cascade); return }
    }
    flash(res.reason ?? (action === 'allocate'
      ? 'Cannot allocate — check column unlock & prerequisites.'
      : 'Cannot remove — would break a prerequisite.'))
  }

  // ── Hover preview (forward path-to / reverse cascade-remove) ────────────────────────────────
  // Lifted to the parent (not computed per-node) because the connector <line>s are drawn once in the parent
  // SVG and need to know which edges belong to the currently-previewed path/cascade. `hoveredNodeId` is kept
  // in lockstep with each TreeNodeG's own tooltip-open state (see TreeNodeG's onHoverChange effect), not a
  // separate mouseenter listener, so there's exactly one source of truth for "what's hovered".
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const setHovered = useCallback((id: string, isOpen: boolean) => {
    setHoveredNodeId(cur => (isOpen ? id : (cur === id ? null : cur)))
  }, [])

  // Forward: what allocating `hoveredNodeId` would actually do — mirrors handleClick's own allocate branch
  // (direct allocate first, solvePathTo fallback second) so the preview never lies about what a click will do.
  const forwardPreview = useMemo((): TreePreview | null => {
    if (!hoveredNodeId) return null
    const node = nodeIndex[hoveredNodeId]
    if (!node) return null
    const direct = tryLocalAllocate(hoveredNodeId, 'allocate')
    let after: Record<string, number> | null = null
    if (direct.allowed && direct.nodeStates) after = direct.nodeStates
    else if (direct.reason && !direct.reason.includes('at max')) after = solvePathTo(hoveredNodeId)
    if (!after) return null
    const changed = diffAdded(nodeStates, after)
    if (Object.keys(changed).length === 0) return null
    return { after, changed, cost: Object.values(changed).reduce((a, b) => a + b, 0) }
  }, [hoveredNodeId, nodeStates, nodeIndex, treePrism])

  // Reverse: only populated when removing WOULD cascade (tryLocalAllocate's direct deallocate is blocked) — a
  // plain 3/3 → 2/3 with no dependents must stay silent (task requirement: no red on every hover).
  const reversePreview = useMemo((): TreePreview | null => {
    if (!hoveredNodeId) return null
    if ((nodeStates[hoveredNodeId] ?? 0) <= 0) return null
    const direct = tryLocalAllocate(hoveredNodeId, 'deallocate')
    if (direct.allowed) return null
    const after = cascadeRemove(hoveredNodeId)
    if (!after) return null
    const changed = diffRemoved(nodeStates, after)
    if (Object.keys(changed).length === 0) return null
    return { after, changed, cost: Object.values(changed).reduce((a, b) => a + b, 0) }
  }, [hoveredNodeId, nodeStates, nodeIndex, treePrism])

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

  // Stable identity for TreeNodeG's `onInteract` prop (2026-07-16 review-performance fix, part 2).
  // `handleNodeInteract` closes over debugMode/debugTool/handleClick/tryLocalAllocate/etc — none of it
  // useCallback'd, and stabilizing that whole ~8-function allocation chain (so ITS identity only changes
  // when something it actually depends on changes) is a much larger refactor than this fix round calls for.
  // Standard workaround: fold the placingPrism branch in HERE (not at the render site, where a ternary
  // would reintroduce a fresh arrow every render and re-break the memo) so there's a single "what interacting
  // with a node does right now" value, stash it in a ref updated every render (always current, never stale),
  // and hand TreeNodeG a useCallback with an EMPTY dep array that only ever reads through the ref. The
  // returned function's identity is then permanently stable — it's the ref indirection, not the dep array,
  // doing the work, since the real behavior legitimately changes every render (debugMode, placingPrism, etc).
  const currentInteract: (node: TreeNode, isRight: boolean) => void =
    placingPrism ? (n) => placePrismAt(n) : handleNodeInteract
  const interactRef = useRef(currentInteract)
  interactRef.current = currentInteract
  const stableInteract = useCallback((n: TreeNode, isRight: boolean) => interactRef.current(n, isRight), [])

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
          {/* Inline, not a `.viewer-canvas` CSS rule — index.css is off-limits right now (the owner has a
              second, unrelated conversation live in it building a points-out-of-115 display). Scoped to just
              this screen's canvas, not the app-wide `--bg` token (#1a1a2e, ~27% saturated navy) — desaturated
              near-neutral AND pushed darker than NODE_EMPTY_FILL (#1c1c24) on purpose: the empty node body
              used to be darker than the canvas (#0e1230 under the old #1a1a2e), reading as recessed; now that
              the empty fill is a touch lighter, the canvas has to go darker still for nodes to read as raised
              chips rather than holes. Inline style (not an SVG <rect>) so it also covers `.viewer-canvas`'s
              4px/8px padding strip — a rect confined to the SVG's own bounds would leave that strip showing
              the old page background and read as an unintended border. */}
          <div className="viewer-canvas" style={{ background: '#101014' }}>
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
                // Preview overlays win over the plain lit/dim state coloring, but never over the debug link
                // highlight. Re-examined 2026-07-16: this tie-break was originally justified by a false
                // invariant ("thr(n) === n.max_points always" — not true, see nodeThreshold's doc comment in
                // utils/passiveTreeDiff.ts) and that justification undersold how often an edge lands in BOTH
                // diffs. hoveredNodeId itself is a member of both forwardPreview.changed and
                // reversePreview.changed whenever the two previews are simultaneously non-null (forward always
                // adds +1 to it; a real reverse cascade always removes from it first) — so EVERY edge touching
                // hoveredNodeId goes both-tagged in that situation, at the exact same frequency as the node-level
                // bothPreview case (TreeNodeG), not rarer than it. What IS genuinely rare is two DIFFERENT nodes
                // — one added via a forward path-fill, one dropped via a reverse cascade (column-strand or,
                // once a shipped tree diverges thr from max_points, a threshold break) — happening to share a
                // direct edge; that coincidence doesn't depend on hoveredNodeId at all. Either way, a LINE
                // (unlike TreeNodeG's node, which has two separate ring radii to show both at once) can only
                // carry one stroke color, so a plain precedence tie is the right shape of fix regardless of
                // which case triggers it — kept as reverse-wins (not worth a second offset line for what's
                // still one edge's ambiguity) since it's more useful to flag "this connection is about to
                // break" than "this connection would extend" when both are momentarily true.
                const inReverse = !!reversePreview &&
                  (reversePreview.changed[from] != null || reversePreview.changed[to] != null)
                const inForward = !!forwardPreview &&
                  (forwardPreview.changed[from] != null || forwardPreview.changed[to] != null)
                // Lit = the prereq this edge depends on is actually satisfied (the "from" node has reached its
                // threshold) — dimmed DOWN when it isn't, so the allocated set reads as one connected shape
                // instead of 25 nodes read one at a time.
                const satisfied = (nodeStates[from] ?? 0) >= nodeThreshold(n1)
                const stroke = isLinked ? '#e9c046'
                  : inReverse ? '#e94560'
                  : inForward ? '#6be946'
                  : satisfied ? '#6b78b8' : '#2a3050'
                return (
                  <line key={i}
                    x1={x1 + ox} y1={y1 + oy} x2={x2 - ox} y2={y2 - oy}
                    stroke={stroke}
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
                const textColor = nodeTextColor(node, nodeStates, locked)
                const isLinkSrc = debugMode && debugTool === 'link' && linkFrom === node.id
                const isHit = !isSearching || searchHits.has(node.id)
                return (
                  <TreeNodeG
                    key={node.id}
                    node={node}
                    cx={cx}
                    cy={cy}
                    pts={pts}
                    textColor={textColor}
                    locked={locked}
                    isLinkSrc={isLinkSrc}
                    isHit={isHit}
                    isSearching={isSearching}
                    processing={processing}
                    debugMode={debugMode}
                    onInteract={stableInteract}
                    maxOverride={ethMaxOverrides[node.id]}
                    inPrismBox={ethBoxNodeIds.has(node.id)}
                    previewAdd={!!forwardPreview?.changed[node.id]}
                    previewRemove={!!reversePreview?.changed[node.id]}
                    // Only the actually-hovered node ever prices a preview delta (see showForward/showReverse,
                    // both gated on tip.open), so every OTHER node gets the same `null` reference here on every
                    // render — a stable prop React.memo's shallow comparison can skip on, instead of a fresh
                    // TreePreview object identity that would defeat memo for all 35 nodes on every hover tick.
                    forwardPreview={node.id === hoveredNodeId ? forwardPreview : null}
                    reversePreview={node.id === hoveredNodeId ? reversePreview : null}
                    onHoverChange={setHovered}
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
