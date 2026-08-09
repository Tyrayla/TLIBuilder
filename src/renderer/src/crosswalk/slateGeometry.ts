/**
 * Slate geometry crosswalk. Compendium encodes a placed slate as `shapeId` (O1/L1/Z1/T1/L2/Z2)
 * + `orientation{rotation, flipH, flipV}`. Builder encodes it as `shapeIndex` + `orientationIndex`
 * + explicit `cells`. The shape codes map directly to Builder's shapeIndex (the renderer's
 * BASE_SHAPES are literally labelled with these codes), but rather than hand-deriving how
 * rotation/flip compose into an orientationIndex, we COMPUTE the placed cell layout from the
 * Compendium transform and find the Builder (shapeIndex, orientationIndex) whose cells match.
 * That is robust to the flip convention and is self-validating.
 *
 * BASE_SHAPES is copied from `tlibuilder/src/renderer/src/screens/SlateScreen.tsx` (the game's
 * 6 tetromino forms × 4 rotations). It is game-constant, not season data.
 */

export const SHAPE_CODE_TO_INDEX: Record<string, number> = { O1: 0, L1: 1, Z1: 2, T1: 3, L2: 4, Z2: 5 }

type Cell = [number, number]
export const BASE_SHAPES: { code: string; rotations: Cell[][] }[] = [
  { code: 'O1', rotations: [[[0,0],[0,1],[1,0],[1,1]],[[0,0],[0,1],[1,0],[1,1]],[[0,0],[0,1],[1,0],[1,1]],[[0,0],[0,1],[1,0],[1,1]]] },
  { code: 'L1', rotations: [[[0,0],[1,0],[1,1],[1,2]],[[0,0],[0,1],[1,0],[2,0]],[[0,0],[0,1],[0,2],[1,2]],[[0,1],[1,1],[2,0],[2,1]]] },
  { code: 'Z1', rotations: [[[0,0],[1,0],[1,1],[2,1]],[[0,1],[0,2],[1,0],[1,1]],[[0,0],[1,0],[1,1],[2,1]],[[0,1],[0,2],[1,0],[1,1]]] },
  { code: 'T1', rotations: [[[0,0],[0,1],[0,2],[1,1]],[[0,1],[1,0],[1,1],[2,1]],[[0,1],[1,0],[1,1],[1,2]],[[0,0],[1,0],[1,1],[2,0]]] },
  { code: 'L2', rotations: [[[0,2],[1,0],[1,1],[1,2]],[[0,0],[1,0],[2,0],[2,1]],[[0,0],[0,1],[0,2],[1,0]],[[0,0],[0,1],[1,1],[2,1]]] },
  { code: 'Z2', rotations: [[[0,1],[1,0],[1,1],[2,0]],[[0,0],[0,1],[1,1],[1,2]],[[0,1],[1,0],[1,1],[2,0]],[[0,0],[0,1],[1,1],[1,2]]] },
]

/** Shift a cell set to the origin and return a stable sorted signature. */
function signature(cells: Cell[]): string {
  const minR = Math.min(...cells.map((c) => c[0]))
  const minC = Math.min(...cells.map((c) => c[1]))
  return cells
    .map(([r, c]) => [r - minR, c - minC] as Cell)
    .sort((a, b) => a[0] - b[0] || a[1] - b[1])
    .map(([r, c]) => `${r},${c}`)
    .join(' ')
}

function rot90cw(cells: Cell[]): Cell[] {
  const maxR = Math.max(...cells.map((c) => c[0]))
  return cells.map(([r, c]) => [c, maxR - r] as Cell)
}

function flipHoriz(cells: Cell[]): Cell[] {
  const maxC = Math.max(...cells.map((c) => c[1]))
  return cells.map(([r, c]) => [r, maxC - c] as Cell)
}
function flipVert(cells: Cell[]): Cell[] {
  const maxR = Math.max(...cells.map((c) => c[0]))
  return cells.map(([r, c]) => [maxR - r, c] as Cell)
}

