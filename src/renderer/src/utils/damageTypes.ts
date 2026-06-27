// Single source of truth for damage-type lists (was duplicated as ALL_DTYPES in PlayerStatsScreen and an inline
// list in statsPayload). Keep the engine's order. "Elemental" in TLI is Fire/Cold/Lightning only (NOT Erosion).

export const DAMAGE_TYPES = ['physical', 'fire', 'cold', 'lightning', 'erosion'] as const
export type DamageType = typeof DAMAGE_TYPES[number]

// True Elemental (excludes Erosion) — matches the in-game definition.
export const ELEMENTAL_TYPES = ['fire', 'cold', 'lightning'] as const
