// The tree-based Hero Trait allocation UI (currently only Selena's "Dance of the Deep") — rendered by
// HeroTraitScreen INSTEAD of the fixed tier-column layout when `selectedTrait.allocation_mode === 'tree'`.
// Renders the connected tree (root + branches) as an SVG grid — mirroring MiniTree.tsx/TreeViewerScreen's
// nodeX/nodeY math — plus the three Hero Memory sockets that gate the allocation points, on a rail beside
// it. All allocation logic itself is the pure, independently-tested `utils/traitTree.ts`; this file is
// display + click wiring only.
//
// Scope note: selection/allocation only — no DPS is modeled for this trait yet (no `hero_traits` engine
// module is registered for it), so there is no damage-delta tooltip band here (unlike TreeViewerScreen's
// passive-tree nodes).
import React, { useEffect } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { HeroTrait, HeroTraitTreeNode, CreatedHeroMemory, MEMORY_RARITY_COLORS, iconUrl } from '../api/client'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { TraitTooltipBody, MemorySlotCircle, memoryTypeIconUrl } from '../components/HeroTraitShared'
import { useReferenceStore } from '../store/referenceStore'
import {
  availableThresholds, canAllocate, allocate, deallocate, reconcile, badgeFor,
} from '../utils/traitTree'

interface Props {
  trait: HeroTrait
  heroMemories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]
  openMemoryCreator: (slotIdx: number) => void
  traitTreeAllocations: string[]
  setTraitTreeAllocations: (allocations: string[]) => void
  characterLevel: number
  resolveLevelAt: number   // 1–5 — the base-node level control's current value; tooltips resolve `/`-scaling at this
}

// Memory-slot rail: slot index (0=origin/1=discipline/2=progress) → its granted threshold + label.
// Mirrors HeroTraitScreen's THRESHOLD_TO_MEMORY_SLOT (45→0, 60→1, 75→2).
const MEMORY_RAIL: { slot: number; threshold: number; label: string }[] = [
  { slot: 0, threshold: 45, label: 'Origin' },
  { slot: 1, threshold: 60, label: 'Discipline' },
  { slot: 2, threshold: 75, label: 'Progress' },
]

const CELL = 150
const NODE_R = 34          // fallback (no x/y on the trait's nodes) — the legacy column/row grid
const XY_NODE_R = 54       // radial layout — tuned for the 1000×760 viewBox
const XY_VW = 1000
const XY_VH = 760
// Render-side headroom above the data's y=0 plane — a root node at y≈0.10 otherwise sits close enough
// to the top edge that its glow-ring blur gets clipped by the viewBox. Pure display offset: shifts every
// node down uniformly (spacing/arrangement unchanged), never touches the data's x/y values.
const XY_TOP_PAD = 40

