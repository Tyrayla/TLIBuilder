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
  { id: 'judgment', label: 'Judgment', iconFile: 'UI_S15Devilblock_shenpan_3_3_112.webp', summary: 'Three cells at the four middle corners', specialRule: 'Increases the effect of slate talents along its connecting path by 40% (owner-confirmed; calculation not modeled yet).' },
  { id: 'contamination', label: 'Contamination', iconFile: 'UI_S15Devilblock_qinran_3_3_112.webp', summary: 'Three cells stacked vertically', specialRule: 'Projects its Branded talent effects onto every directly adjacent Divinity Slate at 12% effect (88% reduced; calculation not modeled yet).' },
  { id: 'banishment', label: 'Banishment', iconFile: 'UI_S15Devilblock_fangzhu_3_3_112.webp', summary: 'Three cells in a diagonal line', specialRule: 'Requires at least 3 adjacent and 3 non-adjacent Divinity Slates for its bonus effect (calculation not modeled yet).' },
]

export const DEFAULT_NETHER_KING_VARIANT: NetherKingVariant = 'judgment'

// Each click on one of the four middle corners selects the matching orientation. The raw Judgment art
// shows TL/TR/BR (orientation 0); its three cells rotate clockwise from there.
const JUDGMENT_LAYOUTS: SlateCell[][] = [
  [[0, 0], [0, 3], [3, 3]], // leave bottom-left open
  [[0, 3], [3, 3], [3, 0]], // leave top-left open
  [[3, 3], [3, 0], [0, 0]], // leave top-right open
  [[3, 0], [0, 0], [0, 3]], // leave bottom-right open
]
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
    // The clicked middle corner is the origin cue. Upper clicks leave the opposite upper corner open;
    // lower clicks leave the opposite lower corner open. This makes all four holes reachable without rotation UI.
    const orientationByPrimary: Record<string, number> = {
      '1,1': 2, // top-left origin -> leave top-right open
      '1,4': 1, // top-right origin -> leave top-left open
      '4,1': 3, // bottom-left origin -> leave bottom-right open
      '4,4': 0, // bottom-right origin -> leave bottom-left open
    }
    const orientationIndex = orientationByPrimary[`${primary[0]},${primary[1]}`]
    const cells = fits(anchor, JUDGMENT_LAYOUTS[orientationIndex]!)
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
