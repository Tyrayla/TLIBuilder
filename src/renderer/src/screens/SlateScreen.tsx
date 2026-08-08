import React, { useState, useEffect, useRef, useMemo } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { api, SlatePool, SlateModifierOption, CoreTalentOption, SavedSlate, SlateTemplate, iconUrl } from '../api/client'
import { useBuildStore } from '../store/buildStore'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { useDamageDelta } from '../components/tooltip/useDamageDelta'
import { TooltipContributions } from '../components/tooltip/TooltipContributions'
import { ModifierBadge, useTextModifierStatuses } from '../components/ModifierBadge'
import { summarizeSlateBonuses } from '../utils/slateBonusSummary'

// One selectable slate modifier option (its effects badged for engine support). Extracted so the
// status hook isn't called inside the options .map().
function SlateModRow({ mod, selected, accentColor, onSelect }: {
  mod: SlateModifierOption; selected: boolean; accentColor: string; onSelect: (m: SlateModifierOption) => void
}) {
  const statuses = useTextModifierStatuses(mod.effects.map(text => ({ text, source: 'talent' as const, nodeId: mod.nodeId })))
  return (
    <div onClick={() => onSelect(mod)} style={{
      padding: '9px 14px', cursor: 'pointer', borderBottom: '1px solid #1a1a30',
      background: selected ? `${accentColor}18` : 'transparent',
      borderLeft: selected ? `2px solid ${accentColor}` : '2px solid transparent',
    }}
    onMouseEnter={e => { if (!selected) (e.currentTarget as HTMLElement).style.background = '#1e1e38' }}
    onMouseLeave={e => { if (!selected) (e.currentTarget as HTMLElement).style.background = 'transparent' }}>
      {mod.effects.map((ef, i) => (
        <div key={i} style={{ fontSize: 14, color: selected ? '#fff' : '#ccc' }}>{ef}<ModifierBadge status={statuses[i]} /></div>
      ))}
      <div style={{ fontSize: 11, color: '#444', marginTop: 3 }}>{mod.treeName} · {mod.nodeType}</div>
    </div>
  )
}

// ── Board ─────────────────────────────────────────────────────────────────────

const BOARD_VALID: boolean[][] = [
  [false, false, true,  true,  false, false],
  [false, true,  true,  true,  true,  false],
  [true,  true,  true,  true,  true,  true ],
  [true,  true,  true,  true,  true,  true ],
  [false, true,  true,  true,  true,  false],
  [false, false, true,  true,  false, false],
]
const BOARD_ROWS = 6
const BOARD_COLS = 6
const TOTAL_CELLS = 24
const CELL = 72
const GAP = 4                 // grid gap between cells (px)
const PITCH = CELL + GAP      // cell-to-cell stride
const BOARD_PX = BOARD_COLS * CELL + (BOARD_COLS - 1) * GAP   // full grid extent (for absolute overlays)

function isValidCell(r: number, c: number): boolean {
  return r >= 0 && r < BOARD_ROWS && c >= 0 && c < BOARD_COLS && BOARD_VALID[r][c]
}

// ── Types ─────────────────────────────────────────────────────────────────────

const PRIMARY_TREES = [
  'God of Might', 'Goddess of Hunting', 'Goddess of Knowledge',
  'God of War', 'Goddess of Deception', 'God of Machines',
] as const
type PrimaryTree = typeof PRIMARY_TREES[number]

type LegendaryKind =
  | 'pedigree'
  | 'fallen_starlight'
  | 'corner_of_divinity'
  | 'spark_of_moth_fire'
  | 'when_sparks_set_prairie_ablaze'
  | 'space_rift'
  | 'residence_of_stars'

type SlateKind = 'base' | LegendaryKind
type SlotType = 'magic' | 'rare' | 'legendary'
type MothDirection = 'above' | 'below' | 'left' | 'right'

const LEGEND_GOLD = '#c8881a'

// ── Base shapes (6 game forms × 4 rotations) ─────────────────────────────────
// The six baseline tetromino forms (O, L, Z, T + the mirrors J=L2, S=Z2). Each form's rotation 0 matches its
// art's natural orientation, and rotations advance 90° CW (so the overlay art rotates with orientationIndex).
// BASE_FORMS (below) carries the matching art form/flip/sizing — kept index-aligned with BASE_SHAPES.

interface BaseShape { label: string; rotations: [number, number][][] }

const BASE_SHAPES: BaseShape[] = [
  {
    label: 'O',   // O1
    rotations: [
      [[0,0],[0,1],[1,0],[1,1]],
      [[0,0],[0,1],[1,0],[1,1]],
      [[0,0],[0,1],[1,0],[1,1]],
      [[0,0],[0,1],[1,0],[1,1]],
    ],
  },
  {
    label: 'L',        // L1
    rotations: [
      [[0,0],[1,0],[1,1],[1,2]],
      [[0,0],[0,1],[1,0],[2,0]],
      [[0,0],[0,1],[0,2],[1,2]],
      [[0,1],[1,1],[2,0],[2,1]],
    ],
  },
  {
    label: 'Z',        // Z1 (vertical S)
    rotations: [
      [[0,0],[1,0],[1,1],[2,1]],
      [[0,1],[0,2],[1,0],[1,1]],
      [[0,0],[1,0],[1,1],[2,1]],
      [[0,1],[0,2],[1,0],[1,1]],
    ],
  },
  {
    label: 'T',        // T1
    rotations: [
      [[0,0],[0,1],[0,2],[1,1]],
      [[0,1],[1,0],[1,1],[2,1]],
      [[0,1],[1,0],[1,1],[1,2]],
      [[0,0],[1,0],[1,1],[2,0]],
    ],
  },
  {
    label: 'J',        // L2 (mirror of L1)
    rotations: [
      [[0,2],[1,0],[1,1],[1,2]],
      [[0,0],[1,0],[2,0],[2,1]],
      [[0,0],[0,1],[0,2],[1,0]],
      [[0,0],[0,1],[1,1],[2,1]],
    ],
  },
  {
    label: 'S',        // Z2 (mirror of Z1)
    rotations: [
      [[0,1],[1,0],[1,1],[2,0]],
      [[0,0],[0,1],[1,1],[1,2]],
      [[0,1],[1,0],[1,1],[2,0]],
      [[0,0],[0,1],[1,1],[1,2]],
    ],
  },
]

// Per-base-form art config, index-aligned with BASE_SHAPES. Mirror forms reuse their partner's art with a
// horizontal flip. `natural` is the art's footprint [cols, rows]; scale/offset/stretch are tuned per form.
interface BaseForm {
  artForm: 'O1' | 'L1' | 'Z1' | 'T1'
  flip: boolean
  natural: [number, number]
  scale: number
  offset: [number, number]
  stretchX?: number
  stretchY?: number
}
const BASE_FORMS: BaseForm[] = [
  { artForm: 'O1', flip: false, natural: [2, 2], scale: 1.35, offset: [7, 12] },  // Square
  { artForm: 'L1', flip: false, natural: [3, 2], scale: 1.35, offset: [13, 20] },  // L
  { artForm: 'Z1', flip: false, natural: [2, 3], scale: 1.35, offset: [22, 17] },  // Z
  { artForm: 'T1', flip: false, natural: [3, 2], scale: 1.35, offset: [10, 18] },  // T
  { artForm: 'L1', flip: true,  natural: [3, 2], scale: 1.35, offset: [-13, 20] }, // J (mirror of L — x negated)
  { artForm: 'Z1', flip: true,  natural: [2, 3], scale: 1.35, offset: [-22, 17] }, // S (mirror of Z — x negated)
]

const ROTATION_LABELS = ['↑ 0°', '→ 90°', '↓ 180°', '← 270°']

// ── Legendary orientations ────────────────────────────────────────────────────

const LEGENDARY_ORIENTATIONS: Record<LegendaryKind, [number, number][][]> = {
  pedigree: [
    [[0,1],[0,2],[1,0],[1,1],[1,2],[2,0],[2,1]],
    [[0,0],[0,1],[1,0],[1,1],[1,2],[2,1],[2,2]],
  ],
  fallen_starlight: [[[0,0],[0,1]], [[0,0],[1,0]]],
  corner_of_divinity: [
    [[0,0],[0,1],[1,0]],
    [[0,0],[0,1],[1,1]],
    [[0,1],[1,0],[1,1]],
    [[0,0],[1,0],[1,1]],
  ],
  spark_of_moth_fire:             [[[0,0]]],
  when_sparks_set_prairie_ablaze: [[[0,0]]],
  space_rift:                     [[[0,0],[1,0],[2,0],[3,0],[4,0],[5,0]]],            // 6 tall × 1 wide
  residence_of_stars:             [[[0,2],[1,0],[1,1],[1,2],[2,1],[2,2],[2,3],[3,1]]], // pinwheel (matches the LL1 art)
}

function getOrientationCells(kind: SlateKind, shapeIndex: number, orientationIndex: number): [number, number][] {
  if (kind === 'base') return BASE_SHAPES[shapeIndex]?.rotations[orientationIndex] ?? BASE_SHAPES[0].rotations[0]
  const orientations = LEGENDARY_ORIENTATIONS[kind as LegendaryKind]
  return orientations?.[orientationIndex] ?? orientations?.[0] ?? [[0, 0]]
}

function getOrientationCount(kind: SlateKind): number {
  if (kind === 'base') return 4
  return LEGENDARY_ORIENTATIONS[kind as LegendaryKind]?.length ?? 0
}

function getCenterOffset(cells: [number, number][]): [number, number] {
  const rows = cells.map(([r]) => r), cols = cells.map(([, c]) => c)
  // Centroid of the footprint's bounding box, then SNAP to the occupied cell nearest it — so the cursor always
  // sits on a cell that's actually part of the slate (no "offset to the side" for L/T/corner/pinwheel shapes).
  const cr = (Math.min(...rows) + Math.max(...rows)) / 2
  const cc = (Math.min(...cols) + Math.max(...cols)) / 2
  let best: [number, number] = cells[0], bestD = Infinity
  for (const [r, c] of cells) {
    const d = (r - cr) ** 2 + (c - cc) ** 2
    if (d < bestD) { bestD = d; best = [r, c] }
  }
  return best
}

function centeredAnchor(kind: SlateKind, shapeIndex: number, orientationIndex: number, cursor: [number, number]): [number, number] {
  const cells = getOrientationCells(kind, shapeIndex, orientationIndex)
  const [cr, cc] = getCenterOffset(cells)
  return [cursor[0] - cr, cursor[1] - cc]
}

function anchorCells(kind: SlateKind, shapeIndex: number, orientationIndex: number, anchor: [number, number]): [number, number][] {
  const [ar, ac] = anchor
  return getOrientationCells(kind, shapeIndex, orientationIndex).map(([dr, dc]) => [ar + dr, ac + dc] as [number, number])
}

// ── Unified slate art overlay ──────────────────────────────────────────────────
// These kinds render their (shaped) art as ONE image spanning the whole footprint — covering the internal
// grid gaps so the slate reads as a single piece — and the art rotates with the slate's orientation. Gaps
// remain BETWEEN slates because each slate's overlay only covers its own footprint. Other kinds still slice
// the art per-cell. (Rolling out one kind at a time: corner first.)
const ART_OVERLAY_KINDS = new Set<SlateKind>(['base', 'corner_of_divinity', 'fallen_starlight', 'pedigree', 'residence_of_stars', 'space_rift', 'spark_of_moth_fire', 'when_sparks_set_prairie_ablaze'])
// Kinds whose orientations are MIRROR states (a horizontal flip) rather than 90° rotations.
const ART_FLIP_KINDS = new Set<SlateKind>(['pedigree'])
// The art's NATURAL footprint in cells [cols, rows] — the orientation the raw image is drawn in. Used to size
// the image before rotating so non-square shapes aren't distorted. Omit → uses the placed bbox (square shapes).
const ART_NATURAL_CELLS: Partial<Record<SlateKind, [number, number]>> = {
  corner_of_divinity: [2, 2],
  fallen_starlight: [1, 2],   // art is a tall vertical domino
}
// Base angle to align each kind's art with its orientation-0 footprint (tune per kind), plus the per-step turn.
// corner_of_divinity art (V1) is opaque at TL/BL/BR with a transparent TOP-RIGHT corner; orientation 0's empty
// cell is BOTTOM-RIGHT, so a +90° base turn moves the art's hole TR→BR to match (then +90°/step from there).
// fallen_starlight art is vertical; orientation 0 is the horizontal domino, so +90° turns it to match.
const ART_BASE_ANGLE: Partial<Record<SlateKind, number>> = { corner_of_divinity: 90, fallen_starlight: 90, pedigree: 0, residence_of_stars: 0, space_rift: 0, spark_of_moth_fire: 0, when_sparks_set_prairie_ablaze: 0 }
function artOverlayAngle(kind: SlateKind, orientationIndex: number): number {
  if (ART_FLIP_KINDS.has(kind)) return ART_BASE_ANGLE[kind] ?? 0   // flip kinds don't rotate per step
  return (ART_BASE_ANGLE[kind] ?? 0) + orientationIndex * 90       // others advance 90° clockwise per index
}
// pedigree art's natural shape = orientation 1; orientation 0 is its horizontal mirror.
function artOverlayFlipX(kind: SlateKind, orientationIndex: number): boolean {
  return kind === 'pedigree' && orientationIndex === 0
}
// Per-kind zoom for the unified art overlay — scales the shaped art up so its soft/feathered edges push past
// the cell edges and the solid core fills each occupied cell (the art's own transparency keeps the hole).
const ART_OVERLAY_SCALE: Partial<Record<SlateKind, number>> = { corner_of_divinity: 1.3, fallen_starlight: 1.6, pedigree: 1.3, residence_of_stars: 1.35, space_rift: 1.4, spark_of_moth_fire: 1.5, when_sparks_set_prairie_ablaze: 1.5 }
// Per-kind fine offset in the art's UNROTATED frame (px) to centre off-centre source art. It rotates with the
// overlay, so one value stays correct across all orientations. For corner (orientation 0 shown rotated 90° CW)
// local +x,+y reads as screen left+down.
const ART_OVERLAY_OFFSET: Partial<Record<SlateKind, [number, number]>> = { corner_of_divinity: [9, 16], fallen_starlight: [10, 10], pedigree: [8, 14], residence_of_stars: [20, 38], space_rift: [25, 10], spark_of_moth_fire: [12, 12], when_sparks_set_prairie_ablaze: [10, -20] }
// Extra stretch (multiplies one axis only) for arts that don't match their footprint's aspect.
const ART_OVERLAY_STRETCH_X: Partial<Record<SlateKind, number>> = { space_rift: 1.6 }
const ART_OVERLAY_STRETCH_Y: Partial<Record<SlateKind, number>> = { when_sparks_set_prairie_ablaze: 1.4 }
// How far the art clip is pulled in from the slate outline (px) — the visible border band between art and bars.
const ART_INSET = 6
// Slate outline colours — the app's light-purple slate accent (not the gold legendary colour).
const OUTLINE_COLOR = '#9d8bc9'        // default bars
const OUTLINE_COLOR_HOVER = '#bcaae8'  // hovered
const OUTLINE_COLOR_SELECTED = '#d9ccff' // selected (light purple)
// Pixel box the unified art fills — extends GAP/2 past the cells on every side so the art meets the slate
// outline (which sits at the gap mid-line). Each cell contributes a full PITCH incl. its outer half-gaps.
function slateBBoxPx(cells: [number, number][]): { left: number; top: number; width: number; height: number } {
  const rs = cells.map(c => c[0]), cs = cells.map(c => c[1])
  const minR = Math.min(...rs), minC = Math.min(...cs)
  const cols = Math.max(...cs) - minC + 1, rows = Math.max(...rs) - minR + 1
  return { left: minC * PITCH - GAP / 2, top: minR * PITCH - GAP / 2, width: cols * PITCH, height: rows * PITCH }
}