function TreeNodeCircle({ node, cx, cy, baseR, isRoot, isAllocated, isAllocatable, badge, resolveLevelAt, onClick, onContextMenu }: {
  node: HeroTraitTreeNode; cx: number; cy: number; baseR: number
  isRoot: boolean; isAllocated: boolean; isAllocatable: boolean; badge: number | null
  resolveLevelAt: number
  onClick: () => void; onContextMenu: () => void
}) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right' })
  const icon = iconUrl('hero_trait', node.icon_url)
  const r = isRoot ? baseR + 6 : baseR
  const active = isRoot || isAllocated
  // Warm red/orange glow ring, per state — root always reads as active; unreachable/locked nodes dim out.
  const stroke = isRoot ? '#ffc47a' : isAllocated ? '#ff7a3d' : isAllocatable ? '#a3502e' : '#3a2a26'
  const fill = active ? '#1c130f' : '#100c10'
  const glow = isRoot || isAllocated ? 'url(#htt-glow-strong)' : isAllocatable ? 'url(#htt-glow-soft)' : undefined
  const dimmed = !isRoot && !isAllocated && !isAllocatable
  return (
    <>
      <g
        {...tip.triggerProps}
        style={{ cursor: isRoot ? 'default' : 'pointer', opacity: dimmed ? 0.4 : 1 }}
        onClick={e => { e.preventDefault(); if (!isRoot) onClick() }}
        onContextMenu={e => { e.preventDefault(); if (!isRoot) onContextMenu() }}
      >
        <circle cx={cx} cy={cy} r={r} fill={fill} stroke={stroke} strokeWidth={isRoot || isAllocated ? 3.5 : 2.5} filter={glow} />
        {icon ? (
          <>
            <clipPath id={`htt-clip-${node.node_id}`}><circle cx={cx} cy={cy} r={r - 4} /></clipPath>
            <image
              href={icon} x={cx - (r - 4)} y={cy - (r - 4)} width={(r - 4) * 2} height={(r - 4) * 2}
              clipPath={`url(#htt-clip-${node.node_id})`} preserveAspectRatio="xMidYMid slice"
              opacity={dimmed ? 0.5 : 1}
              style={{ pointerEvents: 'none' }}
            />
          </>
        ) : (
          <text x={cx} y={cy + 4} textAnchor="middle" fontSize={10} fontWeight="bold" fill="#c0c0e0"
            style={{ pointerEvents: 'none' }}>
            {node.name}
          </text>
        )}
        {active && (
          <>
            <circle cx={cx + r - 13} cy={cy - r + 13} r={15} fill="#1a3a1a" stroke="#6bcb77" strokeWidth={1.5} />
            <text x={cx + r - 13} y={cy - r + 18} textAnchor="middle" fontSize={15} fontWeight="bold" fill="#6bcb77"
              style={{ pointerEvents: 'none' }}>✓</text>
          </>
        )}
        {badge != null && (
          <>
            <circle cx={cx - r + 13} cy={cy + r - 13} r={15} fill="#0d0d1e" stroke="#c8a86a" strokeWidth={2} />
            <text x={cx - r + 13} y={cy + r - 8} textAnchor="middle" fontSize={15} fontWeight="bold" fill="#ffe6ae"
              style={{ pointerEvents: 'none' }}>{badge}</text>
          </>
        )}
      </g>
      {tip.open && (
        <FloatingPortal>
          <div className="trait-info-card" {...tip.floatingProps}>
            <TraitTooltipBody name={node.name} slotLevel={resolveLevelAt} effects={node.effects ?? []} />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

export default function HeroTraitTree({
  trait, heroMemories, openMemoryCreator, traitTreeAllocations, setTraitTreeAllocations, characterLevel, resolveLevelAt,
}: Props) {
  const nodes = trait.tree_nodes ?? []
  const connections = trait.tree_connections ?? []
  const rootId = trait.tree_root_id ?? ''
  const memoryTypes = useReferenceStore(s => s.heroMemories?.memory_types) ?? null
  const thresholds = availableThresholds(characterLevel, heroMemories)
  const budget = thresholds.length

  // Re-validate whenever the point BUDGET changes (a memory gets socketed/removed, or character level
  // crosses a threshold) — trims over-budget allocations and drops any now-disconnected node. Topology
  // itself only changes with the trait, so `trait.trait_id` (not `nodes`/`connections`) is the other dep.
  useEffect(() => {
    if (!nodes.length || !rootId) return
    const next = reconcile(traitTreeAllocations, connections, rootId, budget)
    const changed = next.length !== traitTreeAllocations.length || next.some((id, i) => id !== traitTreeAllocations[i])
    if (changed) setTraitTreeAllocations(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [budget, rootId, trait.trait_id])

  // Horizontal strip along the bottom of the tree (in-game layout): the 3 memory sockets side-by-side,
  // with the points readout alongside them, kept close under the tree (small htt-row gap).
  const memoryRail = (
    <div className="htt-memory-rail">
      <div className="htt-memory-slots-row">
        {MEMORY_RAIL.map(({ slot, label }) => {
          const memory = heroMemories[slot] ?? null
          const rarityColor = memory ? MEMORY_RARITY_COLORS[memory.rarity] : undefined
          return (
            <div key={slot} className="htt-memory-slot">
              <MemorySlotCircle memory={memory} rarityColor={rarityColor} slot={slot} slotLabel={label}
                icon={memory ? memoryTypeIconUrl(memoryTypes, memory.memoryType) : null}
                onOpen={() => openMemoryCreator(slot)} />
            </div>
          )
        })}
      </div>
      <div className="htt-points-readout">
        Points: {traitTreeAllocations.length} / {budget}
        {budget === 0 && (
          <div className="htt-points-hint">Socket a Hero Memory at 45 / 60 / 75 to unlock allocation.</div>
        )}
      </div>
    </div>
  )

  if (!nodes.length || !rootId) {
    return (
      <div className="htt-row">
        <div className="panel-empty">This trait's tree data hasn't loaded — no nodes to allocate.</div>
        {memoryRail}
      </div>
    )
  }

  const byId: Record<string, HeroTraitTreeNode> = Object.fromEntries(nodes.map(n => [n.node_id, n]))
  // Radial layout from the data-supplied x/y (0..1, left→right / top→bottom) when every node has it;
  // otherwise fall back to the legacy column/row grid math so older/incomplete tree data still renders.
  const useXY = nodes.every(n => typeof n.x === 'number' && typeof n.y === 'number')
  const maxCol = Math.max(0, ...nodes.map(n => n.column))
  const maxRow = Math.max(0, ...nodes.map(n => n.row))
  const VW = useXY ? XY_VW : (maxCol + 1) * CELL
  const VH = useXY ? XY_VH + XY_TOP_PAD : (maxRow + 1) * CELL
  const nodeR = useXY ? XY_NODE_R : NODE_R
  const nodeX = (n: HeroTraitTreeNode) => (useXY && typeof n.x === 'number') ? n.x * XY_VW : n.column * CELL + CELL / 2
  const nodeY = (n: HeroTraitTreeNode) => (useXY && typeof n.y === 'number') ? n.y * XY_VH + XY_TOP_PAD : n.row * CELL + CELL / 2

  const handleClick = (nodeId: string) => {
    if (nodeId === rootId) return
    if (traitTreeAllocations.includes(nodeId)) {
      setTraitTreeAllocations(deallocate(nodeId, traitTreeAllocations, connections, rootId))
    } else if (canAllocate(nodeId, traitTreeAllocations, connections, rootId, budget)) {
      setTraitTreeAllocations(allocate(nodeId, traitTreeAllocations, connections, rootId, budget))
    }
  }
  const handleContextMenu = (nodeId: string) => {
    if (nodeId === rootId || !traitTreeAllocations.includes(nodeId)) return
    setTraitTreeAllocations(deallocate(nodeId, traitTreeAllocations, connections, rootId))
  }

  return (
    <div className="htt-row">
      <svg viewBox={`0 0 ${VW} ${VH}`} className="htt-tree-svg">
        <defs>
          {/* Warm glow halos — blur behind, original (crisp) graphic merged on top. */}
          <filter id="htt-glow-strong" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="htt-glow-soft" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {/* No flat backdrop rect here — the tree area shows the screen's own background (matches the
            rest of the panel) rather than a distinct tint. Only the glow filters + connectors draw. */}
        {connections.map(({ from, to }, i) => {
          const n1 = byId[from]; const n2 = byId[to]
          if (!n1 || !n2) return null
          return (
            <line key={i}
              x1={nodeX(n1)} y1={nodeY(n1)} x2={nodeX(n2)} y2={nodeY(n2)}
              className="htt-tree-connector" />
          )
        })}
        {nodes.map(n => {
          const isRoot = n.node_id === rootId
          const isAllocated = traitTreeAllocations.includes(n.node_id)
          const isAllocatable = !isRoot && !isAllocated
            && canAllocate(n.node_id, traitTreeAllocations, connections, rootId, budget)
          const badge = badgeFor(n.node_id, traitTreeAllocations, thresholds)
          return (
            <TreeNodeCircle
              key={n.node_id}
              node={n} cx={nodeX(n)} cy={nodeY(n)} baseR={nodeR}
              isRoot={isRoot} isAllocated={isAllocated} isAllocatable={isAllocatable} badge={badge}
              resolveLevelAt={resolveLevelAt}
              onClick={() => handleClick(n.node_id)}
              onContextMenu={() => handleContextMenu(n.node_id)}
            />
          )
        })}
      </svg>
      {memoryRail}
    </div>
  )
}
