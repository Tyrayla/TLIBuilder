import { create } from 'zustand'
import type {
  LegendaryGearIndexItem, LegendaryGearItem, CraftBaseItemGroup,
  CraftBaseType, Graft, HeroTrait, HeroMemoryAffix, HeroMemoryType, ConditionDef, SkillItem, BeltBlend,
  HeroMemoryBaseStatScaling,
} from '../api/client'
import { api, registerSkillTagVocabulary } from '../api/client'

export interface HeroMemoryData {
  memory_types: HeroMemoryType[]   // per-type catalog rows (name/internal_id/icon_url) — drives type icons
  base_stats: HeroMemoryAffix[]
  fixed_affixes: HeroMemoryAffix[]
  random_affixes: HeroMemoryAffix[]
  // Season-stable base-stat scaling table (source: MinMaxedARPG) — drives the creator's auto base-stat value
  // and the crosswalk import recompute. Optional (missing on very old backends).
  base_stat_scaling?: HeroMemoryBaseStatScaling
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
  memoryRevival: HeroMemoryAffix[] | null   // revival-mod pool (implicit-like affixes for revived memories)
  conditions: Record<string, ConditionDef[]> | null
  // Belt Blends (Blending Rituals) catalog — needed to resolve a belt's equipped blend talent_id → the
  // granted core talent's display name (source 4 of the four core-talent grant paths; see
  // computeSkillSlotEligibility in api/client.ts).
  beltBlends: BeltBlend[] | null
  // Skill/support catalog (carries each item's structured `tooltip` spec). Shared by SkillsScreen and
  // the Stats page, which looks up a contribution's source skill/support by name (`skillsByName`).
  skills: SkillItem[] | null
  skillsByName: Record<string, SkillItem> | null
  skillsById: Record<string, SkillItem> | null

  // true once ALL fetches have settled (any mix of success/failure)
  referenceResolved: boolean
  // Keys of catalogs whose fetch rejected — for per-screen failed-state UI
  failedCatalogs: Set<string>
  // Per-fetch settle counters for the global load-progress pill (LoadProgressBar).
  loadDone: number
  loadTotal: number

  loadReferenceData: () => Promise<void>
  clearReferenceData: () => void
  refreshCraftBaseTypes: () => Promise<void>
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
    memoryRevival: null as HeroMemoryAffix[] | null,
    conditions: null as Record<string, ConditionDef[]> | null,
    beltBlends: null as BeltBlend[] | null,
    skills: null as SkillItem[] | null,
    skillsByName: null as Record<string, SkillItem> | null,
    skillsById: null as Record<string, SkillItem> | null,
    referenceResolved: false,
    failedCatalogs: new Set<string>(),
    loadDone: 0,
    loadTotal: 0,
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

    // Each fetch bumps loadDone as it settles so the progress pill can show real progress
    // rather than a spinner-until-everything blob. Ticks are ignored once superseded.
    const track = <T,>(p: Promise<T>): Promise<T> => {
      p.finally(() => { if (myToken === loadToken) set(s => ({ loadDone: s.loadDone + 1 })) }).catch(() => {})
      return p
    }
    const fetches = [
      track(api.getLegendaryGearIndex()),
      track(api.getLegendaryGear()),
      track(api.getCraftBaseItems()),
      track(api.getCraftBaseTypes()),
      track(api.getGrafts()),
      track(api.getHeroTraits()),
      track(api.getHeroMemories()),
      track(api.getMemoryRevival()),
      track(api.getConditions()),
      track(api.getSkills()),
      track(api.getBeltBlends()),
    ] as const
    set({ loadDone: 0, loadTotal: fetches.length })
    const results = await Promise.allSettled(fetches)

    // Bail if a newer load (or clear) has superseded this one
    if (myToken !== loadToken) return

    const [
      idxResult, catalogResult, baseItemsResult,
      baseTypesResult, graftsResult, traitsResult,
      memoriesResult, revivalResult, conditionsResult, skillsResult,
      beltBlendsResult,
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
        memory_types: r.memory_types,
        base_stats: r.base_stats,
        fixed_affixes: r.fixed_affixes,
        random_affixes: r.random_affixes,
        base_stat_scaling: r.base_stat_scaling,
      }
    } else { failed.add('heroMemories') }

    if (revivalResult.status === 'fulfilled') {
      updates.memoryRevival = revivalResult.value.affixes
    } else { failed.add('memoryRevival') }

    if (conditionsResult.status === 'fulfilled') {
      updates.conditions = conditionsResult.value
    } else { failed.add('conditions') }

    if (skillsResult.status === 'fulfilled') {
      updates.skills = skillsResult.value.skills
      updates.skillsByName = Object.fromEntries(skillsResult.value.skills.map((s) => [s.name, s]))
      updates.skillsById = Object.fromEntries(skillsResult.value.skills.map((s) => [s.item_id, s]))
      // Refresh isSupportCompatible's tag vocabulary against THIS season's catalog, so multi-word
      // support-gate phrases ("Supports Shadow Strike Skills.") match correctly (see client.ts).
      registerSkillTagVocabulary(skillsResult.value.skills)
      if (skillsResult.value.season) season ??= skillsResult.value.season
    } else { failed.add('skills') }

    if (beltBlendsResult.status === 'fulfilled') {
      updates.beltBlends = beltBlendsResult.value.blends
      if (beltBlendsResult.value.season) season ??= beltBlendsResult.value.season
    } else { failed.add('beltBlends') }

    set({ ...updates, season, referenceResolved: true, failedCatalogs: failed })
  },

  clearReferenceData: () => {
    // Increment token so any in-flight load discards its result
    loadToken++
    registerSkillTagVocabulary([]) // reset to the pseudo-tag-only fallback until the next load
    set({ ...freshClearedState() })
  },

  refreshCraftBaseTypes: async () => {
    try {
      const result = await api.getCraftBaseTypes()
      set({ craftBaseTypes: result.base_types })
    } catch {
      // silently fail; stale data remains until next full load
    }
  },
}))