// Precompute every Builder (shapeIndex, orientationIndex) signature.
const SIG_INDEX = new Map<string, { shapeIndex: number; orientationIndex: number; cells: Cell[] }>()
for (let s = 0; s < BASE_SHAPES.length; s++) {
  const shape = BASE_SHAPES[s]!
  for (let o = 0; o < shape.rotations.length; o++) {
    const cells = shape.rotations[o]!
    const sig = signature(cells)
    if (!SIG_INDEX.has(sig)) SIG_INDEX.set(sig, { shapeIndex: s, orientationIndex: o, cells })
  }
}

export interface ResolvedGeometry {
  shapeIndex: number
  orientationIndex: number
  cells: Cell[]
  matched: boolean
}

/**
/**
 * Ground-truth calibration for base-shape placement. The Compendium ships no shape geometry, and
 * its rotation-0 base orientation for each shape is defined differently than Builder's rotations[0]
 * (verified: computing flip+rotate from Builder's base yields the wrong orientation). So we key the
 * exact Builder (shapeIndex, orientationIndex) off the Compendium `(shapeId, rotation, flipH, flipV)`,
 * calibrated from known-correct in-tool layouts. Key: `shapeId|rotation|flipH(0/1)|flipV(0/1)`.
 * Extend this table as more configs are verified; unknown configs fall back to the computed guess.
 */
const BASE_ORIENT_CALIBRATION: Record<string, { shapeIndex: number; orientationIndex: number }> = {
  // Selena "Dance of the Deep" SS13 board (verified 2026-08-08):
  'Z1|270|1|0': { shapeIndex: 2, orientationIndex: 0 }, // both Z pieces → vertical S (Builder Z1 base)
}

/**
 * Resolve a Compendium (shapeId, rotation, flipH, flipV) to Builder (shapeIndex, orientationIndex, cells).
 * Uses the calibration table when available, else computes flip+rotate and signature-matches.
 */
export function resolveGeometry(shapeId: string, rotation = 0, flipH = false, flipV = false): ResolvedGeometry {
  const calib = BASE_ORIENT_CALIBRATION[`${shapeId}|${((Math.round((rotation || 0) / 90) % 4) + 4) % 4 * 90}|${flipH ? 1 : 0}|${flipV ? 1 : 0}`]
  if (calib) {
    const cells = BASE_SHAPES[calib.shapeIndex]?.rotations[calib.orientationIndex]
    if (cells) return { ...calib, cells, matched: true }
  }
  const baseIndex = SHAPE_CODE_TO_INDEX[shapeId] ?? -1
  const base = baseIndex >= 0 ? BASE_SHAPES[baseIndex]!.rotations[0]! : null
  if (!base) return { shapeIndex: 0, orientationIndex: 0, cells: BASE_SHAPES[0]!.rotations[0]!, matched: false }
  let cells: Cell[] = base
  if (flipH) cells = flipHoriz(cells)
  if (flipV) cells = flipVert(cells)
  const steps = ((Math.round(rotation / 90) % 4) + 4) % 4
  for (let i = 0; i < steps; i++) cells = rot90cw(cells)
  const hit = SIG_INDEX.get(signature(cells))
  if (hit) return { ...hit, matched: true }
  // Fall back to the code's own shapeIndex + rotation if no signature match (still a valid piece).
  return { shapeIndex: baseIndex, orientationIndex: steps, cells, matched: false }
}

// Legendary divinity slates are their own shapes (not the 6 base tetrominoes). Copied from
// SlateScreen.tsx LEGENDARY_ORIENTATIONS. Builder keys these by `kind` (a LegendaryKind), not shapeIndex.
export const LEGENDARY_ORIENTATIONS: Record<string, Cell[][]> = {
  pedigree: [[[0,1],[0,2],[1,0],[1,1],[1,2],[2,0],[2,1]],[[0,0],[0,1],[1,0],[1,1],[1,2],[2,1],[2,2]]],
  fallen_starlight: [[[0,0],[0,1]],[[0,0],[1,0]]],
  corner_of_divinity: [[[0,0],[0,1],[1,0]],[[0,0],[0,1],[1,1]],[[0,1],[1,0],[1,1]],[[0,0],[1,0],[1,1]]],
  spark_of_moth_fire: [[[0,0]]],
  when_sparks_set_prairie_ablaze: [[[0,0]]],
  space_rift: [[[0,0],[1,0],[2,0],[3,0],[4,0],[5,0]]],
  residence_of_stars: [[[0,2],[1,0],[1,1],[1,2],[2,1],[2,2],[2,3],[3,1]]],
}