// Outer boundary polygon (board-px points) tracing a footprint's outline — used to draw the whole-slate
// selection frame. Walks the unit-cell boundary edges and chains them; the outline sits GAP/2 outside the cells
// so it reads as a frame wrapping the slate (internal gaps covered → one unified shape). Single loop (our slate
// footprints have no holes).
function footprintOutline(cells: [number, number][]): [number, number][] {
  type P = [number, number]
  const occ = new Set(cells.map(([r, c]) => `${r},${c}`))
  const has = (r: number, c: number) => occ.has(`${r},${c}`)
  const edges: [P, P][] = []
  for (const [r, c] of cells) {
    if (!has(r - 1, c)) edges.push([[r, c], [r, c + 1]])           // top    (L→R)
    if (!has(r, c + 1)) edges.push([[r, c + 1], [r + 1, c + 1]])   // right  (T→B)
    if (!has(r + 1, c)) edges.push([[r + 1, c + 1], [r + 1, c]])   // bottom (R→L)
    if (!has(r, c - 1)) edges.push([[r + 1, c], [r, c]])           // left   (B→T)
  }
  if (!edges.length) return []
  const k = (p: P) => `${p[0]},${p[1]}`
  const byStart = new Map<string, [P, P]>()
  for (const e of edges) byStart.set(k(e[0]), e)
  const startC = edges[0][0]
  const corners: P[] = [startC]
  let cur = edges[0][1]
  for (let guard = 0; k(cur) !== k(startC) && guard < 1000; guard++) {
    corners.push(cur)
    const e = byStart.get(k(cur))
    if (!e) break
    cur = e[1]
  }
  return corners.map(([cr, cc]) => [cc * PITCH - GAP / 2, cr * PITCH - GAP / 2] as P)
}

// Drop collinear vertices so edges strictly alternate horizontal/vertical (the per-cell tracer emits one edge
// per cell side, leaving collinear points along straight runs).
function simplifyRectilinear(pts: [number, number][]): [number, number][] {
  const n = pts.length, out: [number, number][] = []
  for (let i = 0; i < n; i++) {
    const a = pts[(i - 1 + n) % n], b = pts[i], c = pts[(i + 1) % n]
    const cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if (cross !== 0) out.push(b)
  }
  return out
}
// Inset a CW rectilinear polygon inward by `d`. Inward normal for a CW (y-down) edge is (-dy, dx); each vertex
// moves by the sum of its two adjacent edge normals, which gives clean convex AND concave corners (the latter
// is what fixes the little square poking into the L's inner corner).
function insetRectilinear(pts: [number, number][], d: number): [number, number][] {
  const n = pts.length
  const norm = pts.map((p, i) => {
    const q = pts[(i + 1) % n]
    return [-Math.sign(q[1] - p[1]), Math.sign(q[0] - p[0])] as [number, number]
  })
  return pts.map((p, i) => {
    const a = norm[(i - 1 + n) % n], b = norm[i]
    return [p[0] + d * (a[0] + b[0]), p[1] + d * (a[1] + b[1])] as [number, number]
  })
}
// clip-path for the WHOLE footprint as one cohesive shape (relative to the art box origin): the outline polygon
// (which the bars trace) inset inward by `inset`, leaving a border band between the art and the bars. Concave
// corners stay clean. The art rotates/scales inside this clip.
function footprintInsetClip(cells: [number, number][], inset: number): string {
  let pts = footprintOutline(cells)
  if (!pts.length) return ''
  pts = insetRectilinear(simplifyRectilinear(pts), inset)
  const minR = Math.min(...cells.map(c => c[0])), minC = Math.min(...cells.map(c => c[1]))
  const ox = minC * PITCH - GAP / 2, oy = minR * PITCH - GAP / 2   // = slateBBoxPx left/top
  return `polygon(${pts.map(([x, y]) => `${x - ox}px ${y - oy}px`).join(', ')})`
}

// ── Legendary metadata ────────────────────────────────────────────────────────

const LEGENDARY_META: Record<LegendaryKind, { label: string; color: string }> = {
  pedigree:                       { label: 'Pedigree of Gods',                   color: LEGEND_GOLD },
  fallen_starlight:               { label: 'Fallen Starlight',                   color: LEGEND_GOLD },
  corner_of_divinity:             { label: 'Corner of Divinity',                 color: LEGEND_GOLD },
  spark_of_moth_fire:             { label: 'Sparks of Moth Fire',                color: LEGEND_GOLD },
  when_sparks_set_prairie_ablaze: { label: 'When Sparks Set the Prairie Ablaze', color: LEGEND_GOLD },
  space_rift:                     { label: 'Space Rift',                         color: LEGEND_GOLD },
  residence_of_stars:             { label: 'Residence of Stars',                color: LEGEND_GOLD },
}

// Max copies allowed ON THE BOARD per kind (inventory is unlimited). Base slates have no limit.
const SLATE_LIMITS: Partial<Record<SlateKind, number>> = {
  corner_of_divinity: 3,
  fallen_starlight: 3,
  spark_of_moth_fire: 3,
  pedigree: 1,
  residence_of_stars: 1,
  space_rift: 1,
  when_sparks_set_prairie_ablaze: 1,
}
const SLATE_LIMIT_LABEL: Partial<Record<SlateKind, string>> = {
  corner_of_divinity: 'Corners',
  fallen_starlight: 'Starlights',
  spark_of_moth_fire: 'Moths',
  pedigree: 'Pedigree',
  residence_of_stars: 'Residence',
  space_rift: 'Space Rift',
  when_sparks_set_prairie_ablaze: 'Prairie',
}

// Bundled slate icons (served from data/images/icons/divinity_slate/, paired by basename via iconUrl).
// Base art filename = UI_TalantNG_<form>_0_Icon_<treeAbbr>_128.webp; mirror forms reuse the partner art flipped.
const TREE_ABBR: Record<PrimaryTree, string> = {
  'God of War':           'SA',
  'Goddess of Hunting':   'Agi',
  'Goddess of Deception': 'AI',
  'Goddess of Knowledge': 'Int',
  'God of Might':         'Str',
  'God of Machines':      'SI',
}
function baseArtFile(artForm: string, treeType?: string | null): string | null {
  if (!treeType) return null
  const abbr = TREE_ABBR[treeType as PrimaryTree]
  return abbr ? `UI_TalantNG_${artForm}_0_Icon_${abbr}_128.webp` : null
}
const LEGENDARY_ICON: Record<LegendaryKind, string> = {
  pedigree:                       'UI_MI_TalantNG_Gold_ZZ1_0_Icon_128.webp',
  fallen_starlight:               'UI_MI_TalantNG_Gold_I1_0_Icon_128.webp',
  corner_of_divinity:             'UI_MI_TalantNG_Gold_V1_0_Icon_128.webp',
  spark_of_moth_fire:             'UI_MI_TalantNG_Gold_O1_0_Icon_128.webp',
  when_sparks_set_prairie_ablaze: 'UI_MI_TalantNG_Gold_O3_0_Icon_128.webp',
  space_rift:                     'UI_MI_TalantNG_Gold_II1_0_Icon_128.webp',
  residence_of_stars:             'UI_MI_TalantNG_Gold_LL1_0_Icon_128.webp',
}
function slateIconFile(kind: SlateKind, treeType?: string | null, shapeIndex = 0): string | null {
  if (kind === 'base') return baseArtFile(BASE_FORMS[shapeIndex]?.artForm ?? 'O1', treeType)
  return LEGENDARY_ICON[kind as LegendaryKind] ?? null
}
// Versioned URL — bump SLATE_ICON_V when the bundled webp are re-trimmed so the renderer cache reloads them.
const SLATE_ICON_V = '3'
function slateIconUrl(kind: SlateKind, treeType?: string | null, shapeIndex = 0): string | null {
  const u = iconUrl('divinity_slate', slateIconFile(kind, treeType, shapeIndex))
  return u ? `${u}?v=${SLATE_ICON_V}` : null
}
function SlateIcon({ kind, treeType, shapeIndex = 0, size = 26 }: { kind: SlateKind; treeType?: string | null; shapeIndex?: number; size?: number }) {
  const src = slateIconUrl(kind, treeType, shapeIndex)
  if (!src) return null
  const flip = kind === 'base' && !!BASE_FORMS[shapeIndex]?.flip
  return <img src={src} alt="" style={{ width: size, height: size, objectFit: 'contain', flexShrink: 0, transform: flip ? 'scaleX(-1)' : undefined }} />
}

const SLATE_DESCRIPTIONS: Record<SlateKind, string> = {
  base:                           '5 modifiers · tree-based pool',
  pedigree:                       '4 modifiers · all-trees pool',
  fallen_starlight:               '4 modifiers · all-trees pool',
  corner_of_divinity:             '2 modifiers · all-trees pool',
  spark_of_moth_fire:             'Copies one adjacent slate',
  when_sparks_set_prairie_ablaze: 'Copies up to 4 adjacent slates',
  space_rift:                     "Copies a left/right neighbor's Medium talents",
  residence_of_stars:             "Copies adjacent Medium talents (no Legendary)",
}

// ── Slot configuration ────────────────────────────────────────────────────────

interface SectionDef { label: string; count: number; maxType: SlotType; canBeCore?: boolean }

const SLOT_CONFIG: Record<SlateKind, { sections: SectionDef[]; poolScope: 'tree' | 'all' | 'none' }> = {
  base: {
    sections: [
      { label: 'Fixed Talent Nodes', count: 2, maxType: 'legendary' },
      { label: 'Brand Talent Nodes', count: 3, maxType: 'legendary' },
    ],
    poolScope: 'tree',
  },
  fallen_starlight: {
    sections: [
      { label: 'Top Modifiers',    count: 2, maxType: 'rare' },
      { label: 'Bottom Modifiers', count: 2, maxType: 'legendary' },
    ],
    poolScope: 'all',
  },
  corner_of_divinity: {
    sections: [{ label: 'Modifiers', count: 2, maxType: 'legendary' }],
    poolScope: 'all',
  },
  pedigree: {
    sections: [
      { label: 'Talent Modifiers', count: 2, maxType: 'legendary' },
      { label: 'Core Talents',     count: 2, maxType: 'legendary', canBeCore: true },
    ],
    poolScope: 'all',
  },
  spark_of_moth_fire:             { sections: [], poolScope: 'none' },
  when_sparks_set_prairie_ablaze: { sections: [], poolScope: 'none' },
  space_rift:                     { sections: [], poolScope: 'none' },
  residence_of_stars:             { sections: [], poolScope: 'none' },
}

// ── Slot model ────────────────────────────────────────────────────────────────

interface CreatorSlot {
  slotType: SlotType
  maxType: SlotType
  canBeCore: boolean
  isCore: boolean
  selectedNodeId: string | null
  selectedCoreKey: string | null
  coreName: string | null
  effects: string[]
  nodeType?: string | null   // selected node's talent type — for the copy-slate "Medium talents" filter
}

function initSlots(kind: SlateKind): CreatorSlot[] {
  return (SLOT_CONFIG[kind]?.sections ?? []).flatMap(s =>
    Array.from({ length: s.count }, () => ({
      slotType: s.maxType, maxType: s.maxType,
      canBeCore: s.canBeCore ?? false, isCore: s.canBeCore ?? false,
      selectedNodeId: null, selectedCoreKey: null, coreName: null, effects: [] as string[], nodeType: null,
    }))
  )
}

function getSections(kind: SlateKind): { label: string; indices: number[]; canBeCore: boolean }[] {
  let offset = 0
  return (SLOT_CONFIG[kind]?.sections ?? []).map(s => {
    const indices = Array.from({ length: s.count }, (_, i) => offset + i)
    offset += s.count
    return { label: s.label, indices, canBeCore: s.canBeCore ?? false }
  })
}

