import { create } from 'zustand'
import type {
  LegendaryGearIndexItem, LegendaryGearItem, CraftBaseItemGroup,
  CraftBaseType, Graft, HeroTrait, HeroMemoryAffix, ConditionDef,
} from '../api/client'
import { api } from '../api/client'

export interface HeroMemoryData {
  base_stats: HeroMemoryAffix[]
  fixed_affixes: HeroMemoryAffix[]
  random_affixes: HeroMemoryAffix[]
}

interface ReferenceStore {
  // The season these catalogs were fetched for (derived from responses)
  season: string | null

  // Catalogs — null until load settles
  legendaryIndex: LegendaryGearIndexItem[] | null
  legendaryCatalog: LegendaryGearItem[] | null
  craftBaseItems: CraftBaseItemGroup[] | null
  craftBaseTypes: CraftBaseType[] | null
  grafts: Graft[] | null
  heroTraits: HeroTrait[] | null
  heroMemories: HeroMemoryData | null
  conditions: Record<string, ConditionDef[]> | null

  // true once ALL fetches have settled (any mix of success/failure)
  referenceResolved: boolean
  // Keys of catalogs whose fetch rejected — for per-screen failed-state UI
  failedCatalogs: Set<string>

  loadReferenceData: () => Promise<void>
  clearReferenceData: () => void
}

// Factory returns a fresh object (with a fresh Set) on every call.
// Never use a module-level mutable literal — the nested Set would be shared
// across every state reset and corrupt future clears.
function freshClearedState() {
  return {
    season: null as string | null,
    legendaryIndex: null as LegendaryGearIndexItem[] | null,
    legendaryCatalog: null as LegendaryGearItem[] | null,
    craftBaseItems: null as CraftBaseItemGroup[] | null,
    craftBaseTypes: null as CraftBaseType[] | null,
    grafts: null as Graft[] | null,
    heroTraits: null as HeroTrait[] | null,
    heroMemories: null as HeroMemoryData | null,
    conditions: null as Record<string, ConditionDef[]> | null,
    referenceResolved: false,
    failedCatalogs: new Set<string>(),
  }
}

// Monotonic token — incremented on every new load() or clear().
// The final set() call in loadReferenceData is skipped if a newer load has
// already started, preventing stale results from a previous season's fetch
// from overwriting the current season's data.
let loadToken = 0

export const useReferenceStore = create<ReferenceStore>((set) => ({
  ...freshClearedState(),

  loadReferenceData: async () => {
    const myToken = ++loadToken

    const results = await Promise.allSettled([
      api.getLegendaryGearIndex(),
      api.getLegendaryGear(),
      api.getCraftBaseItems(),
      api.getCraftBaseTypes(),
      api.getGrafts(),
      api.getHeroTraits(),
      api.getHeroMemories(),
      api.getConditions(),
    ])

    // Bail if a newer load (or clear) has superseded this one
    if (myToken !== loadToken) return

    const [
      idxResult, catalogResult, baseItemsResult,
      baseTypesResult, graftsResult, traitsResult,
      memoriesResult, conditionsResult,
    ] = results

    const failed = new Set<string>()
    let season: string | null = null
    const updates: Partial<ReferenceStore> = {}

    if (idxResult.status === 'fulfilled') {
      updates.legendaryIndex = idxResult.value.items
      if (idxResult.value.season) season = idxResult.value.season
    } else { failed.add('legendaryIndex') }

    if (catalogResult.status === 'fulfilled') {
      updates.legendaryCatalog = catalogResult.value.items
      if (catalogResult.value.season) season ??= catalogResult.value.season
    } else { failed.add('legendaryCatalog') }

    if (baseItemsResult.status === 'fulfilled') {
      updates.craftBaseItems = baseItemsResult.value.base_types
    } else { failed.add('craftBaseItems') }

    if (baseTypesResult.status === 'fulfilled') {
      updates.craftBaseTypes = baseTypesResult.value.base_types
      if (baseTypesResult.value.season) season ??= baseTypesResult.value.season
    } else { failed.add('craftBaseTypes') }

    if (graftsResult.status === 'fulfilled') {
      updates.grafts = graftsResult.value.grafts
    } else { failed.add('grafts') }

    if (traitsResult.status === 'fulfilled') {
      updates.heroTraits = traitsResult.value.traits
      if (traitsResult.value.season) season ??= traitsResult.value.season
    } else { failed.add('heroTraits') }

    if (memoriesResult.status === 'fulfilled') {
      const r = memoriesResult.value
      updates.heroMemories = {
        base_stats: r.base_stats,
        fixed_affixes: r.fixed_affixes,
        random_affixes: r.random_affixes,
      }
    } else { failed.add('heroMemories') }

    if (conditionsResult.status === 'fulfilled') {
      updates.conditions = conditionsResult.value
    } else { failed.add('conditions') }

    set({ ...updates, season, referenceResolved: true, failedCatalogs: failed })
  },

  clearReferenceData: () => {
    // Increment token so any in-flight load discards its result
    loadToken++
    set({ ...freshClearedState() })
  },
}))