// Compendium legendary-slate template name → Builder LegendaryKind.
const LEGENDARY_TEMPLATE_TO_KIND: Record<string, string> = {
  'sparks of moth fire': 'spark_of_moth_fire',
  'fallen starlight': 'fallen_starlight',
  'a corner of divinity': 'corner_of_divinity',
  'space rift': 'space_rift',
  'pedigree of gods': 'pedigree',
  'residence of stars': 'residence_of_stars',
  'when sparks set the prairie ablaze': 'when_sparks_set_prairie_ablaze',
}

export interface ResolvedLegendary {
  kind: string
  orientationIndex: number
  cells: Cell[]
}

// Per-kind base-orientation offset: the Compendium's rotation-0 for a legendary shape maps to a
// different index in our LEGENDARY_ORIENTATIONS than 0. Calibrated from known-correct layouts.
const LEGENDARY_ORIENT_OFFSET: Record<string, number> = {
  corner_of_divinity: 3, // Compendium rot0 corner = Builder orient 3 (▙), verified 2026-08-08
}

/** Resolve a Compendium legendary slate (template + rotation) to Builder kind + cells. */
export function resolveLegendaryGeometry(templateName: string, rotation = 0): ResolvedLegendary | null {
  const kind = LEGENDARY_TEMPLATE_TO_KIND[(templateName ?? '').toLowerCase().trim()]
  if (!kind) return null
  const orients = LEGENDARY_ORIENTATIONS[kind]!
  const offset = LEGENDARY_ORIENT_OFFSET[kind] ?? 0
  const oi = ((Math.round((rotation || 0) / 90) + offset) % orients.length + orients.length) % orients.length
  return { kind, orientationIndex: oi, cells: orients[oi]! }
}

// Slate slot template per kind — copied VERBATIM from SlateScreen.tsx SLOT_CONFIG + initSlots so a
// converted slate has the exact same fixed slots (count + type) a freshly-created one would. A slate's
// slots are defined by its kind, NOT by how many affixes were imported.
export type SlateSlotType = 'magic' | 'rare' | 'legendary'
interface SlateSectionDef { count: number; maxType: SlateSlotType; canBeCore?: boolean }
const SLATE_SLOT_CONFIG: Record<string, SlateSectionDef[]> = {
  base: [{ count: 2, maxType: 'legendary' }, { count: 3, maxType: 'legendary' }],
  fallen_starlight: [{ count: 2, maxType: 'rare' }, { count: 2, maxType: 'legendary' }],
  corner_of_divinity: [{ count: 2, maxType: 'legendary' }],
  pedigree: [{ count: 2, maxType: 'legendary' }, { count: 2, maxType: 'legendary', canBeCore: true }],
  spark_of_moth_fire: [],
  when_sparks_set_prairie_ablaze: [],
  space_rift: [],
  residence_of_stars: [],
}

export interface SlateSlot {
  slotType: SlateSlotType
  maxType: SlateSlotType
  canBeCore: boolean
  isCore: boolean
  selectedNodeId: string | null
  selectedCoreKey: string | null
  coreName: string | null
  effects: string[]
  nodeType: string | null
}

/** The empty slot template for a slate kind (mirrors SlateScreen.initSlots). */
export function initSlateSlots(kind: string): SlateSlot[] {
  return (SLATE_SLOT_CONFIG[kind] ?? []).flatMap((s) =>
    Array.from({ length: s.count }, (): SlateSlot => ({
      slotType: s.maxType,
      maxType: s.maxType,
      canBeCore: s.canBeCore ?? false,
      isCore: s.canBeCore ?? false,
      selectedNodeId: null,
      selectedCoreKey: null,
      coreName: null,
      effects: [],
      nodeType: null,
    })),
  )
}

/** Emit the geometry reference table for the crosswalk. */
export function geometryTable(): unknown {
  return {
    type: 'slate-geometry',
    note: 'Compendium shapeId → Builder shapeIndex; orientation computed by cell-signature match. BASE_SHAPES copied from renderer SlateScreen.tsx (game-constant).',
    shapeCodeToIndex: SHAPE_CODE_TO_INDEX,
    baseShapes: BASE_SHAPES,
  }
}
