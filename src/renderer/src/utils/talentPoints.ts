// Talent point accounting for tree slots.
//
// MAX_TALENT_POINTS is owner-asserted (level-ups + quest rewards) — no
// help-DB/season-data source exists for this figure yet. Tracked as
// verification item `talent-point-budget`. If a season-data source for the
// in-game talent point cap appears later, it should replace this literal.
export const MAX_TALENT_POINTS = 115

/** Sum of allocated points (nodeStates values) for a single tree slot. */
export function slotPointTotal(
  slot: { nodeStates?: Record<string, number> } | null | undefined
): number {
  if (!slot?.nodeStates) return 0
  return Object.values(slot.nodeStates).reduce((sum, pts) => sum + (pts ?? 0), 0)
}

/** Sum of allocated points across every non-null slot. */
export function totalAllocatedPoints(
  slots: ({ nodeStates?: Record<string, number> } | null | undefined)[]
): number {
  return slots.reduce((sum, slot) => sum + slotPointTotal(slot), 0)
}
