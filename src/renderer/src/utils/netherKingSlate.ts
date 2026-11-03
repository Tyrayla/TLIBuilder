import { LEGENDARY_ORIENTATIONS } from '../crosswalk/slateGeometry'

export type NetherKingVariant = 'judgment' | 'contamination' | 'banishment'
export type SlateCell = [number, number]
export type NetherKingBanishmentEffect = typeof BANISHMENT_EFFECTS[number]['id']

export const BANISHMENT_EFFECTS = [
  { id: 'demolisher', label: 'Demolisher' },
  { id: 'steep_strike', label: 'Steep Strike' },
  { id: 'shadow_strike', label: 'Shadow Strike' },
  { id: 'spell_burst', label: 'Spell Burst' },
  { id: 'ill_omen', label: 'Ill Omen' },
  { id: 'quagmire', label: 'Quagmire' },
  { id: 'projection', label: 'Projection' },
  { id: 'provision', label: 'Provision' },
  { id: 'tangle', label: 'Tangle' },
  { id: 'indomitable', label: 'Indomitable' },
] as const

export const NETHER_KING_VARIANTS: { id: NetherKingVariant; label: string; iconFile: string; summary: string; specialRule: string }[] = [
  { id: 'judgment', label: 'Judgment', iconFile: 'UI_S15Devilblock_shenpan_3_3_112.webp', summary: 'Three cells at the four middle corners', specialRule: 'Owner-reported, not independently verified: +40% effect to slates along its connecting path. Calculation is not modeled.' },
  { id: 'contamination', label: 'Contamination', iconFile: 'UI_S15Devilblock_qinran_3_3_112.webp', summary: 'Three cells stacked vertically', specialRule: 'Projects Branded talent effects onto directly adjacent Divinity Slates at 12% Projection Effect (88% reduced). Calculation is not modeled.' },
  { id: 'banishment', label: 'Banishment', iconFile: 'UI_S15Devilblock_fangzhu_3_3_112.webp', summary: 'Three cells in a diagonal line', specialRule: 'Its bonus effect activates when both adjacent and non-adjacent Divinity Slate counts are at least 3. Calculation is not modeled.' },
]

export const DEFAULT_NETHER_KING_VARIANT: NetherKingVariant = 'judgment'

// Contamination +12% and Banishment threshold 3 match the hydrated SS14 Nether King catalog.
// Footprints follow the owner's in-game screenshots. Judgment's +40% is owner-reported and remains unverified.

const JUDGMENT_MIDDLE_CORNERS = new Set(['1,1', '1,4', '4,1', '4,4'])

export function netherKingIconFile(variant?: string | null): string {
  return NETHER_KING_VARIANTS.find(option => option.id === variant)?.iconFile ?? NETHER_KING_VARIANTS[0]!.iconFile
}

/** Return the valid three-cell footprint when the cursor selects one of its cells. */
export function findNetherKingPlacement(
  variant: NetherKingVariant,
  primary: SlateCell,
  occupied: Map<string, string>,
  isValidCell: (row: number, col: number) => boolean,
): { anchor: SlateCell; orientationIndex: number; cells: SlateCell[] } | null {
  const fits = (anchor: SlateCell, offsets: SlateCell[]) => {
    const cells = offsets.map(([r, c]) => [anchor[0] + r, anchor[1] + c] as SlateCell)
    return cells.every(([r, c]) => isValidCell(r, c) && !occupied.has(`${r},${c}`)) ? cells : null
  }

  if (variant === 'judgment') {
    if (!JUDGMENT_MIDDLE_CORNERS.has(`${primary[0]},${primary[1]}`)) return null
    const anchor: SlateCell = [1, 1]
    // Reuse the crosswalk orientation order so imported and placed cells share one meaning.
    // The clicked middle corner anchors the two other occupied corners around the board's edge.
    const orientationByPrimary: Record<string, number> = {
      '1,1': 1,
      '1,4': 0,
      '4,1': 2,
      '4,4': 3,
    }
    const orientationIndex = orientationByPrimary[`${primary[0]},${primary[1]}`]
    const cells = fits(anchor, LEGENDARY_ORIENTATIONS.nether_kings_divinity[orientationIndex]!)
    return cells ? { anchor, orientationIndex, cells } : null
  }

  const layouts: SlateCell[][] = variant === 'contamination'
    ? [[[0, 0], [1, 0], [2, 0]]]
    : [[[0, 2], [1, 1], [2, 0]], [[0, 0], [1, 1], [2, 2]]]
  for (const [orientationIndex, offsets] of layouts.entries()) {
    for (const [r, c] of offsets) {
      const anchor: SlateCell = [primary[0] - r, primary[1] - c]
      const cells = fits(anchor, offsets)
      if (cells) return { anchor, orientationIndex, cells }
    }
  }
  return null
}

/** Brand nodes without a variant tag are shared; tagged nodes belong only to that variant. */
export function isNetherKingBrandNodeForVariant(effects: string[], variant: NetherKingVariant): boolean {
  const text = effects.join(' ').toLowerCase()
  const owners: [NetherKingVariant, string][] = [
    ['judgment', 'judgment'],
    ['contamination', 'contamination'],
    ['banishment', 'banishment'],
  ]
  const tagged = owners.filter(([, word]) => text.includes(`when ${word} is active`) || text.includes(`when ${word} `))
  return tagged.length === 0 || tagged.some(([owner]) => owner === variant)
}