export interface PlacedSlate {
  id: string                 // unique per board placement
  templateId: string         // stable identity for the inventory entry (survives edits; shared with re-placed copies)
  kind: SlateKind
  cells: [number, number][]
  orientationIndex: number
  shapeIndex: number
  anchor: [number, number]
  slots: CreatorSlot[]
  pool?: SlatePool
  treeType?: PrimaryTree
  mothDirection?: MothDirection
}

// ── Creator state ─────────────────────────────────────────────────────────────

interface CreatorState {
  kind: SlateKind
  shapeIndex: number
  treeType: PrimaryTree | null
  slots: CreatorSlot[]
  orientationIndex: number
  pool: SlatePool | null
  poolLoading: boolean
  openPicker: number | null
  pickerSearch: string
  mothDirection: MothDirection | null
  templateId?: string   // set when re-placing a saved template, so the placed copy links to its inventory entry
}

type PanelMode =
  | { type: 'idle' }
  | { type: 'choosing' }
  | { type: 'creating'; creator: CreatorState }
  | { type: 'editing'; slateId: string; creator: CreatorState }

function defaultCreator(kind: SlateKind): CreatorState {
  return {
    kind, shapeIndex: 0, treeType: null, slots: initSlots(kind),
    orientationIndex: 0, pool: null, poolLoading: false,
    openPicker: null, pickerSearch: '', mothDirection: null,
  }
}

// ── Slot helpers ──────────────────────────────────────────────────────────────

const SLOT_TYPE_COLOR: Record<SlotType, string> = { magic: '#4a90d9', rare: '#9060d0', legendary: '#c8881a' }
const SLOT_TYPE_LABEL: Record<SlotType, string> = { magic: 'M', rare: 'R', legendary: 'L' }

function cycleSlotType(current: SlotType, maxType: SlotType): SlotType {
  const all: SlotType[] = ['legendary', 'rare', 'magic']
  const allowed = all.slice(all.indexOf(maxType))
  return allowed[(allowed.indexOf(current) + 1) % allowed.length]
}

function getSlotModifierPool(pool: SlatePool, slotType: SlotType): SlateModifierOption[] {
  if (slotType === 'magic') return pool.magic
  if (slotType === 'rare') return [...pool.rare, ...pool.magic]
  return [...pool.legendary, ...pool.rare, ...pool.magic]
}

function getBottomEffects(slate: PlacedSlate): string[] {
  if (!slate.slots.length) return []
  return slate.slots[slate.slots.length - 1].effects
}

// ── Saved-slate templates (build inventory) ───────────────────────────────────

// Build the inventory template for a slate, keyed by its STABLE templateId (so editing the slate updates the
// same entry instead of spawning a new one).
function toTemplate(s: PlacedSlate): SlateTemplate {
  return {
    id: s.templateId,
    kind: s.kind, orientationIndex: s.orientationIndex, shapeIndex: s.shapeIndex,
    slots: s.slots.map(sl => ({ ...sl })),
    treeType: s.treeType, mothDirection: s.mothDirection,
  }
}

// Build an inventory template straight from the creator (for "Add to Inventory" — saving without placing).
function creatorToTemplate(c: CreatorState, id: string): SlateTemplate {
  return {
    id,
    kind: c.kind, orientationIndex: c.orientationIndex, shapeIndex: c.shapeIndex,
    slots: c.slots.map(sl => ({ ...sl })),
    treeType: c.treeType ?? undefined, mothDirection: c.mothDirection ?? undefined,
  }
}

// ── Prairie / Moth helpers ────────────────────────────────────────────────────

function getPrairieModifiers(prairie: PlacedSlate, placed: PlacedSlate[]): string[] {
  const [pr, pc] = prairie.anchor
  const seen = new Set<string>()   // a neighbour touching on >1 side is still copied only ONCE
  const out: string[] = []
  for (const [dr, dc] of [[-1,0],[1,0],[0,-1],[0,1]] as [number,number][]) {
    const key = `${pr + dr},${pc + dc}`
    const neighbor = placed.find(s => s.id !== prairie.id && s.cells.some(([r, c]) => `${r},${c}` === key))
    if (!neighbor || seen.has(neighbor.id)) continue
    seen.add(neighbor.id)
    const effects = getBottomEffects(neighbor)
    if (effects.length) out.push(effects.join(' / '))
  }
  return out
}

const MOTH_DELTA: Record<MothDirection, [number, number]> = { above: [-1,0], below: [1,0], left: [0,-1], right: [0,1] }

function getMothModifier(moth: PlacedSlate, placed: PlacedSlate[]): string | null {
  if (!moth.mothDirection) return null
  const [mr, mc] = moth.anchor
  const [dr, dc] = MOTH_DELTA[moth.mothDirection] ?? [0, 0]
  const target = placed.find(s => s.id !== moth.id && s.cells.some(([r, c]) => `${r},${c}` === `${mr + dr},${mc + dc}`))
  if (!target) return null
  const effects = getBottomEffects(target)
  return effects.length ? effects.join(' / ') : null
}

// Space Rift / Residence of Stars copy a neighbor's MEDIUM-talent slot effects (not Micro). Space Rift =
// one chosen L/R direction incl. Legendary Medium; Residence = all four, Medium only (excl. Legendary Medium).
function copyMediumLines(slate: PlacedSlate, placed: PlacedSlate[], dirs: [number, number][], allowLegendaryMedium: boolean): string[] {
  // Footprint-based: look at every cell adjacent to any of this slate's cells; copy each distinct neighbor
  // slate's Medium talents once.
  const seen = new Set<string>()
  const out: string[] = []
  for (const [cr, cc] of slate.cells) for (const [dr, dc] of dirs) {
    const n = placed.find(s => s.id !== slate.id && s.cells.some(([r, c]) => r === cr + dr && c === cc + dc))
    if (!n || seen.has(n.id)) continue
    seen.add(n.id)
    for (const sl of n.slots) {
      const t = sl.nodeType ?? ''
      if (!sl.selectedNodeId || !t.includes('Medium Talent')) continue      // skip empty + Micro
      if (!allowLegendaryMedium && t !== 'Medium Talent') continue           // Residence: skip Legendary Medium
      out.push(...sl.effects)
    }
  }
  return out
}

function slateCopyLines(slate: PlacedSlate, placed: PlacedSlate[]): string[] {
  if (slate.kind === 'spark_of_moth_fire') { const m = getMothModifier(slate, placed); return m ? [m] : [] }
  if (slate.kind === 'when_sparks_set_prairie_ablaze') return getPrairieModifiers(slate, placed)
  if (slate.kind === 'space_rift') return slate.mothDirection ? copyMediumLines(slate, placed, [MOTH_DELTA[slate.mothDirection] ?? [0, 0]], true) : []
  if (slate.kind === 'residence_of_stars') return copyMediumLines(slate, placed, Object.values(MOTH_DELTA), false)
  return []
}

// ── Mini shape preview ────────────────────────────────────────────────────────

function MiniShape({ offsets, color, size = 9 }: { offsets: [number, number][]; color: string; size?: number }) {
  if (!offsets.length) return null
  const maxRow = Math.max(...offsets.map(([r]) => r))
  const maxCol = Math.max(...offsets.map(([, c]) => c))
  const set = new Set(offsets.map(([r, c]) => `${r},${c}`))
  return (
    <div style={{ display: 'inline-grid', gridTemplateColumns: `repeat(${maxCol + 1}, ${size}px)`, gap: 1.5 }}>
      {Array.from({ length: maxRow + 1 }, (_, r) =>
        Array.from({ length: maxCol + 1 }, (_, c) => (
          <div key={`${r},${c}`} style={{
            width: size, height: size,
            background: set.has(`${r},${c}`) ? color : 'rgba(255,255,255,0.04)',
            borderRadius: 2,
          }} />
        ))
      ).flat()}
    </div>
  )
}

// ── Modifier slot ─────────────────────────────────────────────────────────────

interface ModifierSlotProps {
  slot: CreatorSlot; index: number; allSlots: CreatorSlot[]
  pool: SlatePool | null; isOpen: boolean; search: string; accentColor: string
  onTogglePicker: () => void; onCycleType: () => void
  onSelect: (mod: SlateModifierOption) => void; onSelectCore: (core: CoreTalentOption) => void
  onClear: () => void; onSearchChange: (s: string) => void
}

