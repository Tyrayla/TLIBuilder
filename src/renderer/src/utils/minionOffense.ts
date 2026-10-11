export type MinionOffenseBySlot<T = unknown> = Record<string, T> | null | undefined

/** Resolve a slotted minion result, preferring the duplicate-safe slot key over its bare item id. */
export function minionOffenseForSlot<T>(
  minionOffense: MinionOffenseBySlot<T>,
  itemId: string | undefined,
  slot: number,
): T | null {
  if (!minionOffense || !itemId) return null
  return minionOffense[`${itemId}@slot${slot}`]
    ?? minionOffense[itemId]
    ?? Object.values(minionOffense).find(result =>
      (result as { owner_slot?: number }).owner_slot === slot)
    ?? null
}
