// Talent point accounting for tree slots.
//
// MAX_TALENT_POINTS is owner-asserted (level-ups + quest rewards) — no
// help-DB/season-data source exists for this figure yet. Tracked as
// verification item `talent-point-budget`. If a season-data source for the
// in-game talent point cap appears later, it should replace this literal.
export const MAX_TALENT_POINTS = 115

function sumPoints(points: Record<string, number> | null | undefined): number {
  if (!points) return 0
  return Object.values(points).reduce((sum, pts) => sum + (pts ?? 0), 0)
}

type PrismPoints = { kind?: string; boxAllocations?: Record<string, number> }

/**
 * The points a prism adds to its tree's total: only an Inverse Image's mirrored box costs talent points.
 * An Ethereal prism has no box, so any allocations it carries (e.g. from a malformed import) are ignored.
 */
export function prismBoxAllocations(prism: PrismPoints | null | undefined): Record<string, number> {
  return prism?.kind === 'inverse_image' ? (prism.boxAllocations ?? {}) : {}
}

/**
 * Sum of allocated points for a single tree slot: its own nodeStates plus, if an
 * Inverse Image prism is installed on this slot's tree, the points spent in the
 * prism's mirrored box (those cost real talent points in-game, same as any node).
 */
export function slotPointTotal(
  slot: { nodeStates?: Record<string, number> } | null | undefined,
  prism?: PrismPoints | null
): number {
  return sumPoints(slot?.nodeStates) + sumPoints(prismBoxAllocations(prism))
}

/**
 * Sum of allocated points across every non-null slot, including any placed prisms'
 * boxAllocations (matched to a slot by treeName). Without `prisms`, this only
 * accounts for nodeStates — pass it whenever prisms may be in play, or the global
 * total silently undercounts a build that's spent points in an Inverse Image box.
 */
export function totalAllocatedPoints(
  slots: ({ nodeStates?: Record<string, number>; treeName?: string } | null | undefined)[],
  prisms?: (PrismPoints & { treeName: string })[]
): number {
  return slots.reduce((sum, slot) => {
    const prism = slot?.treeName ? prisms?.find(p => p.treeName === slot.treeName) : undefined
    return sum + slotPointTotal(slot, prism)
  }, 0)
}