function ModifierSlot({ slot, allSlots, pool, isOpen, search, accentColor,
  onTogglePicker, onCycleType, onSelect, onSelectCore, onClear, onSearchChange,
}: ModifierSlotProps) {
  const usedNodeIds = new Set(allSlots.map(s => s.selectedNodeId).filter(Boolean) as string[])
  const usedCoreKeys = new Set(allSlots.map(s => s.selectedCoreKey).filter(Boolean) as string[])
  const isDuplicate = slot.isCore && slot.selectedCoreKey
    ? (Array.from(usedCoreKeys).filter(k => k === slot.selectedCoreKey).length > 1) : false

  const displayText = slot.isCore
    ? (slot.selectedCoreKey ? slot.effects.join(' / ') : null)
    : (slot.selectedNodeId ? slot.effects.join(' / ') : null)

  // canBeCore slots (e.g. Pedigree's bottom two) show ONE mixed, searchable list of core talents AND regular
  // modifiers — no mode toggle. Plain slots show only modifiers.
  const modOptions = pool
    ? getSlotModifierPool(pool, slot.slotType).filter(m => {
        if (m.nodeId === slot.selectedNodeId) return true
        if (usedNodeIds.has(m.nodeId)) return false
        return !search || m.effects.some(e => e.toLowerCase().includes(search.toLowerCase()))
      }) : []

  const coreOptions = slot.canBeCore && pool
    ? pool.core.filter(c => {
        if (c.key === slot.selectedCoreKey) return true
        return !search || c.effects.some(e => e.toLowerCase().includes(search.toLowerCase())) || c.name.toLowerCase().includes(search.toLowerCase())
      }) : []

  // canBeCore slots always show golden C
  const badgeColor = slot.canBeCore ? LEGEND_GOLD : SLOT_TYPE_COLOR[slot.slotType]
  const badgeLabel = slot.canBeCore ? 'C' : SLOT_TYPE_LABEL[slot.slotType]

  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 9, padding: '9px 12px',
        background: isDuplicate ? '#2a1010' : '#191930',
        border: `1px solid ${isOpen ? accentColor : isDuplicate ? '#aa3333' : '#252545'}`,
        borderRadius: 6,
      }}>
        <div
          onClick={e => { e.stopPropagation(); if (!slot.canBeCore) onCycleType() }}
          title={slot.canBeCore ? 'Core talent slot' : `${slot.slotType} (click to cycle)`}
          style={{
            width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
            background: badgeColor, color: '#fff', fontSize: 11, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: slot.canBeCore ? 'default' : 'pointer',
          }}
        >{badgeLabel}</div>

        <div onClick={onTogglePicker} style={{ flex: 1, minWidth: 0, cursor: 'pointer' }}>
          {displayText
            ? <div style={{ lineHeight: 1.4 }}>
                {isDuplicate && <span style={{ fontSize: 11, color: '#cc4444' }}>[duplicate] </span>}
                {slot.coreName && (
                  <div style={{ fontSize: 13, fontWeight: 700, color: LEGEND_GOLD, marginBottom: 2 }}>{slot.coreName}</div>
                )}
                <div style={{ fontSize: 13, color: isDuplicate ? '#cc4444' : '#bbb' }}>{displayText}</div>
              </div>
            : <div style={{ fontSize: 13, color: '#404058', fontStyle: 'italic' }}>Empty Talent Node</div>
          }
        </div>

        {(slot.selectedNodeId || slot.selectedCoreKey) && (
          <div onClick={e => { e.stopPropagation(); onClear() }}
            style={{ fontSize: 14, color: '#444', cursor: 'pointer', flexShrink: 0 }}>✕</div>
        )}
      </div>

      {isOpen && (
        <div style={{
          background: '#111128', border: `1px solid ${accentColor}55`,
          borderTop: 'none', borderRadius: '0 0 6px 6px', maxHeight: 260, overflowY: 'auto',
        }} onClick={e => e.stopPropagation()}>
          <div style={{ padding: '6px 9px', borderBottom: '1px solid #1e1e3a', position: 'sticky', top: 0, background: '#111128' }}>
            <input autoFocus value={search} onChange={e => onSearchChange(e.target.value)}
              placeholder="Search modifiers…"
              style={{ width: '100%', boxSizing: 'border-box', background: '#1a1a3a', border: '1px solid #2a2a5a', color: '#ddd', padding: '5px 9px', fontSize: 14, borderRadius: 3 }}
            />
          </div>
          {/* Core talents first (canBeCore slots only), then modifiers — one combined searchable list. */}
          {slot.canBeCore && coreOptions.length > 0 && (
            <>
              <div style={{ padding: '5px 14px', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.6, color: LEGEND_GOLD, background: '#13132a' }}>Core Talents</div>
              {coreOptions.map(core => {
                const selected = core.key === slot.selectedCoreKey
                return (
                  <div key={core.key} onClick={() => onSelectCore(core)} style={{
                    padding: '8px 14px', cursor: 'pointer', borderBottom: '1px solid #1a1a30',
                    background: selected ? `${accentColor}18` : 'transparent',
                    borderLeft: selected ? `2px solid ${accentColor}` : '2px solid transparent',
                    opacity: (!selected && usedCoreKeys.has(core.key)) ? 0.4 : 1,
                  }}>
                    <div style={{ fontSize: 14, color: selected ? '#fff' : '#bbb' }}>{core.name}</div>
                    {core.effects.map((e, i) => <div key={i} style={{ fontSize: 12, color: '#888' }}>{e}</div>)}
                    <div style={{ fontSize: 11, color: '#444', marginTop: 2 }}>{core.treeName}</div>
                  </div>
                )
              })}
            </>
          )}
          {slot.canBeCore && modOptions.length > 0 && (
            <div style={{ padding: '5px 14px', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.6, color: '#7a7aa0', background: '#13132a' }}>Modifiers</div>
          )}
          {modOptions.map(mod => (
            <SlateModRow key={mod.nodeId} mod={mod} selected={mod.nodeId === slot.selectedNodeId} accentColor={accentColor} onSelect={onSelect} />
          ))}
          {modOptions.length === 0 && coreOptions.length === 0 && (
            <div style={{ padding: '11px 14px', fontSize: 14, color: '#444' }}>
              {pool ? 'No matches' : 'No season active — no modifier pool'}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Shape panel (right side) ──────────────────────────────────────────────────

function ShapePanel({ creator, treeColors, onRotate, onSelectOrientation, onSelectShape }: {
  creator: CreatorState; treeColors: Record<string, string>
  onRotate: () => void; onSelectOrientation: (i: number) => void; onSelectShape: (i: number) => void
}) {
  const { kind, orientationIndex, shapeIndex, treeType } = creator
  const color = kind === 'base'
    ? (treeType ? treeColors[treeType] ?? '#888' : '#888')
    : LEGENDARY_META[kind as LegendaryKind]?.color ?? '#888'
  const count = getOrientationCount(kind)

  const legLabel = (idx: number) => {
    if (kind === 'pedigree') return idx === 0 ? '→ Right' : '← Left'
    if (kind === 'fallen_starlight') return idx === 0 ? '↔ H' : '↕ V'
    return ['↗','↘','↙','↖'][idx] ?? `${idx}`
  }

  return (
    <div style={{ width: '100%', boxSizing: 'border-box', background: '#12121e', padding: '16px 14px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      {kind === 'base' ? (
        <>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#666', marginBottom: 8 }}>Shape</div>
            {BASE_SHAPES.map((shape, idx) => {
              const active = idx === shapeIndex
              return (
                <button key={idx} onClick={() => onSelectShape(idx)} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', width: '100%', marginBottom: 4,
                  background: active ? `${color}22` : '#1a1a3a', border: `1px solid ${active ? color : '#252540'}`,
                  borderRadius: 6, cursor: 'pointer',
                }}>
                  <div style={{ minWidth: 32, display: 'flex', justifyContent: 'center' }}>
                    <MiniShape offsets={shape.rotations[0] as [number,number][]} color={active ? color : '#484870'} size={12} />
                  </div>
                  <span style={{ fontSize: 14, color: active ? color : '#777' }}>{shape.label}</span>
                </button>
              )
            })}
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#666', marginBottom: 8 }}>Rotation</div>
            {BASE_SHAPES[shapeIndex].rotations.map((cells, idx) => {
              const active = idx === orientationIndex
              return (
                <button key={idx} onClick={() => onSelectOrientation(idx)} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', width: '100%', marginBottom: 4,
                  background: active ? `${color}22` : '#1a1a3a', border: `1px solid ${active ? color : '#252540'}`,
                  borderRadius: 6, cursor: 'pointer',
                }}>
                  <div style={{ minWidth: 32, display: 'flex', justifyContent: 'center' }}>
                    <MiniShape offsets={cells as [number,number][]} color={active ? color : '#484870'} size={12} />
                  </div>
                  <span style={{ fontSize: 13, color: active ? color : '#777' }}>{ROTATION_LABELS[idx]}</span>
                </button>
              )
            })}
            <button onClick={onRotate} style={{ padding: '8px 12px', fontSize: 14, width: '100%', marginTop: 4, background: '#1e1e38', color: '#888', border: '1px solid #2a2a50', borderRadius: 6, cursor: 'pointer' }}>
              ↻ Rotate
            </button>
          </div>
        </>
      ) : (
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#666', marginBottom: 8 }}>
            {count > 1 ? 'Rotation' : 'Shape'}
          </div>
          {(LEGENDARY_ORIENTATIONS[kind as LegendaryKind] ?? []).map((offsets, idx) => {
            const active = idx === orientationIndex
            return (
              <button key={idx} onClick={() => onSelectOrientation(idx)} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', width: '100%', marginBottom: 4,
                background: active ? `${color}20` : '#1a1a3a', border: `1px solid ${active ? color : '#252540'}`,
                borderRadius: 6, cursor: 'pointer',
              }}>
                <div style={{ minWidth: 32, display: 'flex', justifyContent: 'center' }}>
                  <MiniShape offsets={offsets as [number,number][]} color={active ? color : '#484870'} size={12} />
                </div>
                <span style={{ fontSize: 14, color: active ? color : '#777' }}>{legLabel(idx)}</span>
              </button>
            )
          })}
          {count > 1 && (
            <button onClick={onRotate} style={{ padding: '8px 12px', fontSize: 14, marginTop: 4, width: '100%', background: '#1e1e38', color: '#888', border: '1px solid #2a2a50', borderRadius: 6, cursor: 'pointer' }}>
              ↻ Rotate
            </button>
          )}
          <div style={{ fontSize: 12, color: '#3a3a5a', marginTop: 4, lineHeight: 1.7 }}>
            {kind === 'pedigree' && 'Flip to mirror'}
            {kind === 'spark_of_moth_fire' && 'No rotation'}
            {kind === 'when_sparks_set_prairie_ablaze' && 'No rotation'}
            {kind === 'fallen_starlight' && 'H or V orientation'}
            {kind === 'corner_of_divinity' && '4 clockwise rotations'}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Slate tooltip body (rendered inside a floating `.tooltip`) ─────────────────
// Per-slate detail: icon/label/tree, copy mechanics, slot effects, and (for placed slates) the removal DPS
// delta. `noDelta` is set for inventory tiles, which have no placed instance.

function SlateTooltipBody({ slate, treeColors, placed: allPlaced, noDelta }: {
  slate: PlacedSlate; treeColors: Record<string, string>; placed: PlacedSlate[]; noDelta?: boolean
}) {
  const isMoth = slate.kind === 'spark_of_moth_fire'
  const isPrairie = slate.kind === 'when_sparks_set_prairie_ablaze'
  const isMediumCopy = slate.kind === 'space_rift' || slate.kind === 'residence_of_stars'
  const mediumCopyLines = isMediumCopy ? slateCopyLines(slate, allPlaced) : []
  const color = slate.kind === 'base'
    ? (treeColors[slate.treeType ?? ''] ?? '#666')
    : LEGENDARY_META[slate.kind as LegendaryKind]?.color ?? '#666'
  const label = slate.kind === 'base' ? 'Base Slate' : LEGENDARY_META[slate.kind as LegendaryKind]?.label ?? 'Slate'

  const mothMod = isMoth ? getMothModifier(slate, allPlaced) : null
  const prairieMods = isPrairie ? getPrairieModifiers(slate, allPlaced) : []

  // What you'd LOSE by removing this placed slate (step = build without it, base = current) — a
  // negative/red band, matching the talent-node convention.
  const delta = useDamageDelta(
    { key: `slate:rm:${slate.id}`, step: s => ({ ...s, slates: s.slates.filter(sl => sl.id !== slate.id) }) },
    !noDelta,
  )

  return (
    <div style={{ minWidth: 200, maxWidth: 300, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <SlateIcon kind={slate.kind} treeType={slate.treeType} shapeIndex={slate.shapeIndex} size={30} />
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color, marginBottom: 2 }}>{label}</div>
          {slate.treeType && <div style={{ fontSize: 11, color: '#666' }}>{slate.treeType}</div>}
        </div>
      </div>

      {isMoth && (
        <div>
          <div style={{ fontSize: 11, color: '#555', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
            Copies {slate.mothDirection ?? '?'}
          </div>
          {mothMod
            ? <div style={{ fontSize: 12, color: '#ddd', lineHeight: 1.5 }}>{mothMod}</div>
            : <div style={{ fontSize: 12, color: '#3a3a5a', fontStyle: 'italic' }}>No adjacent slate</div>}
        </div>
      )}

      {isPrairie && (
        <div>
          <div style={{ fontSize: 11, color: '#555', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
            Copies {prairieMods.length} adjacent
          </div>
          {prairieMods.length > 0
            ? prairieMods.map((m, i) => <div key={i} style={{ fontSize: 12, color: '#ddd', lineHeight: 1.5, marginBottom: 3 }}>{m}</div>)
            : <div style={{ fontSize: 12, color: '#3a3a5a', fontStyle: 'italic' }}>No adjacent slates</div>}
        </div>
      )}

      {isMediumCopy && (
        <div>
          <div style={{ fontSize: 11, color: '#555', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
            {slate.kind === 'space_rift' ? `Copies Medium talents (${slate.mothDirection ?? '?'})` : 'Copies adjacent Medium talents'}
          </div>
          {mediumCopyLines.length > 0
            ? mediumCopyLines.map((m, i) => <div key={i} style={{ fontSize: 12, color: '#ddd', lineHeight: 1.5, marginBottom: 3 }}>{m}</div>)
            : <div style={{ fontSize: 12, color: '#3a3a5a', fontStyle: 'italic' }}>No adjacent Medium talents</div>}
        </div>
      )}

      {slate.slots.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {slate.slots.map((slot, i) => {
            const filled = !!(slot.selectedNodeId || slot.selectedCoreKey)
            const text = filled ? slot.effects.join(' / ') : null
            const badgeColor = slot.canBeCore ? LEGEND_GOLD : SLOT_TYPE_COLOR[slot.slotType]
            const badgeLabel = slot.canBeCore ? 'C' : SLOT_TYPE_LABEL[slot.slotType]
            return (
              <div key={i} style={{ display: 'flex', gap: 7, alignItems: 'flex-start', opacity: filled ? 1 : 0.28 }}>
                <div style={{
                  width: 18, height: 18, borderRadius: '50%', flexShrink: 0, marginTop: 2,
                  background: badgeColor, color: '#fff', fontSize: 9, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>{badgeLabel}</div>
                <div style={{ minWidth: 0 }}>
                  {slot.coreName && filled && (
                    <div style={{ fontSize: 12, fontWeight: 700, color: LEGEND_GOLD, marginBottom: 2 }}>{slot.coreName}</div>
                  )}
                  <div style={{ fontSize: 12, color: filled ? '#ccc' : '#3a3a5a', lineHeight: 1.5, fontStyle: filled ? 'normal' : 'italic' }}>
                    {text ?? 'Empty Talent Node'}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {!noDelta && <TooltipContributions delta={delta} />}
    </div>
  )
}

// Saved-slate thumbnail in the inventory grid: click to place, right-click to delete, hover for a floating
// detail tooltip (built from the template — no placed instance, so no DPS delta).
function InventoryTile({ template, color, treeColors, onPlace, onDelete, onDuplicate, onRename }: {
  template: SlateTemplate; color: string; treeColors: Record<string, string>
  onPlace: () => void; onDelete: () => void; onDuplicate: () => void
  onRename: (next: string) => void   // sets a DISPLAY label only (true kind name kept in the tooltip)
}) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right' })
  const [renaming, setRenaming] = useState(false)
  const [renameDraft, setRenameDraft] = useState('')
  const commitRename = () => { onRename(renameDraft); setRenaming(false) }
  const cornerBtn = (extra: React.CSSProperties): React.CSSProperties => ({
    position: 'absolute', width: 18, height: 18, padding: 0,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'var(--bg-surface)', color: 'var(--fg-muted)', border: `1px solid ${color}55`, borderRadius: 5,
    fontSize: 11, cursor: 'pointer', lineHeight: 1, ...extra,
  })
  const pseudo: PlacedSlate = {
    id: `tpl-${template.id}`, templateId: template.id, kind: template.kind as SlateKind, cells: [], anchor: [0, 0],
    orientationIndex: template.orientationIndex, shapeIndex: template.shapeIndex,
    slots: template.slots as unknown as CreatorSlot[],
    treeType: template.treeType as PrimaryTree | undefined,
    mothDirection: template.mothDirection as MothDirection | undefined,
  }
  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, width: 62 }}>
        <div {...tip.triggerProps} onClick={onPlace} onContextMenu={e => { e.preventDefault(); onDelete() }}
          title="Click to place · right-click to delete"
          style={{
            position: 'relative', width: 62, height: 62, display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: '#16162a', border: `1px solid ${color}55`, borderRadius: 7, cursor: 'pointer',
          }}>
          <SlateIcon kind={template.kind as SlateKind} treeType={template.treeType} shapeIndex={template.shapeIndex} size={48} />
          <button onClick={e => { e.stopPropagation(); setRenameDraft(template.displayName ?? ''); setRenaming(true) }}
            title="Rename — set a display label" style={cornerBtn({ top: -6, left: -6 })}>✎</button>
          <button onClick={e => { e.stopPropagation(); onDuplicate() }}
            title="Duplicate — tweak a copy and compare" style={cornerBtn({ top: -6, right: -6 })}>⧉</button>
        </div>
        {renaming ? (
          <input className="gear-build-rename-input" autoFocus value={renameDraft} placeholder="Label…"
            style={{ width: 62, fontSize: 9, padding: '1px 3px' }}
            onChange={e => setRenameDraft(e.target.value)} onBlur={commitRename}
            onKeyDown={e => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setRenaming(false) }} />
        ) : template.displayName ? (
          <span title={template.displayName}
            style={{ fontSize: 9, color: 'var(--fg-muted)', maxWidth: 62, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {template.displayName}
          </span>
        ) : null}
      </div>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip" {...tip.floatingProps}>
            <SlateTooltipBody slate={pseudo} treeColors={treeColors} placed={[]} noDelta />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

// ── Slate bonuses overview (right panel, idle) ────────────────────────────────

// Bottom-slot effect lines copied by a Moth slate (one neighbour) / Prairie slate (all four).
function mothBottomLines(moth: PlacedSlate, placed: PlacedSlate[]): string[] {
  if (!moth.mothDirection) return []
  const [mr, mc] = moth.anchor
  const [dr, dc] = ({ above: [-1,0], below: [1,0], left: [0,-1], right: [0,1] } as Record<MothDirection,[number,number]>)[moth.mothDirection]
  const target = placed.find(s => s.id !== moth.id && s.cells.some(([r, c]) => r === mr + dr && c === mc + dc))
  return target ? getBottomEffects(target) : []
}
function prairieBottomLines(prairie: PlacedSlate, placed: PlacedSlate[]): string[] {
  const [pr, pc] = prairie.anchor
  const seen = new Set<string>()   // copy each distinct neighbour slate only once
  const out: string[] = []
  for (const [dr, dc] of [[-1,0],[1,0],[0,-1],[0,1]] as [number,number][]) {
    const n = placed.find(s => s.id !== prairie.id && s.cells.some(([r, c]) => r === pr + dr && c === pc + dc))
    if (!n || seen.has(n.id)) continue
    seen.add(n.id)
    out.push(...getBottomEffects(n))
  }
  return out
}

function SlateOverview({ placed, hideHeading }: { placed: PlacedSlate[]; hideHeading?: boolean }) {
  // Split placed-slate effects into deduped CORE TALENTS (count once by key, like the engine — never
  // summed) and modifier LINES (summed arithmetically by summarizeSlateBonuses).
  const { cores, modLines } = useMemo(() => {
    const coreMap = new Map<string, { name: string; effects: string[] }>()
    const lines: string[] = []
    for (const slate of placed) {
      if (slate.kind === 'spark_of_moth_fire') { lines.push(...mothBottomLines(slate, placed)); continue }
      if (slate.kind === 'when_sparks_set_prairie_ablaze') { lines.push(...prairieBottomLines(slate, placed)); continue }
      if (slate.kind === 'space_rift') { lines.push(...(slate.mothDirection ? copyMediumLines(slate, placed, [MOTH_DELTA[slate.mothDirection] ?? [0, 0]], true) : [])); continue }
      if (slate.kind === 'residence_of_stars') { lines.push(...copyMediumLines(slate, placed, Object.values(MOTH_DELTA), false)); continue }
      for (const s of slate.slots) {
        if (s.isCore && s.selectedCoreKey) {
          if (!coreMap.has(s.selectedCoreKey)) coreMap.set(s.selectedCoreKey, { name: s.coreName ?? 'Core Talent', effects: s.effects })
        } else if (s.selectedNodeId) {
          lines.push(...s.effects)
        }
      }
    }
    return { cores: [...coreMap.values()], modLines: lines }
  }, [placed])

  const summary = useMemo(() => summarizeSlateBonuses(modLines), [modLines])
  const modStatuses = useTextModifierStatuses(summary.map(l => ({ text: l.badgeText, source: 'slate' as const })))
  const coreEffects = useMemo(() => cores.flatMap(c => c.effects), [cores])
  const coreStatuses = useTextModifierStatuses(coreEffects.map(text => ({ text, source: 'talent' as const })))

  const empty = cores.length === 0 && summary.length === 0
  // A thin divider BETWEEN entries (a core talent is one combined entry with its lines; each modifier
  // line is its own entry). Applied as a top border on every entry except the first.
  const entryStyle = (first: boolean): React.CSSProperties => ({
    padding: '6px 0', ...(first ? {} : { borderTop: '1px solid #20204a' }),
  })
  let coreIdx = 0
  return (
    <div style={{ padding: '14px 14px', boxSizing: 'border-box' }}>
      {!hideHeading && <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#8a7ad0', marginBottom: 4 }}>Slate Bonuses</div>}
      {empty && <div style={{ fontSize: 12, color: '#3a3a5a', fontStyle: 'italic', paddingTop: 6 }}>Configure slates to see their combined bonuses.</div>}

      {cores.map((c, ci) => (
        <div key={`core-${ci}`} style={entryStyle(ci === 0)}>
          <div style={{ fontSize: 12, fontWeight: 700, color: LEGEND_GOLD, marginBottom: 2 }}>{c.name}</div>
          {c.effects.map(eff => {
            const status = coreStatuses[coreIdx++]
            return <div key={coreIdx} style={{ fontSize: 12, color: '#cbd0e0', lineHeight: 1.5 }}>{eff}<ModifierBadge status={status} /></div>
          })}
        </div>
      ))}

      {summary.map((l, i) => (
        <div key={`mod-${i}`} style={{ fontSize: 12, color: '#cbd0e0', lineHeight: 1.5, ...entryStyle(cores.length === 0 && i === 0) }}>
          {l.text}
          {l.maxDivinity && <span style={{ fontSize: 10, color: '#7a7aa0' }}> (Max Divinity)</span>}
          <ModifierBadge status={modStatuses[i]} />
        </div>
      ))}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

interface Props {
  treeColors: Record<string, string>
  onBack: () => void
}

export default function SlateScreen({ treeColors }: Props) {
  const slates = useBuildStore(s => s.slates)
  const setSlates = useBuildStore(s => s.setSlates)
  const slateInventory = useBuildStore(s => s.slateInventory)
  const setSlateInventory = useBuildStore(s => s.setSlateInventory)
  const activeLoadoutId = useBuildStore(s => s.activeLoadoutId)
  const [placed, setPlaced] = useState<PlacedSlate[]>(
    () => (slates as unknown as PlacedSlate[]).map(s => ({ ...s, templateId: s.templateId ?? s.id })))
  const [mode, setMode] = useState<PanelMode>({ type: 'idle' })
  const [hover, setHover] = useState<[number, number] | null>(null)
  const [hoverSlateId, setHoverSlateId] = useState<string | null>(null)
  const [dragSlate, setDragSlate] = useState<{ slate: PlacedSlate; startCell: [number, number] } | null>(null)
  const suppressNextClick = useRef(false)
  const boardRef = useRef<HTMLDivElement>(null)
  const [bonusesOpen, setBonusesOpen] = useState(false)
  const boardTip = useFloatingTooltip({ anchor: 'cursor', side: 'right' })
  // Pre-edit snapshot of the slate currently being edited, so Cancel can revert (edits otherwise apply live).
  const editSnapshot = useRef<PlacedSlate | null>(null)
  const editingSlateId = mode.type === 'editing' ? mode.slateId : null

  // Sync the local board back to the build store — but ONLY when the slates actually changed.
  // Comparing against the store (instead of a first-render ref) avoids spuriously bumping
  // buildVersion (marking the build dirty) on entry, including StrictMode's double-invoked mount.
  useEffect(() => {
    const next = placed.map(({ pool: _p, ...s }) => s as SavedSlate)
    if (JSON.stringify(next) !== JSON.stringify(useBuildStore.getState().slates)) {
      setSlates(next)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [placed])

  // Auto-keep every placed slate in the build's inventory so it can be re-placed without rebuilding —
  // INCLUDING slates with no modifiers yet (empty base slates, Corner of Divinity, and Moth/Prairie
  // legendary slates that have no node slots at all). Entries are keyed by the slate's STABLE templateId
  // and UPSERTED — so editing a slate updates its single entry rather than spawning one per intermediate
  // state. Only the slate currently being edited is skipped so its in-progress states aren't saved; it's
  // upserted once editing ends / focus switches away.
  useEffect(() => {
    const inv = useBuildStore.getState().slateInventory
    const byId = new Map(inv.map(t => [t.id, t]))
    let changed = false
    for (const sl of placed) {
      if (sl.id === editingSlateId) continue                                     // skip in-progress edits
      const t = toTemplate(sl)
      const prev = byId.get(t.id)
      if (!prev || JSON.stringify(prev) !== JSON.stringify(t)) { byId.set(t.id, t); changed = true }
    }
    if (changed) setSlateInventory([...byId.values()])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [placed, editingSlateId])

  // Re-seed the local board when the active loadout changes. The `placed` initializer only runs on
  // mount, so a loadout switch (which swaps store.slates) would otherwise leave the board showing the
  // previous loadout until you navigate away and back. The store→local reseed here is followed by the
  // local→store sync effect above finding them equal (no spurious dirty bump / loop).
  useEffect(() => {
    setPlaced((useBuildStore.getState().slates as unknown as PlacedSlate[]).map(s => ({ ...s, templateId: s.templateId ?? s.id })))
    setMode({ type: 'idle' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLoadoutId])

  useEffect(() => {
    const handler = () => setMode(prev => {
      if (prev.type !== 'creating' && prev.type !== 'editing') return prev
      return { ...prev, creator: { ...prev.creator, openPicker: null } }
    })
    window.addEventListener('click', handler)
    return () => window.removeEventListener('click', handler)
  }, [])

  // Global pointer-up: finish drag or open edit
  useEffect(() => {
    const handler = () => {
      if (!dragSlate) return
      suppressNextClick.current = true

      const sameCell = hover && hover[0] === dragSlate.startCell[0] && hover[1] === dragSlate.startCell[1]

      if (sameCell || !hover) {
        // Press+release without moving = open/switch edit for this slate. Edits apply live, so switching away
        // from another slate keeps its changes automatically. Snapshot this slate so Cancel can revert it — but
        // only when STARTING a session on it (opening from idle or switching from another slate), NOT when
        // re-clicking the slate already being edited, so the snapshot keeps its session-start position/config.
        const slate = dragSlate.slate
        const sameSession = mode.type === 'editing' && mode.slateId === slate.id
        if (!sameSession) {
          editSnapshot.current = { ...slate, slots: slate.slots.map(s => ({ ...s })), cells: slate.cells.map(c => [...c] as [number, number]) }
        }
        const poolScope = SLOT_CONFIG[slate.kind]?.poolScope
        const needsPoolLoad = !slate.pool && poolScope !== 'none'
        setMode({
          type: 'editing', slateId: slate.id, creator: {
            kind: slate.kind, shapeIndex: slate.shapeIndex, treeType: slate.treeType ?? null,
            slots: slate.slots.map(s => ({ ...s })), orientationIndex: slate.orientationIndex,
            pool: slate.pool ?? null, poolLoading: needsPoolLoad, openPicker: null, pickerSearch: '',
            mothDirection: slate.mothDirection ?? null,
          },
        })
        // Reload pool from API — always stripped from SavedSlate on back-navigation
        if (needsPoolLoad) {
          const slateId = slate.id
          const poolPromise = poolScope === 'tree' && slate.treeType
            ? api.getSlatePool(slate.treeType as PrimaryTree)
            : api.getSlatePoolAll()
          poolPromise
            .then(pool => setMode(prev =>
              prev.type === 'editing' && prev.slateId === slateId
                ? { ...prev, creator: { ...prev.creator, pool, poolLoading: false } }
                : prev
            ))
            .catch(() => setMode(prev =>
              prev.type === 'editing' && prev.slateId === slateId
                ? { ...prev, creator: { ...prev.creator, poolLoading: false } }
                : prev
            ))
        }
      } else if (hover) {
        // Drag — move to new position (allow anywhere within grid bounds); mode stays unchanged. Reorder the
        // moved slate to the END so it layers on top and is the one selected where it overlaps others.
        const { slate } = dragSlate
        const anchor = centeredAnchor(slate.kind, slate.shapeIndex, slate.orientationIndex, hover)
        const cells = anchorCells(slate.kind, slate.shapeIndex, slate.orientationIndex, anchor)
        if (cells.every(([r, c]) => r >= 0 && r < BOARD_ROWS && c >= 0 && c < BOARD_COLS)) {
          setPlaced(prev => {
            const moved = prev.find(s => s.id === slate.id)
            if (!moved) return prev
            return [...prev.filter(s => s.id !== slate.id), { ...moved, cells, anchor }]
          })
        }
      }

      setDragSlate(null)
    }
    window.addEventListener('pointerup', handler)
    return () => window.removeEventListener('pointerup', handler)
  }, [dragSlate, hover, placed, mode])

  // Right-click anywhere exits editing/creating/choosing mode. Editing changes are already applied live, so
  // this just returns to the inventory.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (mode.type === 'idle') return
      e.preventDefault()
      setMode({ type: 'idle' })
    }
    window.addEventListener('contextmenu', handler)
    return () => window.removeEventListener('contextmenu', handler)
  }, [mode])

  const creator = (mode.type === 'creating' || mode.type === 'editing') ? mode.creator : null

  // Apply edits to the placed slate LIVE (slots, rolls, shape, rotation, tree, direction) — so the board, the
  // bonuses panel, and the build stay current as you edit, and switching to another slate keeps these changes
  // with no explicit Save. Cancel reverts from editSnapshot. Keyed on the data fields (not openPicker/search).
  const editCreatorKey = mode.type === 'editing'
    ? JSON.stringify([mode.creator.slots, mode.creator.shapeIndex, mode.creator.orientationIndex, mode.creator.treeType, mode.creator.mothDirection, !!mode.creator.pool])
    : null
  useEffect(() => {
    if (mode.type !== 'editing') return
    const { slateId, creator: c } = mode
    setPlaced(prev => prev.map(s => {
      if (s.id !== slateId) return s
      const cells = anchorCells(s.kind, c.shapeIndex, c.orientationIndex, s.anchor)
      const inBounds = cells.every(([r, cc]) => r >= 0 && r < BOARD_ROWS && cc >= 0 && cc < BOARD_COLS)
      return {
        ...s,
        slots: c.slots.map(sl => ({ ...sl })),
        pool: c.pool ?? s.pool, treeType: c.treeType ?? s.treeType,
        mothDirection: c.mothDirection ?? s.mothDirection,
        orientationIndex: c.orientationIndex, shapeIndex: c.shapeIndex,
        ...(inBounds ? { cells } : {}),
      }
    }))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editCreatorKey])

  // Build occupied map (skip slate being edited or dragged)
  const occupied = new Map<string, string>()
  for (const s of placed) {
    if (s.id === editingSlateId) continue
    if (dragSlate && s.id === dragSlate.slate.id) continue
    for (const [r, c] of s.cells) occupied.set(`${r},${c}`, s.id)
  }

  // While DRAGGING a placed slate, move it LIVE to the cursor — but only once it's actually moved off its start
  // cell, so clicking-without-moving leaves it put (no flash to a new spot). The slate itself follows the
  // pointer (feels attached) instead of leaving a static ghost behind.
  const dragMoved = !!(dragSlate && hover && (hover[0] !== dragSlate.startCell[0] || hover[1] !== dragSlate.startCell[1]))
  let dragTarget: { cells: [number, number][]; anchor: [number, number] } | null = null
  if (dragMoved && dragSlate && hover) {
    const { slate } = dragSlate
    const anchor = centeredAnchor(slate.kind, slate.shapeIndex, slate.orientationIndex, hover)
    dragTarget = { cells: anchorCells(slate.kind, slate.shapeIndex, slate.orientationIndex, anchor), anchor }
  }
  // Placed slates as rendered: the dragged slate shown at its live target while moving, and moved to the END so
  // it layers on TOP of whatever it overlaps (newest-over-area wins).
  const renderPlaced = dragTarget && dragSlate
    ? [...placed.filter(s => s.id !== dragSlate.slate.id),
       { ...(placed.find(s => s.id === dragSlate.slate.id) ?? dragSlate.slate), cells: dragTarget.cells, anchor: dragTarget.anchor }]
    : placed

  // Ghost cells — only the creating-mode placement preview (drag uses the live move above).
  let ghostCells: [number, number][] = []
  if (hover && creator && mode.type === 'creating') {
    const anchor = centeredAnchor(creator.kind, creator.shapeIndex, creator.orientationIndex, hover)
    ghostCells = anchorCells(creator.kind, creator.shapeIndex, creator.orientationIndex, anchor)
  }
  const ghostSet = new Set(ghostCells.map(([r, c]) => `${r},${c}`))

  // Per-cell ghost validity: valid board cell AND not occupied by another slate
  const ghostValidCells = new Set<string>()
  for (const [r, c] of ghostCells) {
    if (isValidCell(r, c) && !occupied.has(`${r},${c}`)) ghostValidCells.add(`${r},${c}`)
  }

  // All placed cells for rendering — from renderPlaced. LAST slate wins per cell so the top-most (newest moved
  // over the area) is the one selected/rendered, matching the visual layer order.
  const placedCellMap = new Map<string, string>()
  for (const s of renderPlaced) {
    for (const [r, c] of s.cells) placedCellMap.set(`${r},${c}`, s.id)
  }

  // Conflicted cells: out-of-bounds OR overlapping (from renderPlaced so a drag preview flags bad drops live).
  const conflictedCells = new Set<string>()
  {
    const cellSlates = new Map<string, string[]>()
    for (const s of renderPlaced) {
      for (const [r, c] of s.cells) {
        const k = `${r},${c}`
        if (!isValidCell(r, c)) conflictedCells.add(k)
        if (!cellSlates.has(k)) cellSlates.set(k, [])
        cellSlates.get(k)!.push(s.id)
      }
    }
    for (const [k, ids] of cellSlates) if (ids.length > 1) conflictedCells.add(k)
  }
  // Per-kind placement limits (board only; the inventory is unlimited). Exceeding any invalidates the build.
  const overLimit: [SlateKind, number][] = []
  {
    const counts = new Map<SlateKind, number>()
    for (const s of placed) counts.set(s.kind, (counts.get(s.kind) ?? 0) + 1)
    for (const [k, n] of counts) {
      const max = SLATE_LIMITS[k]
      if (max != null && n > max) overLimit.push([k, max])
    }
  }
  const hasConflict = conflictedCells.size > 0
  const boardIsValid = !hasConflict && overLimit.length === 0
  const invalidReason = hasConflict
    ? 'Slates overlap or leave the board'
    : overLimit.length
      ? `Too many ${SLATE_LIMIT_LABEL[overLimit[0][0]]} (max ${overLimit[0][1]})`
      : ''

  const editingCells = new Set((editingSlateId ? placed.find(s => s.id === editingSlateId)?.cells : null)?.map(([r, c]) => `${r},${c}`) ?? [])
  const hoverSlateCells = new Set(!dragSlate && !creator && hoverSlateId
    ? (placed.find(s => s.id === hoverSlateId)?.cells ?? []).map(([r, c]) => `${r},${c}`)
    : [])
  const hoverSlate = !creator && !dragSlate && hoverSlateId
    ? placed.find(s => s.id === hoverSlateId) ?? null
    : null

  // ── Creator helpers ─────────────────────────────────────────────────────────

  function updateCreator(patch: Partial<CreatorState>) {
    setMode(prev => (prev.type !== 'creating' && prev.type !== 'editing') ? prev : { ...prev, creator: { ...prev.creator, ...patch } })
  }

  async function loadTreePool(tree: PrimaryTree) {
    // Changing the tree swaps the entire modifier pool, so any modifiers already picked from the old
    // tree are now invalid — reset the slots to avoid impossible cross-tree combos. (Call site only
    // fires this when the tree actually changes, so this never wipes a same-tree re-click.)
    updateCreator({ treeType: tree, poolLoading: true, pool: null, slots: initSlots(creator?.kind ?? 'base') })
    try { updateCreator({ pool: await api.getSlatePool(tree), poolLoading: false }) }
    catch { updateCreator({ poolLoading: false }) }
  }

  function startCreating(kind: SlateKind) {
    const initial = defaultCreator(kind)
    if (kind === 'base') initial.treeType = PRIMARY_TREES[0]
    if (kind === 'spark_of_moth_fire') initial.mothDirection = 'above'
    if (kind === 'space_rift') initial.mothDirection = 'left'   // Space Rift copies left OR right
    setMode({ type: 'creating', creator: initial })
    if (kind === 'base') {
      setTimeout(() => {
        setMode(prev => (prev.type !== 'creating' && prev.type !== 'editing') ? prev : { ...prev, creator: { ...prev.creator, poolLoading: true } })
        api.getSlatePool(PRIMARY_TREES[0])
          .then(pool => setMode(prev => (prev.type !== 'creating' && prev.type !== 'editing') ? prev : { ...prev, creator: { ...prev.creator, pool, poolLoading: false } }))
          .catch(() => setMode(prev => (prev.type !== 'creating' && prev.type !== 'editing') ? prev : { ...prev, creator: { ...prev.creator, poolLoading: false } }))
      }, 0)
    } else if (SLOT_CONFIG[kind]?.poolScope === 'all') {
      setTimeout(() => {
        setMode(prev => (prev.type !== 'creating' && prev.type !== 'editing') ? prev : { ...prev, creator: { ...prev.creator, poolLoading: true } })
        api.getSlatePoolAll()
          .then(pool => setMode(prev => (prev.type !== 'creating' && prev.type !== 'editing') ? prev : { ...prev, creator: { ...prev.creator, pool, poolLoading: false } }))
          .catch(() => setMode(prev => (prev.type !== 'creating' && prev.type !== 'editing') ? prev : { ...prev, creator: { ...prev.creator, poolLoading: false } }))
      }, 0)
    }
  }

  // Re-place a saved inventory template: enter creating mode pre-filled with its config, then the user
  // clicks the board to drop it (reuses the normal placement + ghost flow).
  function placeFromTemplate(t: SlateTemplate) {
    const kind = t.kind as SlateKind
    const scope = SLOT_CONFIG[kind]?.poolScope
    const needsPool = (kind === 'base' && !!t.treeType) || scope === 'all'
    setMode({ type: 'creating', creator: {
      kind, shapeIndex: t.shapeIndex, treeType: (t.treeType as PrimaryTree) ?? null,
      slots: t.slots.map(s => ({ ...s })), orientationIndex: t.orientationIndex,
      pool: null, poolLoading: needsPool, openPicker: null, pickerSearch: '',
      mothDirection: (t.mothDirection as MothDirection) ?? null,
      templateId: t.id,   // re-placed copy shares the saved entry's identity
    } })
    if (kind === 'base' && t.treeType) {
      api.getSlatePool(t.treeType as PrimaryTree).then(pool => updateCreator({ pool, poolLoading: false })).catch(() => updateCreator({ poolLoading: false }))
    } else if (scope === 'all') {
      api.getSlatePoolAll().then(pool => updateCreator({ pool, poolLoading: false })).catch(() => updateCreator({ poolLoading: false }))
    }
  }

  function deleteTemplate(id: string) {
    setSlateInventory(useBuildStore.getState().slateInventory.filter(t => t.id !== id))
  }

  // Clone a saved slate so small variants can be compared side by side.
  function duplicateTemplate(id: string) {
    const inv = useBuildStore.getState().slateInventory
    const src = inv.find(t => t.id === id)
    if (!src) return
    // Prefixed + random — same-millisecond duplicates must never share an id (the inventory
    // upsert Map and delete-by-id would silently collapse or double-delete them).
    const copy = { ...(JSON.parse(JSON.stringify(src)) as typeof src), id: `dup-${Date.now()}-${Math.random()}` }
    setSlateInventory([...inv, copy])
  }

  // Rename sets a DISPLAY label only (mirrors gear/hero-memory rename): strip control chars, cap 60, clear
  // when empty. The true kind name stays in the tooltip; the label shows as a caption under the tile.
  function renameTemplate(id: string, nextRaw: string) {
    const next = nextRaw.replace(/\p{C}/gu, '').trim().slice(0, 60)
    setSlateInventory(useBuildStore.getState().slateInventory.map(t =>
      t.id === id ? { ...t, displayName: next || undefined } : t))
  }

  function updateSlot(idx: number, patch: Partial<CreatorSlot>) {
    if (!creator) return
    updateCreator({ slots: creator.slots.map((s, i) => i === idx ? { ...s, ...patch } : s) })
  }

  function handleCycleSlotType(idx: number) {
    if (!creator) return
    const slot = creator.slots[idx]
    updateSlot(idx, { slotType: cycleSlotType(slot.slotType, slot.maxType), selectedNodeId: null, selectedCoreKey: null, coreName: null, effects: [], isCore: false, nodeType: null })
  }

  function handleTogglePicker(idx: number) {
    updateCreator({ openPicker: creator?.openPicker === idx ? null : idx, pickerSearch: '' })
  }

  function handleSelectModifier(idx: number, mod: SlateModifierOption) {
    updateSlot(idx, { isCore: false, selectedNodeId: mod.nodeId, selectedCoreKey: null, coreName: null, effects: mod.effects, nodeType: mod.nodeType })
    updateCreator({ openPicker: null })
  }

  function handleSelectCore(idx: number, core: CoreTalentOption) {
    updateSlot(idx, { isCore: true, selectedCoreKey: core.key, selectedNodeId: null, coreName: core.name, effects: core.effects, nodeType: null })
    updateCreator({ openPicker: null })
  }

  function handleRotate() {
    if (!creator) return
    updateCreator({ orientationIndex: (creator.orientationIndex + 1) % getOrientationCount(creator.kind) })
  }

  // ── Board interactions ──────────────────────────────────────────────────────

  function handleCellPointerDown(row: number, col: number) {
    if (mode.type === 'creating' || mode.type === 'choosing') return
    // In idle OR editing, press on ANY placed slate: a release on the same cell opens/switches its editor,
    // a release on a different cell moves it. Uses placedCellMap so the slate being edited is included too.
    const slateId = placedCellMap.get(`${row},${col}`)
    if (!slateId) return
    const slate = placed.find(s => s.id === slateId)
    if (!slate) return
    setDragSlate({ slate, startCell: [row, col] })
  }

  function handleCellClick(row: number, col: number) {
    if (suppressNextClick.current) { suppressNextClick.current = false; return }
    if (!creator) return
    if (mode.type === 'editing') return

    const anchor = centeredAnchor(creator.kind, creator.shapeIndex, creator.orientationIndex, [row, col])
    const cells = anchorCells(creator.kind, creator.shapeIndex, creator.orientationIndex, anchor)
    if (!cells.every(([r, c]) => r >= 0 && r < BOARD_ROWS && c >= 0 && c < BOARD_COLS)) return

    const id = `${Date.now()}-${Math.random()}`
    setPlaced(prev => [...prev, {
      id, templateId: creator.templateId ?? id, kind: creator.kind, cells, anchor,
      orientationIndex: creator.orientationIndex, shapeIndex: creator.shapeIndex,
      slots: creator.slots.map(s => ({ ...s })),
      pool: creator.pool ?? undefined, treeType: creator.treeType ?? undefined,
      mothDirection: creator.mothDirection ?? undefined,
    }])
    setMode({ type: 'idle' })
  }

  function handleRemoveSlate(id: string) {
    setPlaced(prev => prev.filter(s => s.id !== id))
    if (editingSlateId === id) setMode({ type: 'idle' })
  }

  // Save the in-progress slate to the inventory WITHOUT placing it on the board (upsert by templateId), then
  // return to the inventory view. Placed slates are auto-saved separately; this covers "build it for later".
  function handleAddToInventory() {
    if (!creator) return
    const id = creator.templateId ?? `${Date.now()}-${Math.random()}`
    const byId = new Map(useBuildStore.getState().slateInventory.map(t => [t.id, t]))
    byId.set(id, creatorToTemplate(creator, id))
    setSlateInventory([...byId.values()])
    setMode({ type: 'idle' })
  }

  // Save: edits are already applied live, so just close the editor.
  function handleSaveEdit() {
    editSnapshot.current = null
    setMode({ type: 'idle' })
  }

  // Cancel: revert the in-progress slate to its pre-edit snapshot (editing), or return to the chooser (creating).
  function handleCancelEdit() {
    if (mode.type === 'editing' && editSnapshot.current) {
      const snap = editSnapshot.current
      setPlaced(prev => prev.map(s => s.id === snap.id ? snap : s))
    }
    editSnapshot.current = null
    setMode({ type: 'idle' })
  }

  const usedCells = placed.reduce((n, s) => n + s.cells.length, 0)

  // ── Left panel ──────────────────────────────────────────────────────────────

  function renderCreatorPanel() {
    if (!creator) return null
    const { kind, treeType, slots, pool, poolLoading, openPicker, pickerSearch, mothDirection } = creator
    const accentColor = kind === 'base'
      ? (treeType ? treeColors[treeType] ?? '#888' : '#888')
      : LEGENDARY_META[kind as LegendaryKind]?.color ?? '#888'
    const sections = getSections(kind)
    const showDividers = kind === 'base'
    // "Add to Inventory" is available while CREATING once the slate is meaningfully configured (≥1 modifier slot
    // filled, or a copy-type slate which has no slots). Editing slates are already auto-saved to the inventory.
    const canSaveToInventory = slots.some(s => s.selectedNodeId || s.selectedCoreKey)
      || SLOT_CONFIG[kind]?.poolScope === 'none'

    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }} onClick={e => e.stopPropagation()}>

        {/* Save / Cancel / Remove header (editing shows all three; creating shows Add-to-Inventory + Cancel + a place hint) */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexShrink: 0 }}>
          {mode.type === 'editing' && (
            <button onClick={handleSaveEdit} style={{
              flex: 1, padding: '10px 12px', fontSize: 14, fontWeight: 700,
              background: '#1a4a1a', color: '#5fdf5f', border: '1px solid #2d8a2d', borderRadius: 7, cursor: 'pointer',
            }}>✓ Save</button>
          )}
          {mode.type === 'creating' && (
            <button onClick={handleAddToInventory} disabled={!canSaveToInventory}
              title={canSaveToInventory ? 'Save this slate to your inventory without placing it' : 'Configure a modifier first'}
              style={{
                flex: 1, padding: '10px 12px', fontSize: 14, fontWeight: 600,
                background: canSaveToInventory ? '#1e2a4a' : '#15151f', color: canSaveToInventory ? '#9db4e8' : '#444',
                border: `1px solid ${canSaveToInventory ? '#2d4a7a' : '#23233a'}`, borderRadius: 7,
                cursor: canSaveToInventory ? 'pointer' : 'default',
              }}>+ Add to Inventory</button>
          )}
          <button onClick={handleCancelEdit} style={{
            flex: mode.type === 'editing' ? '0 0 auto' : 1, padding: '10px 12px', fontSize: 14, fontWeight: 600,
            background: '#1a1a3a', color: '#999', border: '1px solid #2a2a50', borderRadius: 7, cursor: 'pointer',
          }}>✕ Cancel</button>
          {mode.type === 'editing' && (
            <button onClick={() => handleRemoveSlate(editingSlateId!)} style={{
              flex: '0 0 auto', padding: '10px 12px', fontSize: 14, fontWeight: 600,
              background: '#3a1010', color: '#dd5555', border: '1px solid #6a2020', borderRadius: 7, cursor: 'pointer',
            }}>⊗ Remove</button>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexShrink: 0 }}>
          <SlateIcon kind={kind} treeType={treeType} shapeIndex={creator.shapeIndex} size={28} />
          <span style={{ fontSize: 17, fontWeight: 700, color: kind === 'base' ? '#ccc' : accentColor }}>
            {kind === 'base' ? 'Base Slate' : LEGENDARY_META[kind as LegendaryKind]?.label ?? 'Slate'}
          </span>
          {mode.type === 'creating' && (
            <span style={{ marginLeft: 'auto', fontSize: 11, color: '#666' }}>Click the board to place</span>
          )}
        </div>

        {kind === 'base' && (
          <div style={{ marginBottom: 14, flexShrink: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#555', marginBottom: 7 }}>Tree Branch</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
              {PRIMARY_TREES.map(tree => {
                const tc = treeColors[tree] ?? '#888'
                const active = treeType === tree
                return (
                  <button key={tree} onClick={() => { if (!active) loadTreePool(tree) }} style={{
                    padding: '6px 7px', fontSize: 13, textAlign: 'left',
                    background: active ? `${tc}22` : '#1a1a3a', color: active ? tc : '#666',
                    border: `1px solid ${active ? tc : '#252545'}`, borderRadius: 4, cursor: 'pointer',
                  }}>
                    {tree.replace('Goddess of ', '').replace('God of ', '')}
                  </button>
                )
              })}
            </div>
            {poolLoading && <div style={{ fontSize: 13, color: '#555', marginTop: 6 }}>Loading modifiers…</div>}
          </div>
        )}

        {kind !== 'base' && poolLoading && (
          <div style={{ fontSize: 13, color: '#555', marginBottom: 10, flexShrink: 0 }}>Loading modifiers…</div>
        )}

        {(kind === 'spark_of_moth_fire' || kind === 'space_rift') && (
          <div style={{ marginBottom: 14, flexShrink: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#555', marginBottom: 7 }}>Copy Direction</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
              {((kind === 'space_rift' ? ['left', 'right'] : ['above', 'below', 'left', 'right']) as MothDirection[]).map(dir => {
                const active = mothDirection === dir
                const icon = { above: '↑', below: '↓', left: '←', right: '→' }[dir]
                return (
                  <button key={dir} onClick={() => updateCreator({ mothDirection: dir })} style={{
                    padding: '7px 8px', fontSize: 14,
                    background: active ? `${LEGEND_GOLD}22` : '#1a1a3a', color: active ? LEGEND_GOLD : '#777',
                    border: `1px solid ${active ? LEGEND_GOLD : '#252545'}`, borderRadius: 5, cursor: 'pointer',
                  }}>
                    {icon} {dir.charAt(0).toUpperCase() + dir.slice(1)}
                  </button>
                )
              })}
            </div>
            {!mothDirection && <div style={{ fontSize: 12, color: '#555', marginTop: 7 }}>Select direction before placing</div>}
          </div>
        )}

        {kind === 'when_sparks_set_prairie_ablaze' && (
          <div style={{ fontSize: 13, color: '#666', lineHeight: 1.7, marginBottom: 12 }}>
            Copies the bottom modifier of each adjacent slate (up to 4).
          </div>
        )}

        {kind === 'residence_of_stars' && (
          <div style={{ fontSize: 13, color: '#666', lineHeight: 1.7, marginBottom: 12 }}>
            Copies the Medium talents of each adjacent slate (up to 4). Legendary Medium talents are not copied.
          </div>
        )}

        <div className="dark-scroll" style={{ flex: 1, overflowY: 'auto' }}>
          {sections.map(({ label, indices }) => (
            <div key={label} style={{ marginBottom: 10 }}>
              {showDividers && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <div style={{ flex: 1, height: 1, background: '#252545' }} />
                  <span style={{ fontSize: 10, fontWeight: 700, color: '#4a4a6a', textTransform: 'uppercase', letterSpacing: 0.5, whiteSpace: 'nowrap' }}>{label}</span>
                  <div style={{ flex: 1, height: 1, background: '#252545' }} />
                </div>
              )}
              {indices.map(idx => {
                // slots[idx] can go briefly undefined under rapid place/remove input (a
                // stale-snapshot race between the local `slots` view and the store) — skip
                // rendering rather than let ModifierSlot deref a missing slot and crash the
                // whole app (no error boundary existed here before this fix landed).
                const slot = slots[idx]
                if (!slot) return null
                return (
                  <ModifierSlot key={idx} slot={slot} index={idx} allSlots={slots} pool={pool}
                    isOpen={openPicker === idx} search={openPicker === idx ? pickerSearch : ''}
                    accentColor={accentColor}
                    onTogglePicker={() => handleTogglePicker(idx)}
                    onCycleType={() => handleCycleSlotType(idx)}
                    onSelect={mod => handleSelectModifier(idx, mod)}
                    onSelectCore={core => handleSelectCore(idx, core)}
                    onClear={() => updateSlot(idx, { selectedNodeId: null, selectedCoreKey: null, coreName: null, effects: [], nodeType: null })}
                    onSearchChange={s => updateCreator({ pickerSearch: s })}
                  />
                )
              })}
            </div>
          ))}

          {/* Shape / rotation controls — below the mod slots. */}
          <ShapePanel
            creator={creator} treeColors={treeColors}
            onRotate={handleRotate}
            onSelectOrientation={idx => updateCreator({ orientationIndex: idx })}
            onSelectShape={idx => updateCreator({ shapeIndex: idx, orientationIndex: 0 })}
          />
        </div>
      </div>
    )
  }

  // The slate-type chooser — opened by "Create Slate", replaces the left panel (Cancel returns to inventory).
  function renderChooserPanel() {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto' }} className="dark-scroll">
        <button onClick={() => setMode({ type: 'idle' })} style={{
          width: '100%', padding: '10px 12px', marginBottom: 12, flexShrink: 0, fontSize: 14, fontWeight: 600,
          background: '#1a1a3a', color: '#999', border: '1px solid #2a2a50', borderRadius: 7, cursor: 'pointer',
        }}>✕ Cancel</button>
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#555', marginBottom: 10, flexShrink: 0 }}>Create Slate</div>

        {/* Base Slate */}
        <button onClick={() => startCreating('base')} style={{
          width: '100%', padding: '11px 14px', marginBottom: 6, textAlign: 'left',
          background: '#1a1a3a', border: '1px solid #2a2a50', borderRadius: 7,
          cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 14,
        }}>
          <div style={{ flexShrink: 0, minWidth: 50, display: 'flex', justifyContent: 'center' }}>
            <SlateIcon kind='base' treeType='God of War' shapeIndex={3} size={46} />
          </div>
          <div>
            <div style={{ fontSize: 17, fontWeight: 600, color: '#ccc', marginBottom: 3 }}>Base Slate</div>
            <div style={{ fontSize: 12, color: '#555' }}>{SLATE_DESCRIPTIONS.base}</div>
          </div>
        </button>

        {/* Legendary slates */}
        {(Object.entries(LEGENDARY_META) as [LegendaryKind, typeof LEGENDARY_META[LegendaryKind]][]).map(([kind, meta]) => (
          <button key={kind} onClick={() => startCreating(kind)} style={{
            width: '100%', padding: '11px 14px', marginBottom: 6, textAlign: 'left',
            background: '#1a1a3a', border: `1px solid #252540`, borderLeft: `3px solid ${meta.color}`,
            borderRadius: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 14,
          }}>
            <div style={{ flexShrink: 0, minWidth: 50, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 4 }}>
              <SlateIcon kind={kind} size={46} />
            </div>
            <div>
              <div style={{ fontSize: 17, fontWeight: 600, color: meta.color, marginBottom: 3 }}>{meta.label}</div>
              <div style={{ fontSize: 12, color: '#555' }}>{SLATE_DESCRIPTIONS[kind]}</div>
            </div>
          </button>
        ))}
      </div>
    )
  }

  function renderIdlePanel() {
    return (
      <div className="dark-scroll" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto' }}>
        <button onClick={() => setMode({ type: 'choosing' })} style={{
          width: '100%', padding: '12px 14px', marginBottom: 14, flexShrink: 0,
          fontSize: 15, fontWeight: 700, background: '#1e2a4a', color: '#9db4e8',
          border: '1px solid #2d4a7a', borderRadius: 8, cursor: 'pointer',
        }}>+ Create Slate</button>

        {slateInventory.length > 0 ? (
          <>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#555', marginBottom: 8 }}>
              Saved Slates <span style={{ color: '#3a3a5a' }}>(click to place · right-click to delete)</span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {slateInventory.map(t => {
                const color = t.kind === 'base'
                  ? (treeColors[t.treeType ?? ''] ?? '#666')
                  : LEGENDARY_META[t.kind as LegendaryKind]?.color ?? '#666'
                return (
                  <InventoryTile key={t.id} template={t} color={color} treeColors={treeColors}
                    onPlace={() => placeFromTemplate(t)} onDelete={() => deleteTemplate(t.id)} onDuplicate={() => duplicateTemplate(t.id)}
                    onRename={(next) => renameTemplate(t.id, next)} />
                )
              })}
            </div>
          </>
        ) : (
          <div style={{ fontSize: 13, color: '#333', lineHeight: 1.8 }}>
            No saved slates yet. Click <b style={{ color: '#888' }}>Create Slate</b> to build one.<br />
            Drag placed slates to move, click to edit, right-click to remove.
          </div>
        )}
      </div>
    )
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const ghostColor = creator
    ? (creator.kind === 'base' && creator.treeType ? treeColors[creator.treeType] ?? '#888'
        : creator.kind !== 'base' ? LEGENDARY_META[creator.kind as LegendaryKind]?.color ?? '#888' : '#888')
    : dragSlate
      ? (dragSlate.slate.kind === 'base' ? treeColors[dragSlate.slate.treeType ?? ''] ?? '#888'
          : LEGENDARY_META[dragSlate.slate.kind as LegendaryKind]?.color ?? '#888')
      : '#888'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0e0e1e', color: '#e0e0e0', userSelect: 'none' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid #2a2a4a', background: '#1a1a2e', flexShrink: 0 }}>
        <h2 style={{ margin: 0, fontSize: 18, color: '#c0a0ff' }}>Slate Board</h2>
        <span style={{ marginLeft: 'auto', fontSize: 13, color: '#555' }}>{usedCells} / {TOTAL_CELLS} cells</span>
        {placed.length > 0 && !creator && !dragSlate && (
          <span style={{ fontSize: 12, fontWeight: 600, color: boardIsValid ? '#4ab87a' : '#f05555' }}>
            {boardIsValid ? '✓ Valid' : `⚠ ${invalidReason}`}
          </span>
        )}
        {(creator || dragSlate) && (
          <span style={{ fontSize: 12, color: '#555' }}>
            {dragSlate ? 'Dragging — release to place'
              : mode.type === 'editing' ? 'Right-click or Done to finish'
              : 'Click board to place'}
          </span>
        )}
      </div>

      {/* Layout lives on the classes (index.css) so the mobile stacking rules can override
          without !important; this screen's colors stay inline like the rest of the file. */}
      <div className="slate-body">
        {/* Left panel */}
        <div className="slate-left">
          {mode.type === 'choosing' ? renderChooserPanel() : creator ? renderCreatorPanel() : renderIdlePanel()}
        </div>

        {/* Board */}
        <div {...boardTip.triggerProps} className="slate-board-wrap">
          {/* Collapsible Slate Bonuses panel — top-right of the board area (stacks above the board on mobile) */}
          <div className="slate-bonuses">
            {bonusesOpen ? (
              <div className="dark-scroll slate-bonuses-panel" style={{ overflowY: 'auto', background: '#101020', border: '1px solid #2a2a4a', borderRadius: 8, boxShadow: '0 6px 24px rgba(0,0,0,0.55)' }}>
                <button onClick={() => setBonusesOpen(false)} style={{
                  position: 'sticky', top: 0, width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '9px 13px', background: '#16162a', border: 'none', borderBottom: '1px solid #2a2a4a',
                  color: '#8a7ad0', fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, cursor: 'pointer',
                }}>Slate Bonuses <span>▾</span></button>
                <SlateOverview placed={placed} hideHeading />
              </div>
            ) : (
              <button onClick={() => setBonusesOpen(true)} style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '9px 13px',
                background: '#16162a', border: '1px solid #2a2a4a', borderRadius: 8, color: '#8a7ad0',
                fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, cursor: 'pointer',
                boxShadow: '0 2px 12px rgba(0,0,0,0.45)',
              }}>≡ Slate Bonuses <span>▸</span></button>
            )}
          </div>
          <div ref={boardRef}
            onPointerMove={e => {
              // Track the hovered cell from the pointer position (not per-cell onMouseEnter) so the ghost follows
              // the cursor smoothly with no gap dead-zones — only while placing or dragging.
              if (!creator && !dragSlate) return
              const rect = boardRef.current?.getBoundingClientRect()
              if (!rect) return
              const lx = e.clientX - rect.left, ly = e.clientY - rect.top
              const c = Math.floor(lx / PITCH), r = Math.floor(ly / PITCH)
              if (r < 0 || r >= BOARD_ROWS || c < 0 || c >= BOARD_COLS) return
              // Hysteresis: only switch to a NEW cell once the cursor is well inside its body (not the edge/gap),
              // so the slate lingers in place instead of twitching/teleporting when moving fast across boundaries.
              const M = 8
              setHover(prev => {
                if (prev && prev[0] === r && prev[1] === c) return prev
                const inX = lx - c * PITCH, inY = ly - r * PITCH
                if (inX < M || inX > CELL - M || inY < M || inY > CELL - M) return prev   // near edge/gap → keep current
                return [r, c]
              })
            }}
            onPointerLeave={() => { if (creator || dragSlate) setHover(null) }}
            style={{ position: 'relative', display: 'grid', gridTemplateColumns: `repeat(${BOARD_COLS}, ${CELL}px)`, gridTemplateRows: `repeat(${BOARD_ROWS}, ${CELL}px)`, gap: GAP }}>
            {Array.from({ length: BOARD_ROWS }, (_, row) =>
              Array.from({ length: BOARD_COLS }, (_, col) => {
                const key = `${row},${col}`
                const valid = isValidCell(row, col)
                const isGhost = ghostSet.has(key)
                const isPlacedHere = placedCellMap.has(key)
                // Every grid cell is interactive (full square), even the "invisible" out-of-area ones — you can
                // place/drag onto them; they're just flagged invalid (red outline + warning) rather than blocked.

                const slateId = placedCellMap.get(key) ?? null
                const slate = slateId ? placed.find(s => s.id === slateId) : null
                const isDragging = dragSlate && dragSlate.slate.cells.some(([r, c]) => r === row && c === col)
                const isEditing = editingCells.has(key)
                const isHovered = hoverSlateCells.has(key)
                const isConflicted = conflictedCells.has(key)
                const isGhostValid = ghostValidCells.has(key)
                const sColor = slate
                  ? (slate.kind === 'base' ? treeColors[slate.treeType ?? ''] ?? '#666' : LEGENDARY_META[slate.kind as LegendaryKind]?.color ?? '#666')
                  : null
                const isSelected = slate?.id === editingSlateId

                const bg = isGhost
                  ? (isGhostValid ? `${ghostColor}28` : '#ff444418')
                  : isDragging ? (valid ? '#15152a' : 'transparent')
                  : isConflicted ? '#ff222218'
                  : isEditing ? `${sColor}40`
                  : sColor ? `${sColor}22` : (valid ? '#15152a' : 'transparent')

                const borderColor = isGhost
                  ? (isGhostValid ? ghostColor : '#ff4444')
                  : isDragging ? (valid ? '#1e1e3a' : 'transparent')
                  : isConflicted ? '#cc3333'
                  : isHovered ? '#9090b8'
                  : isEditing || isSelected ? (sColor ?? '#888')
                  : sColor ? `${sColor}88` : (valid ? '#1e1e3a' : 'transparent')

                // The slate's icon fills its whole footprint: each occupied cell renders its slice of the
                // image (sized to the slate's bounding box), so the art reads as one image across the shape.
                // Art-overlay kinds draw their art via the single overlay layer below — the cell itself stays
                // bare (transparent fill/border unless highlighted) so the footprint reads as one unified piece.
                const useArtOverlay = !!slate && ART_OVERLAY_KINDS.has(slate.kind) && !isDragging
                const slateIconSrc = slate && !isDragging && !useArtOverlay ? slateIconUrl(slate.kind, slate.treeType) : null
                let iconBg: React.CSSProperties = {}
                if (slate && slateIconSrc) {
                  const rs = slate.cells.map(([r]) => r), cs = slate.cells.map(([, c]) => c)
                  const minR = Math.min(...rs), minC = Math.min(...cs)
                  const cols = Math.max(...cs) - minC + 1, rows = Math.max(...rs) - minR + 1, step = CELL + 4
                  iconBg = cols === 1 && rows === 1
                    ? { backgroundImage: `url(${slateIconSrc})`, backgroundSize: 'cover', backgroundPosition: 'center', backgroundRepeat: 'no-repeat' }
                    : {
                        // Multi-cell: stretch the (trimmed) art across the slate's bounding box; each cell
                        // shows its slice (step accounts for the 4px grid gaps).
                        backgroundImage: `url(${slateIconSrc})`,
                        backgroundSize: `${cols * CELL + (cols - 1) * 4}px ${rows * CELL + (rows - 1) * 4}px`,
                        backgroundPosition: `-${(col - minC) * step}px -${(row - minR) * step}px`,
                        backgroundRepeat: 'no-repeat',
                      }
                }

                // Overlay slates stay fully bare — the art + the whole-slate outline do all the drawing, incl.
                // conflict (red outline) and selection/hover state. No per-cell tint/border.
                const cellBg = useArtOverlay ? 'transparent' : bg
                const cellBorder = useArtOverlay ? 'transparent' : borderColor

                return (
                  <div key={key}
                    className="slate-cell"
                    onClick={() => handleCellClick(row, col)}
                    onPointerDown={() => handleCellPointerDown(row, col)}
                    onContextMenu={e => {
                      // Right-click a placed slate to remove it from the board (not while placing a new one).
                      if (slateId && mode.type !== 'creating') { e.preventDefault(); handleRemoveSlate(slateId) }
                    }}
                    onMouseEnter={() => {
                      // During placing/dragging the grid's pointer-move (with hysteresis) owns `hover`; here we
                      // only track which slate is hovered for the idle detail tooltip.
                      if (!creator && !dragSlate) setHoverSlateId(slateId)
                      else if (!slateId) setHoverSlateId(null)
                    }}
                    onMouseLeave={() => { setHoverSlateId(null) }}
                    style={{
                      width: CELL, height: CELL, boxSizing: 'border-box',
                      backgroundColor: cellBg, ...iconBg, border: `2px solid ${cellBorder}`, borderRadius: 6,
                      cursor: (creator && mode.type === 'creating') ? 'crosshair' : dragSlate ? 'grabbing' : slate ? 'grab' : 'default',
                      transition: 'border-color 60ms, background-color 60ms',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end',
                      padding: '3px 2px', position: 'relative', overflow: 'hidden',
                      boxShadow: (isPlacedHere && !isGhost && !isDragging && !useArtOverlay) ? 'inset 0 0 0 2px rgba(0,0,0,0.88)' : undefined,
                    }}
                  />
                )
              })
            ).flat()}

            {/* Unified art overlay: one rotated image per art-overlay slate, spanning its whole footprint
                (covers the internal grid gaps so the slate reads as a single piece). Uses renderPlaced so a
                dragged slate's art follows the cursor live. */}
            {renderPlaced.map(s => {
              if (!ART_OVERLAY_KINDS.has(s.kind)) return null
              const cs = s.cells.map(c => c[1]), rs = s.cells.map(c => c[0])
              const placedCR: [number, number] = [Math.max(...cs) - Math.min(...cs) + 1, Math.max(...rs) - Math.min(...rs) + 1]

              // Resolve art + transform params. Base slates are per-FORM (art swapped by tree, mirror forms
              // flipped, rotation per orientation); legendaries are per-KIND via the const maps above.
              let src: string | null, ox: number, oy: number, sx: number, sy: number
              let natural: [number, number], angle: number, flipX: boolean
              if (s.kind === 'base') {
                const form = BASE_FORMS[s.shapeIndex] ?? BASE_FORMS[0]
                src = slateIconUrl('base', s.treeType, s.shapeIndex)
                ;[ox, oy] = form.offset; natural = form.natural
                angle = s.orientationIndex * 90; flipX = form.flip
                sx = form.scale * (form.stretchX ?? 1); sy = form.scale * (form.stretchY ?? 1)
              } else {
                src = slateIconUrl(s.kind, s.treeType)
                const scale = ART_OVERLAY_SCALE[s.kind] ?? 1
                ;[ox, oy] = ART_OVERLAY_OFFSET[s.kind] ?? [0, 0]
                natural = ART_NATURAL_CELLS[s.kind] ?? placedCR
                angle = artOverlayAngle(s.kind, s.orientationIndex); flipX = artOverlayFlipX(s.kind, s.orientationIndex)
                sx = scale * (ART_OVERLAY_STRETCH_X[s.kind] ?? 1); sy = scale * (ART_OVERLAY_STRETCH_Y[s.kind] ?? 1)
              }
              if (!src) return null
              const box = slateBBoxPx(s.cells)
              // Image is sized to the art's NATURAL footprint, centred in the wrapper, then rotated/flipped so a
              // non-square shape isn't distorted by objectFit before the transform.
              const imgW = natural[0] * PITCH, imgH = natural[1] * PITCH
              const flipScaleX = (flipX ? -1 : 1) * sx
              // Wrapper clips to the WHOLE footprint shape (one cohesive unit, gaps covered); the art rotates and
              // scales up INSIDE the clip so it fills to the outline without bleeding or splitting per cell.
              return (
                <div key={`art-${s.id}`}
                  style={{
                    position: 'absolute', left: box.left, top: box.top, width: box.width, height: box.height,
                    overflow: 'hidden', clipPath: footprintInsetClip(s.cells, ART_INSET), pointerEvents: 'none',
                  }}>
                  <img src={src} alt="" draggable={false}
                    style={{
                      position: 'absolute', left: (box.width - imgW) / 2, top: (box.height - imgH) / 2, width: imgW, height: imgH,
                      objectFit: 'fill', display: 'block', transformOrigin: 'center',
                      // Flip-only kinds (pedigree): offset BEFORE scale so it lives in the art's natural frame and
                      // mirrors with the flip. Rotating kinds (incl. base): offset after scale, before rotate, so
                      // the tuned value follows the rotation.
                      transform: ART_FLIP_KINDS.has(s.kind)
                        ? `scale(${flipScaleX}, ${sy}) translate(${ox}px, ${oy}px)`
                        : `rotate(${angle}deg) translate(${ox}px, ${oy}px) scale(${flipScaleX}, ${sy})`,
                    }} />
                </div>
              )
            })}

            {/* Whole-slate outline: a single frame tracing each art-overlay slate's outer shape (board-space,
                so it follows the real cells). Brightens when the slate is selected / hovered. */}
            {renderPlaced.map(s => {
              if (!ART_OVERLAY_KINDS.has(s.kind)) return null
              const pts = footprintOutline(s.cells)
              if (!pts.length) return null
              const sel = s.id === editingSlateId
              const hov = s.id === hoverSlateId
              const conflict = s.cells.some(([r, c]) => conflictedCells.has(`${r},${c}`))
              const col = conflict ? '#ff3030' : sel ? OUTLINE_COLOR_SELECTED : hov ? OUTLINE_COLOR_HOVER : OUTLINE_COLOR
              return (
                <svg key={`out-${s.id}`} width={BOARD_PX} height={BOARD_PX}
                  style={{ position: 'absolute', left: 0, top: 0, pointerEvents: 'none', overflow: 'visible' }}>
                  <polygon points={pts.map(p => p.join(',')).join(' ')} fill="none" stroke={col}
                    strokeWidth={conflict ? 3.5 : sel ? 3.5 : hov ? 2.5 : 2} strokeOpacity={conflict || sel ? 1 : hov ? 0.95 : 0.7} strokeLinejoin="round" />
                </svg>
              )
            })}

          </div>

          {/* Floating detail tooltip for the hovered board slate (idle only). */}
          {boardTip.open && hoverSlate && (
            <FloatingPortal>
              <div className="tooltip" {...boardTip.floatingProps}>
                <SlateTooltipBody slate={hoverSlate} treeColors={treeColors} placed={placed} />
              </div>
            </FloatingPortal>
          )}
        </div>
      </div>
    </div>
  )
}
